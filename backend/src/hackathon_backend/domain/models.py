"""Strict public inputs. Owner identity and revisions are always server controlled."""

from typing import Annotated, Literal
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


class ConnectorInput(Input):
    label: str = Field(default="Superhuman Go", min_length=1, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=90)


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
