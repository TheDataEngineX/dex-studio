"""DEX Studio auth — password gate using signed session cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.requests import HTTPConnection

SESSION_COOKIE = "dex_session"
_DATA_DIR = Path(os.environ.get("DEX_STUDIO_DATA_DIR", "")) or Path.home() / ".dex-studio"
_HASH_FILE = _DATA_DIR / "auth.hash"

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


def has_password() -> bool:
    """Return True if a password is configured (hash file exists with content)."""
    return _HASH_FILE.exists() and bool(_HASH_FILE.read_text().strip())


def has_password() -> bool:
    """Return True if a password is configured (hash file exists with content)."""
    return _HASH_FILE.exists() and bool(_HASH_FILE.read_text().strip())


def set_password(password: str) -> None:
    """Hash and persist a user-chosen password to the hash file."""
    _HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HASH_FILE.write_text(_hash_password(password))
    _HASH_FILE.chmod(0o600)


def reset_password() -> None:
    """Unlink the password hash file, clearing all authentication."""
    _HASH_FILE.unlink(missing_ok=True)


def setup_password() -> None:
    """Ensure a password exists. Call once at app startup.

    No-op when DEX_STUDIO_PASSPHRASE env var is set.
    Generates and hashes a random password on first boot; on subsequent boots
    with no PASSPHRASE env var, the /setup route handles password creation.
    """
    if os.environ.get("DEX_STUDIO_PASSPHRASE", "").strip():
        return
    if _HASH_FILE.exists() and _HASH_FILE.read_text().strip():
        return
    password = _generate_password()
    _HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HASH_FILE.write_text(_hash_password(password))
    _HASH_FILE.chmod(0o600)


def reset_password() -> None:
    """Unlink the password hash file, clearing all authentication."""
    _HASH_FILE.unlink(missing_ok=True)


def setup_password() -> None:
    """Ensure hash file directory exists. Call once at app startup.

    On first boot with no password set, the /setup route handles password creation.
    """
    if _HASH_FILE.exists() and _HASH_FILE.read_text().strip():
        return
    _HASH_FILE.parent.mkdir(parents=True, exist_ok=True)


def is_authenticated(request: HTTPConnection) -> bool:
    return request.session.get("authenticated") is True


def auth_required(request: Request) -> RedirectResponse | None:
    if not has_password():
        return RedirectResponse(url="/setup", status_code=303)
    if is_authenticated(request):
        return None
    return RedirectResponse(url="/login", status_code=303)


def validate_and_login(request: Request, submitted: str) -> bool:
    """Verify submitted password against stored PBKDF2 hash; set session on success."""
    submitted = submitted.strip()
    ok = False
    if _HASH_FILE.exists():
        stored = _HASH_FILE.read_text().strip()
        ok = bool(stored) and _verify_password(submitted, stored)
    if ok:
        request.session["authenticated"] = True
    return ok


def logout(request: Request) -> None:
    request.session.clear()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "") or "unknown"


def rate_limit_blocked(ip: str) -> bool:
    return _limiter.is_blocked(ip)


def record_failed_login(ip: str) -> None:
    _limiter.record_failure(ip)


def clear_rate_limit(ip: str) -> None:
    _limiter.clear(ip)
