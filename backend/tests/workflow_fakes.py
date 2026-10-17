"""In-memory Calendar/Gmail fakes that model the provider semantics Member 3's workflows rely on."""

import base64
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.policy import default

from hackathon_backend.providers.google.oauth import StaticTokenSource
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.memory import InMemoryWorkflowStore
from hackathon_backend.workflows.models import (
    Approval,
    ContentKind,
    EventSnapshot,
    GeneratedContent,
    Invitee,
    Producer,
)
from hackathon_backend.workflows.ports import ProviderError
from hackathon_backend.workflows.rsvp import RSVPTracker

OWNER = "owner-a"
ORGANIZER_EMAIL = "organizer@example.com"


class FakeCalendar:
    def __init__(self) -> None:
        self.events: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_next: int | None = None
        self.crash_after_insert = False  # the worker process dies after Google applied the insert

    def _maybe_fail(self):
        if self.fail_next:
            status, self.fail_next = self.fail_next, None
            raise ProviderError(status, f"Calendar returned status {status}")

    async def insert_event(self, owner_id, calendar_id, body, send_updates):
        self.calls.append(("insert", send_updates))
        self._maybe_fail()
        if body["id"] in self.events:
            raise ProviderError(409, "duplicate")
        self.events[body["id"]] = {**body, "etag": '"1"', "htmlLink": f"https://cal/{body['id']}"}
        if self.crash_after_insert:
            self.crash_after_insert = False
            raise RuntimeError("worker process crashed")
        return self.events[body["id"]]

    async def get_event(self, owner_id, calendar_id, event_id):
        if event_id not in self.events:
            raise ProviderError(404, "not found")
        return self.events[event_id]

    async def patch_event(self, owner_id, calendar_id, event_id, body, send_updates, etag):
        self.calls.append(("patch", send_updates))
        self._maybe_fail()
        current = self.events[event_id]
        if etag and etag != current["etag"]:
            raise ProviderError(412, "conditionNotMet")
        version = int(current["etag"].strip('"')) + 1
        attendees = current.get("attendees", [])  # keep response statuses like Google does
        merged = {**current, **body, "etag": f'"{version}"'}
        by_email = {a["email"]: a for a in attendees}
        merged["attendees"] = [by_email.get(a["email"], a) for a in body.get("attendees", [])]
        self.events[event_id] = merged
        return merged


