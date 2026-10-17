"""RSVP tracking from Calendar response statuses and Go-classified, sender-matched email replies.

Replies are matched to an invitee by sender address *and* to the event by its sent Gmail thread.
Go classifies the reply text; the backend downgrades anything forwarded, conditional, low
confidence, or unsupported by a quote from the sender's own (unquoted) text to `needs_review`.
"""

import re
from datetime import UTC, datetime

from pydantic import BaseModel

from hackathon_backend.providers.google.mime import (
    is_forwarded,
    message_header,
    message_text,
    sender_email,
    strip_quoted,
)
from hackathon_backend.workflows.go_work import WorkflowError, require_event
from hackathon_backend.workflows.models import (
    EventSnapshot,
    InboundReply,
    RSVPObservation,
    RSVPStatus,
    WorkItem,
    WorkKind,
    utcnow,
)
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
CLASSIFIABLE = {RSVPStatus.ATTENDING, RSVPStatus.MAYBE, RSVPStatus.NOT_ATTENDING}
MIN_CONFIDENCE = 0.75


class InviteeRSVP(BaseModel):
    invitee_id: str
    email: str
    status: RSVPStatus
    source: str | None
    observed_at: str | None
    conflict: bool  # Calendar and email disagree; organizer should look
    private_note: str | None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


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

    async def ingest_replies(self, owner_id: str, event_id: str) -> list[InboundReply]:
        """Queue new invitee replies in the event's sent threads for Go classification."""
        event = await require_event(self.store, owner_id, event_id)
        binding = await self.store.get_gmail_binding(owner_id, event_id)
        if binding is None:
            return []
        threads = {h["thread_id"] for h in binding.sent_history if h.get("thread_id")}
        organizer = (await self.tokens.account_email(owner_id)).lower()
        by_email = {invitee.email: invitee for invitee in event.invitees}
        queued = []
        for thread_id in sorted(threads):
            for message in await self.gmail.list_thread_messages(owner_id, thread_id):
                labels = set(message.get("labelIds", []))
                sender = sender_email(message_header(message, "From") or "")
                if labels & {"SENT", "DRAFT"} or sender == organizer:
                    continue
                if await self.store.get_reply(owner_id, message["id"]) is not None:
                    continue  # already ingested
                reply = self._reply(owner_id, event, thread_id, message, sender, by_email)
                await self.store.put_reply(reply)
                if reply.state == "awaiting_go":
                    await self.store.put_work(
                        WorkItem(
                            owner_id=owner_id,
                            event_id=event_id,
                            event_revision=event.revision,
                            kind=WorkKind.CLASSIFY_REPLY,
                            payload={"reply_id": reply.id},
                        )
                    )
                    queued.append(reply)
        return queued

    def _reply(self, owner_id, event: EventSnapshot, thread_id, message, sender, by_email):
        subject = message_header(message, "Subject") or ""
        full_text = message_text(message)
        invitee = by_email.get(sender)
        internal = message.get("internalDate")
        received = utcnow()
        if internal:
            received = datetime.fromtimestamp(int(internal) / 1000, UTC)
        return InboundReply(
            id=message["id"],
            owner_id=owner_id,
            event_id=event.id,
            thread_id=thread_id,
            invitee_id=invitee.id if invitee else None,
            from_email=sender,
            subject=subject,
            body_text=strip_quoted(full_text),
            forwarded=is_forwarded(subject, full_text),
            received_at=received,
            # Unknown senders never change anyone's RSVP; they stay out of Go's queue.
            state="awaiting_go" if invitee else "unmatched",
        )

    async def record_classification(
        self,
        owner_id: str,
        *,
        reply_id: str,
        status: RSVPStatus,
        confidence: float,
        evidence: str,
        conditional: bool = False,
        private_note: str | None = None,
    ) -> RSVPObservation:
        reply = await self.store.get_reply(owner_id, reply_id)
        if reply is None or reply.invitee_id is None:
            raise WorkflowError("forbidden", "matched reply not found for this organizer")
        if reply.state != "awaiting_go":
            raise WorkflowError("revision_conflict", f"reply already {reply.state}")
        event = await require_event(self.store, owner_id, reply.event_id)
        grounded = bool(evidence.strip()) and _squash(evidence) in _squash(reply.body_text)
        final = status
        if (
            status not in CLASSIFIABLE
            or reply.forwarded
            or conditional
            or confidence < MIN_CONFIDENCE
            or not grounded
        ):
            final = RSVPStatus.NEEDS_REVIEW
        observation = RSVPObservation(
            event_id=reply.event_id,
            invitee_id=reply.invitee_id,
            status=final,
            source="email",
            source_id=reply.id,
            observed_at=reply.received_at,
            event_revision=event.revision,
            classified_by="superhuman_go",
            evidence=evidence[:500] if grounded else None,
            private_note=private_note,
        )
        await self.store.add_rsvp(owner_id, observation)
        state = "needs_review" if final == RSVPStatus.NEEDS_REVIEW else "classified"
        await self.store.put_reply(reply.model_copy(update={"state": state}))
        for item in await self.store.list_work(owner_id, {"awaiting_go", "running"}):
            if item.kind == WorkKind.CLASSIFY_REPLY and item.payload.get("reply_id") == reply_id:
                await self.store.put_work(item.model_copy(update={"state": "succeeded"}))
        return observation

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
