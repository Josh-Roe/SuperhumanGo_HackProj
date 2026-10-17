"""OAuth transport/PKCE/browser binding/rotation tests. No live credentials or provider calls."""

import asyncio
import base64
import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.providers.canva import CanvaError
from hackathon_backend.providers.canva.oauth import (
    RESOURCE,
    TOKEN_URL,
    CanvaOAuthConfig,
    CanvaOAuthStates,
    CanvaTokens,
)
from hackathon_backend.workflows.asset_wiring import VaultCanvaSessions
from hackathon_backend.workflows.canva_connect import canva_connect_router

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp()
CONFIG = CanvaOAuthConfig(
    "synthetic-client", "synthetic-secret", "https://backend.example/api/canva/callback"
)
SETTINGS = Settings(app_url="https://dashboard.example")


class Vault:
    def __init__(self):
        self.records = {}

    async def get_secret(self, owner, provider):
        return self.records.get((owner, provider))

    async def put_secret(self, owner, provider, value):
        self.records[(owner, provider)] = value


@pytest.fixture
def host():
    vault, requests, clock = Vault(), [], [NOW]
    payload = {
        "access_token": "synthetic-access",
        "refresh_token": "synthetic-refresh",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    def server(request):
        assert str(request.url) == TOKEN_URL
        expected = base64.b64encode(b"synthetic-client:synthetic-secret").decode()
        assert request.headers["authorization"] == "Basic " + expected
        requests.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json=payload)

    tokens = CanvaTokens(vault, CONFIG, transport=httpx.MockTransport(server), now=lambda: clock[0])
    states = CanvaOAuthStates()

    async def owner(header):
        if header not in {"Bearer owner-a", "Bearer owner-b"}:
            raise DomainError("unauthenticated", "Sign in", 401)
        return header.removeprefix("Bearer ")

    @asynccontextmanager
    async def connect(**kwargs):
        assert kwargs["access_token"] == "synthetic-access"
        yield SimpleNamespace(
            capabilities=lambda: SimpleNamespace(
                available_actions=("create", "review", "export"), missing_tools=()
            )
        )

    app = FastAPI()
    app.include_router(
        canva_connect_router(SETTINGS, tokens, resolve_owner=owner, states=states, connect=connect)
    )
    with TestClient(app, base_url="https://backend.example") as client:
        yield client, vault, requests, tokens, states, clock, payload


