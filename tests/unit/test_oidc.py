"""Tests dex_studio.oidc — Authentik OIDC login flow + JWT admin dependency.

Discovery/token/JWKS endpoints are mocked (no real Authentik needed); ID-token
signature verification runs for real against an in-memory RSA keypair so the
security-critical validation logic (signature, audience, issuer, expiry,
nonce) is actually exercised, not just the plumbing around it.
"""

from __future__ import annotations

import time
from typing import Annotated, Any
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dex_studio import oidc
from dex_studio.routers._deps import admin_dep

_ISSUER = "https://auth.example.test/application/o/dex-studio/"
_CLIENT_ID = "dex-studio"
_SESSION_SECRET = "s" * 32
_CALLBACK_URI = "https://dex.example.test/auth/callback"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

_DISCOVERY_DOC = {
    "issuer": _ISSUER,
    "authorization_endpoint": f"{_ISSUER}authorize/",
    "token_endpoint": f"{_ISSUER}token/",
    "jwks_uri": f"{_ISSUER}jwks/",
}


def _sign(claims: dict[str, Any], *, key: Any = _PRIVATE_KEY) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


def _base_claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": _CLIENT_ID,
        "sub": "user-123",
        "exp": now + 300,
        "iat": now,
        "groups": [],
    }
    claims.update(overrides)
    return claims


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEX_STUDIO_OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("DEX_STUDIO_OIDC_CLIENT_ID", _CLIENT_ID)
    monkeypatch.setenv("DEX_STUDIO_OIDC_CLIENT_SECRET", "test-client-secret")  # gitleaks:allow
    monkeypatch.setattr(oidc, "_DISCOVERY_CACHE", {"issuer": _ISSUER, "doc": _DISCOVERY_DOC})
    # Bypass the real network JWKS fetch — signature verification itself still
    # runs for real inside jwt.decode using this public key.
    monkeypatch.setattr(oidc, "_get_signing_key", lambda token, jwks_uri: _PUBLIC_KEY)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET, session_cookie="dex_session")

    @app.get("/start")
    def start(request: Request) -> Any:
        return oidc.authorize_redirect(request, _CALLBACK_URI)

    @app.get("/callback")
    def callback(request: Request, code: str = "", state: str = "") -> Any:
        try:
            claims = oidc.handle_callback(
                request, code=code, state=state, redirect_uri=_CALLBACK_URI
            )
        except oidc.OIDCError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        oidc.login_via_claims(request, claims)
        return {"authenticated": request.session.get("authenticated")}

    return app


def _start_flow(client: TestClient) -> tuple[str, str]:
    resp = client.get("/start", follow_redirects=False)
    qs = parse_qs(urlparse(resp.headers["location"]).query)
    return qs["state"][0], qs["nonce"][0]


class TestOIDCEnabled:
    def test_enabled_when_all_vars_set(self) -> None:
        assert oidc.oidc_enabled()

    def test_disabled_when_client_secret_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_OIDC_CLIENT_SECRET", raising=False)
        assert not oidc.oidc_enabled()


class TestAuthorizeRedirect:
    def test_redirects_to_authorization_endpoint_with_state(self) -> None:
        client = TestClient(_make_app())
        resp = client.get("/start", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].startswith(_DISCOVERY_DOC["authorization_endpoint"])
        assert "state=" in resp.headers["location"]
        assert "nonce=" in resp.headers["location"]


class TestCallback:
    def test_successful_callback_creates_valid_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TestClient(_make_app())
        state, nonce = _start_flow(client)

        id_token = _sign(_base_claims(nonce=nonce))
        mock_resp = MagicMock(raise_for_status=MagicMock())
        mock_resp.json.return_value = {"id_token": id_token}
        monkeypatch.setattr(oidc.httpx, "post", MagicMock(return_value=mock_resp))

        resp = client.get(f"/callback?code=abc123&state={state}")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True

    def test_invalid_state_rejected(self) -> None:
        client = TestClient(_make_app())
        _start_flow(client)  # primes a state, but we send a different one
        resp = client.get("/callback?code=abc123&state=wrong-state")
        assert resp.status_code == 400

    def test_expired_id_token_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_make_app())
        state, nonce = _start_flow(client)

        expired = _sign(_base_claims(nonce=nonce, exp=int(time.time()) - 60))
        mock_resp = MagicMock(raise_for_status=MagicMock())
        mock_resp.json.return_value = {"id_token": expired}
        monkeypatch.setattr(oidc.httpx, "post", MagicMock(return_value=mock_resp))

        resp = client.get(f"/callback?code=abc123&state={state}")
        assert resp.status_code == 400

    def test_wrong_signing_key_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_make_app())
        state, nonce = _start_flow(client)

        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = _sign(_base_claims(nonce=nonce), key=other_key)
        mock_resp = MagicMock(raise_for_status=MagicMock())
        mock_resp.json.return_value = {"id_token": forged}
        monkeypatch.setattr(oidc.httpx, "post", MagicMock(return_value=mock_resp))

        resp = client.get(f"/callback?code=abc123&state={state}")
        assert resp.status_code == 400

    def test_nonce_mismatch_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_make_app())
        state, _nonce = _start_flow(client)

        id_token = _sign(_base_claims(nonce="not-the-real-nonce"))
        mock_resp = MagicMock(raise_for_status=MagicMock())
        mock_resp.json.return_value = {"id_token": id_token}
        monkeypatch.setattr(oidc.httpx, "post", MagicMock(return_value=mock_resp))

        resp = client.get(f"/callback?code=abc123&state={state}")
        assert resp.status_code == 400


_AdminClaims = Annotated[dict[str, Any], Depends(admin_dep)]


class TestAdminDep:
    """JWT-protected admin dependency — Bearer token, independent of session."""

    def _app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/admin")
        def admin_route(claims: _AdminClaims) -> Any:
            return {"sub": claims["sub"]}

        return app

    def test_missing_token_401(self) -> None:
        resp = TestClient(self._app()).get("/admin")
        assert resp.status_code == 401

    def test_invalid_token_401(self) -> None:
        resp = TestClient(self._app()).get(
            "/admin", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        assert resp.status_code == 401

    def test_valid_token_without_admin_group_403(self) -> None:
        token = _sign(_base_claims(groups=["some-other-group"]))
        resp = TestClient(self._app()).get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_valid_admin_token_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_OIDC_ADMIN_GROUP", "dex-studio-admins")
        token = _sign(_base_claims(groups=["dex-studio-admins"]))
        resp = TestClient(self._app()).get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user-123"
