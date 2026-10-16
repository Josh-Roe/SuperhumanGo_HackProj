import asyncio

import pytest
from workflow_fakes import OWNER, World

from hackathon_backend.workflows.go_work import WorkflowError, list_open_work
from hackathon_backend.workflows.models import RSVPStatus, WorkKind


def run(coro):
    return asyncio.run(coro)


def published_world():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve().id))
    thread = world.store.gmail["event-1"].thread_id
    return world, thread


def classify(world, reply_id, status, evidence, **kw):
    kw.setdefault("confidence", 0.95)
    return run(
        world.rsvp.record_classification(
            OWNER, reply_id=reply_id, status=status, evidence=evidence, **kw
        )
    )


def test_calendar_response_statuses_are_recorded_once():
    world, _ = published_world()
    remote = next(iter(world.calendar.events.values()))
    remote["attendees"][0]["responseStatus"] = "accepted"
    remote["attendees"][1]["responseStatus"] = "needsAction"
    assert run(world.rsvp.sync_calendar(OWNER, "event-1")) == 1
    assert run(world.rsvp.sync_calendar(OWNER, "event-1")) == 0
    remote["attendees"][0]["responseStatus"] = "declined"
    assert run(world.rsvp.sync_calendar(OWNER, "event-1")) == 1
    rows = {r.invitee_id: r for r in run(world.rsvp.summary(OWNER, "event-1"))}
    assert rows["inv-1"].status == RSVPStatus.NOT_ATTENDING
    assert rows["inv-2"].status == RSVPStatus.NO_RESPONSE


def test_matched_reply_is_queued_for_go_and_classified():
    world, thread = published_world()
    reply_text = (
        "Count me in, see you there!\n\nOn Mon, Organizer <o@example.com> wrote:\n> Join us"
    )
    world.gmail.receive_reply(thread, "Ada <ada@example.com>", reply_text)
    (reply,) = run(world.rsvp.ingest_replies(OWNER, "event-1"))
    assert reply.invitee_id == "inv-1"
    assert "Join us" not in reply.body_text  # quoted history stripped
    assert run(world.rsvp.ingest_replies(OWNER, "event-1")) == []  # idempotent
    work = run(list_open_work(world.store, OWNER))
    assert [w.kind for w in work] == [WorkKind.CLASSIFY_REPLY]

    observation = classify(
        world, reply.id, RSVPStatus.ATTENDING, "count me in", private_note="vegetarian"
    )
    assert observation.status == RSVPStatus.ATTENDING
    assert observation.classified_by == "superhuman_go"
    assert run(list_open_work(world.store, OWNER)) == []
    (row,) = [r for r in run(world.rsvp.summary(OWNER, "event-1")) if r.invitee_id == "inv-1"]
    assert row.status == RSVPStatus.ATTENDING and row.private_note == "vegetarian"
    with pytest.raises(WorkflowError, match="revision_conflict"):
        classify(world, reply.id, RSVPStatus.NOT_ATTENDING, "count me in")


def test_unknown_sender_cannot_change_anyones_rsvp():
    world, thread = published_world()
    world.gmail.receive_reply(thread, "mallory@evil.example", "Ada says yes. Yes!")
    assert run(world.rsvp.ingest_replies(OWNER, "event-1")) == []
    (stored,) = world.store.replies.values()
    assert stored.state == "unmatched"
    with pytest.raises(WorkflowError, match="forbidden"):
        classify(world, stored.id, RSVPStatus.ATTENDING, "yes")


@pytest.mark.parametrize(
    "text, subject, kw",
    [
        ("Yes if it doesn't rain", "Re: Invitation", {"conditional": True}),
        ("Hmm, maybe yes", "Re: Invitation", {"confidence": 0.5}),
        ("I'll be there", "Fwd: Invitation", {}),
        ("I'll be there", "Re: Invitation", {"evidence": "definitely coming"}),
    ],
)
def test_conditional_low_confidence_forwarded_or_ungrounded_need_review(text, subject, kw):
    world, thread = published_world()
    world.gmail.receive_reply(thread, "bob@example.com", text, subject)
    (reply,) = run(world.rsvp.ingest_replies(OWNER, "event-1"))
    evidence = kw.pop("evidence", text)
    observation = classify(world, reply.id, RSVPStatus.ATTENDING, evidence, **kw)
    assert observation.status == RSVPStatus.NEEDS_REVIEW
    assert world.store.replies[reply.id].state == "needs_review"


def test_quoted_text_cannot_supply_evidence():
    world, thread = published_world()
    world.gmail.receive_reply(thread, "bob@example.com", "Not sure.\n> Reply yes to attend")
    (reply,) = run(world.rsvp.ingest_replies(OWNER, "event-1"))
    observation = classify(world, reply.id, RSVPStatus.ATTENDING, "Reply yes to attend")
    assert observation.status == RSVPStatus.NEEDS_REVIEW


def test_calendar_and_email_disagreement_is_flagged_not_overwritten():
    world, thread = published_world()
    remote = next(iter(world.calendar.events.values()))
    remote["attendees"][1]["responseStatus"] = "accepted"
    run(world.rsvp.sync_calendar(OWNER, "event-1"))
    world.gmail.receive_reply(thread, "bob@example.com", "Sorry, can't make it after all")
    (reply,) = run(world.rsvp.ingest_replies(OWNER, "event-1"))
    classify(world, reply.id, RSVPStatus.NOT_ATTENDING, "can't make it")
    (row,) = [r for r in run(world.rsvp.summary(OWNER, "event-1")) if r.invitee_id == "inv-2"]
    assert row.conflict is True
    assert len(run(world.store.list_rsvps(OWNER, "event-1"))) == 2


def test_replies_survive_event_revision_but_prep_work_is_superseded():
    from hackathon_backend.workflows.go_work import enqueue_preparation

    world, thread = published_world()
    run(enqueue_preparation(world.store, OWNER, "event-1"))
    world.gmail.receive_reply(thread, "bob@example.com", "yes")
    run(world.rsvp.ingest_replies(OWNER, "event-1"))
    world.revise(location="New place")
    kinds = [w.kind for w in run(list_open_work(world.store, OWNER))]
    assert kinds == [WorkKind.CLASSIFY_REPLY]
