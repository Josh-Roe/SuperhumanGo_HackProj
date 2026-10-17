"""RSVP tracking from Google Calendar attendee response statuses.

Email-reply RSVPs (Go classifying guests' Gmail replies) are future work; see docs/SUPERHUMAN.md.
"""

from pydantic import BaseModel

from hackathon_backend.workflows.go_work import require_event
from hackathon_backend.workflows.models import RSVPObservation, RSVPStatus
from hackathon_backend.workflows.ports import (
    CalendarAPI,
    GmailAPI,
    GoogleTokenSource,
    WorkflowStore,
)

CALENDAR_STATUS = {
    "accepted": RSVPStatus.ATTENDING,
    "tentative": RSVPStatus.MAYBE,
    "declined": RSVPStatus.NOT_ATTENDING,
    "needsAction": RSVPStatus.NO_RESPONSE,
}


class InviteeRSVP(BaseModel):
    invitee_id: str
    email: str
    status: RSVPStatus
    source: str | None
    observed_at: str | None
    conflict: bool  # Calendar and email disagree; organizer should look
    private_note: str | None


class RSVPTracker:
    def __init__(
        self,
        store: WorkflowStore,
        calendar: CalendarAPI,
        gmail: GmailAPI,
        tokens: GoogleTokenSource,
    ) -> None:
        self.store = store
        self.calendar = calendar
        self.gmail = gmail
        self.tokens = tokens

    async def sync_calendar(self, owner_id: str, event_id: str) -> int:
        """Record changed attendee response statuses. Returns the number of new observations."""
        event = await require_event(self.store, owner_id, event_id)
        binding = await self.store.get_calendar_binding(owner_id, event_id)
        if binding is None:
            return 0
        remote = await self.calendar.get_event(
            owner_id, binding.calendar_id, binding.remote_event_id
        )
        by_email = {invitee.email: invitee for invitee in event.invitees}
        history = await self.store.list_rsvps(owner_id, event_id)
        added = 0
        for attendee in remote.get("attendees", []):
            invitee = by_email.get(str(attendee.get("email", "")).strip().lower())
            status = CALENDAR_STATUS.get(attendee.get("responseStatus", ""))
            if invitee is None or status is None:
                continue
            previous = [r for r in history if r.invitee_id == invitee.id and r.source == "calendar"]
            last = max(previous, key=lambda r: r.observed_at, default=None)
            if last is not None and last.status == status:
                continue
            if last is None and status == RSVPStatus.NO_RESPONSE:
                continue
            await self.store.add_rsvp(
                owner_id,
                RSVPObservation(
                    event_id=event_id,
                    invitee_id=invitee.id,
                    status=status,
                    source="calendar",
                    source_id=binding.remote_event_id,
                    event_revision=event.revision,
                ),
            )
            added += 1
        return added

    async def summary(self, owner_id: str, event_id: str) -> list[InviteeRSVP]:
        event = await require_event(self.store, owner_id, event_id)
        history = await self.store.list_rsvps(owner_id, event_id)
        rows = []
        for invitee in event.invitees:
            mine = sorted(
                (r for r in history if r.invitee_id == invitee.id), key=lambda r: r.observed_at
            )
            latest = mine[-1] if mine else None
            settled = {
                source: next((r.status for r in reversed(mine) if r.source == source), None)
                for source in ("calendar", "email")
            }
            conflict = (
                None not in settled.values()
                and RSVPStatus.NEEDS_REVIEW not in settled.values()
                and RSVPStatus.NO_RESPONSE not in settled.values()
                and settled["calendar"] != settled["email"]
            )
            rows.append(
                InviteeRSVP(
                    invitee_id=invitee.id,
                    email=invitee.email,
                    status=latest.status if latest else RSVPStatus.NO_RESPONSE,
                    source=latest.source if latest else None,
                    observed_at=latest.observed_at.isoformat() if latest else None,
                    conflict=conflict,
                    private_note=next(
                        (r.private_note for r in reversed(mine) if r.private_note), None
                    ),
                )
            )
        return rows
