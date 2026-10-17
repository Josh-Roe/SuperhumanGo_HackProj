"""Member 4 boundary types; callers supply a validated organizer principal."""

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EventSnapshot(BoundaryModel):
    id: Identifier
    owner_id: Identifier
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=250)
    location: str = Field(min_length=1, max_length=500)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone: str

    @model_validator(mode="after")
    def valid_interval(self) -> "EventSnapshot":
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone") from None
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must be after start")
        return self

    def flyer_fields(self) -> dict[str, str]:
        zone = ZoneInfo(self.timezone)
        start, end = self.starts_at.astimezone(zone), self.ends_at.astimezone(zone)
        return {
            "title": self.title,
            "when": f"{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M} ({self.timezone})",
            "location": self.location,
        }


class GoContent(BoundaryModel):
    """Load from Member 3's trusted content repository, never raw browser claims."""

    event_id: Identifier
    owner_id: Identifier
    event_revision: int = Field(ge=1)
    producer: Literal["superhuman_go"]
    generation_id: Identifier
    kind: Literal[
        "flyer_brief", "flyer_copy", "event_document", "plain_language_summary", "flyer_alt_text"
    ]
    body: str = Field(min_length=1, max_length=30_000)
    language: str = Field(default="en", pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
    reviewed_by_organizer: bool = False


class StaleRevisionError(ValueError):
    pass


def require_scope(event: EventSnapshot, owner_id: str, *contents: GoContent) -> None:
    if event.owner_id != owner_id:
        raise PermissionError("Event is outside the current organizer scope")
    for content in contents:
        if content.owner_id != owner_id or content.event_id != event.id:
            raise PermissionError("Content is outside the event/organizer scope")
        if content.event_revision != event.revision:
            raise StaleRevisionError("Go content belongs to another event revision")


class DesignRef(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int = Field(ge=1)
    design_id: Identifier
    edit_url: str
    view_url: str
    generation_id: Identifier


class Approval(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int = Field(ge=1)
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_at: AwareDatetime
    approval_id: Identifier


class StorageReceipt(BoundaryModel):
    object_key: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=1)


class AssetPreviewMetadata(BoundaryModel):
    """Authenticated preview DTO; provider/source IDs are references, never credentials."""

    event_id: Identifier
    event_revision: int = Field(ge=1)
    kind: Literal["event_document", "flyer_png"]
    content_type: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=1, le=10_000_000)
    canva_design_id: str | None
    canva_export_id: str | None
    canva_generation_id: str | None
    go_generation_id: Identifier
    created_at: AwareDatetime
    review_state: Literal["needs_review", "reviewed"]


class AssetRecord(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int = Field(ge=1)
    kind: Literal["event_document", "flyer_png"]
    object_key: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=1, le=10_000_000)
    content_type: str
    go_generation_id: Identifier
    review_state: Literal["needs_review", "reviewed"]
    created_at: AwareDatetime
    canva_design_id: str | None = None
    canva_export_id: str | None = None
    canva_generation_id: str | None = None

    def preview_metadata(self) -> dict[str, str | int | None]:
        """Frontend adds a scoped, short-lived URL via Member 2; no CDN secrets here."""
        return AssetPreviewMetadata.model_validate(
            {name: getattr(self, name) for name in AssetPreviewMetadata.model_fields}
        ).model_dump(mode="json")
