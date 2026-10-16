"""Member 2 router factory. Member 3 includes it before the catch-all MCP mount."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from hackathon_backend.auth.connectors import issue_connector
from hackathon_backend.auth.identity import authenticate
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import (
    ApprovalInput,
    ConnectorInput,
    ContentReview,
    DomainError,
    ErrorResponse,
    EventInput,
    EventRecord,
    EventUpdate,
    IdempotencyKey,
    RevisionInput,
    TaskInput,
    TaskRecord,
    TaskUpdate,
)
from hackathon_backend.repositories.assets import SupabaseAssetStorage
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import WorkItem, WorkKind
from hackathon_backend.workflows.ports import RevisionConflict


class DomainRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                response = await original(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except RequestValidationError:
                return JSONResponse(
                    {"detail": {"code": "invalid_request", "message": "Input validation failed"}},
                    status_code=422,
                    headers={"Cache-Control": "no-store"},
                )
            except DomainError as error:
                return JSONResponse(
                    {"detail": {"code": error.code, "message": error.message}},
                    status_code=error.status,
                    headers={"WWW-Authenticate": "Bearer"} if error.status == 401 else None,
                )
            except (WorkflowError, RevisionConflict) as error:
                code = getattr(error, "code", "revision_conflict")
                return JSONResponse({"detail": {"code": code, "message": str(error)}}, 409)

        return handler


def create_router(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> APIRouter:
    router = APIRouter(
        prefix="/api",
        route_class=DomainRoute,
        responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 502, 503)},
    )

    async def repository(authorization: Annotated[str | None, Header()] = None):
        identity = await authenticate(settings, authorization, transport)
        return OrganizerRepository(
            Database(settings, token=identity.token, transport=transport),
            identity.owner_id,
        )

    Repo = Annotated[OrganizerRepository, Depends(repository)]
    Key = Annotated[IdempotencyKey, Header(alias="Idempotency-Key")]
    Limit = Annotated[int, Query(ge=1, le=100)]
    Offset = Annotated[int, Query(ge=0)]

    @router.get("/config")
    async def config():
        return {
            "supabase_url": settings.supabase_url,
            "supabase_publishable_key": settings.supabase_publishable_key,
            "configured": bool(settings.supabase_url and settings.supabase_publishable_key),
            "go_mode": "organizer_mcp",
            "provider_connections_verified": False,
        }

    @router.get("/events", response_model=list[EventRecord])
    async def events(repo: Repo, limit: Limit = 50, offset: Offset = 0):
        return await repo.list_records("events", limit, offset)

    @router.post("/events", response_model=EventRecord, status_code=201)
    async def create_event(payload: EventInput, repo: Repo, idempotency_key: Key):
        return await repo.create_event(payload, idempotency_key)

    @router.get("/events/{event_id}", response_model=EventRecord)
    async def event(event_id: UUID, repo: Repo):
        return await repo.get("events", str(event_id))

    @router.put("/events/{event_id}", response_model=EventRecord)
    async def update_event(event_id: UUID, payload: EventUpdate, repo: Repo):
        return await repo.update_event(str(event_id), payload)

    @router.get("/events/{event_id}/revisions")
    async def event_revisions(event_id: UUID, repo: Repo):
        return await repo.revisions("events", str(event_id))

    @router.get("/tasks", response_model=list[TaskRecord])
    async def tasks(repo: Repo, limit: Limit = 50, offset: Offset = 0):
        return await repo.list_records("tasks", limit, offset)

    @router.post("/tasks", response_model=TaskRecord, status_code=201)
    async def create_task(payload: TaskInput, repo: Repo, idempotency_key: Key):
        return await repo.create_task(payload, idempotency_key)

    @router.get("/tasks/{task_id}", response_model=TaskRecord)
    async def task(task_id: UUID, repo: Repo):
        return await repo.get("tasks", str(task_id))

    @router.put("/tasks/{task_id}", response_model=TaskRecord)
    async def update_task(task_id: UUID, payload: TaskUpdate, repo: Repo):
        return await repo.update_task(str(task_id), payload)

    @router.get("/tasks/{task_id}/revisions")
    async def task_revisions(task_id: UUID, repo: Repo):
        return await repo.revisions("tasks", str(task_id))

    @router.post("/events/{event_id}/prepare", status_code=202)
    async def prepare(event_id: UUID, payload: RevisionInput, repo: Repo):
        event = await repo.get("events", str(event_id))
        if event["revision"] != payload.expected_revision:
            raise DomainError("revision_conflict", "Event changed before preparation")
        work = WorkItem(
            owner_id=repo.owner_id,
            event_id=str(event_id),
            event_revision=event["revision"],
            kind=WorkKind.PREPARE_CONTENT,
            payload={
                "kinds": [
                    "description",
                    "summary",
                    "invitation",
                    "change_notice",
                    "flyer_brief",
                    "flyer_copy",
                    "event_document",
                    "plain_language_summary",
                    "flyer_alt_text",
                ],
                "batch": "event_and_assets_v1",
                "idempotency_key": f"{event_id}:{event['revision']}:event_and_assets_v1",
            },
        )
        await SupabaseWorkflowStore(repo.db).put_work(work)
        return work

    @router.get("/events/{event_id}/review")
    async def review(event_id: UUID, repo: Repo):
        event = await repo.get("events", str(event_id))
        return {
            "event": event,
            **{
                table: await repo.event_children(str(event_id), table)
                for table in ("generated_content", "artifacts", "inclusion_facts")
            },
        }

    @router.post("/content/{content_id}/review")
    async def review_content(content_id: UUID, payload: ContentReview, repo: Repo):
        return await repo.review_content(
            str(content_id),
            payload.expected_revision,
            payload.body,
            payload.subject,
        )

    @router.post("/events/{event_id}/approvals", status_code=201)
    async def approve(event_id: UUID, payload: ApprovalInput, repo: Repo):
        return await repo.approve(
            str(event_id),
            payload.expected_revision,
            str(payload.invitation_content_id),
            payload.action,
            payload.acknowledged_unknowns,
        )

    @router.get("/events/{event_id}/operations")
    async def operations(event_id: UUID, repo: Repo):
        return await SupabaseWorkflowStore(repo.db).list_operations(repo.owner_id, str(event_id))

    @router.get("/events/{event_id}/rsvps")
    async def rsvps(event_id: UUID, repo: Repo):
        return await SupabaseWorkflowStore(repo.db).list_rsvps(repo.owner_id, str(event_id))

    @router.get("/events/{event_id}/artifacts")
    async def artifacts(event_id: UUID, repo: Repo):
        return await repo.event_children(str(event_id), "artifacts")

    @router.get("/events/{event_id}/artifacts/{kind}/current")
    async def current_artifact(event_id: UUID, kind: str, repo: Repo):
        if kind not in {"event_document", "flyer_png"}:
            raise DomainError("not_found", "Artifact kind not found", 404)
        return await SupabaseAssetStorage(repo.db, repo.owner_id).current(str(event_id), kind)

    @router.post("/connectors", status_code=201)
    async def connector(payload: ConnectorInput, repo: Repo):
        return await issue_connector(repo.db, repo.owner_id, payload.label, payload.expires_in_days)

    @router.get("/connectors")
    async def connectors(repo: Repo):
        return await repo.db.rows(
            "connector_tokens",
            owner_id=f"eq.{repo.owner_id}",
            select="id,label,expires_at,revoked_at,created_at",
            order="created_at.desc",
            limit=100,
        )

    @router.delete("/connectors/{connector_id}", status_code=204)
    async def revoke_connector(connector_id: UUID, repo: Repo):
        await repo.db.request(
            "PATCH",
            "/rest/v1/connector_tokens",
            params={"id": f"eq.{connector_id}", "owner_id": f"eq.{repo.owner_id}"},
            json={"revoked_at": datetime.now(UTC).isoformat()},
        )

    return router
