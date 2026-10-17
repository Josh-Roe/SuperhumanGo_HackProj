"""Member 2 router factory. Member 3 includes it before the catch-all MCP mount."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from hackathon_backend.api.inclusion import InclusionSave, InclusionView, read_inclusion
from hackathon_backend.api.read_models import WorkspaceResponse
from hackathon_backend.auth.connectors import issue_connector
from hackathon_backend.auth.identity import authenticate
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import (
    ApprovalInput,
    ApprovalRecord,
    ArtifactReview,
    BindingsResponse,
    ConnectorInput,
    ContentReview,
    DistributionInput,
    DomainError,
    ErrorResponse,
    EventInput,
    EventRecord,
    EventUpdate,
    IdempotencyKey,
    InclusionFactsResponse,
    InclusionFactsUpdate,
    RevisionInput,
    TaskInput,
    TaskRecord,
    TaskUpdate,
    WorkRecord,
    WorkState,
)
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.repositories.assets import SupabaseAssetStorage
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore
from hackathon_backend.services.assets.models import StaleRevisionError
from hackathon_backend.services.assets.preparation import EventAssetPreparationService
from hackathon_backend.services.inclusion import HolidayCalendar, InclusionInput
from hackathon_backend.workflows.distribution import DistributionPlan, DistributionResult
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
                    headers={
                        "Cache-Control": "no-store",
                        **({"WWW-Authenticate": "Bearer"} if error.status == 401 else {}),
                    },
                )
            except (WorkflowError, RevisionConflict, StaleRevisionError) as error:
                code = getattr(error, "code", "revision_conflict")
                return JSONResponse(
                    {"detail": {"code": code, "message": str(error)}},
                    409,
                    headers={"Cache-Control": "no-store"},
                )

        return handler


def create_router(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    events: EventToolDeps | None = None,
    holidays: HolidayCalendar | None = None,
) -> APIRouter:
    holidays = holidays or HolidayCalendar()
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
    async def list_events(repo: Repo, limit: Limit = 50, offset: Offset = 0):
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

    @router.post("/events/{event_id}/prepare", status_code=202, response_model=WorkItem)
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

    @router.get("/events/{event_id}/workspace", response_model=WorkspaceResponse)
    async def workspace(event_id: UUID, repo: Repo):
        return await repo.workspace(str(event_id))

    @router.get("/events/{event_id}/inclusion/revision", response_model=InclusionView)
    async def revision_inclusion(event_id: UUID, repo: Repo):
        return await read_inclusion(repo, str(event_id))

    @router.put("/events/{event_id}/inclusion/revision", response_model=EventRecord)
    async def save_revision_inclusion(event_id: UUID, payload: InclusionSave, repo: Repo):
        await repo.get("events", str(event_id))
        return await Database(settings, admin=True, transport=transport).rpc(
            "organizer_save_inclusion",
            p_owner=repo.owner_id,
            p_event=str(event_id),
            p_expected=payload.expected_revision,
            p_inputs=payload.facts.model_dump(mode="json"),
        )

    @router.post("/content/{content_id}/review")
    async def review_content(content_id: UUID, payload: ContentReview, repo: Repo):
        return await repo.review_content(
            str(content_id),
            payload.expected_revision,
            payload.body,
            payload.subject,
        )

    @router.post("/events/{event_id}/approvals", status_code=201, response_model=ApprovalRecord)
    async def approve(event_id: UUID, payload: ApprovalInput, repo: Repo, response: Response):
        """Idempotent per (revision, action, invitation_content_id): repeats return 200."""
        approval = await repo.approve(
            str(event_id),
            payload.expected_revision,
            str(payload.invitation_content_id),
            payload.action,
            payload.acknowledged_unknowns,
        )
        if approval.pop("replayed", False):
            response.status_code = 200
        return approval

    @router.get("/events/{event_id}/approvals", response_model=list[ApprovalRecord])
    async def approvals(
        event_id: UUID,
        repo: Repo,
        revision: Annotated[int | None, Query(ge=1)] = None,
    ):
        return await repo.list_approvals(str(event_id), revision)

    @router.get("/events/{event_id}/work", response_model=list[WorkRecord])
    async def work(
        event_id: UUID,
        repo: Repo,
        state: Annotated[list[WorkState] | None, Query()] = None,
    ):
        return await repo.list_work(str(event_id), set(state or ("awaiting_go", "running")))

    @router.get("/events/{event_id}/bindings", response_model=BindingsResponse)
    async def bindings(event_id: UUID, repo: Repo):
        return await repo.bindings(str(event_id))

    async def inclusion_view(repo: OrganizerRepository, event_id: str, row: dict | None):
        facts = InclusionInput.model_validate(row["facts"]) if row else InclusionInput()
        event = await repo.get("events", event_id)
        review = await EventAssetPreparationService(
            SupabaseWorkflowStore(repo.db), None, holidays
        ).inclusion(repo.owner_id, event_id, event["revision"], facts)
        return {
            "event_id": event_id,
            "version": row["version"] if row else 0,
            "saved_at_event_revision": row["event_revision"] if row else None,
            "updated_at": row["updated_at"] if row else None,
            "facts": facts,
            "review": review,
        }

    @router.get("/events/{event_id}/inclusion", response_model=InclusionFactsResponse)
    async def inclusion(event_id: UUID, repo: Repo):
        await repo.get("events", str(event_id))
        return await inclusion_view(repo, str(event_id), await repo.inclusion_facts(str(event_id)))

    @router.put("/events/{event_id}/inclusion", response_model=InclusionFactsResponse)
    async def save_inclusion(event_id: UUID, payload: InclusionFactsUpdate, repo: Repo):
        row = await repo.save_inclusion_facts(
            str(event_id), payload.expected_version, payload.facts.model_dump(mode="json")
        )
        return await inclusion_view(repo, str(event_id), row)

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

    @router.post("/events/{event_id}/artifacts/{artifact_id}/review")
    async def review_artifact(
        event_id: UUID,
        artifact_id: UUID,
        payload: ArtifactReview,
        repo: Repo,
    ):
        # The user session authorizes the event first. Only the server can mutate
        # trusted artifact metadata; browser column grants stay read-only.
        await repo.get("events", str(event_id))
        database = Database(settings, admin=True, transport=transport)
        return await database.rpc(
            "organizer_review_asset",
            p_owner=repo.owner_id,
            p_event=str(event_id),
            p_asset=str(artifact_id),
            p_expected=payload.expected_revision,
            p_hash=payload.sha256,
        )

    def distribution(request: Request):
        nonlocal events
        if events is None:
            # Member 3's middleware holds the actual shared production services.
            # Reuse them so REST observes the same provider policy/token cache as Go.
            events = next(
                (
                    middleware.kwargs.get("deps")
                    for middleware in request.app.user_middleware
                    if middleware.cls.__name__ == "MCPBearerAuth"
                ),
                None,
            )
        if events is None:
            from hackathon_backend.api.dependencies import create_tool_dependencies

            events = create_tool_dependencies(settings, transport=transport)
        if events.distributor is None:
            raise DomainError(
                "integration_not_connected", "Google distribution is not configured", 503
            )
        return events.distributor

    async def require_revision(repo: OrganizerRepository, event_id: UUID, expected: int):
        current = await repo.get("events", str(event_id))
        if current["revision"] != expected:
            raise DomainError("revision_conflict", "Event changed; reload before distribution")

    @router.post("/events/{event_id}/distribution/preview", response_model=DistributionPlan)
    async def distribution_preview(
        event_id: UUID, payload: RevisionInput, repo: Repo, request: Request
    ):
        await require_revision(repo, event_id, payload.expected_revision)
        plan = await distribution(request).preview(repo.owner_id, str(event_id))
        await require_revision(repo, event_id, payload.expected_revision)
        return plan

    @router.post("/events/{event_id}/distribution/execute", response_model=DistributionResult)
    async def distribution_execute(
        event_id: UUID, payload: DistributionInput, repo: Repo, request: Request
    ):
        await require_revision(repo, event_id, payload.expected_revision)
        return await distribution(request).execute(
            repo.owner_id, str(event_id), str(payload.approval_id)
        )

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