def begin(client, owner="owner-a"):
    response = client.post("/api/canva/connect", headers={"Authorization": "Bearer " + owner})
    assert response.status_code == 200
    bootstrap = response.json()["authorization_url"]
    assert bootstrap.startswith("https://backend.example/api/canva/start?")
    response = client.get(
        bootstrap, headers={"Referer": "https://dashboard.example/"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["set-cookie"].lower().count("httponly") == 1
    assert (
        "Secure" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    return parse_qs(urlsplit(response.headers["location"]).query)


def test_full_flow_exact_pkce_owner_binding_no_token_responses_and_single_use(host):
    client, vault, requests, _, states, _, _ = host
    query = begin(client, "owner-b")
    assert query["resource"] == [RESOURCE] and query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    verifier = states.pending[state].verifier
    assert query["code_challenge"] == [
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    ]
    url = "/api/canva/callback?state=" + state + "&code=synthetic-code"
    response = client.get(url, follow_redirects=False)
    assert (
        response.status_code == 303
        and response.headers["location"] == "https://dashboard.example/?canva=connected"
    )
    assert "synthetic-access" not in response.text and "synthetic-secret" not in response.text
    assert ("owner-b", "canva") in vault.records and ("owner-a", "canva") not in vault.records
    assert requests[0]["code_verifier"] == [verifier] and requests[0]["resource"] == [RESOURCE]
    assert (
        "reason=invalid_state" in client.get(url, follow_redirects=False).headers["location"]
        and len(requests) == 1
    )
    status = client.get("/api/canva/status", headers={"Authorization": "Bearer owner-b"})
    assert status.json()["connected"]
    assert "synthetic-" not in status.text
    verified = client.post("/api/canva/verify", headers={"Authorization": "Bearer owner-b"})
    assert (
        verified.json()["flyer_workflow_ready"] and verified.headers["cache-control"] == "no-store"
    )


def test_connect_auth_start_origin_and_callback_cookie_are_required(host):
    client, vault, requests, _, _, _, _ = host
    assert client.post("/api/canva/connect").status_code == 401
    assert client.post("/api/canva/verify").status_code == 401
    assert client.get("/api/canva/status").status_code == 401
    bootstrap = client.post(
        "/api/canva/connect", headers={"Authorization": "Bearer owner-a"}
    ).json()["authorization_url"]
    assert client.get(bootstrap, follow_redirects=False).status_code == 403
    assert (
        client.get(
            bootstrap, headers={"Referer": "https://evil.example"}, follow_redirects=False
        ).status_code
        == 403
    )
    query = begin(client)
    client.cookies.clear()
    response = client.get(
        "/api/canva/callback",
        params={"state": query["state"][0], "code": "secret-code"},
        follow_redirects=False,
    )
    assert (
        response.status_code == 303
        and "reason=invalid_state" in response.headers["location"]
        and "secret-code" not in response.text
    )
    assert not vault.records and not requests
    assert response.headers["cache-control"] == "no-store"


def test_expiry_denial_and_invalid_input_do_not_exchange(host):
    client, _, requests, _, states, _, _ = host
    query = begin(client)
    response = client.get(
        "/api/canva/callback",
        params={"state": query["state"][0], "error": "raw-private-error"},
        follow_redirects=False,
    )
    assert (
        response.status_code == 303
        and "reason=denied" in response.headers["location"]
        and "raw-private-error" not in response.text
    )
    query = begin(client)
    states.now = lambda: float("inf")
    assert (
        client.get(
            "/api/canva/callback",
            params={"state": query["state"][0], "code": "x"},
            follow_redirects=False,
        )
        .headers["location"]
        .endswith("reason=invalid_state")
    )
    response = client.get("/api/canva/callback", params={"state": "x" * 300})
    assert response.status_code == 422 and not requests


@pytest.mark.parametrize(
    "bad",
    [
        {"access_token": "contains whitespace"},
        {"token_type": "MAC"},
        {"expires_in": -1},
        {"expires_in": True},
        {"expires_in": "3600"},
        {"refresh_token": 42},
    ],
)
def test_invalid_grants_never_enter_vault(host, bad):
    client, vault, _, _, _, _, payload = host
    payload.update(bad)
    query = begin(client)
    response = client.get(
        "/api/canva/callback",
        params={"state": query["state"][0], "code": "x"},
        follow_redirects=False,
    )
    assert (
        response.status_code == 303
        and not vault.records
        and "synthetic-secret" not in response.text
    )


def test_refresh_serializes_concurrent_reads_rotates_and_reuses_tokens(host):
    _, vault, requests, tokens, _, clock, payload = host

    async def run():
        await tokens.authorize("owner-a", "code", "verifier")
        clock[0] += 3600
        payload["access_token"] = "refreshed-access"
        payload["refresh_token"] = "rotated-refresh"
        assert (
            await asyncio.gather(tokens.access_token("owner-a"), tokens.access_token("owner-a"))
            == ["refreshed-access"] * 2
        )
        assert len(requests) == 2 and requests[1]["refresh_token"] == ["synthetic-refresh"]
        assert vault.records[("owner-a", "canva")]["refresh_token"] == "rotated-refresh"
        clock[0] += 3600
        payload.pop("refresh_token")
        assert await tokens.access_token("owner-a") == "refreshed-access"
        assert vault.records[("owner-a", "canva")]["refresh_token"] == "rotated-refresh"
        assert await tokens.access_token("foreign-owner") is None

    asyncio.run(run())


def test_refresh_is_used_by_the_actual_canva_session_port(host):
    _, _, requests, tokens, _, clock, _ = host
    seen = []

    @asynccontextmanager
    async def connect(*, owner_id, access_token):
        seen.append((owner_id, access_token))
        yield object()

    async def run():
        await tokens.authorize("owner-a", "code", "verifier")
        clock[0] += 3600
        sessions = VaultCanvaSessions(tokens.vault, connect=connect, tokens=tokens)
        async with sessions.open("owner-a"):
            pass
        assert seen == [("owner-a", "synthetic-access")] and len(requests) == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "uri",
    [
        "http://evil.example/callback",
        "https://user:secret@backend.example/callback",
        "https://backend.example/callback?x=y",
    ],
)
def test_oauth_secrets_not_in_repr_and_redirects_are_constrained(uri):
    assert "synthetic-secret" not in repr(CONFIG)
    with pytest.raises(ValueError):
        CanvaOAuthConfig("id", "secret", uri)


def test_expired_without_refresh_and_legacy_tokens_require_reconnect(host):
    client, vault, requests, tokens, _, clock, payload = host

    async def run():
        payload.pop("refresh_token")
        await tokens.authorize("owner-a", "code", "verifier")
        clock[0] += 3600
        assert await tokens.access_token("owner-a") is None
        await vault.put_secret("legacy", "canva", {"access_token": "manually-inserted"})
        with pytest.raises(CanvaError, match="reconnect"):
            await tokens.access_token("legacy")
        assert len(requests) == 1

    asyncio.run(run())
    response = client.get("/api/canva/status", headers={"Authorization": "Bearer owner-a"})
    assert response.json()["connected"] is False


@pytest.mark.parametrize("kind", ["denied", "redirect", "network"])
def test_failed_exchange_does_not_save_or_echo_provider_details(host, kind):
    client, vault, _, tokens, _, _, _ = host

    def bad(request):
        if kind == "network":
            raise httpx.ConnectError("secret-token-upstream-url", request=request)
        return httpx.Response(
            302 if kind == "redirect" else 401,
            headers={"Location": "https://evil.example"},
            json={"error_description": "private-upstream-content"},
        )

    tokens._transport = httpx.MockTransport(bad)
    query = begin(client)
    response = client.get(
        "/api/canva/callback",
        params={"state": query["state"][0], "code": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303 and not vault.records
    assert "private-upstream-content" not in response.text and "evil.example" not in response.text


@pytest.mark.parametrize(
    "resource", [None, "https://api.canva.com", "https://mcp.canva.com/mcp"]
)
def test_existing_unknown_or_rest_grant_requires_reconnecting_to_mcp(host, resource):
    _, vault, requests, tokens, _, clock, _ = host

    async def run():
        await vault.put_secret(
            "owner-a",
            "canva",
            {
                "access_token": "unverified-audience",
                "refresh_token": "unverified-refresh",
                "expires_at": clock[0] + 3600,
                "resource": resource,
            },
        )
        assert await tokens.connected("owner-a") is False
        with pytest.raises(CanvaError, match="reconnect"):
            await tokens.access_token("owner-a")
        assert requests == []

    asyncio.run(run())
