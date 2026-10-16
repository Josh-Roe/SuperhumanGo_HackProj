import asyncio

import pytest
from fastapi.testclient import TestClient
from workflow_fakes import OWNER, World, make_event

from hackathon_backend.config import Settings
from hackathon_backend.main import create_app
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.workflows import dev as dev_module
from hackathon_backend.workflows.go_work import enqueue_preparation
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver


@pytest.fixture
def setup():
    world = World()
    world.store.put_event(make_event(id="event-b", owner_id="owner-b"))
    principals = InMemoryPrincipalResolver()
    tokens = {"a": principals.issue(OWNER), "b": principals.issue("owner-b")}
    deps = EventToolDeps(world.store, principals, world.distributor, world.rsvp)
    app = create_app(Settings(mcp_auth_token="deploy-token"), events=deps)
    with TestClient(app, base_url="http://localhost") as client:
        yield world, client, tokens


def call(client, token, name, arguments=None):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def ok(result):
    assert not result.get("isError"), result
    structured = result["structuredContent"]
    return structured.get("result", structured)


def test_tool_annotations_mark_reads_and_sends(setup):
    _, client, tokens = setup
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={
            "Authorization": f"Bearer {tokens['a']}",
            "Accept": "application/json, text/event-stream",
        },
    )
    tools = {t["name"]: t["annotations"] for t in response.json()["result"]["tools"]}
    assert tools["get_event"]["readOnlyHint"] is True
    assert tools["list_rsvps"]["readOnlyHint"] is True
    assert tools["execute_distribution"]["destructiveHint"] is True
    assert tools["save_generated_content"]["readOnlyHint"] is False
    assert {"workspace_status", "count_text"} <= set(tools)


def test_deployment_token_and_unknown_tokens_get_no_event_data(setup):
    _, client, _ = setup
    result = call(client, "deploy-token", "get_event", {"event_id": "event-1"})
    assert result["isError"] and "unauthenticated" in result["content"][0]["text"]
    assert client.post("/mcp", headers={"Authorization": "Bearer guess"}).status_code == 401


def test_organizers_are_isolated(setup):
    _, client, tokens = setup
    result = call(client, tokens["b"], "get_event", {"event_id": "event-1"})
    assert result["isError"] and "forbidden" in result["content"][0]["text"]
    assert ok(call(client, tokens["b"], "get_event", {"event_id": "event-b"}))


def test_get_event_hides_owner_and_invitee_emails(setup):
    _, client, tokens = setup
    snapshot = ok(call(client, tokens["a"], "get_event", {"event_id": "event-1"}))["event"]
    assert "owner_id" not in snapshot
    assert "example.com" not in str(snapshot["invitees"])
    assert snapshot["invitee_count"] == 2


def test_go_round_trip_publish_and_rsvp(setup):
    world, client, tokens = setup
    asyncio.run(enqueue_preparation(world.store, OWNER, "event-1"))
    (work,) = ok(call(client, tokens["a"], "list_go_work"))
    assert work["state"] == "awaiting_go"
    ok(call(client, tokens["a"], "claim_go_work", {"work_id": work["id"]}))
    saved = None
    for kind in ("description", "summary", "invitation"):
        saved = ok(
            call(
                client,
                tokens["a"],
                "save_generated_content",
                {
                    "event_id": "event-1",
                    "expected_revision": 1,
                    "kind": kind,
                    "body": f"Go wrote this {kind}.",
                    "subject": "You're invited",
                    "work_id": work["id"],
                },
            )
        )
        assert saved["producer"] == "superhuman_go"
    assert world.store.work[work["id"]].state == "succeeded"

    blocked = ok(call(client, tokens["a"], "preview_distribution", {"event_id": "event-1"}))
    assert any("needs_review" in b for b in blocked["blockers"])

    # Organizer approves in the website (simulated); Go cannot mint approvals itself.
    approval = world.approve()
    result = ok(
        call(
            client,
            tokens["a"],
            "execute_distribution",
            {"event_id": "event-1", "approval_id": approval.id},
        )
    )
    assert result["sent"] is True
    stolen = call(
        client,
        tokens["b"],
        "execute_distribution",
        {"event_id": "event-1", "approval_id": approval.id},
    )
    assert stolen["isError"]

    thread = world.store.gmail["event-1"].thread_id
    world.gmail.receive_reply(thread, "ada@example.com", "Yes! I'm vegan, FYI.")
    synced = ok(call(client, tokens["a"], "sync_rsvps", {"event_id": "event-1"}))
    (reply_id,) = synced["replies_to_classify"]
    reply = ok(call(client, tokens["a"], "get_reply", {"reply_id": reply_id}))
    assert reply["body_text"].startswith("Yes!")
    recorded = ok(
        call(
            client,
            tokens["a"],
            "record_rsvp_classification",
            {
                "reply_id": reply_id,
                "status": "attending",
                "confidence": 0.9,
                "evidence": "Yes!",
                "private_note": "vegan",
            },
        )
    )
    assert recorded["status"] == "attending" and "private_note" not in recorded
    rows = ok(call(client, tokens["a"], "list_rsvps", {"event_id": "event-1"}))
    assert "vegan" not in str(rows) and "example.com" not in str(rows)


def test_google_tools_report_missing_configuration():
    world = World()
    principals = InMemoryPrincipalResolver()
    token = principals.issue(OWNER)
    app = create_app(Settings(), events=EventToolDeps(world.store, principals))
    with TestClient(app, base_url="http://localhost") as client:
        result = call(client, token, "preview_distribution", {"event_id": "event-1"})
        assert "integration_not_connected" in result["content"][0]["text"]
        assert ok(call(client, token, "get_event", {"event_id": "event-1"}))


def test_dev_mode_routes(monkeypatch):
    token = "d" * 32
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "1")
    monkeypatch.setenv("DEV_CONNECTOR_TOKEN", token)
    monkeypatch.setenv("DEV_INVITEES", "guest@example.com")
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    dev = dev_module.dev_workflow_from_env()
    app = create_app(Settings(), dev=dev)
    auth = {"Authorization": f"Bearer {token}"}
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/dev/events/dev-event-1").status_code == 401
        work = client.post("/api/dev/events/dev-event-1/prepare", headers=auth).json()
        saved = ok(
            call(
                client,
                token,
                "save_generated_content",
                {
                    "event_id": "dev-event-1",
                    "expected_revision": 1,
                    "kind": "invitation",
                    "body": "Hello",
                    "subject": "Hi",
                    "work_id": work["id"],
                },
            )
        )
        approval = client.post(
            "/api/dev/events/dev-event-1/approve", headers=auth, json={"content_id": saved["id"]}
        ).json()
        assert approval["event_revision"] == 1
        revised = client.post(
            "/api/dev/events/dev-event-1/revise", headers=auth, json={"location": "Elsewhere"}
        ).json()
        assert revised["revision"] == 2
        status = client.get("/api/dev/events/dev-event-1", headers=auth).json()
        assert status["label"].startswith("dev mode")
        assert status["event"]["location"] == "Elsewhere"
        connect = client.post("/api/dev/google/connect", headers=auth)
        assert connect.status_code == 400


def test_dev_mode_requires_strong_token(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "1")
    monkeypatch.setenv("DEV_CONNECTOR_TOKEN", "short")
    with pytest.raises(ValueError, match="DEV_CONNECTOR_TOKEN"):
        dev_module.dev_workflow_from_env()
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "0")
    assert dev_module.dev_workflow_from_env() is None
