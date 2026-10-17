"""Superhuman Go MCP tools that create and update the organizer's canonical events and tasks.

They mirror the website REST routes (`POST/PUT /api/events`, `/api/tasks`): creates need an
idempotency key, updates need the expected revision. The organizer is resolved from the bearer
connector token on every call; `owner_id` is never a tool argument.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlencode

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, HttpUrl, ValidationError

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import (
    DomainError,
    EventInput,
    EventUpdate,
    IdempotencyKey,
    InviteeInput,
    TaskInput,
    TaskUpdate,
)
from hackathon_backend.mcp_tools.event_tools import READ, WRITE, bearer_token
from hackathon_backend.workflows.models import Principal
from hackathon_backend.workflows.ports import PrincipalResolver

RecordId = Annotated[str, Field(min_length=1, max_length=64)]
Revision = Annotated[int, Field(ge=1)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
LongText = Annotated[str, Field(max_length=30_000)]
Limit = Annotated[int, Field(ge=1, le=100)]
TaskStatus = Literal["todo", "in_progress", "done"]


class OrganizerRecords(Protocol):
    """The subset of `OrganizerRepository` these tools use (lets tests inject a fake)."""

    async def list_records(self, kind: str, limit: int = 50, offset: int = 0) -> list[dict]: ...
    async def get(self, kind: str, record_id: str) -> dict[str, Any]: ...
    async def create_event(self, payload: EventInput, key: str) -> dict[str, Any]: ...
    async def update_event(self, event_id: str, payload: EventUpdate) -> dict[str, Any]: ...
    async def create_task(self, payload: TaskInput, key: str) -> dict[str, Any]: ...
    async def update_task(self, task_id: str, payload: TaskUpdate) -> dict[str, Any]: ...


RepositoryFactory = Callable[[Settings, Principal], OrganizerRecords]

EVENT_FIELDS = ("title", "description", "location", "starts_at", "ends_at", "timezone")
EVENT_FIELDS += ("links", "organizer_contact")
TASK_FIELDS = ("title", "description", "status", "due_at", "event_id")


def _default_factory(settings: Settings, principal: Principal) -> OrganizerRecords:
    from hackathon_backend.api.dependencies import task_repository

    return task_repository(settings, principal)


def event_summary(row: dict[str, Any], app_url: str = "") -> dict[str, Any]:
    """Saved id/revision, key facts and dashboard link. Invitee emails stay out of Go's context."""
    invitees = row.get("invitees") or []
    summary = {
        "id": row["id"],
        "revision": row["revision"],
        "status": row.get("status"),
        "title": row.get("title"),
        "starts_at": row.get("starts_at"),
        "ends_at": row.get("ends_at"),
        "timezone": row.get("timezone"),
        "location": row.get("location"),
        "invitee_count": len(invitees),
        "updated_at": row.get("updated_at"),
    }
    if app_url:
        summary["dashboard_url"] = f"{app_url}/?{urlencode({'event': row['id']})}"
    return summary


def task_summary(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "revision", "title", "status", "due_at", "event_id", "updated_at")
    return {key: row.get(key) for key in keys}


def _validation_message(error: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in item['loc']) or 'input'}: {item['msg']}"
        for item in error.errors()[:5]
    ]
    return "invalid_request: " + "; ".join(parts)


async def _call(coro):
    try:
        return await coro
    except DomainError as error:
        raise ToolError(f"{error.code}: {error.message}") from None
    except ValueError as error:  # malformed UUIDs from the repository
        raise ToolError(f"invalid_request: {error}") from None


