"""Strict public inputs. Owner identity and revisions are always server controlled."""

from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from hackathon_backend.services.inclusion import InclusionInput, InclusionReport

IdempotencyKey = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[!-~]+$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InviteeInput(Input):
    email: str = Field(min_length=3, max_length=254)
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        value = value.lower()
        if value.count("@") != 1 or any(c.isspace() for c in value):
            raise ValueError("Expected an email address")
        local, domain = value.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Expected an email address")
        return value


class EventInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=30_000)
    location: str = Field(default="", max_length=500)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone: str = Field(max_length=100)
    links: list[HttpUrl] = Field(default_factory=list, max_length=20)
    organizer_contact: str = Field(default="", max_length=500)
    invitees: list[InviteeInput] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_event(self) -> "EventInput":
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must be after start")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone") from None
        if len({i.email for i in self.invitees}) != len(self.invitees):
            raise ValueError("Invitee emails must be unique")
        return self


class EventUpdate(EventInput):
    expected_revision: int = Field(ge=1)


class TaskInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=30_000)
    status: Literal["todo", "in_progress", "done"] = "todo"
    due_at: AwareDatetime | None = None
    event_id: UUID | None = None


class TaskUpdate(TaskInput):
    expected_revision: int = Field(ge=1)


class InviteeRecord(InviteeInput):
    id: UUID


class EventRecord(EventInput):
    id: UUID
    owner_id: UUID
    revision: int
    status: str
    invitees: list[InviteeRecord] = Field(default_factory=list)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TaskRecord(TaskInput):
    id: UUID
    owner_id: UUID
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class RevisionInput(Input):
    expected_revision: int = Field(ge=1)


class ApprovalInput(RevisionInput):
    action: Literal["publish", "update", "draft_only"]
    invitation_content_id: UUID
    acknowledged_unknowns: bool


class ContentReview(RevisionInput):
    body: str | None = Field(default=None, min_length=1, max_length=30_000)
    subject: str | None = Field(default=None, min_length=1, max_length=200)


class ArtifactReview(RevisionInput):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DistributionInput(RevisionInput):
    approval_id: UUID


class ConnectorInput(Input):
    label: str = Field(default="Superhuman Go", min_length=1, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=90)


# A10 read contracts. Responses never include owner IDs, credentials or private RSVP notes.

WorkState = Literal["awaiting_go", "running", "succeeded", "failed", "superseded"]


class WorkRecord(BaseModel):
    id: str
    event_id: str
    event_revision: int
    kind: str
    state: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: AwareDatetime | None = None
    claimed_at: AwareDatetime | None = None


class GmailBindingRecord(BaseModel):
    event_revision: int
    content_id: str
    draft_id: str | None = None
    message_id: str | None = None
    thread_id: str | None = None
    sent: bool = False
    sent_history: list[dict[str, Any]] = Field(default_factory=list)
    stale: bool


class CalendarBindingRecord(BaseModel):
    event_revision: int
    calendar_id: str = "primary"
    remote_event_id: str
    html_link: str | None = None
    stale: bool


class BindingsResponse(BaseModel):
    event_id: UUID
    event_revision: int
    calendar: CalendarBindingRecord | None
    gmail: GmailBindingRecord | None


class ApprovalRecord(BaseModel):
    id: UUID
    event_id: UUID
    event_revision: int
    action: Literal["publish", "update", "draft_only"]
    invitation_content_id: UUID
    content_hash: str
    acknowledged_unknowns: bool
    approved_at: AwareDatetime


class InclusionFactsUpdate(Input):
    expected_version: int = Field(ge=0)
    facts: InclusionInput


class InclusionFactsResponse(BaseModel):
    event_id: UUID
    version: int
    saved_at_event_revision: int | None
    updated_at: AwareDatetime | None
    facts: InclusionInput
    review: InclusionReport


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class DomainError(Exception):
    """Only safe, public error codes/messages cross the API boundary."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
