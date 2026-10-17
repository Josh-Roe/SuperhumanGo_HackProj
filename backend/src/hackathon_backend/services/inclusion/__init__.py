"""Sourced organizer review; no inferred diagnoses or venue guarantees.

Religious observances come from organizer-supplied intervals plus Google's public holiday
calendars (`holidays.py`) for the traditions the organizer keeps selected.
"""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from hackathon_backend.services.assets.models import (
    BoundaryModel,
    EventSnapshot,
    GoContent,
    require_scope,
)
from hackathon_backend.services.inclusion.holidays import (
    ALL_TRADITIONS,
    CalendarCheck,
    HolidayCalendar,
    Tradition,
)

__all__ = [
    "ALL_TRADITIONS",
    "CalendarCheck",
    "Fact",
    "Finding",
    "HolidayCalendar",
    "InclusionInput",
    "InclusionReport",
    "Observance",
    "Source",
    "Tradition",
    "check_inclusion",
]


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
    # Public holiday calendars to check automatically; an empty tuple opts out.
    traditions: tuple[Tradition, ...] = ALL_TRADITIONS


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
    calendar: CalendarCheck | None = None,
) -> InclusionReport:
    """Evaluate explicit facts. Even a fully recorded report is not certification.

    `calendar` is the holiday-feed lookup for `facts.traditions`; None means it was not run.
    """
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

    findings.append(_observance_finding(event, facts, calendar))
    return InclusionReport(
        event_id=event.id,
        event_revision=event.revision,
        findings=tuple(findings),
        requires_review=any(f.status != "recorded" for f in findings),
    )


def _observance_finding(
    event: EventSnapshot, facts: InclusionInput, calendar: CalendarCheck | None
) -> Finding:
    def overlaps(starts: datetime, ends: datetime) -> bool:
        return event.starts_at < ends and starts < event.ends_at

    manual = facts.observances if facts.observances_selected else ()
    conflicts = [o.name for o in manual if overlaps(o.starts_at, o.ends_at)]
    sources = [o.source for o in manual]
    missing: tuple[str, ...] = ()
    if facts.traditions:
        if calendar is None:
            missing = tuple(facts.traditions)
        else:
            missing = tuple(t for t in facts.traditions if t in calendar.unavailable)
            conflicts += [
                o.name
                for o in calendar.observances
                if o.tradition in facts.traditions and overlaps(o.starts_at, o.ends_at)
            ]
            sources += [
                Source(
                    label=f"Google Calendar public holidays: {feed.calendar_name}",
                    observed_at=feed.fetched_at,
                    confirmed_by="Google Calendar public holiday feed",
                    url=feed.url,
                )
                for feed in calendar.feeds
                if feed.tradition in facts.traditions
            ]
    checked = bool(manual) or (bool(facts.traditions) and len(missing) < len(facts.traditions))
    if conflicts:
        status, reason = "attention", "overlap_with_observance"
    elif missing:
        status, reason = "unknown", "holiday_calendar_unavailable"
    elif checked:
        status, reason = "recorded", "no_overlap_in_checked_observances"
    elif facts.observances_selected:
        status, reason = "unknown", "supply_sourced_observance_intervals"
    else:
        status, reason = "unknown", "select_relevant_observances"
    return Finding(
        category="religious_observances",
        status=status,
        reason=reason,
        sources=tuple(sources),
        conflicts=tuple(dict.fromkeys(conflicts)),
    )
