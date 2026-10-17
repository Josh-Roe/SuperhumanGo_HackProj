"""Member 3 workflow records, mirroring docs/INTEGRATION_CONTRACT.md until Member 2 freezes v0.

These are the shapes Go tools and Google orchestration need. Member 2's Supabase repository
implements `WorkflowStore` (see ports.py) over the canonical tables.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class Principal(BaseModel):
    """An authenticated organizer. Never built from request JSON."""

    owner_id: str


class Invitee(BaseModel):
    id: str
    email: str
    display_name: str | None = None

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.strip().lower()


class EventSnapshot(BaseModel):
    id: str
    owner_id: str
    revision: int = Field(ge=1)
    title: str
    description: str = ""
    location: str = ""
    starts_at: datetime
    ends_at: datetime
    timezone: str
    links: list[str] = []
    organizer_contact: str
    status: str = "draft"
    invitees: list[Invitee] = []

    @model_validator(mode="after")
    def check_times(self) -> "EventSnapshot":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("event times must be timezone-aware")
        if self.ends_at <= self.starts_at:
            raise ValueError("event end must be after start")
        return self


class ContentKind(StrEnum):
    DESCRIPTION = "description"
    SUMMARY = "summary"
    INVITATION = "invitation"
    CHANGE_NOTICE = "change_notice"
    DOCUMENT = "document"
    # Member 4 asset prose (Canva flyer + event document); see docs/canva/MEMBER4_INTEGRATION.md
    FLYER_BRIEF = "flyer_brief"
    FLYER_COPY = "flyer_copy"
    EVENT_DOCUMENT = "event_document"
    PLAIN_LANGUAGE_SUMMARY = "plain_language_summary"
    FLYER_ALT_TEXT = "flyer_alt_text"


class Producer(StrEnum):
    SUPERHUMAN_GO = "superhuman_go"
    ORGANIZER = "organizer"  # organizer edited Go output in the website


class GeneratedContent(BaseModel):
    id: str = Field(default_factory=new_id)
    event_id: str
    event_revision: int
    kind: ContentKind
    subject: str | None = None
    body: str
    producer: Producer
    state: str = "needs_review"  # organizer review in the website moves it to "ready"
    created_at: datetime = Field(default_factory=utcnow)


class WorkKind(StrEnum):
    PREPARE_CONTENT = "prepare_content"
    CLASSIFY_REPLY = "classify_reply"


class WorkItem(BaseModel):
    """Work queued by the website or reply ingestion for a Go session to claim."""

    id: str = Field(default_factory=new_id)
    owner_id: str
    event_id: str
    event_revision: int
    kind: WorkKind
    state: str = "awaiting_go"  # awaiting_go -> running -> succeeded | superseded
    payload: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=utcnow)
    claimed_at: datetime | None = None


class Approval(BaseModel):
    """Organizer's in-app publish/update action. Go can read but never create one."""

    id: str
    event_id: str
    event_revision: int
    action: str  # "publish" | "update"
    invitation_content_id: str
    approved_at: datetime = Field(default_factory=utcnow)


class OperationKind(StrEnum):
    CALENDAR_UPSERT = "calendar_upsert"
    GMAIL_DRAFT = "gmail_draft"
    GMAIL_SEND = "gmail_send"


# Failure codes that prove no provider effect, so a retry is allowed without read-back.
# Mirrors organizer_put_operation in Supabase.
NO_EFFECT_CODES = frozenset({"integration_not_connected", "confirmed_no_effect"})


class Operation(BaseModel):
    id: str = Field(default_factory=new_id)
    event_id: str
    event_revision: int
    kind: OperationKind
    idempotency_key: str
    approval_id: str
    state: str = "queued"  # queued | running | succeeded | failed
    attempts: int = 0
    error_code: str | None = None
    receipt: dict[str, Any] = {}
    updated_at: datetime = Field(default_factory=utcnow)


class CalendarBinding(BaseModel):
    event_id: str
    calendar_id: str = "primary"
    remote_event_id: str
    html_link: str | None = None
    etag: str | None = None
    event_revision: int


class GmailBinding(BaseModel):
    """The latest invitation/change message for an event. Sent history is kept separately."""

    event_id: str
    draft_id: str | None = None
    message_id: str | None = None
    thread_id: str | None = None
    sent: bool = False
    event_revision: int
    content_id: str
    sent_history: list[dict[str, Any]] = []


class RSVPStatus(StrEnum):
    ATTENDING = "attending"
    MAYBE = "maybe"
    NOT_ATTENDING = "not_attending"
    NO_RESPONSE = "no_response"
    NEEDS_REVIEW = "needs_review"


class RSVPObservation(BaseModel):
    """One observed response with provenance. Conflicts are kept, not silently overwritten."""

    event_id: str
    invitee_id: str
    status: RSVPStatus
    source: str  # "calendar" | "email"
    source_id: str  # Calendar event ID or Gmail message ID
    observed_at: datetime = Field(default_factory=utcnow)
    event_revision: int
    classified_by: str | None = None  # "superhuman_go" for email classifications
    evidence: str | None = None
    private_note: str | None = None  # dietary/accessibility details; organizer-only


class InboundReply(BaseModel):
    id: str  # Gmail message ID: ingestion is idempotent per message
    owner_id: str
    event_id: str
    thread_id: str
    invitee_id: str | None
    from_email: str
    subject: str
    body_text: str  # quoted history removed
    forwarded: bool = False
    received_at: datetime
    state: str = "awaiting_go"  # awaiting_go | classified | needs_review | unmatched
