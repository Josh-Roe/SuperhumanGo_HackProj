"""Organizer REST seam for the distribution preview the Go MCP tool already offers."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workflow_fakes import OWNER, World

from hackathon_backend.domain.models import DomainError
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.workflows.distribution_routes import distribution_router

TOKENS = {"Bearer owner-session": OWNER, "Bearer other-session": "owner-b"}


async def resolve_owner(authorization):
    if authorization not in TOKENS:
        raise DomainError("unauthenticated", "A Supabase session is required", 401)
    return TOKENS[authorization]


def client(world: World) -> TestClient:
    app = FastAPI()
    deps = EventToolDeps(world.store, principals=None, distributor=world.distributor)
    app.include_router(distribution_router(deps, resolve_owner))
    return TestClient(app)


def test_owner_sees_blockers_for_unwritten_invitation():
    response = client(World()).get(
        "/api/events/event-1/distribution/preview",
        headers={"Authorization": "Bearer owner-session"},
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["event_id"] == "event-1"
    assert plan["event_revision"] == 1
    assert plan["calendar_action"] == "create"
    assert plan["calendar_event_id"] is None
    assert plan["gmail_action"] == "create_draft"
    assert plan["invitee_count"] == 2
    assert plan["blockers"] == ["awaiting_go: no invitation for revision 1"]


def test_other_organizer_gets_not_found():
    response = client(World()).get(
        "/api/events/event-1/distribution/preview",
        headers={"Authorization": "Bearer other-session"},
    )
    assert response.status_code == 404
    assert "ada@example.com" not in response.text.lower()
