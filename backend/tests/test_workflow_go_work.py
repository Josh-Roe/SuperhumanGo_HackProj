import asyncio

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows import go_work
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind, Producer


def run(coro):
    return asyncio.run(coro)


def save(world, kind, revision=1, **kw):
    kw.setdefault("subject", "Subject")
    return run(
        go_work.save_go_content(
            world.store,
            OWNER,
            event_id="event-1",
            expected_revision=revision,
            kind=kind,
            body=f"{kind.value} text",
            **kw,
        )
    )


def test_preparation_lifecycle_awaiting_running_succeeded():
    world = World()
    item = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    assert item.state == "awaiting_go"
    assert item.payload["kinds"] == ["description", "summary", "invitation"]
    claimed = run(go_work.claim_work(world.store, OWNER, item.id))
    assert claimed.state == "running"
    for kind in (ContentKind.DESCRIPTION, ContentKind.SUMMARY):
        saved = save(world, kind, work_id=item.id)
        assert saved.producer == Producer.SUPERHUMAN_GO and saved.state == "needs_review"
    assert world.store.work[item.id].state == "running"
    save(world, ContentKind.INVITATION, work_id=item.id)
    assert world.store.work[item.id].state == "succeeded"


def test_new_revision_supersedes_prep_and_rejects_stale_content():
    world = World()
    old = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    world.revise(location="Moved")
    with pytest.raises(WorkflowError, match="revision_conflict"):
        save(world, ContentKind.DESCRIPTION, revision=1)
    assert run(go_work.list_open_work(world.store, OWNER)) == []
    assert world.store.work[old.id].state == "superseded"
    new = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    assert new.event_revision == 2


def test_reenqueue_keeps_same_revision_job_and_supersedes_older_revision():
    world = World()
    first = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    again = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    assert again.id == first.id and world.store.work[first.id].state == "awaiting_go"
    world.revise(location="Moved")
    newer = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    assert world.store.work[first.id].state == "superseded"
    assert newer.id != first.id and newer.event_revision == 2


def test_change_notice_requested_after_invitation_was_sent():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve().id))
    world.revise(location="Moved")
    item = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    assert "change_notice" in item.payload["kinds"]


def test_email_content_requires_subject_and_owner_scope():
    world = World()
    with pytest.raises(WorkflowError, match="subject"):
        save(world, ContentKind.INVITATION, subject=None)
    with pytest.raises(WorkflowError, match="forbidden"):
        run(go_work.enqueue_preparation(world.store, "owner-b", "event-1"))
    item = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    with pytest.raises(WorkflowError, match="forbidden"):
        run(go_work.claim_work(world.store, "owner-b", item.id))
