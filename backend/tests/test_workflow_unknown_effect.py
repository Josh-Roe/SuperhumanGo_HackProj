"""A14: an unknown provider outcome is read back before any retry; never retried blindly."""

import asyncio
from datetime import timedelta

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import utcnow


def run(coro):
    return asyncio.run(coro)


def publish(world, approval):
    return run(world.distributor.execute(OWNER, "event-1", approval.id))


def operations(world):
    return {op.kind.value: op for op in run(world.store.list_operations(OWNER, "event-1"))}


def test_send_that_timed_out_after_gmail_sent_it_is_adopted_not_resent():
    world = World()
    approval = world.approve()
    world.gmail.crash_after_send = True
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)

    result = publish(world, approval)

    assert result.sent is True
    assert len(world.gmail.sent) == 1
    send = operations(world)["gmail_send"]
    assert send.state == "succeeded" and send.attempts == 1
    assert send.receipt["message_id"] == world.gmail.sent[0]["id"]


def test_send_that_never_reached_gmail_is_sent_exactly_once():
    world = World()
    approval = world.approve()
    world.gmail.fail_send_before = 504
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)
    assert world.gmail.sent == []

    result = publish(world, approval)

    assert result.sent is True
    assert len(world.gmail.sent) == 1
    assert operations(world)["gmail_send"].attempts == 2


def test_calendar_insert_from_a_crashed_worker_is_adopted():
    world = World()
    approval = world.approve()
    world.calendar.crash_after_insert = True
    with pytest.raises(RuntimeError):
        publish(world, approval)
    crashed = operations(world)["calendar_upsert"]
    assert crashed.state == "running"
    world.distributor.clock = lambda: utcnow() + timedelta(minutes=10)  # worker is long dead

    result = publish(world, approval)

    assert [call for call, _ in world.calendar.calls] == ["insert"]
    assert len(world.calendar.events) == 1
    calendar = operations(world)["calendar_upsert"]
    assert calendar.state == "succeeded" and calendar.attempts == 1
    assert result.calendar_link == next(iter(world.calendar.events.values()))["htmlLink"]
    assert result.sent is True


def test_running_operation_of_a_live_worker_is_not_taken_over():
    world = World()
    approval = world.approve()
    world.calendar.crash_after_insert = True
    with pytest.raises(RuntimeError):
        publish(world, approval)

    with pytest.raises(WorkflowError, match="operation_in_progress"):
        publish(world, approval)
    assert [call for call, _ in world.calendar.calls] == ["insert"]


def test_draft_created_before_a_timeout_is_adopted_not_duplicated():
    world = World()
    approval = world.approve()
    world.gmail.fail_after_create = 504
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)

    result = publish(world, approval)

    assert world.gmail.drafts_created == 1
    assert operations(world)["gmail_draft"].attempts == 1
    assert result.sent is True and len(world.gmail.sent) == 1


def test_unprovable_gmail_state_needs_review_and_sends_nothing():
    world = World()
    approval = world.approve()
    world.gmail.fail_send_before = 504
    with pytest.raises(WorkflowError, match="provider_failed"):
        publish(world, approval)
    world.gmail.user_deletes_drafts()  # draft gone, no sent copy: send cannot be proven either way

    with pytest.raises(WorkflowError, match="needs_review"):
        publish(world, approval)
    assert world.gmail.sent == []
    assert operations(world)["gmail_send"].state == "failed"
