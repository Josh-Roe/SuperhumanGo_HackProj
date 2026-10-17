"""A11 Canva part: per-organizer Canva MCP OAuth (PKCE) and token refresh. HTTP is mocked."""

import asyncio
import base64
import hashlib
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_google_connect import OWNER_A, OWNER_B, SESSIONS, Clock

from hackathon_backend.config import Settings
from hackathon_backend.main import create_app
from hackathon_backend.providers.canva.oauth import CanvaOAuthConfig, CanvaTokens
from hackathon_backend.workflows.asset_wiring import VaultCanvaSessions
from hackathon_backend.workflows.canva_connect import PkceStates, canva_connect_router
from hackathon_backend.workflows.go_work import WorkflowError

SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_publishable_key="publishable",
    supabase_service_role_key="server-secret",
    credential_encryption_key="unused-with-fake-vault",
    canva_client_id="canva-client",
    canva_client_secret="canva-secret",
    canva_redirect_uri="https://demo.example/api/canva/callback",
)
CONFIG = CanvaOAuthConfig("canva-client", "canva-secret", SETTINGS.canva_redirect_uri)


class FakeVault:
    def __init__(self):
        self.secrets = {}

    async def put_secret(self, owner_id, provider, value):
        self.secrets[(owner_id, provider)] = value

    async def get_secret(self, owner_id, provider):
        return self.secrets.get((owner_id, provider))


class CanvaTokenEndpoint:
    """Fake `POST /token`; issues numbered tokens and enforces one-use refresh."""

    def __init__(self):
        self.forms, self.auth, self.used_refresh, self.issued = [], [], set(), 0

    def __call__(self, request):
        if request.url.path == "/auth/v1/user":
            token = request.headers["authorization"].removeprefix("Bearer ")
            if token not in SESSIONS:
                return httpx.Response(401, json={"msg": "invalid"})
            return httpx.Response(200, json={"id": SESSIONS[token]})
        assert (request.url.host, request.url.path) == ("mcp.canva.com", "/token")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.forms.append(form)
        self.auth.append(request.headers["authorization"])
        if form.get("code") == "bad" or form.get("refresh_token") in self.used_refresh:
            return httpx.Response(400, json={"error": "invalid_grant"})
        if "refresh_token" in form:
            self.used_refresh.add(form["refresh_token"])
        self.issued += 1
        return httpx.Response(
            200,
            json={
                "access_token": f"access-{self.issued}",
                "refresh_token": f"refresh-{self.issued}",
                "token_type": "Bearer",
                "expires_in": 14400,
                "scope": "design:meta:read",
            },
        )


@pytest.fixture
def env():
    vault, endpoint, wall = FakeVault(), CanvaTokenEndpoint(), Clock()
    transport = httpx.MockTransport(endpoint)
    tokens = CanvaTokens(vault, CONFIG, transport=transport, now=wall)
    settings = replace(SETTINGS, app_url="https://app.example")
    app = FastAPI()
    app.include_router(
        canva_connect_router(settings, tokens, states=PkceStates(now=Clock()), transport=transport)
    )
    with TestClient(app, base_url="https://demo.example") as client:
        yield SimpleNamespace(
            client=client, vault=vault, endpoint=endpoint, tokens=tokens, wall=wall
        )


def start(client, session="session-a"):
    response = client.post("/api/canva/connect", headers={"Authorization": f"Bearer {session}"})
    assert response.status_code == 200, response.text
    bootstrap = response.json()["authorization_url"]
    response = client.get(
        bootstrap, headers={"Referer": "https://app.example/"}, follow_redirects=False
    )
    assert response.status_code == 302
    url = urlsplit(response.headers["location"])
    assert (url.hostname, url.path) == ("mcp.canva.com", "/authorize")
    return {k: v[0] for k, v in parse_qs(url.query).items()}


