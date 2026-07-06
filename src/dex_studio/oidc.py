"""OIDC (Authentik) authorization-code login — additional login path alongside auth.py.

Reuses the existing session/cookie mechanism: a successful callback just sets
``request.session["authenticated"] = True`` (same key ``auth.is_authenticated``
checks), so downstream route-protection code needs no changes.

Config is env-only, never hardcoded:
  DEX_STUDIO_OIDC_ISSUER         e.g. https://auth.thedataenginex.org/application/o/dex-studio/
  DEX_STUDIO_OIDC_CLIENT_ID
  DEX_STUDIO_OIDC_CLIENT_SECRET
  DEX_STUDIO_OIDC_ADMIN_GROUP    optional, default "dex-studio-admins"
"""

from __future__ import annotations

import hmac
import os
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse

logger = structlog.get_logger()

_ALG = "RS256"
_HTTP_TIMEOUT = 5.0

# ponytail: single-issuer cache, keyed on issuer so env-var changes (tests) bust it
_DISCOVERY_CACHE: dict[str, Any] = {}


def _issuer() -> str:
    return os.environ.get("DEX_STUDIO_OIDC_ISSUER", "").strip()


def _client_id() -> str:
    return os.environ.get("DEX_STUDIO_OIDC_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("DEX_STUDIO_OIDC_CLIENT_SECRET", "").strip()


def oidc_enabled() -> bool:
    """True when all required OIDC env vars are set."""
    return bool(_issuer() and _client_id() and _client_secret())


def _discovery() -> dict[str, Any]:
    """Fetch (and cache) the OIDC discovery document for the configured issuer."""
    issuer = _issuer()
    if _DISCOVERY_CACHE.get("issuer") != issuer:
        resp = httpx.get(
            f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=_HTTP_TIMEOUT
        )
        resp.raise_for_status()
        _DISCOVERY_CACHE["issuer"] = issuer
        _DISCOVERY_CACHE["doc"] = resp.json()
    doc: dict[str, Any] = _DISCOVERY_CACHE["doc"]
    return doc


def _get_signing_key(token: str, jwks_uri: str) -> str:
    """Resolve the RSA public key matching *token*'s ``kid`` from the JWKS endpoint."""
    jwks_client = jwt.PyJWKClient(jwks_uri)
    return jwks_client.get_signing_key_from_jwt(token).key  # type: ignore[no-any-return]


def authorize_redirect(request: Request, redirect_uri: str) -> RedirectResponse:
    """Start the authorization-code flow: stash state/nonce in session, redirect to Authentik."""
    disc = _discovery()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email groups",
        "state": state,
        "nonce": nonce,
    }
    return RedirectResponse(f"{disc['authorization_endpoint']}?{urlencode(params)}")


class OIDCError(Exception):
    """Raised on any failure in the callback/token-exchange/validation flow."""


def handle_callback(
    request: Request, *, code: str, state: str, redirect_uri: str
) -> dict[str, Any]:
    """Exchange *code* for tokens and return validated ID-token claims.

    Does NOT set the session — caller decides what to do with the claims
    (see ``login_via_claims``). Raises OIDCError on any validation failure.
    """
    expected_state = request.session.pop("oidc_state", None)
    if not expected_state or not hmac.compare_digest(state, expected_state):
        raise OIDCError("invalid or missing oauth state")
    expected_nonce = request.session.pop("oidc_nonce", None)

    disc = _discovery()
    try:
        resp = httpx.post(
            disc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
            },
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise OIDCError(f"token exchange failed: {exc}") from exc

    id_token = resp.json().get("id_token")
    if not id_token:
        raise OIDCError("token response missing id_token")

    try:
        signing_key = _get_signing_key(id_token, disc["jwks_uri"])
        claims: dict[str, Any] = jwt.decode(
            id_token,
            signing_key,
            algorithms=[_ALG],
            audience=_client_id(),
            issuer=disc.get("issuer") or _issuer(),
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(f"invalid id_token: {exc}") from exc

    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise OIDCError("nonce mismatch")

    return claims


def login_via_claims(request: Request, claims: dict[str, Any]) -> None:
    """Create a local session from validated OIDC claims — same mechanism as password login."""
    request.session["authenticated"] = True
    request.session["oidc_sub"] = claims.get("sub")
    request.session["oidc_groups"] = claims.get("groups", [])
    logger.info("oidc_login_ok", sub=claims.get("sub"))


def validate_bearer_token(token: str) -> dict[str, Any]:
    """Validate a standalone Bearer JWT (access/ID token) against Authentik's JWKS.

    Independent of session state — for JWT-protected API/admin routes.
    Raises OIDCError on any failure.
    """
    disc = _discovery()
    try:
        signing_key = _get_signing_key(token, disc["jwks_uri"])
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=[_ALG],
            audience=_client_id(),
            issuer=disc.get("issuer") or _issuer(),
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(f"invalid token: {exc}") from exc
    return claims


def is_admin_claims(claims: dict[str, Any]) -> bool:
    admin_group = os.environ.get("DEX_STUDIO_OIDC_ADMIN_GROUP", "dex-studio-admins")
    return admin_group in (claims.get("groups") or [])
