"""Sourced organizer review; no inferred diagnoses, holidays, or venue guarantees."""

from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from hackathon_backend.services.assets.models import (
    BoundaryModel,
    EventSnapshot,
    GoContent,
    require_scope,
)


class Source(BoundaryModel):
    label: str = Field(min_length=1, max_length=300)
    observed_at: AwareDatetime
    confirmed_by: str = Field(min_length=1, max_length=200)
    url: HttpUrl | None = None


class Fact(BoundaryModel):
    value: Literal["yes", "no", "unknown"] = "unknown"
    source: Source | None = None

    @property
    def verified_value(self) -> str:
        return self.value if self.source else "unknown"


class Observance(BoundaryModel):
    name: str = Field(min_length=1, max_length=200)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    source: Source

    @model_validator(mode="after")
    def valid_interval(self) -> "Observance":
        if self.ends_at <= self.starts_at:
            raise ValueError("Observance end must be after start")
        return self


class InclusionInput(BoundaryModel):
    step_free_entrance: Fact = Field(default_factory=Fact)
    above_ground_floor: Fact = Field(default_factory=Fact)
    elevator: Fact = Field(default_factory=Fact)
    food_served: Fact = Field(default_factory=Fact)
    diet_options: tuple[str, ...] = ()
    diet_source: Source | None = None
    required_diets: tuple[str, ...] = Field(default=(), repr=False)
    captions: Fact = Field(default_factory=Fact)
    loud_sound: Fact = Field(default_factory=Fact)
    strobes: Fact = Field(default_factory=Fact)
    observances_selected: bool = False
    observances: tuple[Observance, ...] = ()


class Finding(BoundaryModel):
    category: str
    status: Literal["recorded", "attention", "unknown", "needs_review"]
    reason: str
    sources: tuple[Source, ...] = ()
    conflicts: tuple[str, ...] = ()
    go_generation_id: str | None = None


class InclusionReport(BoundaryModel):
    event_id: str
    event_revision: int
    audience: Literal["organizer_private"] = "organizer_private"
    findings: tuple[Finding, ...]
    requires_review: bool
    certification: Literal[False] = False


def check_inclusion(
    event: EventSnapshot,
    facts: InclusionInput,
    *,
    owner_id: str,
    summary: GoContent | None = None,
) -> InclusionReport:
    """Evaluate explicit facts. Even a fully recorded report is not certification."""
    require_scope(event, owner_id, *((summary,) if summary else ()))
    findings: list[Finding] = []

    def add_fact(category: str, fact: Fact, *, caution_value: str = "no") -> None:
        value = fact.verified_value
        findings.append(
            Finding(
                category=category,
                status="unknown"
                if value == "unknown"
                else ("attention" if value == caution_value else "recorded"),
                reason="missing_source_or_answer" if value == "unknown" else f"reported_{value}",
                sources=(fact.source,) if fact.source else (),
            )
        )

    if summary and summary.kind != "plain_language_summary":
        raise ValueError("Expected Go plain-language summary")
    findings.append(
        Finding(
            category="plain_language",
            status="recorded" if summary and summary.reviewed_by_organizer else "needs_review",
            reason="organizer_reviewed_go_summary"
            if summary and summary.reviewed_by_organizer
            else "awaiting_go_summary_or_organizer_review",
            go_generation_id=summary.generation_id if summary else None,
        )
    )
    add_fact("step_free_entrance", facts.step_free_entrance)
    if facts.above_ground_floor.verified_value == "no":
        findings.append(
            Finding(
                category="elevator",
                status="recorded",
                reason="reported_ground_floor",
                sources=(facts.above_ground_floor.source,),
            )
        )
    elif facts.above_ground_floor.verified_value == "unknown":
        findings.append(
            Finding(
                category="elevator",
                status="unknown",
                reason="floor_and_route_need_confirmation",
            )
        )
    else:
        add_fact("elevator", facts.elevator)
        findings[-1] = findings[-1].model_copy(
            update={
                "sources": (facts.above_ground_floor.source,) + findings[-1].sources,
            }
        )
    add_fact("captions", facts.captions)
    add_fact("loud_sound", facts.loud_sound, caution_value="yes")
    add_fact("strobes", facts.strobes, caution_value="yes")

    food = facts.food_served.verified_value
    if food == "unknown" or (food == "yes" and not facts.diet_source):
        diet_status, reason = "unknown", "food_or_diet_options_need_confirmation"
    elif food == "no":
        diet_status, reason = "recorded", "reported_no_food"
    else:
        options = {value.strip().casefold() for value in facts.diet_options}
        unmet = [need for need in facts.required_diets if need.strip().casefold() not in options]
        diet_status = "attention" if unmet else "needs_review"
        # No names or individual dietary restrictions are exposed in the finding.
        reason = (
            "unmet_reported_dietary_requirements" if unmet else "confirm_options_with_attendees"
        )
    findings.append(
        Finding(
            category="diet",
            status=diet_status,
            reason=reason,
            sources=tuple(
                source
                for source in (facts.food_served.source, facts.diet_source)
                if source is not None
            ),
        )
    )

    conflicts = tuple(
        observance.name
        for observance in facts.observances
        if event.starts_at < observance.ends_at and observance.starts_at < event.ends_at
    )
    findings.append(
        Finding(
            category="religious_observances",
            status="unknown"
            if not facts.observances_selected or not facts.observances
            else ("attention" if conflicts else "recorded"),
            reason="select_relevant_observances"
            if not facts.observances_selected
            else (
                "supply_sourced_observance_intervals"
                if not facts.observances
                else (
                    "overlap_with_supplied_observance"
                    if conflicts
                    else "no_overlap_in_supplied_intervals"
                )
            ),
            sources=tuple(observance.source for observance in facts.observances),
            conflicts=conflicts,
        )
    )
    return InclusionReport(
        event_id=event.id,
        event_revision=event.revision,
        findings=tuple(findings),
        requires_review=any(f.status != "recorded" for f in findings),
    )
