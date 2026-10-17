"""A10 organizer read/save contracts through the HTTP seam; Supabase and holiday feeds mocked."""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hackathon_backend.api import create_router
from hackathon_backend.config import Settings
from hackathon_backend.services.inclusion import HolidayCalendar
from hackathon_backend.services.inclusion.holidays import feed_url

OWNER = "00000000-0000-4000-8000-000000000001"
EVENT = "00000000-0000-4000-8000-000000000003"
CONTENT = "00000000-0000-4000-8000-000000000004"
APPROVAL = "00000000-0000-4000-8000-000000000005"
SETTINGS = Settings(supabase_url="https://example.supabase.co", supabase_publishable_key="public")
AUTH = {"Authorization": "Bearer session"}

EVENT_ROW = {
    "id": EVENT,
    "owner_id": OWNER,
    "revision": 3,
    "title": "Community picnic",
    "description": "Bring a friend.",
    "location": "Rose Park",
    "starts_at": "2026-10-16T18:00:00-07:00",
    "ends_at": "2026-10-16T19:00:00-07:00",
    "timezone": "America/Los_Angeles",
    "links": [],
    "organizer_contact": "host@example.com",
    "status": "changed",
    "invitees": [],
    "created_at": "2026-10-16T10:00:00Z",
    "updated_at": "2026-10-16T12:00:00Z",
}
SOURCE = {
    "label": "Venue walkthrough",
    "observed_at": "2026-10-15T17:00:00Z",
    "confirmed_by": "Organizer",
}
JEWISH_FEED = (
    "BEGIN:VCALENDAR\r\nX-WR-CALNAME:Jewish Holidays\r\n"
    "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261016\r\nDTEND;VALUE=DATE:20261017\r\n"
    "SUMMARY:Synthetic Fast\r\nDESCRIPTION:Observance\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


class FakeSupabase:
    """Owner-filtered PostgREST double: answers only for OWNER's EVENT; records RPC bodies."""

    def __init__(self, **tables):
        self.tables = {"go_work": [], "provider_bindings": [], "approvals": [], **tables}
        self.rpc_results: dict[str, list[httpx.Response]] = {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        if path == "/rest/v1/rpc/organizer_event_json":
            body = json.loads(request.content)
            return httpx.Response(200, json=EVENT_ROW if body["p_id"] == EVENT else None)
        if path.startswith("/rest/v1/rpc/"):
            name = path.removeprefix("/rest/v1/rpc/")
            self.calls.append((name, json.loads(request.content)))
            return self.rpc_results[name].pop(0)
        table = path.removeprefix("/rest/v1/")
        params = dict(request.url.params)
        self.calls.append((table, params))
        assert params.get("owner_id", f"eq.{OWNER}") == f"eq.{OWNER}"
        return httpx.Response(200, json=self.tables.get(table, []))


def client_for(fake: FakeSupabase) -> TestClient:
    holidays = HolidayCalendar(
        transport=httpx.MockTransport(
            lambda r: (
                httpx.Response(200, text=JEWISH_FEED)
                if str(r.url) == feed_url("jewish")
                else httpx.Response(503)
            )
        )
    )
    app = FastAPI()
    app.include_router(
        create_router(SETTINGS, transport=httpx.MockTransport(fake), holidays=holidays)
    )
    return TestClient(app)


def approval_row(**overrides):
    return {
        "id": APPROVAL,
        "owner_id": OWNER,
        "event_id": EVENT,
        "event_revision": 3,
        "action": "publish",
        "invitation_content_id": CONTENT,
        "content_hash": "0" * 32,
        "acknowledged_unknowns": True,
        "approved_at": "2026-10-16T12:05:00Z",
        **overrides,
    }


def test_repeated_approval_returns_the_original_with_200_after_a_201_create():
    fake = FakeSupabase()
    fake.rpc_results["organizer_approve"] = [
        httpx.Response(200, json=approval_row(replayed=False)),
        httpx.Response(200, json=approval_row(replayed=True)),
    ]
    body = {
        "expected_revision": 3,
        "action": "publish",
        "invitation_content_id": CONTENT,
        "acknowledged_unknowns": True,
    }
    with client_for(fake) as client:
        first = client.post(f"/api/events/{EVENT}/approvals", headers=AUTH, json=body)
        again = client.post(f"/api/events/{EVENT}/approvals", headers=AUTH, json=body)

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"] == APPROVAL
    assert "replayed" not in again.json() and "owner_id" not in again.json()


def test_approvals_list_recovers_prior_approval_for_a_revision():
    fake = FakeSupabase(approvals=[approval_row()])
    with client_for(fake) as client:
        response = client.get(f"/api/events/{EVENT}/approvals?revision=3", headers=AUTH)

    assert response.status_code == 200
    assert [a["id"] for a in response.json()] == [APPROVAL]
    assert (
        "approvals",
        {
            "owner_id": f"eq.{OWNER}",
            "event_id": f"eq.{EVENT}",
            "event_revision": "eq.3",
            "order": "approved_at.desc,id.desc",
            "limit": "100",
        },
    ) in (fake.calls)


def test_bindings_report_sent_gmail_as_stale_and_missing_calendar_as_null():
    gmail = {
        "event_id": EVENT,
        "event_revision": 2,
        "content_id": CONTENT,
        "draft_id": None,
        "message_id": "m-1",
        "thread_id": "t-1",
        "sent": True,
        "sent_history": [{"message_id": "m-1"}],
    }
    fake = FakeSupabase(provider_bindings=[{"provider": "gmail", "data": gmail}])
    with client_for(fake) as client:
        response = client.get(f"/api/events/{EVENT}/bindings", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "event_id": EVENT,
        "event_revision": 3,
        "calendar": None,
        "gmail": {**{k: v for k, v in gmail.items() if k != "event_id"}, "stale": True},
    }


def test_work_defaults_to_open_items_newest_first_without_owner_ids():
    item = {
        "owner_id": OWNER,
        "event_id": EVENT,
        "event_revision": 3,
        "kind": "prepare_content",
        "state": "awaiting_go",
        "payload": {},
        "claimed_at": None,
    }
    older = {**item, "id": "w-old", "created_at": "2026-10-16T11:00:00Z"}
    newer = {**item, "id": "w-new", "created_at": "2026-10-16T12:00:00Z"}
    fake = FakeSupabase(go_work=[{"data": older}, {"data": newer}])
    with client_for(fake) as client:
        response = client.get(f"/api/events/{EVENT}/work", headers=AUTH)

    assert [w["id"] for w in response.json()] == ["w-new", "w-old"]
    assert all("owner_id" not in w for w in response.json())
    query = next(params for name, params in fake.calls if name == "go_work")
    assert query["state"] == "in.(awaiting_go,running)"


@pytest.mark.parametrize("suffix", ["work", "bindings", "approvals", "inclusion"])
def test_reads_for_another_organizers_event_are_not_found(suffix):
    with client_for(FakeSupabase()) as client:
        response = client.get(
            f"/api/events/00000000-0000-4000-8000-0000000000ff/{suffix}", headers=AUTH
        )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_inclusion_before_any_save_is_version_zero_and_all_unknown():
    with client_for(FakeSupabase()) as client:
        response = client.get(f"/api/events/{EVENT}/inclusion", headers=AUTH)

    body = response.json()
    assert response.status_code == 200
    assert (body["version"], body["saved_at_event_revision"]) == (0, None)
    assert body["facts"]["step_free_entrance"] == {"value": "unknown", "source": None}
    statuses = {f["category"]: f["status"] for f in body["review"]["findings"]}
    assert statuses["step_free_entrance"] == "unknown"
    assert body["review"]["requires_review"] is True


def test_saving_facts_returns_new_version_and_observance_conflict_review():
    facts = {
        "step_free_entrance": {"value": "yes", "source": SOURCE},
        "elevator": {"value": "no"},  # no source: must stay unknown in the review
        "traditions": ["jewish"],
    }
    fake = FakeSupabase()
    fake.rpc_results["organizer_save_inclusion"] = [
        httpx.Response(
            200,
            json={
                "event_id": EVENT,
                "owner_id": OWNER,
                "version": 1,
                "event_revision": 3,
                "facts": facts,
                "updated_at": "2026-10-16T12:10:00Z",
            },
        )
    ]
    with client_for(fake) as client:
        response = client.put(
            f"/api/events/{EVENT}/inclusion",
            headers=AUTH,
            json={"expected_version": 0, "facts": facts},
        )

    body = response.json()
    assert response.status_code == 200
    assert (body["version"], body["saved_at_event_revision"]) == (1, 3)
    findings = {f["category"]: f for f in body["review"]["findings"]}
    assert findings["step_free_entrance"]["status"] == "recorded"
    assert findings["religious_observances"]["status"] == "attention"
    assert findings["religious_observances"]["conflicts"] == ["Synthetic Fast"]
    save = next(body for name, body in fake.calls if name == "organizer_save_inclusion")
    assert save["p_owner"] == OWNER and save["p_expected_version"] == 0
    assert save["p_facts"]["elevator"] == {"value": "no", "source": None}


def test_stale_inclusion_version_is_a_409_conflict():
    fake = FakeSupabase()
    fake.rpc_results["organizer_save_inclusion"] = [
        httpx.Response(400, json={"message": "revision_conflict"})
    ]
    with client_for(fake) as client:
        response = client.put(
            f"/api/events/{EVENT}/inclusion",
            headers=AUTH,
            json={"expected_version": 1, "facts": {}},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_conflict"


def test_inclusion_save_rejects_unknown_fact_fields():
    with client_for(FakeSupabase()) as client:
        response = client.put(
            f"/api/events/{EVENT}/inclusion",
            headers=AUTH,
            json={"expected_version": 0, "facts": {"wheelchair_ok": "yes"}},
        )
    assert response.status_code == 422
