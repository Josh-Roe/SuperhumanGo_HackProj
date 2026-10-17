"""Required flyer must be deliverable before any Calendar/Gmail side effect (fakes only)."""

import asyncio

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows.asset_wiring import (
    FlyerRequiredPolicy,
    FlyerState,
    MemoryFlyerStateStore,
)
from hackathon_backend.workflows.go_work import WorkflowError

PNG = b"\x89PNG\r\n\x1a\nfixture"


def run(coro):
    return asyncio.run(coro)


class Policy:
    def __init__(self, required=True):
        self.required = required

    async def requires_attachments(self, owner_id, event):
        return self.required


class Source:
    def __init__(self, files=None, error=None):
        self.files = files or []
        self.error = error
        self.calls = 0

    async def current_attachments(self, owner_id, event):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.files)


def world_with(source, policy):
    world = World()
    world.distributor.attachments = source
    world.distributor.attachment_policy = policy
    return world


def no_side_effects(world):
    assert world.calendar.events == {} and world.calendar.calls == []
    assert world.gmail.drafts == {} and world.gmail.sent == []


class CodedError(RuntimeError):
    def __init__(self, code):
        super().__init__(f"{code}: storage said no")
        self.code = code


@pytest.mark.parametrize(
    "source,code",
    [
        (Source(), "needs_review"),
        (Source(error=WorkflowError("needs_review", "flyer unreviewed")), "needs_review"),
        (Source(error=CodedError("revision_conflict")), "revision_conflict"),
        (Source(error=RuntimeError("signed url leaked https://x")), "provider_failed"),
        (None, "integration_not_connected"),
    ],
)
def test_missing_required_flyer_blocks_preview_and_execute_without_side_effects(source, code):
    world = world_with(source, Policy())
    plan = run(world.distributor.preview(OWNER, "event-1"))
    assert any(blocker.startswith(code) for blocker in plan.blockers)
    approval = world.approve()
    with pytest.raises(WorkflowError) as raised:
        run(world.distributor.execute(OWNER, "event-1", approval.id))
    assert raised.value.code == code
    assert "https://x" not in str(raised.value)
    no_side_effects(world)
    # Refused before any operation was claimed, so nothing is left running.
    assert all(op.state != "running" for op in run(world.store.list_operations(OWNER, "event-1")))


def test_required_flyer_present_publishes_with_attachment():
    source = Source([("event-1-r1-flyer.png", "image/png", PNG)])
    world = world_with(source, Policy())
    approval = world.approve()
    assert run(world.distributor.preview(OWNER, "event-1")).blockers == []
    result = run(world.distributor.execute(OWNER, "event-1", approval.id))
    assert result.sent is True and len(world.calendar.events) == 1
    (attachment,) = world.gmail.sent[0]["parsed"].iter_attachments()
    assert attachment.get_payload(decode=True) == PNG
    assert attachment.get_filename() == "event-1-r1-flyer.png"


def test_flyer_added_after_refusal_then_publish_succeeds_once():
    source = Source()
    world = world_with(source, Policy())
    approval = world.approve()
    with pytest.raises(WorkflowError, match="needs_review"):
        run(world.distributor.execute(OWNER, "event-1", approval.id))
    source.files = [("flyer.png", "image/png", PNG)]
    result = run(world.distributor.execute(OWNER, "event-1", approval.id))
    assert result.sent is True and len(world.gmail.sent) == 1
    assert [call[0] for call in world.calendar.calls] == ["insert"]


def test_not_required_event_never_reads_or_attaches_files():
    source = Source([("flyer.png", "image/png", PNG)])
    world = world_with(source, Policy(required=False))
    approval = world.approve()
    assert run(world.distributor.preview(OWNER, "event-1")).blockers == []
    run(world.distributor.execute(OWNER, "event-1", approval.id))
    assert source.calls == 0
    assert list(world.gmail.sent[0]["parsed"].iter_attachments()) == []


def test_without_policy_original_lenient_behavior_is_unchanged():
    empty = World()
    empty.distributor.attachments = Source()
    approval = empty.approve()
    assert run(empty.distributor.preview(OWNER, "event-1")).blockers == []
    assert run(empty.distributor.execute(OWNER, "event-1", approval.id)).sent is True
    present = World()
    present.distributor.attachments = Source([("flyer.png", "image/png", PNG)])
    run(present.distributor.execute(OWNER, "event-1", present.approve().id))
    assert len(list(present.gmail.sent[0]["parsed"].iter_attachments())) == 1


def test_flyer_policy_requires_started_flyer_until_abandoned():
    flyers = MemoryFlyerStateStore()
    policy = FlyerRequiredPolicy(flyers)
    world = World()
    event = world.store.events["event-1"]
    assert run(policy.requires_attachments(OWNER, event)) is False
    state = FlyerState(event_id="event-1", event_revision=1, stage="pending")
    run(flyers.put(OWNER, state))
    assert run(policy.requires_attachments(OWNER, event)) is True
    assert run(policy.requires_attachments("owner-b", event)) is False
    run(flyers.put(OWNER, state.model_copy(update={"stage": "abandoned"})))
    assert run(policy.requires_attachments(OWNER, event)) is False
