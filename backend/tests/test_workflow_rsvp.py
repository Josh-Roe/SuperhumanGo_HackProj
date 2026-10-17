import asyncio

from workflow_fakes import OWNER, World

from hackathon_backend.workflows.models import RSVPStatus


def run(coro):
    return asyncio.run(coro)


def published_world():
    world = World()
    run(world.distributor.execute(OWNER, "event-1", world.approve().id))
    thread = world.store.gmail["event-1"].thread_id
    return world, thread


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
