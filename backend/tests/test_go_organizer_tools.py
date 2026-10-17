import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.mcp_tools.organizer_tools import register_organizer_tools
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver

OWNER_A, OWNER_B = str(uuid4()), str(uuid4())
NOW = "2026-10-16T12:00:00+00:00"


class FakeOrganizerDB:
    """Mimics organizer_write_record: per-owner idempotency keys and optimistic revisions."""

    def __init__(self):
        self.records: dict[str, dict] = {}
        self.keys: dict[tuple, tuple[str, dict]] = {}
        self.writes = 0


class FakeRepo:
    def __init__(self, db: FakeOrganizerDB, owner_id: str):
        self.db, self.owner_id = db, owner_id

    async def list_records(self, kind, limit=50, offset=0):
        rows = [r for r in self.db.records.values() if r["_kind"] == kind]
        return [r for r in rows if r["owner_id"] == self.owner_id][offset : offset + limit]

    async def get(self, kind, record_id):
        row = self.db.records.get(record_id)
        if row is None or row["owner_id"] != self.owner_id or row["_kind"] != kind:
            raise DomainError("not_found", "Record not found", 404)
        return row

    async def _create(self, kind, payload, key):
        data = payload.model_dump(mode="json")
        digest = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
        prior = self.db.keys.get((self.owner_id, kind, key))
        if prior:
            if prior[0] != digest:
                raise DomainError("idempotency_conflict", "idempotency conflict")
            return prior[1]
        row = {**data, "_kind": kind, "id": str(uuid4()), "owner_id": self.owner_id}
        row.update(revision=1, updated_at=NOW)
        if kind == "events":
            row["status"] = "draft"
        self.db.records[row["id"]] = row
        self.db.keys[(self.owner_id, kind, key)] = (digest, row)
        self.db.writes += 1
        return row

    async def _update(self, kind, record_id, payload):
        row = await self.get(kind, record_id)
        if row["revision"] != payload.expected_revision:
            raise DomainError("revision_conflict", "revision conflict")
        row.update(payload.model_dump(mode="json", exclude={"expected_revision"}))
        row["revision"] += 1
        if kind == "events":
            row["status"] = "changed"
        self.db.writes += 1
        return row

    async def create_event(self, payload, key):
        return await self._create("events", payload, key)

    async def update_event(self, event_id, payload):
        return await self._update("events", event_id, payload)

    async def create_task(self, payload, key):
        return await self._create("tasks", payload, key)

    async def update_task(self, task_id, payload):
        return await self._update("tasks", task_id, payload)