def register_organizer_tools(
    mcp: FastMCP,
    settings: Settings,
    principals: PrincipalResolver,
    repository_factory: RepositoryFactory | None = None,
) -> None:
    factory = repository_factory or _default_factory

    async def repo(ctx: Context) -> OrganizerRecords:
        token = bearer_token(ctx)
        found = await principals.resolve(token) if token else None
        if found is None:
            raise ToolError(
                "unauthenticated: install the connector with your personal organizer token"
            )
        try:
            return factory(settings, found)
        except DomainError as error:
            raise ToolError(f"{error.code}: {error.message}") from None

    def build(model, data: dict[str, Any]):
        try:
            return model.model_validate(data)
        except ValidationError as error:
            raise ToolError(_validation_message(error)) from None

    @mcp.tool(annotations=READ)
    async def list_events(ctx: Context, limit: Limit = 50) -> list[dict[str, Any]]:
        """List your events (newest first) with id, revision, status, time and location.

        Use an event's `revision` as `expected_revision` for update_event. Invitee emails are not
        returned; get_event gives the full event.
        """
        records = await repo(ctx)
        rows = await _call(records.list_records("events", limit, 0))
        return [event_summary(row, settings.app_url) for row in rows]

    @mcp.tool(annotations=WRITE)
    async def create_event(
        idempotency_key: IdempotencyKey,
        title: Title,
        starts_at: datetime,
        ends_at: datetime,
        timezone: Annotated[str, Field(max_length=100)],
        ctx: Context,
        description: LongText = "",
        location: Annotated[str, Field(max_length=500)] = "",
        links: Annotated[list[HttpUrl], Field(max_length=20)] | None = None,
        organizer_contact: Annotated[str, Field(max_length=500)] = "",
        invitees: Annotated[list[InviteeInput], Field(max_length=500)] | None = None,
    ) -> dict[str, Any]:
        """Create an event ONLY when the organizer asks you to in this conversation.

        Confirm the details with the organizer first. Use only facts they gave you: never invent a
        venue, time, accessibility detail or contact; leave unknown fields empty so they stay
        unknown. starts_at/ends_at need a UTC offset; timezone is an IANA name such as
        "America/New_York". `idempotency_key` is any unique string you choose for this request
        (for example "go-create-<short description>-<date>"); reuse the SAME key if you retry so
        the event is not created twice. A different payload with a used key fails with
        idempotency_conflict. Returns the saved id, revision (1) and, when configured, a
        dashboard_url: give it to the organizer so they can open the event in the website.
        Creating an event does not write prose, send email or create Calendar invites; the
        organizer prepares, reviews and publishes in the website.
        """
        records = await repo(ctx)
        payload = build(
            EventInput,
            {
                "title": title,
                "description": description,
                "location": location,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "timezone": timezone,
                "links": links or [],
                "organizer_contact": organizer_contact,
                "invitees": invitees or [],
            },
        )
        return event_summary(
            await _call(records.create_event(payload, idempotency_key)), settings.app_url
        )

    @mcp.tool(annotations=WRITE)
    async def update_event(
        event_id: RecordId,
        expected_revision: Revision,
        ctx: Context,
        title: Title | None = None,
        description: LongText | None = None,
        location: Annotated[str, Field(max_length=500)] | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        timezone: Annotated[str, Field(max_length=100)] | None = None,
        links: Annotated[list[HttpUrl], Field(max_length=20)] | None = None,
        organizer_contact: Annotated[str, Field(max_length=500)] | None = None,
        invitees: Annotated[list[InviteeInput], Field(max_length=500)] | None = None,
    ) -> dict[str, Any]:
        """Change an event ONLY when the organizer asks you to; confirm the change first.

        Pass only the fields that change; omitted fields keep their saved values. `invitees`, if
        given, REPLACES the whole guest list. `expected_revision` must be the revision you last
        read (list_events/get_event); if the event changed since, this fails with
        revision_conflict: re-read it and confirm with the organizer again. Never invent facts.
        Returns the saved id and the NEW revision. Saving marks the event "changed" and
        supersedes Go drafts, flyers and queued Go work for the old revision. Nothing is sent:
        the organizer re-runs preparation and reviews/approves the update in the website before
        any Calendar update or change notice goes out.
        """
        records = await repo(ctx)
        current = await _call(records.get("events", event_id))
        data = {field: current.get(field) for field in EVENT_FIELDS}
        data["links"] = data["links"] or []
        data["invitees"] = [
            {"email": i["email"], "display_name": i.get("display_name")}
            for i in current.get("invitees") or []
        ]
        changes = {
            "title": title,
            "description": description,
            "location": location,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "timezone": timezone,
            "links": links,
            "organizer_contact": organizer_contact,
            "invitees": invitees,
        }
        data.update({key: value for key, value in changes.items() if value is not None})
        payload = build(EventUpdate, {**data, "expected_revision": expected_revision})
        return event_summary(await _call(records.update_event(event_id, payload)), settings.app_url)

    @mcp.tool(annotations=READ)
    async def list_tasks(ctx: Context, limit: Limit = 50) -> list[dict[str, Any]]:
        """List your organizer tasks (newest first) with id, revision, status and due date."""
        records = await repo(ctx)
        rows = await _call(records.list_records("tasks", limit, 0))
        return [task_summary(row) for row in rows]

    @mcp.tool(annotations=WRITE)
    async def create_task(
        idempotency_key: IdempotencyKey,
        title: Title,
        ctx: Context,
        description: LongText = "",
        status: TaskStatus = "todo",
        due_at: datetime | None = None,
        event_id: RecordId | None = None,
    ) -> dict[str, Any]:
        """Create an organizer to-do ONLY when the organizer asks; confirm it first.

        Optionally link it to one of their events with event_id. due_at needs a UTC offset.
        Reuse the SAME idempotency_key when retrying so the task is not duplicated. Returns the
        saved id and revision.
        """
        records = await repo(ctx)
        payload = build(
            TaskInput,
            {
                "title": title,
                "description": description,
                "status": status,
                "due_at": due_at,
                "event_id": event_id,
            },
        )
        return task_summary(await _call(records.create_task(payload, idempotency_key)))

    @mcp.tool(annotations=WRITE)
    async def update_task(
        task_id: RecordId,
        expected_revision: Revision,
        ctx: Context,
        title: Title | None = None,
        description: LongText | None = None,
        status: TaskStatus | None = None,
        due_at: datetime | None = None,
        clear_due_at: bool = False,
        event_id: RecordId | None = None,
    ) -> dict[str, Any]:
        """Change a task (e.g. mark it done) ONLY when the organizer asks.

        Pass only fields that change; set clear_due_at=true to remove the due date.
        `expected_revision` is the revision you last read; revision_conflict means it changed:
        re-read with list_tasks. Returns the saved id and NEW revision.
        """
        records = await repo(ctx)
        current = await _call(records.get("tasks", task_id))
        data = {field: current.get(field) for field in TASK_FIELDS}
        changes = {
            "title": title,
            "description": description,
            "status": status,
            "due_at": due_at,
            "event_id": event_id,
        }
        data.update({key: value for key, value in changes.items() if value is not None})
        if clear_due_at:
            data["due_at"] = None
        payload = build(TaskUpdate, {**data, "expected_revision": expected_revision})
        return task_summary(await _call(records.update_task(task_id, payload)))
