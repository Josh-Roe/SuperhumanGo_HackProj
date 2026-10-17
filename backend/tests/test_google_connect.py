"""Production Google connect: Supabase session auth, single-use owner-bound state, vault."""

import asyncio
import base64
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hackathon_backend.config import Settings
from hackathon_backend.providers.google.oauth import GoogleOAuthConfig, VaultTokenSource
from hackathon_backend.workflows.google_connect import OAuthStates, google_connect_router

OWNER_A = "00000000-0000-4000-8000-00000000000a"
OWNER_B = "00000000-0000-4000-8000-00000000000b"
SESSIONS = {"session-a": OWNER_A, "session-b": OWNER_B}
SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_publishable_key="publishable",
    supabase_service_role_key="server-secret",
    credential_encryption_key="unused-with-fake-vault",
    google_client_id="client-id",
    google_client_secret="client-secret",
    google_redirect_uri="https://demo.example/api/google/callback",
)


class FakeVault:
    def __init__(self) -> None:
        self.saved: dict[str, tuple[str, str, str]] = {}

    async def put_refresh_token(self, owner_id, account_email, refresh_token, scopes) -> None:
        self.saved[owner_id] = (account_email, refresh_token, scopes)

    async def get_refresh_token(self, owner_id):
        return self.saved.get(owner_id, (None, None))[1]

    async def get_account_email(self, owner_id):
        return self.saved.get(owner_id, (None,))[0]


