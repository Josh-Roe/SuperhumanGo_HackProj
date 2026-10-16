"""Google Calendar v3 adapter: idempotent client-ID inserts and etag-guarded patches."""

import base64
import hashlib
from typing import Any

import httpx

from hackathon_backend.providers.google._http import GoogleREST, segment
from hackathon_backend.workflows.models import EventSnapshot
from hackathon_backend.workflows.ports import GoogleTokenSource

CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"
SEND_UPDATES = {"all", "externalOnly", "none"}


def deterministic_event_id(namespace: str, event_id: str) -> str:
    """Stable Calendar client ID (base32hex: a-v, 0-9) so publish retries hit 409, not dupes."""
    digest = hashlib.sha256(f"{namespace}:{event_id}".encode()).digest()
    return base64.b32hexencode(digest).decode("ascii").rstrip("=").lower()


def calendar_body(event: EventSnapshot, description: str) -> dict[str, Any]:
    return {
        "summary": event.title,
        "description": description,
        "location": event.location,
        "start": {"dateTime": event.starts_at.isoformat(), "timeZone": event.timezone},
        "end": {"dateTime": event.ends_at.isoformat(), "timeZone": event.timezone},
        "attendees": [{"email": invitee.email} for invitee in event.invitees],
        "guestsCanSeeOtherGuests": False,
        "extendedProperties": {
            "private": {"app_event_id": event.id, "app_revision": str(event.revision)}
        },
    }


def _send_updates(value: str) -> str:
    if value not in SEND_UPDATES:
        raise ValueError("sendUpdates must be one of: all, externalOnly, none")
    return value


class GoogleCalendarAPI:
    def __init__(
        self, tokens: GoogleTokenSource, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._rest = GoogleREST("Google Calendar", CALENDAR_BASE_URL, tokens, transport)

    async def insert_event(
        self, owner_id: str, calendar_id: str, body: dict[str, Any], send_updates: str
    ) -> dict[str, Any]:
        """Raises ProviderError(409) when body["id"] already exists."""
        result = await self._rest.request(
            owner_id,
            "POST",
            f"/calendars/{segment(calendar_id)}/events",
            params={"sendUpdates": _send_updates(send_updates)},
            json=body,
        )
        assert result is not None
        return result

    async def get_event(self, owner_id: str, calendar_id: str, event_id: str) -> dict[str, Any]:
        result = await self._rest.request(
            owner_id, "GET", f"/calendars/{segment(calendar_id)}/events/{segment(event_id)}"
        )
        assert result is not None
        return result

    async def patch_event(
        self,
        owner_id: str,
        calendar_id: str,
        event_id: str,
        body: dict[str, Any],
        send_updates: str,
        etag: str | None,
    ) -> dict[str, Any]:
        """Raises ProviderError(412) when etag no longer matches the remote event."""
        result = await self._rest.request(
            owner_id,
            "PATCH",
            f"/calendars/{segment(calendar_id)}/events/{segment(event_id)}",
            params={"sendUpdates": _send_updates(send_updates)},
            json=body,
            headers={"If-Match": etag} if etag else None,
        )
        assert result is not None
        return result
