from copy import deepcopy

import pytest
from pydantic import ValidationError

from hackathon_backend.domain.models import EventInput, EventUpdate, TaskInput

EVENT = {
    "title": "Community dinner",
    "description": "Organizer supplied details",
    "location": "Room A",
    "starts_at": "2026-11-01T17:00:00-08:00",
    "ends_at": "2026-11-01T19:00:00-08:00",
    "timezone": "America/Los_Angeles",
    "links": ["https://example.org/event"],
    "organizer_contact": "organizer@example.org",
    "invitees": [{"email": "Friend@Example.org", "display_name": "Friend"}],
}


def test_event_normalizes_invitees_and_keeps_explicit_timezone():
    event = EventInput(**EVENT)
    assert event.invitees[0].email == "friend@example.org"
    assert event.starts_at.utcoffset().total_seconds() == -8 * 3600


@pytest.mark.parametrize(
    "change",
    [
        {"title": "   "},
        {"timezone": "Mars/Olympus"},
        {"starts_at": "2026-11-01T17:00:00"},
        {"ends_at": "2026-11-01T16:00:00-08:00"},
        {"links": ["javascript:alert(1)"]},
        {"owner_id": "forged"},
        {"revision": 99},
        {"invitees": [{"email": "bad\r\nBcc:attacker@example.org"}]},
        {"invitees": [{"email": "friend@example.org"}, {"email": "FRIEND@example.org"}]},
    ],
)
def test_event_rejects_unsafe_or_invalid_inputs(change):
    with pytest.raises(ValidationError):
        EventInput(**(deepcopy(EVENT) | change))


def test_edits_require_a_positive_expected_revision():
    with pytest.raises(ValidationError):
        EventUpdate(**EVENT)
    with pytest.raises(ValidationError):
        EventUpdate(**EVENT, expected_revision=0)


@pytest.mark.parametrize(
    "change",
    [
        {"due_at": "2026-11-01T17:00:00"},
        {"owner_id": "forged"},
        {"status": "published"},
        {"event_id": "not-a-uuid"},
    ],
)
def test_task_validation(change):
    with pytest.raises(ValidationError):
        TaskInput(**({"title": "Arrange the room"} | change))
