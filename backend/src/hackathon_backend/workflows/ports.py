"""Interfaces Member 3's workflows depend on. Implementations come from other owners.

- `WorkflowStore`, `PrincipalResolver`, `GoogleTokenSource`: Member 2 (Supabase tables, connector
  tokens, credential vault). `memory.py` is the test/dev implementation.
- `CalendarAPI`, `GmailAPI`: Member 3 (`providers/google`).
- `AttachmentSource`: Member 4 (current flyer/document export for an event revision).
"""

from typing import Any, Protocol

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


class RevisionConflict(Exception):
    """Write targeted a revision that is no longer current."""


class WorkflowStore(Protocol):
    """Every method is scoped by owner_id taken from a validated Principal."""

    async def get_event(self, owner_id: str, event_id: str) -> EventSnapshot | None: ...

    async def list_work(self, owner_id: str, states: set[str]) -> list[WorkItem]: ...

    async def get_work(self, owner_id: str, work_id: str) -> WorkItem | None: ...

    async def put_work(self, item: WorkItem) -> None: ...

    async def save_content(
        self, owner_id: str, content: GeneratedContent, expected_revision: int
    ) -> GeneratedContent:
        """Persist content; raise RevisionConflict if the event is not at expected_revision."""
        ...

    async def get_content(self, owner_id: str, content_id: str) -> GeneratedContent | None: ...

    async def latest_content(
        self, owner_id: str, event_id: str, revision: int, kind: ContentKind
    ) -> GeneratedContent | None: ...

    async def get_approval(self, owner_id: str, approval_id: str) -> Approval | None: ...

    async def get_operation(self, owner_id: str, idempotency_key: str) -> Operation | None: ...

    async def put_operation(self, owner_id: str, operation: Operation) -> None: ...

    async def list_operations(self, owner_id: str, event_id: str) -> list[Operation]: ...

    async def reconcile_operation(
        self, owner_id: str, key: str, attempt: int, outcome: str, receipt: dict[str, Any]
    ) -> Operation:
        """Server-only, after provider read-back: outcome "succeeded" records the receipt;
        "not_applied" marks failed/confirmed_no_effect so one retry is allowed."""
        ...

    async def get_calendar_binding(
        self, owner_id: str, event_id: str
    ) -> CalendarBinding | None: ...

    async def put_calendar_binding(self, owner_id: str, binding: CalendarBinding) -> None: ...

    async def get_gmail_binding(self, owner_id: str, event_id: str) -> GmailBinding | None: ...

    async def put_gmail_binding(self, owner_id: str, binding: GmailBinding) -> None: ...

    async def add_rsvp(self, owner_id: str, observation: RSVPObservation) -> None: ...

    async def list_rsvps(self, owner_id: str, event_id: str) -> list[RSVPObservation]: ...

    async def get_reply(self, owner_id: str, message_id: str) -> InboundReply | None: ...

    async def put_reply(self, reply: InboundReply) -> None: ...


class PrincipalResolver(Protocol):
    async def resolve(self, connector_token: str) -> Principal | None:
        """Map an organizer's personal Go connector token to that organizer, or None."""
        ...


class GoogleTokenSource(Protocol):
    async def access_token(self, owner_id: str) -> str:
        """Fresh access token for this organizer; raise IntegrationNotConnected if absent."""
        ...

    async def account_email(self, owner_id: str) -> str: ...


class IntegrationNotConnected(Exception):
    pass


class ProviderError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class CalendarAPI(Protocol):
    async def insert_event(
        self, owner_id: str, calendar_id: str, body: dict[str, Any], send_updates: str
    ) -> dict[str, Any]:
        """Raise ProviderError(409) if body["id"] already exists."""
        ...

    async def get_event(self, owner_id: str, calendar_id: str, event_id: str) -> dict[str, Any]: ...

    async def patch_event(
        self,
        owner_id: str,
        calendar_id: str,
        event_id: str,
        body: dict[str, Any],
        send_updates: str,
        etag: str | None,
    ) -> dict[str, Any]: ...


class GmailAPI(Protocol):
    async def create_draft(self, owner_id: str, raw_mime: bytes, thread_id: str | None) -> dict: ...

    async def update_draft(
        self, owner_id: str, draft_id: str, raw_mime: bytes, thread_id: str | None
    ) -> dict:
        """Raise ProviderError(404) if the draft no longer exists (sent or deleted)."""
        ...

    async def get_draft(self, owner_id: str, draft_id: str) -> dict | None: ...

    async def send_draft(self, owner_id: str, draft_id: str) -> dict: ...

    async def get_message(self, owner_id: str, message_id: str) -> dict | None:
        """Metadata including labelIds; None if missing."""
        ...

    async def list_thread_messages(self, owner_id: str, thread_id: str) -> list[dict]:
        """Full messages (payload headers + text body) in the thread."""
        ...

    async def find_by_message_id(self, owner_id: str, rfc822_message_id: str) -> list[dict]:
        """Non-trashed messages whose Message-ID header matches: [{id, threadId, labelIds,
        draft_id}] with draft_id set when the message is still a draft."""
        ...


class AttachmentSource(Protocol):
    async def current_attachments(
        self, owner_id: str, event: EventSnapshot
    ) -> list[tuple[str, str, bytes]]:
        """(filename, mime type, bytes) for this exact event revision; [] if none."""
        ...
