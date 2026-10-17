from datetime import timedelta

import pytest
from test_assets_support import NOW, event, go

from hackathon_backend.services.assets.models import StaleRevisionError
from hackathon_backend.services.inclusion import (
    Fact,
    InclusionInput,
    Observance,
    Source,
    check_inclusion,
)


def source():
    return Source(
        label="Synthetic organizer confirmation",
        observed_at=NOW,
        confirmed_by="fixture-owner",
        url="https://example.org/fixture",
    )


def findings(report):
    return {finding.category: finding for finding in report.findings}


def test_missing_and_unsourced_answers_stay_unknown():
    report = check_inclusion(
        event(), InclusionInput(step_free_entrance=Fact(value="yes")), owner_id="fixture-owner"
    )
    found = findings(report)
    assert found["step_free_entrance"].status == "unknown"
    assert found["religious_observances"].reason == "holiday_calendar_unavailable"
    assert report.requires_review and report.certification is False
    assert report.audience == "organizer_private"


def test_ground_floor_does_not_claim_an_elevator_is_required():
    facts = InclusionInput(
        above_ground_floor=Fact(value="no", source=source()),
        elevator=Fact(value="no", source=source()),
    )
    found = findings(check_inclusion(event(), facts, owner_id="fixture-owner"))
    assert found["elevator"].reason == "reported_ground_floor"
    assert found["elevator"].sources[0].observed_at == NOW


def test_upper_floor_without_elevator_and_sensory_hazards_need_attention():
    facts = InclusionInput(
        above_ground_floor=Fact(value="yes", source=source()),
        elevator=Fact(value="no", source=source()),
        loud_sound=Fact(value="yes", source=source()),
        strobes=Fact(value="yes", source=source()),
    )
    found = findings(check_inclusion(event(), facts, owner_id="fixture-owner"))
    assert all(found[name].status == "attention" for name in ["elevator", "loud_sound", "strobes"])


def test_unmet_diets_are_private_and_not_inferred_from_names():
    facts = InclusionInput(
        food_served=Fact(value="yes", source=source()),
        diet_source=source(),
        diet_options=("vegan",),
        required_diets=("private-restriction",),
    )
    report = check_inclusion(event(), facts, owner_id="fixture-owner")
    assert findings(report)["diet"].status == "attention"
    assert "private-restriction" not in report.model_dump_json()


def test_diet_options_require_confirmation_even_when_labels_match():
    facts = InclusionInput(
        food_served=Fact(value="yes", source=source()),
        diet_source=source(),
        diet_options=(" Vegan ",),
        required_diets=("vegan",),
    )
    assert (
        findings(check_inclusion(event(), facts, owner_id="fixture-owner"))["diet"].status
        == "needs_review"
    )


def test_observance_overlap_handles_timezone_and_keeps_source():
    snapshot = event()
    overlap = Observance(
        name="Organizer-selected synthetic observance",
        starts_at=snapshot.starts_at.astimezone(NOW.tzinfo) - timedelta(hours=1),
        ends_at=snapshot.ends_at,
        source=source(),
    )
    adjacent = Observance(
        name="Adjacent interval",
        starts_at=snapshot.ends_at,
        ends_at=snapshot.ends_at + timedelta(hours=1),
        source=source(),
    )
    facts = InclusionInput(observances_selected=True, observances=(overlap, adjacent))
    finding = findings(check_inclusion(snapshot, facts, owner_id="fixture-owner"))[
        "religious_observances"
    ]
    assert finding.conflicts == (overlap.name,)
    assert finding.status == "attention" and finding.sources[0].url == source().url


def test_empty_observance_coverage_remains_unknown():
    report = check_inclusion(
        event(), InclusionInput(observances_selected=True), owner_id="fixture-owner"
    )
    assert findings(report)["religious_observances"].status == "unknown"


def test_go_summary_requires_review_and_matching_revision():
    snapshot = event()
    summary = go(snapshot, "plain_language_summary")
    assert (
        findings(
            check_inclusion(snapshot, InclusionInput(), owner_id=snapshot.owner_id, summary=summary)
        )["plain_language"].status
        == "needs_review"
    )
    reviewed = summary.model_copy(update={"reviewed_by_organizer": True})
    assert (
        findings(
            check_inclusion(
                snapshot, InclusionInput(), owner_id=snapshot.owner_id, summary=reviewed
            )
        )["plain_language"].status
        == "recorded"
    )
    with pytest.raises(StaleRevisionError):
        check_inclusion(event(2), InclusionInput(), owner_id=snapshot.owner_id, summary=summary)


def test_cross_owner_and_wrong_content_kind_rejected():
    with pytest.raises(PermissionError):
        check_inclusion(event(), InclusionInput(), owner_id="another-owner")
    with pytest.raises(ValueError, match="plain-language"):
        check_inclusion(event(), InclusionInput(), owner_id="fixture-owner", summary=go(event()))