def id_token(email: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def settings():
    return SETTINGS


@pytest.fixture
def env(settings):
    vault, clock, exchanged = FakeVault(), Clock(), []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/v1/user":
            token = request.headers["authorization"].removeprefix("Bearer ")
            if token not in SESSIONS:
                return httpx.Response(401, json={"msg": "invalid"})
            return httpx.Response(200, json={"id": SESSIONS[token]})
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            exchanged.append(form)
            if form["code"] == ["bad"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            grant = {
                "access_token": "access",
                "expires_in": 3600,
                "refresh_token": "refresh-" + form["code"][0],
                "scope": "openid email",
                "id_token": id_token("organizer@example.com"),
            }
            if form["code"] == ["no-refresh"]:
                del grant["refresh_token"]
            return httpx.Response(200, json=grant)
        raise AssertionError(f"unexpected request {request.url}")

    app = FastAPI()
    app.include_router(
        google_connect_router(
            settings,
            vault,
            states=OAuthStates(ttl=600, now=clock),
            transport=httpx.MockTransport(handler),
        )
    )
    with TestClient(app, base_url="http://localhost") as client:
        yield client, vault, clock, exchanged


def connect(client, session="session-a") -> str:
    response = client.post("/api/google/connect", headers={"Authorization": f"Bearer {session}"})
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert query["redirect_uri"] == [SETTINGS.google_redirect_uri]
    assert query["access_type"] == ["offline"]
    assert len(query["state"][0]) >= 40
    return query["state"][0]


def test_connect_requires_supabase_session(env):
    client, *_ = env
    assert client.post("/api/google/connect").status_code == 401
    assert (
        client.post("/api/google/connect", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
    assert client.get("/api/google/status").status_code == 401


def test_callback_stores_refresh_token_for_state_owner_once(env):
    client, vault, _, exchanged = env
    state_a, state_b = connect(client, "session-a"), connect(client, "session-b")
    assert state_a != state_b
    response = client.get("/api/google/callback", params={"state": state_a, "code": "abc"})
    assert response.status_code == 200
    assert response.json() == {"connected": True, "email": "organizer@example.com"}
    assert "refresh-abc" not in response.text
    assert vault.saved == {OWNER_A: ("organizer@example.com", "refresh-abc", "openid email")}
    assert response.headers["cache-control"] == "no-store"
    # Single use: replaying the same state fails before any token exchange.
    replay = client.get("/api/google/callback", params={"state": state_a, "code": "abc"})
    assert replay.status_code == 400 and replay.json()["detail"]["code"] == "invalid_state"
    assert len(exchanged) == 1
    status = {"Authorization": "Bearer session-a"}
    assert client.get("/api/google/status", headers=status).json() == {
        "connected": True,
        "email": "organizer@example.com",
    }
    other = client.get("/api/google/status", headers={"Authorization": "Bearer session-b"})
    assert other.json() == {"connected": False, "email": None}


@pytest.mark.parametrize("state", ["", "forged-state"])
def test_unknown_state_rejected(env, state):
    client, vault, _, exchanged = env
    response = client.get("/api/google/callback", params={"state": state, "code": "abc"})
    assert response.status_code == 400
    assert not vault.saved and not exchanged


def test_expired_state_rejected(env):
    client, vault, clock, exchanged = env
    state = connect(client)
    clock.now += 601
    assert (
        client.get("/api/google/callback", params={"state": state, "code": "x"}).status_code == 400
    )
    assert not vault.saved and not exchanged


def test_denied_or_failed_exchange_consumes_state_and_stores_nothing(env):
    client, vault, _, _ = env
    denied = connect(client)
    response = client.get(
        "/api/google/callback", params={"state": denied, "error": "access_denied"}
    )
    assert response.status_code == 400
    failed = connect(client)
    response = client.get("/api/google/callback", params={"state": failed, "code": "bad"})
    assert response.status_code == 502
    assert "client-secret" not in response.text
    assert (
        client.get("/api/google/callback", params={"state": failed, "code": "x"}).status_code == 400
    )
    assert not vault.saved


APP = "https://app.example"


@pytest.mark.parametrize("settings", [replace(SETTINGS, app_url=APP)])
def test_callback_redirects_to_app_url_on_success_without_secrets(env):
    client, vault, *_ = env
    state = connect(client)
    response = client.get(
        "/api/google/callback", params={"state": state, "code": "abc"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"{APP}/?google=connected"
    assert response.headers["cache-control"] == "no-store"
    assert vault.saved[OWNER_A][1] == "refresh-abc"


@pytest.mark.parametrize("settings", [replace(SETTINGS, app_url=APP)])
@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"state": "forged", "code": "abc"}, "invalid_state"),
        ({"error": "access_denied"}, "denied"),
        ({"code": "bad"}, "exchange_failed"),
        ({"code": "no-refresh"}, "no_refresh_token"),
    ],
)
def test_callback_redirects_failures_with_reason_code(env, params, reason):
    client, vault, *_ = env
    params = {"state": connect(client), **params}
    response = client.get("/api/google/callback", params=params, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"{APP}/?google=error&reason={reason}"
    assert not vault.saved


def test_reconnect_drops_cached_access_token_so_next_call_uses_new_grant():
    vault = FakeVault()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER_A})
        form = parse_qs(request.content.decode())
        if form["grant_type"] == ["authorization_code"]:
            return httpx.Response(
                200,
                json={
                    "access_token": "unused",
                    "refresh_token": "refresh-" + form["code"][0],
                    "id_token": id_token("organizer@example.com"),
                },
            )
        return httpx.Response(
            200, json={"access_token": "access-for-" + form["refresh_token"][0], "expires_in": 3600}
        )

    transport = httpx.MockTransport(handler)
    config = GoogleOAuthConfig("client-id", "client-secret", SETTINGS.google_redirect_uri)
    tokens = VaultTokenSource(config, vault, transport)
    app = FastAPI()
    app.include_router(
        google_connect_router(SETTINGS, vault, transport=transport, on_change=tokens.forget)
    )
    with TestClient(app, base_url="http://localhost") as client:
        client.get("/api/google/callback", params={"state": connect(client), "code": "old"})
        assert asyncio.run(tokens.access_token(OWNER_A)) == "access-for-refresh-old"

        client.get("/api/google/callback", params={"state": connect(client), "code": "new"})

        assert asyncio.run(tokens.access_token(OWNER_A)) == "access-for-refresh-new"
