"""main.py composition: website REST and Go MCP tools share one Supabase-backed store."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from workflow_fakes import OWNER, World

from hackathon_backend import main
from hackathon_backend.config import Settings
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.workflows import dev as dev_module
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver

SUPABASE = dict(
    supabase_url="https://example.supabase.co",
    supabase_publishable_key="publishable",
    supabase_service_role_key="server-secret",
)
GOOGLE = dict(
    credential_encryption_key=Fernet.generate_key().decode(),
    google_client_id="client-id",
    google_client_secret="client-secret",
    google_redirect_uri="https://demo.example/api/google/callback",
)


@pytest.fixture
def wiring(monkeypatch):
    """Replace server factories with fakes so no Supabase/Google network is touched."""
    calls: dict[str, list] = {"deps": [], "organizer": [], "assets": []}
    world = World()
    principals = InMemoryPrincipalResolver()
    token = principals.issue(OWNER)
    deps = EventToolDeps(world.store, principals)

    def fake_deps(settings):
        calls["deps"].append(settings)
        return deps

    monkeypatch.setattr(main, "create_tool_dependencies", fake_deps)
    monkeypatch.setattr(
        main,
        "register_organizer_tools",
        lambda mcp, settings, principals: calls["organizer"].append(principals),
    )
    monkeypatch.setattr(
        main,
        "register_asset_services",
        lambda app, mcp, settings, events: calls["assets"].append(events),
    )
    return calls, deps, token


def paths(app) -> set[str]:
    return set(app.openapi()["paths"])


def list_tools(client, token) -> set[str]:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code == 200, response.text
    return {tool["name"] for tool in response.json()["result"]["tools"]}


def test_supabase_app_shares_store_between_rest_and_go_tools(wiring):
    calls, deps, token = wiring
    app = main.create_app(Settings(**SUPABASE))
    assert {"/api/events", "/api/tasks", "/api/events/{event_id}/prepare"} <= paths(app)
    assert "/api/google/connect" not in paths(app)  # Google not configured
    assert len(calls["deps"]) == 1
    assert calls["organizer"] == [deps.principals]
    assert calls["assets"] == [deps]
    assert type(app.routes[-1]).__name__ == "Mount"  # MCP catch-all stays last
    with TestClient(app, base_url="http://localhost") as client:
        unauthenticated = client.get("/api/events")  # reaches REST, not the MCP mount
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["detail"]["code"] == "unauthenticated"
        assert {"get_event", "save_generated_content"} <= list_tools(client, token)
        assert client.get("/api/health").status_code == 200


def test_supabase_and_google_config_registers_google_connect(wiring):
    app = main.create_app(Settings(**SUPABASE, **GOOGLE))
    assert {"/api/google/connect", "/api/google/callback", "/api/google/status"} <= paths(app)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/google/connect").status_code == 401


def test_rest_only_without_service_key_registers_no_server_tools(wiring):
    calls, _, _ = wiring
    app = main.create_app(
        Settings(supabase_url=SUPABASE["supabase_url"], supabase_publishable_key="publishable")
    )
    assert "/api/events" in paths(app)
    assert calls == {"deps": [], "organizer": [], "assets": []}
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/mcp").status_code == 503


def test_unconfigured_app_starts_and_fails_closed(wiring):
    calls, _, _ = wiring
    app = main.create_app(Settings())
    assert "/api/events" not in paths(app)
    assert calls == {"deps": [], "organizer": [], "assets": []}
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/mcp").status_code == 503


def test_dev_mode_unchanged_even_with_supabase_settings(wiring, monkeypatch):
    calls, _, _ = wiring
    token = "d" * 32
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "1")
    monkeypatch.setenv("DEV_CONNECTOR_TOKEN", token)
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    app = main.create_app(Settings(**SUPABASE, **GOOGLE), dev=dev_module.dev_workflow_from_env())
    assert "/api/dev/events/{event_id}" in paths(app)
    assert not {"/api/events", "/api/google/connect"} & paths(app)
    assert calls == {"deps": [], "organizer": [], "assets": []}
    with TestClient(app, base_url="http://localhost") as client:
        assert "get_event" in list_tools(client, token)
