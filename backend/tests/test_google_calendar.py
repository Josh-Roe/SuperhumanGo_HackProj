import asyncio
import json
import re
from datetime import UTC, datetime

import httpx
import pytest

from hackathon_backend.providers.google.calendar import (
    GoogleCalendarAPI,
    calendar_body,
    deterministic_event_id,
)
from hackathon_backend.providers.google.oauth import StaticTokenSource
from hackathon_backend.workflows.models import EventSnapshot, Invitee
from hackathon_backend.workflows.ports import IntegrationNotConnected, ProviderError

TOKENS = StaticTokenSource({"owner-1": "ya29.secret-token"}, {"owner-1": "org@example.com"})


def api(handler):
    return GoogleCalendarAPI(TOKENS, transport=httpx.MockTransport(handler))


def event() -> EventSnapshot:
    return EventSnapshot(
        id="evt-1",
        owner_id="owner-1",
        revision=3,
        title="Picnic",
        location="Park",
        starts_at=datetime(2026, 11, 1, 18, tzinfo=UTC),
        ends_at=datetime(2026, 11, 1, 20, tzinfo=UTC),
        timezone="America/New_York",
        organizer_contact="org@example.com",
        invitees=[Invitee(id="i1", email="A@Example.com"), Invitee(id="i2", email="b@x.org")],
    )


def test_deterministic_event_id_is_valid_and_stable():
    first = deterministic_event_id("app", "evt-1")
    assert first == deterministic_event_id("app", "evt-1")
    assert first != deterministic_event_id("app", "evt-2")
    assert first != deterministic_event_id("other", "evt-1")
    assert re.fullmatch(r"[a-v0-9]{5,1024}", first)


def test_calendar_body_hides_guest_list_and_records_revision():
    body = calendar_body(event(), "Bring snacks")
    assert body["attendees"] == [{"email": "a@example.com"}, {"email": "b@x.org"}]
    assert body["guestsCanSeeOtherGuests"] is False
    assert body["extendedProperties"]["private"] == {"app_event_id": "evt-1", "app_revision": "3"}
    assert body["start"] == {
        "dateTime": "2026-11-01T18:00:00+00:00",
        "timeZone": "America/New_York",
    }
    assert body["description"] == "Bring snacks"


def test_insert_event_request_shape():
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert (
            request.url.raw_path
            == b"/calendar/v3/calendars/team%40group.calendar.google.com/events?sendUpdates=all"
        )
        assert request.headers["authorization"] == "Bearer ya29.secret-token"
        assert json.loads(request.content)["id"] == "abc123"
        return httpx.Response(200, json={"id": "abc123", "etag": '"1"'})

    result = asyncio.run(
        api(handler).insert_event(
            "owner-1", "team@group.calendar.google.com", {"id": "abc123"}, "all"
        )
    )
    assert result["etag"] == '"1"'


def test_insert_duplicate_maps_to_409_without_body_leak():
    def handler(request):
        return httpx.Response(
            409,
            json={"error": {"errors": [{"reason": "duplicate"}], "message": "ya29.secret-token"}},
        )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(api(handler).insert_event("owner-1", "primary", {"id": "abc"}, "none"))
    assert caught.value.status == 409
    assert "duplicate" in str(caught.value)
    assert "secret" not in str(caught.value)


def test_get_and_patch_with_etag():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "e/1", "etag": '"7"'})
        if request.headers.get("if-match") == '"7"':
            return httpx.Response(200, json={"id": "e/1", "etag": '"8"'})
        return httpx.Response(412, json={"error": {"errors": [{"reason": "conditionNotMet"}]}})

    calendar = api(handler)

    async def run():
        current = await calendar.get_event("owner-1", "primary", "e/1")
        patched = await calendar.patch_event(
            "owner-1", "primary", "e/1", {"location": "Hall"}, "all", current["etag"]
        )
        assert patched["etag"] == '"8"'
        with pytest.raises(ProviderError) as caught:
            await calendar.patch_event("owner-1", "primary", "e/1", {}, "all", '"stale"')
        assert caught.value.status == 412

    asyncio.run(run())
    assert seen[0].url.raw_path == b"/calendar/v3/calendars/primary/events/e%2F1"
    assert seen[1].method == "PATCH"
    assert seen[1].url.params["sendUpdates"] == "all"


def test_patch_without_etag_sends_no_if_match():
    def handler(request):
        assert "if-match" not in request.headers
        return httpx.Response(200, json={"id": "x"})

    asyncio.run(api(handler).patch_event("owner-1", "primary", "x", {}, "none", None))


def test_invalid_send_updates_and_missing_connection():
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(ValueError):
        asyncio.run(api(handler).insert_event("owner-1", "primary", {}, "everyone"))
    with pytest.raises(IntegrationNotConnected):
        asyncio.run(api(handler).get_event("owner-2", "primary", "x"))


def test_timeout_maps_to_provider_error():
    def handler(request):
        raise httpx.ReadTimeout("ya29.secret-token", request=request)

    with pytest.raises(ProviderError) as caught:
        asyncio.run(api(handler).get_event("owner-1", "primary", "x"))
    assert caught.value.status == 504
    assert "secret" not in str(caught.value)
