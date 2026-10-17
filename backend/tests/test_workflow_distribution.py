import asyncio
from datetime import timedelta

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind


def run(coro):
    return asyncio.run(coro)


def publish(world, approval):
    return run(world.distributor.execute(OWNER, "event-1", approval.id))


def test_publish_creates_one_calendar_event_and_sends_bcc_invitation():
    world = World()
    result = publish(world, world.approve())
    assert result.sent is True
    assert [op.state for op in result.operations] == ["succeeded"] * 3
    assert len(world.calendar.events) == 1
    remote = next(iter(world.calendar.events.values()))
    assert {a["email"] for a in remote["attendees"]} == {"ada@example.com", "bob@example.com"}
    assert result.calendar_link == remote["htmlLink"]
    (sent,) = world.gmail.sent
    mime = sent["parsed"]
    assert mime["To"] == "organizer@example.com"
    assert "ada@example.com" in mime["Bcc"]
    body = mime.get_body().get_content()
    assert "Join us!" in body and remote["htmlLink"] in body
    assert "https://example.com/event-1" in body


def test_retry_after_success_does_not_duplicate_anything():
    world = World()
    approval = world.approve()
    publish(world, approval)
    publish(world, approval)
    assert len(world.calendar.events) == 1
    assert [c[0] for c in world.calendar.calls] == ["insert"]
    assert len(world.gmail.sent) == 1


def test_crash_after_gmail_send_reconciles_instead_of_resending():
    world = World()
    approval = world.approve()
    world.gmail.crash_after_send = True
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)
    send_op = run(world.store.list_operations(OWNER, "event-1"))[-1]
    assert send_op.state == "failed"
    result = publish(world, approval)
    assert result.sent is True
    assert len(world.gmail.sent) == 1


def test_calendar_created_before_binding_saved_is_adopted_not_duplicated():
    world = World()
    approval = world.approve()
    publish(world, approval)
    world.store.calendar.clear()  # simulate crash between insert and binding save
    world.store.operations.clear()
    world.gmail.sent.clear()
    world.store.gmail.clear()
    publish(world, approval)
    assert len(world.calendar.events) == 1


def test_change_after_send_updates_same_calendar_and_requires_change_notice():
    world = World()
    publish(world, world.approve())
    calendar_id = next(iter(world.calendar.events))
    world.revise(
        location="Park B",
        starts_at=world.store.events["event-1"].starts_at + timedelta(hours=1),
        ends_at=world.store.events["event-1"].ends_at + timedelta(hours=1),
    )
    plan = run(world.distributor.preview(OWNER, "event-1"))
    assert plan.calendar_action == "update"
    assert plan.gmail_action == "new_change_notice"
    assert plan.required_content_kind == ContentKind.CHANGE_NOTICE

    with pytest.raises(WorkflowError, match="change_notice"):
        publish(world, world.approve(ContentKind.INVITATION, "update"))

    result = publish(world, world.approve(ContentKind.CHANGE_NOTICE, "update", "Moved to B"))
    assert list(world.calendar.events) == [calendar_id]
    assert world.calendar.events[calendar_id]["location"] == "Park B"
    assert ("patch", "all") in world.calendar.calls
    assert len(world.gmail.sent) == 2
    first, second = world.gmail.sent
    assert first["threadId"] == second["threadId"]  # replies stay in one matched thread
    binding = world.store.gmail["event-1"]
    assert [h["event_revision"] for h in binding.sent_history] == [1, 2]
    assert result.sent


def test_unsent_draft_is_replaced_in_place():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve(action="draft_only").id))
    first_draft = world.store.gmail["event-1"].draft_id
    world.revise(location="Park C")
    result = run(world.distributor.execute(OWNER, "event-1", world.approve(action="draft_only").id))
    binding = world.store.gmail["event-1"]
    assert binding.draft_id == first_draft
    assert result.operations[1].receipt["replaced_unsent_draft"] is True
    assert len(world.gmail.drafts) == 1 and not world.gmail.sent


def test_draft_deleted_by_user_is_recreated_not_treated_as_sent():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve(action="draft_only").id))
    world.gmail.drafts.clear()
    world.gmail.messages.clear()
    publish(world, world.approve())
    assert len(world.gmail.sent) == 1
    assert world.store.gmail["event-1"].sent_history[0]["event_revision"] == 1


def test_draft_sent_manually_in_gmail_is_detected():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve(action="draft_only").id))
    draft_id = world.store.gmail["event-1"].draft_id
    run(world.gmail.send_draft(OWNER, draft_id))
    plan_before = run(world.distributor.preview(OWNER, "event-1"))
    assert plan_before.gmail_action == "replace_draft"  # preview does not call providers
    with pytest.raises(WorkflowError, match="change_notice"):
        # The organizer approved the same invitation again: reconciliation sees it was sent.
        world.revise(location="Park D")
        publish(world, world.approve())
    assert world.store.gmail["event-1"].sent is True


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda w, a: w.revise(location="Elsewhere"), "revision_conflict"),
        (
            lambda w, a: w.store.content.update(
                {
                    a.invitation_content_id: w.store.content[a.invitation_content_id].model_copy(
                        update={"state": "needs_review"}
                    )
                }
            ),
            "needs_review",
        ),
    ],
)
def test_execute_refuses_stale_or_unreviewed_content(mutate, code):
    world = World()
    approval = world.approve()
    mutate(world, approval)
    with pytest.raises(WorkflowError, match=code):
        publish(world, approval)
    assert not world.calendar.events and not world.gmail.sent


def test_other_organizer_cannot_use_approval_or_event():
    world = World()
    approval = world.approve()
    with pytest.raises(WorkflowError, match="forbidden"):
        run(world.distributor.execute("owner-b", "event-1", approval.id))


def test_provider_failure_is_recorded_and_retryable():
    world = World()
    approval = world.approve()
    world.calendar.fail_next = 500
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)
    (op,) = run(world.store.list_operations(OWNER, "event-1"))
    assert op.state == "failed" and op.error_code == "provider_failed:500"
    result = publish(world, approval)
    assert result.operations[0].attempts == 2
    assert len(world.calendar.events) == 1


def test_stale_etag_retries_once_with_fresh_etag():
    world = World()
    publish(world, world.approve())
    world.revise(location="Park E")
    world.calendar.fail_next = 412
    publish(world, world.approve(ContentKind.CHANGE_NOTICE, "update"))
    remote = next(iter(world.calendar.events.values()))
    assert remote["location"] == "Park E"
