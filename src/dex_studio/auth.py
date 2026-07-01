"""DEX Studio auth — password gate using signed session cookies."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import os
import secrets
import threading
import time

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.requests import HTTPConnection

logger = structlog.get_logger()

SESSION_COOKIE = "dex_session"

_PBKDF2_ITERS = 600_000
MIN_PASSWORD_LEN = 8


class RequiresLogin(Exception):
    """Raised by auth_dep — app exception handler redirects to /login."""


class RequiresEngine(Exception):
    """Raised by engine_dep — app exception handler redirects to /onboarding."""


class _RateLimiter:
    """Per-IP rate limiter: 5 failures → locked out for 5 minutes."""

    _WINDOW_S = 300.0
    _MAX_FAILS = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def _clean(self, ip: str, now: float) -> None:
        self._failures[ip] = [t for t in self._failures.get(ip, []) if now - t < self._WINDOW_S]

    def is_blocked(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._clean(ip, now)
            return len(self._failures.get(ip, [])) >= self._MAX_FAILS

    def record_failure(self, ip: str) -> None:
        with self._lock:
            self._failures.setdefault(ip, []).append(time.monotonic())

    def clear(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)


_limiter = _RateLimiter()


def _hash_password(password: str) -> str:
    """Return base64-encoded PBKDF2-SHA256 hash with embedded 32-byte salt."""
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)  # noqa: S324
    return base64.b64encode(salt + dk).decode()


def _verify_password(password: str, stored: str) -> bool:
    """Constant-time verify password against a stored PBKDF2 hash."""
    raw = base64.b64decode(stored.encode())
    salt, dk_stored = raw[:32], raw[32:]
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)  # noqa: S324
    return hmac.compare_digest(dk, dk_stored)


def _generate_password() -> str:
    return "-".join(secrets.token_urlsafe(8) for _ in range(3))


def has_password() -> bool:
    """Return True if a password is configured (env var or DB hash)."""
    if os.environ.get("DEX_STUDIO_PASSPHRASE", "").strip():
        return True
    from dex_studio import db_store

    return db_store.get_setting("auth.hash") is not None


def set_password(password: str) -> None:
    """Hash and persist a user-chosen password to the database."""
    from dex_studio import db_store

    db_store.set_setting("auth.hash", _hash_password(password))
    logger.info("password_set")


def reset_password() -> None:
    """Clear the stored password hash.

    Raises RuntimeError when DEX_STUDIO_PASSPHRASE env var is set,
    because the env-var password cannot be mutated at runtime.
    """
    if os.environ.get("DEX_STUDIO_PASSPHRASE", "").strip():
        raise RuntimeError(
            "Cannot reset password when DEX_STUDIO_PASSPHRASE is set via environment"
        )
    from dex_studio import db_store

    db_store.delete_setting("auth.hash")
    logger.info("password_reset")


def setup_password() -> None:
    """Ensure a password exists. Call once at app startup.

    No-op when DEX_STUDIO_PASSPHRASE env var is set or hash already stored.
    Generates and hashes a random password on first boot; on subsequent boots
    with no PASSPHRASE env var, the /setup route handles password creation.
    """
    if os.environ.get("DEX_STUDIO_PASSPHRASE", "").strip():
        return
    from dex_studio import db_store

    if db_store.get_setting("auth.hash") is not None:
        return
    password = _generate_password()
    db_store.set_setting("auth.hash", _hash_password(password))
    logger.info("password_setup_auto", note="random password generated on first boot")


def is_authenticated(request: HTTPConnection) -> bool:
    return request.session.get("authenticated") is True


def auth_required(request: Request) -> RedirectResponse | None:
    if not has_password():
        return RedirectResponse(url="/setup", status_code=303)
    if is_authenticated(request):
        return None
    return RedirectResponse(url="/login", status_code=303)


def validate_and_login(request: Request, submitted: str) -> bool:
    """Verify submitted password against env var or stored PBKDF2 hash; set session on success."""
    submitted = submitted.strip()
    ok = False

    passphrase = os.environ.get("DEX_STUDIO_PASSPHRASE", "").strip()
    if passphrase:
        ok = hmac.compare_digest(submitted.encode(), passphrase.encode())
    else:
        from dex_studio import db_store

        stored = db_store.get_setting("auth.hash")
        ok = stored is not None and _verify_password(submitted, stored)

    if ok:
        request.session["authenticated"] = True
        logger.info("login_ok", ip=get_client_ip(request))
    else:
        logger.info("login_failed", ip=get_client_ip(request))
    return ok


def logout(request: Request) -> None:
    request.session.clear()
    logger.info("logout", ip=get_client_ip(request))


def get_client_ip(request: Request) -> str:
    """Return the real client IP for rate-limiting purposes.

    ``X-Forwarded-For`` is only trusted when ``DEX_TRUSTED_PROXIES`` env var
    is set to a positive integer (the number of trusted reverse-proxy hops).
    Without it, an attacker can spoof the header to bypass rate limiting.
    """
    trusted_hops = 0
    with contextlib.suppress(ValueError):
        trusted_hops = int(os.environ.get("DEX_TRUSTED_PROXIES", "0"))

    if trusted_hops > 0:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",")]
            # The rightmost N−1 hops are added by trusted proxies;
            # the leftmost is the originating client.
            idx = max(0, len(parts) - trusted_hops)
            return parts[idx]

    return (request.client.host if request.client else "") or "unknown"


def rate_limit_blocked(ip: str) -> bool:
    return _limiter.is_blocked(ip)


def record_failed_login(ip: str) -> None:
    _limiter.record_failure(ip)


def clear_rate_limit(ip: str) -> None:
    _limiter.clear(ip)