def test_connect_callback_stores_tokens_for_state_owner_with_pkce(env):
    query = start(env.client)
    assert query["client_id"] == "canva-client" and query["response_type"] == "code"
    assert query["redirect_uri"] == SETTINGS.canva_redirect_uri

    done = env.client.get(
        "/api/canva/callback",
        params={"state": query["state"], "code": "good"},
        follow_redirects=False,
    )

    assert done.status_code == 303
    assert done.headers["location"] == "https://app.example/?canva=connected"
    (form,) = env.endpoint.forms
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(form["code_verifier"].encode()).digest()
    ).rstrip(b"=")
    assert challenge.decode() == query["code_challenge"]
    assert form["grant_type"] == "authorization_code" and form["code"] == "good"
    basic = base64.b64encode(b"canva-client:canva-secret").decode()
    assert env.endpoint.auth == [f"Basic {basic}"]
    record = env.vault.secrets[(OWNER_A, "canva")]
    assert record["access_token"] == "access-1" and record["refresh_token"] == "refresh-1"
    assert (OWNER_B, "canva") not in env.vault.secrets
    assert "access-1" not in done.text + done.headers["location"]

    def connected(session):
        headers = {"Authorization": f"Bearer {session}"}
        return env.client.get("/api/canva/status", headers=headers).json()

    assert connected("session-a")["connected"] is True
    assert connected("session-b")["connected"] is False

    replay = env.client.get(
        "/api/canva/callback",
        params={"state": query["state"], "code": "good"},
        follow_redirects=False,
    )
    assert replay.headers["location"] == "https://app.example/?canva=error&reason=invalid_state"


@pytest.mark.parametrize(
    ("params", "reason"),
    [({"error": "access_denied"}, "denied"), ({"code": "bad"}, "exchange_failed")],
)
def test_callback_failures_redirect_with_reason_and_store_nothing(env, params, reason):
    state = start(env.client)["state"]
    done = env.client.get(
        "/api/canva/callback", params={"state": state, **params}, follow_redirects=False
    )
    assert done.headers["location"] == f"https://app.example/?canva=error&reason={reason}"
    assert env.vault.secrets == {}


def test_connect_requires_organizer_session(env):
    assert env.client.post("/api/canva/connect").status_code == 401


def test_expired_access_token_is_refreshed_once_and_rotated_refresh_token_stored(env):
    async def flow():
        await env.tokens.save_grant(
            OWNER_A,
            {"access_token": "old", "refresh_token": "refresh-0", "expires_at": env.wall.now + 30},
        )
        first, second = await asyncio.gather(
            env.tokens.access_token(OWNER_A), env.tokens.access_token(OWNER_A)
        )
        return first, second

    first, second = asyncio.run(flow())

    assert first == second == "access-1"
    assert [f["grant_type"] for f in env.endpoint.forms] == ["refresh_token"]
    assert env.vault.secrets[(OWNER_A, "canva")]["refresh_token"] == "refresh-1"


def test_sessions_use_fresh_token_keep_legacy_record_and_ask_reconnect_on_rejected_refresh(env):
    opened = []

    @asynccontextmanager
    async def connect(*, owner_id, access_token):
        opened.append(access_token)
        yield SimpleNamespace()

    sessions = VaultCanvaSessions(env.vault, connect=connect, tokens=env.tokens)

    async def flow():
        await env.tokens.save_grant(
            OWNER_A, {"access_token": "fresh", "expires_at": env.wall.now + 3600}
        )
        async with sessions.open(OWNER_A):
            pass
        await env.vault.put_secret(
            OWNER_B,
            "canva",
            {
                "access_token": "x",
                "refresh_token": "revoked",
                "expires_at": 0,
                "resource": "https://mcp.canva.com/mcp",
            },
        )
        env.endpoint.used_refresh.add("revoked")
        with pytest.raises(WorkflowError, match="integration_not_connected"):
            async with sessions.open(OWNER_B):
                pass

    asyncio.run(flow())
    assert opened == ["fresh"]


def test_canva_routes_register_only_when_configured():
    def paths(settings):
        return set(create_app(settings).openapi()["paths"])

    assert "/api/canva/connect" not in paths(Settings())
    configured = replace(SETTINGS, credential_encryption_key=Fernet.generate_key().decode())
    assert {"/api/canva/connect", "/api/canva/callback", "/api/canva/status"} <= paths(configured)


def test_registered_callback_and_flyer_sessions_share_one_token_source(monkeypatch):
    from hackathon_backend.workflows import canva_connect

    created, routed = [], []
    original_router = canva_connect.canva_connect_router

    def router(settings, tokens):
        routed.append(tokens)
        return original_router(settings, tokens)

    def token_source(*args, **kwargs):
        instance = CanvaTokens(*args, **kwargs)
        created.append(instance)
        return instance

    monkeypatch.setattr("hackathon_backend.providers.canva.oauth.CanvaTokens", token_source)
    monkeypatch.setattr(canva_connect, "CanvaTokens", token_source)
    monkeypatch.setattr(canva_connect, "canva_connect_router", router)
    configured = replace(SETTINGS, credential_encryption_key=Fernet.generate_key().decode())
    app = create_app(configured)
    assert len(created) == 1
    assert routed == created
    assert {"/api/canva/callback", "/api/canva/verify"} <= set(app.openapi()["paths"])
