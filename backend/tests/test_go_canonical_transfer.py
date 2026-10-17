"""Real app/MCP/REST composition with mocked Supabase HTTP, never a live Go claim."""

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_go_mcp_tools import call, ok

from hackathon_backend.config import Settings
from hackathon_backend.main import create_app
from hackathon_backend.repositories.transport import Database

OWNER = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
TOKEN = "go_" + "a" * 43
TOKEN_B = "go_" + "b" * 43
PAYLOAD = {
    "title": "Braindump picnic",
    "location": "Test Garden",
    "description": "Synthetic test",
    "starts_at": "2026-11-14T10:00:00-08:00",
    "ends_at": "2026-11-14T12:00:00-08:00",
    "timezone": "America/Los_Angeles",
    "links": [],
    "organizer_contact": "test@example.com",
    "invitees": [],
}


@pytest.fixture
def connected(monkeypatch):
    records, keys = {}, {}
    calls = []
    owners = {
        hashlib.sha256(t.encode()).hexdigest(): o for t, o in [(TOKEN, OWNER), (TOKEN_B, OTHER)]
    }

    def upstream(request):
        calls.append(request.url.path)
        path = request.url.path
        if path == "/auth/v1/user":
            return httpx.Response(
                200,
                json={
                    "id": OWNER if request.headers["authorization"] == "Bearer session-a" else OTHER
                },
            )
        if path.endswith("/connector_tokens"):
            owner = owners.get(request.url.params["token_hash"].removeprefix("eq."))
            return httpx.Response(200, json=[{"owner_id": owner}] if owner else [])
        if path.endswith("/events"):
            owner = request.url.params["owner_id"].removeprefix("eq.")
            return httpx.Response(200, json=[r for r in records.values() if r["owner_id"] == owner])
        if path.endswith("/generated_content"):
            return httpx.Response(200, json=[])
        data = json.loads(request.content)
        if path.endswith("/organizer_event_json"):
            row = records.get(data["p_id"])
            return httpx.Response(
                200, json=row if row and row["owner_id"] == data["p_owner"] else None
            )
        assert path.endswith("/organizer_write_record")
        assert request.headers["authorization"] == "Bearer server-secret"
        owner, key, event_id = data["p_owner"], data["p_key"], data["p_id"]
        if event_id is None:
            if (owner, key) in keys:
                old = records[keys[owner, key]]
                return httpx.Response(200, json=old)
            event_id, revision = str(uuid4()), 1
            keys[owner, key] = event_id
        else:
            old = records.get(event_id)
            if not old or old["owner_id"] != owner:
                return httpx.Response(400, json={"message": "not_found"})
            if old["revision"] != data["p_expected"]:
                return httpx.Response(
                    400, json={"message": "revision_conflict", "details": "private SQL"}
                )
            revision = old["revision"] + 1
        row = {
            **data["p_data"],
            "id": event_id,
            "owner_id": owner,
            "revision": revision,
            "status": "draft",
            "created_at": "2026-10-16T00:00:00Z",
            "updated_at": "2026-10-16T00:00:00Z",
        }
        records[event_id] = deepcopy(row)
        return httpx.Response(200, json=row)

    init = Database.__init__

    def database(self, *args, **kwargs):
        if kwargs.get("transport") is None:
            kwargs["transport"] = httpx.MockTransport(upstream)
        init(self, *args, **kwargs)

    monkeypatch.setattr(Database, "__init__", database)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="public",
        supabase_service_role_key="server-secret",
        mcp_auth_token="scaffold",
    )
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        yield client, records, calls


def test_mcp_create_is_visible_in_owner_rest_and_updates_same_id(connected):
    client, records, _ = connected
    created = ok(
        call(client, TOKEN, "create_event", {**PAYLOAD, "idempotency_key": "brain-1"})
    )
    assert created["revision"] == 1 and "owner_id" not in created
    again = ok(
        call(client, TOKEN, "create_event", {**PAYLOAD, "idempotency_key": "brain-1"})
    )
    assert again["id"] == created["id"] and len(records) == 1
    headers = {"Authorization": "Bearer session-a"}
    rows = client.get("/api/events?limit=100&offset=0", headers=headers).json()
    assert isinstance(rows, list), rows
    assert rows[0]["id"] == created["id"]
    detail = client.get(f"/api/events/{created['id']}", headers=headers)
    assert detail.status_code == 200 and detail.json()["location"] == "Test Garden"
    changed = {**PAYLOAD, "location": "Test Pavilion", "expected_revision": 1}
    result = ok(
        call(client, TOKEN, "update_event", {"event_id": created["id"], **changed})
    )
    assert result["id"] == created["id"] and result["revision"] == 2
    assert (
        client.get(f"/api/events/{created['id']}", headers=headers).json()["location"]
        == "Test Pavilion"
    )
    stale = call(client, TOKEN, "update_event", {"event_id": created["id"], **changed})
    assert (
        stale["isError"] and "revision_conflict" in str(stale) and "private SQL" not in str(stale)
    )
    assert client.get("/api/events", headers={"Authorization": "Bearer session-b"}).json() == []
    foreign = call(client, TOKEN_B, "update_event", {"event_id": created["id"], **changed})
    assert foreign["isError"] and "not_found" in str(foreign)


def test_auth_and_typed_inputs_fail_before_writes(connected):
    client, records, _ = connected
    assert client.get("/api/config").json()["configured"] is True
    assert client.get("/api/events").status_code == 401
    for payload in [
        {**PAYLOAD, "ends_at": "2026-11-14T09:00:00-08:00"},
        {k: v for k, v in PAYLOAD.items() if k != "timezone"},
    ]:
        result = call(
            client, TOKEN, "create_event", {**payload, "idempotency_key": "invalid"}
        )
        assert result["isError"]
    denied = call(
        client, "scaffold", "create_event", {**PAYLOAD, "idempotency_key": "invalid"}
    )
    assert denied["isError"] and "unauthenticated" in str(denied)
    assert not records


def test_unconfigured_app_exposes_readiness_without_unprotected_mcp():
    with TestClient(create_app(Settings()), base_url="http://localhost") as client:
        assert client.get("/api/config").status_code == 404
        assert client.get("/api/events").status_code == 404
        assert client.post("/mcp").status_code == 503
