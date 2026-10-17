"""Organizer REST view of the distribution plan the `preview_distribution` MCP tool returns.

`GET /api/events/{event_id}/distribution/preview` authenticates the organizer's Supabase
session and calls the same `Distributor.preview` as the Go tool, so the website and Go see one
plan: Calendar create/update, Gmail draft action, invitee count, and blockers. Read-only.
Missing and other-owner events both answer 404 so event IDs cannot be probed.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Header
from pydantic import Field
from starlette.responses import JSONResponse

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.pipeline import (
    ChatApprovals,
    SupabaseChatApprovals,
    event_progress,
)

OwnerResolver = Callable[[str | None], Awaitable[str]]
PathId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
STATUS = {
    "unauthenticated": 401,
    "forbidden": 404,  # require_event's answer for missing *and* foreign events
    "integration_not_connected": 503,
    "provider_failed": 502,
}


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"detail": {"code": code, "message": message}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def distribution_router(events: EventToolDeps, resolve_owner: OwnerResolver) -> APIRouter:
    router = APIRouter(prefix="/api/events/{event_id}/distribution", tags=["distribution"])

    @router.get("/preview")
    async def preview(event_id: PathId, authorization: Annotated[str | None, Header()] = None):
        try:
            owner_id = await resolve_owner(authorization)
        except DomainError as error:
            return _error(error.code, error.message, error.status)
        if events.distributor is None:
            return _error(
                "integration_not_connected", "Google OAuth is not configured on the server", 503
            )
        try:
            plan = await events.distributor.preview(owner_id, event_id)
        except WorkflowError as error:
            message = str(error).removeprefix(f"{error.code}: ")
            return _error(error.code, message, STATUS.get(error.code, 409))
        return JSONResponse(plan.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    return router


def progress_router(
    events: EventToolDeps, approvals: ChatApprovals, resolve_owner: OwnerResolver
) -> APIRouter:
    """`GET /api/events/{event_id}/progress`: the same guided-pipeline stages Go's
    `event_progress` tool returns, for the website's read-only progress view."""
    router = APIRouter(prefix="/api/events/{event_id}", tags=["distribution"])

    @router.get("/progress")
    async def progress(event_id: PathId, authorization: Annotated[str | None, Header()] = None):
        try:
            owner_id = await resolve_owner(authorization)
        except DomainError as error:
            return _error(error.code, error.message, error.status)
        try:
            report = await event_progress(
                events.store, approvals, events.distributor, owner_id, event_id
            )
        except WorkflowError as error:
            message = str(error).removeprefix(f"{error.code}: ")
            return _error(error.code, message, STATUS.get(error.code, 409))
        return JSONResponse(report, headers={"Cache-Control": "no-store"})

    return router


def register_distribution_routes(app: FastAPI, settings: Settings, events: EventToolDeps) -> None:
    """Supabase-mode composition, called from main.py before the MCP mount at "/"."""
    from hackathon_backend.auth.identity import authenticate

    async def resolve_owner(authorization: str | None) -> str:
        return (await authenticate(settings, authorization)).owner_id

    app.include_router(distribution_router(events, resolve_owner))
    app.include_router(progress_router(events, SupabaseChatApprovals(settings), resolve_owner))
