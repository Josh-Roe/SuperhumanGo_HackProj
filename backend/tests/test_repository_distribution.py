import asyncio

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.repositories.distribution import PersistentDistributor, PreflightAttachments
from hackathon_backend.workflows.go_work import WorkflowError


def persistent(world, source):
    return PersistentDistributor(world.store, world.calendar, world.gmail, world.tokens, source)


@pytest.mark.parametrize("code", ["needs_review", "revision_conflict", "provider_failed"])
def test_asset_preflight_failure_never_invites_calendar_guests(code):
    class MissingAsset:
        async def current_attachments(self, owner_id, event):
            raise WorkflowError(code, "Cannot deliver the reviewed current flyer")

    world = World()
    approval = world.approve()
    distributor = persistent(world, MissingAsset())
    with pytest.raises(WorkflowError) as caught:
        asyncio.run(distributor.execute(OWNER, "event-1", approval.id))
    assert caught.value.code == code
    assert world.calendar.calls == []
    assert world.gmail.sent == [] and world.gmail.drafts == {}
    assert asyncio.run(world.store.list_operations(OWNER, "event-1")) == []
    plan = asyncio.run(distributor.preview(OWNER, "event-1"))
    assert any(code in blocker for blocker in plan.blockers)


def test_verified_bytes_are_pinned_for_mime_and_retry_reuses_provider_receipts():
    class Files:
        calls = 0

        async def current_attachments(self, owner_id, event):
            self.calls += 1
            return [("reviewed.html", "text/html", b"Immutable Go document")]

    world, source = World(), Files()
    distributor = persistent(world, source)
    approval = world.approve()
    first = asyncio.run(distributor.execute(OWNER, "event-1", approval.id))
    second = asyncio.run(distributor.execute(OWNER, "event-1", approval.id))
    assert first.sent and second.sent
    assert source.calls == 2  # once per execution, no second Storage read after Calendar
    assert len(world.gmail.sent) == 1
    assert [call[0] for call in world.calendar.calls] == ["insert"]
    attachments = list(world.gmail.sent[0]["parsed"].iter_attachments())
    assert attachments[0].get_payload(decode=True) == b"Immutable Go document"
    assert distributor.preflight.prepared.get() is None


def test_concurrent_attachment_contexts_cannot_mix_organizers_or_revisions():
    source = PreflightAttachments(None)

    async def call(owner):
        event = type("Event", (), {"id": "event", "revision": 2})()
        files = [(owner, "text/html", owner.encode())]
        token = source.prepared.set((owner, "event", 2, tuple(files)))
        try:
            await asyncio.sleep(0)
            assert await source.current_attachments(owner, event) == files
            with pytest.raises(WorkflowError):
                await source.current_attachments("other-" + owner, event)
        finally:
            source.prepared.reset(token)

    async def concurrent():
        await asyncio.gather(call("one"), call("two"))

    asyncio.run(concurrent())
    assert source.prepared.get() is None


def test_member3_asset_policy_registration_keeps_preflight_bytes_through_mime():
    class Files:
        calls = 0

        async def current_attachments(self, owner_id, event):
            self.calls += 1
            return [("reviewed.html", "text/html", b"Preflight snapshot")]

    class Replacement:
        async def current_attachments(self, owner_id, event):
            raise AssertionError("Must use the pinned preflight snapshot")

    class Policy:
        async def requires_attachments(self, owner_id, event):
            return True

    world, source = World(), Files()
    distributor = persistent(world, source)
    # These are the exact attributes Member 3's register_assets composes.
    distributor.attachments = Replacement()
    distributor.attachment_policy = Policy()
    result = asyncio.run(distributor.execute(OWNER, "event-1", world.approve().id))
    assert result.sent and source.calls == 1
    attachment = next(world.gmail.sent[0]["parsed"].iter_attachments())
    assert attachment.get_payload(decode=True) == b"Preflight snapshot"
