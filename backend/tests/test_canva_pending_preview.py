"""A9: asset status exposes the pending Canva operation preview the organizer can approve.

Canva is faked at its session boundary; the coordinator and approval route logic are real.
"""

from datetime import timedelta

from test_assets_preparation import EVENT, OWNER, put_prose, workflow_event
from test_workflow_asset_wiring import LATER, FakeCanva, build, run

from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS


def test_status_lists_approvable_preview_until_approved_or_event_changes():
    async def flow():
        store, _, coord, clock = build(FakeCanva())
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        await coord.start_flyer(OWNER, EVENT, 1)
        clock.now = LATER
        await coord.poll_flyer(OWNER, EVENT, 1)
        before = (await coord.status(OWNER, EVENT))["flyer_pending_approval"]
        preview = (await coord.preview_flyer(OWNER, EVENT, 1))["preview"]
        pending = (await coord.status(OWNER, EVENT))["flyer_pending_approval"]

        clock.now += timedelta(seconds=1)
        body = pending["approve"]["body"]
        await coord.approve_flyer(OWNER, EVENT, body["expected_revision"], body["preview_digest"])
        approved = await coord.status(OWNER, EVENT)

        await coord.preview_flyer(OWNER, EVENT, 1)
        store.put_event(workflow_event(revision=2))
        changed = await coord.status(OWNER, EVENT)
        return before, preview, pending, approved, changed

    before, preview, pending, approved, changed = run(flow())
    assert before is None
    assert pending == {
        "operation_id": "test-job",
        "design_id": "D-synthetic",
        "event_revision": 1,
        "digest": preview["digest"],
        "thumbnail_urls": ["https://media.canva.com/synthetic-preview"],
        "approve": {
            "method": "POST",
            "path": f"/api/events/{EVENT}/assets/flyer/approve",
            "body": {"expected_revision": 1, "preview_digest": preview["digest"]},
        },
    }
    assert approved["flyer"]["stage"] == "approved" and approved["flyer_pending_approval"] is None
    assert changed["flyer_stale"] is True and changed["flyer_pending_approval"] is None
