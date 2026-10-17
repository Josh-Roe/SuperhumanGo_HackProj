"""Exact private workspace response; worker payloads and secret state are excluded."""

from pydantic import BaseModel

from hackathon_backend.domain.models import EventRecord
from hackathon_backend.workflows.models import (
    Approval,
    CalendarBinding,
    GeneratedContent,
    GmailBinding,
    Operation,
    RSVPObservation,
)


class WorkSummary(BaseModel):
    id: str
    event_revision: int
    kind: str
    state: str


class ArtifactSummary(BaseModel):
    id: str
    event_id: str
    event_revision: int
    kind: str
    is_current: bool
    content_type: str
    sha256: str
    byte_length: int
    canva_design_id: str | None
    review_state: str


class WorkspaceResponse(BaseModel):
    event: EventRecord
    generated_content: list[GeneratedContent]
    artifacts: list[ArtifactSummary]
    inclusion_facts: list[dict]
    work: list[WorkSummary]
    operations: list[Operation]
    rsvps: list[RSVPObservation]
    calendar: CalendarBinding | None
    gmail: GmailBinding | None
    approvals: list[Approval]
    truncated: dict[str, bool]


class ProviderBindings(BaseModel):
    calendar: CalendarBinding | None
    gmail: GmailBinding | None
