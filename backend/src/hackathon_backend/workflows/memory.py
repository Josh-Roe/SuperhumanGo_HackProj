"""In-process WorkflowStore for tests and the labeled local dev mode. Not Supabase evidence."""

import hashlib
import secrets

from hackathon_backend.workflows.models import (
    Approval,
    CalendarBinding,
    ContentKind,
    EventSnapshot,
    GeneratedContent,
    GmailBinding,
    InboundReply,
    Operation,
    Principal,
    RSVPObservation,
    WorkItem,
)
from hackathon_backend.workflows.ports import RevisionConflict


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InMemoryPrincipalResolver:
    """Stores only SHA-256 hashes of organizer connector tokens."""

    def __init__(self) -> None:
        self._owners: dict[str, str] = {}

    def issue(self, owner_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.register(token, owner_id)
        return token

    def register(self, token: str, owner_id: str) -> None:
        self._owners[token_hash(token)] = owner_id

    async def resolve(self, connector_token: str) -> Principal | None:
        owner = self._owners.get(token_hash(connector_token))
        return Principal(owner_id=owner) if owner else None


class InMemoryWorkflowStore:
    def __init__(self) -> None:
        self.events: dict[str, EventSnapshot] = {}
        self.work: dict[str, WorkItem] = {}
        self.content: dict[str, GeneratedContent] = {}
        self.approvals: dict[str, Approval] = {}
        self.operations: dict[str, Operation] = {}
        self.calendar: dict[str, CalendarBinding] = {}
        self.gmail: dict[str, GmailBinding] = {}
        self.rsvps: list[RSVPObservation] = []
        self.replies: dict[str, InboundReply] = {}

    def _owns(self, owner_id: str, event_id: str) -> bool:
        event = self.events.get(event_id)
        return event is not None and event.owner_id == owner_id

    # Test/dev setup helpers; production writes come through Member 2's API.
    def put_event(self, event: EventSnapshot) -> None:
        self.events[event.id] = event

    def put_approval(self, approval: Approval) -> None:
        self.approvals[approval.id] = approval

    async def get_event(self, owner_id, event_id):
        return self.events[event_id] if self._owns(owner_id, event_id) else None

    async def list_work(self, owner_id, states):
        items = [w for w in self.work.values() if w.owner_id == owner_id and w.state in states]
        return sorted(items, key=lambda w: w.created_at)

    async def get_work(self, owner_id, work_id):
        item = self.work.get(work_id)
        return item if item and item.owner_id == owner_id else None

    async def put_work(self, item):
        self.work[item.id] = item

    async def save_content(self, owner_id, content, expected_revision):
        event = await self.get_event(owner_id, content.event_id)
        if event is None:
            raise KeyError(content.event_id)
        if event.revision != expected_revision or content.event_revision != expected_revision:
            raise RevisionConflict(f"event is at revision {event.revision}")
        self.content[content.id] = content
        return content

    async def get_content(self, owner_id, content_id):
        content = self.content.get(content_id)
        return content if content and self._owns(owner_id, content.event_id) else None

    async def latest_content(self, owner_id, event_id, revision, kind: ContentKind):
        if not self._owns(owner_id, event_id):
            return None
        matches = [
            c
            for c in self.content.values()
            if c.event_id == event_id and c.event_revision == revision and c.kind == kind
        ]
        return max(matches, key=lambda c: c.created_at, default=None)

    async def get_approval(self, owner_id, approval_id):
        approval = self.approvals.get(approval_id)
        return approval if approval and self._owns(owner_id, approval.event_id) else None

    async def get_operation(self, owner_id, idempotency_key):
        op = self.operations.get(idempotency_key)
        return op if op and self._owns(owner_id, op.event_id) else None

    async def put_operation(self, owner_id, operation):
        self.operations[operation.idempotency_key] = operation

    async def list_operations(self, owner_id, event_id):
        if not self._owns(owner_id, event_id):
            return []
        return [o for o in self.operations.values() if o.event_id == event_id]

    async def get_calendar_binding(self, owner_id, event_id):
        return self.calendar.get(event_id) if self._owns(owner_id, event_id) else None

    async def put_calendar_binding(self, owner_id, binding):
        self.calendar[binding.event_id] = binding

    async def get_gmail_binding(self, owner_id, event_id):
        return self.gmail.get(event_id) if self._owns(owner_id, event_id) else None

    async def put_gmail_binding(self, owner_id, binding):
        self.gmail[binding.event_id] = binding

    async def add_rsvp(self, owner_id, observation):
        self.rsvps.append(observation)

    async def list_rsvps(self, owner_id, event_id):
        if not self._owns(owner_id, event_id):
            return []
        return [r for r in self.rsvps if r.event_id == event_id]

    async def get_reply(self, owner_id, message_id):
        reply = self.replies.get(message_id)
        return reply if reply and reply.owner_id == owner_id else None

    async def put_reply(self, reply):
        self.replies[reply.id] = reply