@pytest.fixture
def setup():
    db = FakeOrganizerDB()
    principals = InMemoryPrincipalResolver()
    tokens = {"a": principals.issue(OWNER_A), "b": principals.issue(OWNER_B)}
    mcp = FastMCP(
        "test",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register_organizer_tools(
        mcp, Settings(), principals, lambda _settings, who: FakeRepo(db, who.owner_id)
    )
    with TestClient(mcp.streamable_http_app(), base_url="http://localhost") as client:
        yield db, client, tokens


def rpc(client, token, method, params):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def call(client, token, name, arguments):
    return rpc(client, token, "tools/call", {"name": name, "arguments": arguments})


def ok(result):
    assert not result.get("isError"), result
    structured = result["structuredContent"]
    return structured.get("result", structured)


def error_text(result):
    assert result.get("isError"), result
    return result["content"][0]["text"].split(": ", 1)[1]  # drop "Error executing tool x"


EVENT = {
    "idempotency_key": "go-create-picnic-1",
    "title": "Community picnic",
    "starts_at": "2026-11-01T17:00:00+00:00",
    "ends_at": "2026-11-01T19:00:00+00:00",
    "timezone": "America/New_York",
    "invitees": [{"email": "Guest@Example.com", "display_name": "Guest"}],
}


def test_tools_are_listed_with_read_write_annotations(setup):
    _, client, tokens = setup
    tools = {t["name"]: t for t in rpc(client, tokens["a"], "tools/list", {})["tools"]}
    for name in ("list_events", "list_tasks"):
        assert tools[name]["annotations"]["readOnlyHint"] is True
    for name in ("create_event", "update_event", "create_task", "update_task"):
        assert tools[name]["annotations"]["readOnlyHint"] is False
        assert "owner_id" not in tools[name]["inputSchema"]["properties"]
    assert "idempotency_key" in tools["create_event"]["inputSchema"]["required"]
    assert "expected_revision" in tools["update_event"]["inputSchema"]["required"]


def test_unauthenticated_calls_are_rejected(setup):
    db, client, _ = setup
    for token in ("", "guess"):
        result = call(client, token, "create_event", EVENT)
        assert "unauthenticated" in error_text(result)
        assert "unauthenticated" in error_text(call(client, token, "list_events", {}))
    assert db.writes == 0


def test_create_event_is_idempotent_and_hides_invitee_emails(setup):
    db, client, tokens = setup
    first = ok(call(client, tokens["a"], "create_event", EVENT))
    again = ok(call(client, tokens["a"], "create_event", EVENT))
    assert first["id"] == again["id"] and first["revision"] == 1
    assert first["invitee_count"] == 1 and "guest@example.com" not in json.dumps(first)
    assert db.writes == 1
    changed = call(client, tokens["a"], "create_event", {**EVENT, "title": "Other"})
    assert error_text(changed).startswith("idempotency_conflict")
    listed = ok(call(client, tokens["a"], "list_events", {}))
    assert [e["id"] for e in listed] == [first["id"]]


def test_event_results_link_to_the_dashboard_when_app_url_is_set():
    db, principals = FakeOrganizerDB(), InMemoryPrincipalResolver()
    token = principals.issue(OWNER_A)
    mcp = FastMCP(
        "test",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    settings = Settings(app_url="https://dashboard.example")
    register_organizer_tools(mcp, settings, principals, lambda _s, who: FakeRepo(db, who.owner_id))
    with TestClient(mcp.streamable_http_app(), base_url="http://localhost") as client:
        event = ok(call(client, token, "create_event", EVENT))
        link = f"https://dashboard.example/?event={event['id']}"
        assert event["dashboard_url"] == link
        assert ok(call(client, token, "list_events", {}))[0]["dashboard_url"] == link
        update = {"event_id": event["id"], "expected_revision": 1, "location": "Library"}
        assert ok(call(client, token, "update_event", update))["dashboard_url"] == link


@pytest.mark.parametrize(
    "app_url", ["mtcx.vercel.app", "https://mtcx.vercel.app/events", "http://evil.example"]
)
def test_app_url_rejects_non_origins(app_url):
    with pytest.raises(ValueError):
        Settings(app_url=app_url)


def test_update_event_merges_fields_and_rejects_stale_revision(setup):
    db, client, tokens = setup
    event = ok(call(client, tokens["a"], "create_event", EVENT))
    update = {"event_id": event["id"], "expected_revision": 1, "location": "Riverside Park"}
    saved = ok(call(client, tokens["a"], "update_event", update))
    assert saved["revision"] == 2 and saved["location"] == "Riverside Park"
    assert saved["title"] == "Community picnic" and saved["invitee_count"] == 1
    stale = call(client, tokens["a"], "update_event", {**update, "location": "Library"})
    assert error_text(stale).startswith("revision_conflict")
    assert db.records[event["id"]]["location"] == "Riverside Park"


def test_update_event_validates_merged_event(setup):
    _, client, tokens = setup
    event = ok(call(client, tokens["a"], "create_event", EVENT))
    bad = {"event_id": event["id"], "expected_revision": 1, "ends_at": "2026-11-01T16:00:00Z"}
    assert error_text(call(client, tokens["a"], "update_event", bad)).startswith("invalid_request")


def test_owner_comes_from_token_never_arguments(setup):
    db, client, tokens = setup
    # An injected owner_id is ignored by the tool schema; the token's organizer owns the event.
    result = call(client, tokens["a"], "create_event", {**EVENT, "owner_id": OWNER_B})
    event_id = ok(result)["id"]
    assert db.records[event_id]["owner_id"] == OWNER_A
    assert ok(call(client, tokens["b"], "list_events", {})) == []
    other = call(
        client,
        tokens["b"],
        "update_event",
        {"event_id": event_id, "expected_revision": 1, "title": "Hijacked"},
    )
    assert error_text(other).startswith("not_found")
    assert db.records[event_id]["title"] == "Community picnic"


def test_tasks_create_idempotently_and_update_with_revision(setup):
    db, client, tokens = setup
    args = {"idempotency_key": "go-task-1", "title": "Book chairs", "due_at": NOW}
    task = ok(call(client, tokens["a"], "create_task", args))
    assert ok(call(client, tokens["a"], "create_task", args))["id"] == task["id"]
    assert db.writes == 1 and task["revision"] == 1 and task["status"] == "todo"
    done = ok(
        call(
            client,
            tokens["a"],
            "update_task",
            {"task_id": task["id"], "expected_revision": 1, "status": "done", "clear_due_at": True},
        )
    )
    assert done["revision"] == 2 and done["status"] == "done" and done["due_at"] is None
    assert done["title"] == "Book chairs"
    stale = call(
        client, tokens["a"], "update_task", {"task_id": task["id"], "expected_revision": 1}
    )
    assert error_text(stale).startswith("revision_conflict")
    assert [t["id"] for t in ok(call(client, tokens["a"], "list_tasks", {}))] == [task["id"]]
    assert ok(call(client, tokens["b"], "list_tasks", {})) == []
