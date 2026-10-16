import asyncio
from types import SimpleNamespace

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows import go_work
from hackathon_backend.workflows.asset_queue import ASSET_KINDS, GoAssetQueue, load_go_content
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind


def run(coro):
    return asyncio.run(coro)


def request(revision=1, owner=OWNER):
    return SimpleNamespace(
        owner_id=owner,
        event_id="event-1",
        event_revision=revision,
        kinds=tuple(k.value for k in ASSET_KINDS),
        idempotency_key=f"{owner}:event-1:r{revision}:go:asset-prose-v1",
    )


def test_enqueue_is_idempotent_and_independent_of_invitation_prep():
    world = World()
    queue = GoAssetQueue(world.store)
    invitation_work = run(go_work.enqueue_preparation(world.store, OWNER, "event-1"))
    first = run(queue.enqueue(request()))
    again = run(queue.enqueue(request()))
    assert first.state == "awaiting_go" and again.operation_id == first.operation_id
    open_work = run(go_work.list_open_work(world.store, OWNER))
    assert {w.id for w in open_work} == {invitation_work.id, first.operation_id}


def test_enqueue_rejects_stale_foreign_or_unknown_kinds():
    world = World()
    queue = GoAssetQueue(world.store)
    with pytest.raises(WorkflowError, match="revision_conflict"):
        run(queue.enqueue(request(revision=2)))
    with pytest.raises(WorkflowError, match="forbidden"):
        run(queue.enqueue(request(owner="owner-b")))
    bad = request()
    bad.kinds = ("invitation",)
    with pytest.raises(WorkflowError, match="unsupported"):
        run(queue.enqueue(bad))


def test_new_revision_supersedes_asset_batch_and_go_content_loads_as_trusted():
    world = World()
    queue = GoAssetQueue(world.store)
    receipt = run(queue.enqueue(request()))
    for kind in ASSET_KINDS:
        run(
            go_work.save_go_content(
                world.store,
                OWNER,
                event_id="event-1",
                expected_revision=1,
                kind=kind,
                body=f"{kind.value} text",
                work_id=receipt.operation_id,
            )
        )
    assert world.store.work[receipt.operation_id].state == "succeeded"
    assert run(queue.enqueue(request())).state == "queued"  # deduped; prose already exists
    loaded = run(load_go_content(world.store, OWNER, "event-1", 1, ContentKind.FLYER_COPY))
    assert loaded["producer"] == "superhuman_go" and loaded["reviewed_by_organizer"] is False
    assert (
        run(load_go_content(world.store, "owner-b", "event-1", 1, ContentKind.FLYER_COPY)) is None
    )

    world.revise(location="Park B")
    second = run(queue.enqueue(request(revision=2)))
    assert second.operation_id != receipt.operation_id
