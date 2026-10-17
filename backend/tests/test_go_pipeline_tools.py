import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from workflow_fakes import OWNER, World, make_event

from hackathon_backend.mcp_tools.event_tools import EventToolDeps, register_event_tools
from hackathon_backend.mcp_tools.pipeline_tools import register_pipeline_tools
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver
from hackathon_backend.workflows.pipeline import MemoryChatApprovals


@pytest.fixture
def setup():
    world = World()
    world.store.put_event(make_event(id="event-b", owner_id="owner-b"))
    principals = InMemoryPrincipalResolver()
    tokens = {"a": principals.issue(OWNER), "b": principals.issue("owner-b")}
    deps = EventToolDeps(world.store, principals, world.distributor, world.rsvp)
    mcp = FastMCP(
        "test",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register_event_tools(mcp, deps)
    register_pipeline_tools(mcp, deps, MemoryChatApprovals(world.store))
    with TestClient(mcp.streamable_http_app(), base_url="http://localhost") as client:
        yield world, client, tokens


def call(client, token, name, arguments):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
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


def error_text(result):
    assert result.get("isError"), result
    return result["content"][0]["text"]


def write_drafts(client, token, revision, send_kind="invitation"):
    saved = {}
    for kind in ("description", "summary", send_kind):
        saved[kind] = ok(
            call(
                client,
                token,
                "save_generated_content",
                {
                    "event_id": "event-1",
                    "expected_revision": revision,
                    "kind": kind,
                    "body": f"Go wrote this {kind}.",
                    "subject": f"{kind} subject",
                },
            )
        )
    return saved[send_kind]


def progress(client, token):
    return ok(call(client, token, "event_progress", {"event_id": "event-1"}))


def statuses(report):
    return {stage["stage"]: stage["status"] for stage in report["stages"]}


def test_pipeline_walks_from_writing_to_one_sent_invitation(setup):
    world, client, tokens = setup
    assert progress(client, tokens["a"])["next_stage"] == "writing"

    invitation = write_drafts(client, tokens["a"], revision=1)
    assert progress(client, tokens["a"])["next_stage"] == "review"

    approved = ok(
        call(
            client,
            tokens["a"],
            "approve_draft",
            {"content_id": invitation["id"], "expected_revision": 1, "subject": "Picnic Sunday!"},
        )
    )
    assert approved["state"] == "ready"
    assert progress(client, tokens["a"])["next_stage"] == "inclusion"

    ok(
        call(
            client,
            tokens["a"],
            "save_inclusion_facts",
            {"event_id": "event-1", "step_free_entrance": "yes", "captions": "unknown"},
        )
    )
    report = progress(client, tokens["a"])
    assert report["next_stage"] == "send"
    assert statuses(report)["send"] == "todo"

    sent = ok(
        call(
            client, tokens["a"], "send_invitations", {"event_id": "event-1", "expected_revision": 1}
        )
    )
    retry = ok(
        call(
            client, tokens["a"], "send_invitations", {"event_id": "event-1", "expected_revision": 1}
        )
    )

    assert sent["sent"] is True and sent["action"] == "publish"
    assert retry["approval_id"] == sent["approval_id"]
    assert len(world.gmail.sent) == 1
    assert world.gmail.sent[0]["parsed"]["Subject"] == "Picnic Sunday!"  # organizer's edit
    assert statuses(progress(client, tokens["a"]))["send"] == "done"


def test_send_refuses_an_unapproved_draft_without_touching_google(setup):
    world, client, tokens = setup
    write_drafts(client, tokens["a"], revision=1)

    result = call(
        client, tokens["a"], "send_invitations", {"event_id": "event-1", "expected_revision": 1}
    )

    assert "needs_review" in error_text(result)
    assert world.calendar.calls == [] and world.gmail.sent == []


def test_change_after_send_asks_for_a_change_notice_and_updates_the_same_invite(setup):
    world, client, tokens = setup
    invitation = write_drafts(client, tokens["a"], revision=1)
    ok(
        call(
            client,
            tokens["a"],
            "approve_draft",
            {"content_id": invitation["id"], "expected_revision": 1},
        )
    )
    first = ok(
        call(
            client, tokens["a"], "send_invitations", {"event_id": "event-1", "expected_revision": 1}
        )
    )
    world.revise(location="Park B")

    report = progress(client, tokens["a"])
    assert report["mode"] == "update" and report["next_stage"] == "writing"
    assert "change_notice" in report["stages"][1]["detail"]

    notice = write_drafts(client, tokens["a"], revision=2, send_kind="change_notice")
    ok(
        call(
            client,
            tokens["a"],
            "approve_draft",
            {"content_id": notice["id"], "expected_revision": 2},
        )
    )
    second = ok(
        call(
            client, tokens["a"], "send_invitations", {"event_id": "event-1", "expected_revision": 2}
        )
    )

    assert second["action"] == "update"
    assert second["calendar_link"] == first["calendar_link"]
    assert len(world.gmail.sent) == 2


def test_inclusion_answers_merge_and_unknown_is_not_sourced(setup):
    world, client, tokens = setup
    args = {"event_id": "event-1", "elevator": "yes", "diet_options": ["vegan"]}
    ok(call(client, tokens["a"], "save_inclusion_facts", args))

    saved = ok(
        call(
            client,
            tokens["a"],
            "save_inclusion_facts",
            {"event_id": "event-1", "captions": "unknown"},
        )
    )

    assert saved["version"] == 2
    assert saved["elevator"] == "yes" and saved["diet_options"] == ["vegan"]
    assert saved["captions"] == "unknown"


def test_another_organizer_cannot_read_progress_or_send(setup):
    _, client, tokens = setup
    for name, args in (
        ("event_progress", {"event_id": "event-1"}),
        ("send_invitations", {"event_id": "event-1", "expected_revision": 1}),
    ):
        assert "forbidden" in error_text(call(client, tokens["b"], name, args))
