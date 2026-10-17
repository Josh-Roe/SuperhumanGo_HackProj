"""Owner-authorized persistence around Member 4's pure inclusion checker."""

from pydantic import BaseModel, Field, field_validator

from hackathon_backend.domain.models import DomainError, RevisionInput
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore
from hackathon_backend.services.assets.preparation import EventAssetPreparationService
from hackathon_backend.services.inclusion import InclusionInput, InclusionReport


class InclusionView(BaseModel):
    event_id: str
    event_revision: int
    facts_saved: bool
    facts: InclusionInput
    report: InclusionReport


class InclusionSave(RevisionInput):
    facts: InclusionInput = Field(repr=False)

    @field_validator("facts")
    @classmethod
    def bounded_private_inputs(cls, value: InclusionInput):
        if len(value.model_dump_json().encode()) > 64_000:
            raise ValueError("Inclusion input exceeds the supported size")
        return value


async def read_inclusion(repo: OrganizerRepository, event_id: str) -> dict:
    event = await repo.get("events", event_id)
    rows = await repo.event_children(event_id, "inclusion_facts")
    saved = next((row for row in rows if row["revision"] == event["revision"]), None)
    facts = InclusionInput.model_validate(saved.get("inputs", {})) if saved else InclusionInput()
    report = await EventAssetPreparationService(SupabaseWorkflowStore(repo.db)).inclusion(
        repo.owner_id, event_id, event["revision"], facts
    )
    if (await repo.get("events", event_id))["revision"] != event["revision"]:
        raise DomainError("revision_conflict", "Event changed while reading inclusion facts")
    return {
        "event_id": event_id,
        "event_revision": event["revision"],
        "facts_saved": saved is not None,
        "facts": facts.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
    }