class FakeGmail:
    def __init__(self) -> None:
        self.drafts: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}
        self.threads: dict[str, list[str]] = {}
        self.sent: list[dict] = []
        self.counter = 0
        self.drafts_created = 0
        self.crash_after_send = False
        self.fail_send_before: int | None = None  # request never reached Gmail (status raised)
        self.fail_after_create: int | None = None  # draft created, then the response was lost

    def _id(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter}"

    def _store(self, raw: bytes, thread_id, labels):
        message_id = self._id("m")
        thread_id = thread_id or self._id("t")
        parsed = message_from_bytes(raw, policy=default)
        self.messages[message_id] = {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": labels,
            "parsed": parsed,
        }
        self.threads.setdefault(thread_id, []).append(message_id)
        return self.messages[message_id]

    async def create_draft(self, owner_id, raw_mime, thread_id):
        draft_id = self._id("d")
        message = self._store(raw_mime, thread_id, ["DRAFT"])
        self.drafts[draft_id] = message
        self.drafts_created += 1
        if self.fail_after_create:
            status, self.fail_after_create = self.fail_after_create, None
            raise ProviderError(status, "Gmail request timed out")
        return {"id": draft_id, "message": {"id": message["id"], "threadId": message["threadId"]}}

    async def update_draft(self, owner_id, draft_id, raw_mime, thread_id):
        if draft_id not in self.drafts:
            raise ProviderError(404, "not found")
        old = self.drafts[draft_id]
        self.messages.pop(old["id"])
        self.threads[old["threadId"]].remove(old["id"])
        message = self._store(raw_mime, old["threadId"], ["DRAFT"])
        self.drafts[draft_id] = message
        return {"id": draft_id, "message": {"id": message["id"], "threadId": message["threadId"]}}

    async def get_draft(self, owner_id, draft_id):
        return {"id": draft_id} if draft_id in self.drafts else None

    async def send_draft(self, owner_id, draft_id):
        if self.fail_send_before:
            status, self.fail_send_before = self.fail_send_before, None
            raise ProviderError(status, "Gmail request timed out")
        if draft_id not in self.drafts:
            raise ProviderError(404, "not found")
        message = self.drafts.pop(draft_id)
        message["labelIds"] = ["SENT"]
        self.sent.append(message)
        if self.crash_after_send:
            self.crash_after_send = False
            raise ProviderError(504, "Gmail request timed out after the send was applied")
        return {"id": message["id"], "threadId": message["threadId"], "labelIds": ["SENT"]}

    async def get_message(self, owner_id, message_id):
        return self.messages.get(message_id)

    async def list_thread_messages(self, owner_id, thread_id):
        return [self.messages[m] for m in self.threads.get(thread_id, [])]

    async def find_by_message_id(self, owner_id, rfc822_message_id):
        bare = rfc822_message_id.strip("<>")
        draft_ids = {message["id"]: draft_id for draft_id, message in self.drafts.items()}
        return [
            {
                "id": message["id"],
                "threadId": message["threadId"],
                "labelIds": message["labelIds"],
                "draft_id": draft_ids.get(message["id"]),
            }
            for message in self.messages.values()
            if "parsed" in message and (message["parsed"]["Message-ID"] or "").strip("<>") == bare
        ]

    def user_deletes_drafts(self):
        """Deleting a draft in Gmail deletes its message too; nothing was sent."""
        for message in self.drafts.values():
            self.messages.pop(message["id"], None)
            self.threads[message["threadId"]].remove(message["id"])
        self.drafts.clear()

    def receive_reply(self, thread_id, sender, text, subject="Re: Invitation"):
        message_id = self._id("r")
        body = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
        self.messages[message_id] = {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": ["INBOX"],
            "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": sender},
                    {"name": "Subject", "value": subject},
                ],
                "body": {"data": body},
            },
        }
        self.threads.setdefault(thread_id, []).append(message_id)
        return message_id


def make_event(revision=1, **overrides) -> EventSnapshot:
    start = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
    values = dict(
        id="event-1",
        owner_id=OWNER,
        revision=revision,
        title="Picnic",
        location="Park A",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        timezone="America/Los_Angeles",
        links=["https://example.com/event-1"],
        organizer_contact=ORGANIZER_EMAIL,
        invitees=[
            Invitee(id="inv-1", email="Ada@Example.com", display_name="Ada"),
            Invitee(id="inv-2", email="bob@example.com"),
        ],
    )
    return EventSnapshot(**(values | overrides))


class World:
    def __init__(self) -> None:
        self.store = InMemoryWorkflowStore()
        self.calendar = FakeCalendar()
        self.gmail = FakeGmail()
        self.tokens = StaticTokenSource({OWNER: "tok"}, {OWNER: ORGANIZER_EMAIL})
        self.distributor = Distributor(self.store, self.calendar, self.gmail, self.tokens)
        self.rsvp = RSVPTracker(self.store, self.calendar, self.gmail, self.tokens)
        self.store.put_event(make_event())

    def approve(self, kind=ContentKind.INVITATION, action="publish", body="Join us!") -> Approval:
        event = self.store.events["event-1"]
        content = GeneratedContent(
            event_id=event.id,
            event_revision=event.revision,
            kind=kind,
            subject=f"{kind.value}: {event.title}",
            body=body,
            producer=Producer.SUPERHUMAN_GO,
            state="ready",
        )
        self.store.content[content.id] = content
        approval = Approval(
            id=f"approval-{len(self.store.approvals) + 1}",
            event_id=event.id,
            event_revision=event.revision,
            action=action,
            invitation_content_id=content.id,
        )
        self.store.put_approval(approval)
        return approval

    def revise(self, **changes) -> EventSnapshot:
        event = self.store.events["event-1"]
        revised = event.model_copy(update={**changes, "revision": event.revision + 1})
        self.store.put_event(revised)
        return revised
