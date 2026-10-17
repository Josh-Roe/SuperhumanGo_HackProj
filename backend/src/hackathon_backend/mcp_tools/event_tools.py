"""Organizer-scoped MCP tools that Superhuman Go calls to read events, save prose, and coordinate.

Each organizer installs the Go connector with their own connector token; the tool resolves that
token to a Principal on every call. The global development MCP token authorizes no event data.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from hackathon_backend.workflows import go_work
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind, Principal
from hackathon_backend.workflows.ports import PrincipalResolver, WorkflowStore
from hackathon_backend.workflows.rsvp import RSVPTracker

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
SEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
SYNC = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)

EventId = Annotated[str, Field(min_length=1, max_length=128)]
Body = Annotated[str, Field(min_length=1, max_length=20_000)]


@dataclass
class EventToolDeps:
    store: WorkflowStore
    principals: PrincipalResolver
    distributor: Distributor | None = None  # None until Google OAuth is configured
    rsvp: RSVPTracker | None = None


def bearer_token(ctx: Context) -> str:
    request = ctx.request_context.request
    header = request.headers.get("authorization", "") if request is not None else ""
    scheme, _, credential = header.partition(" ")
    return credential.strip() if scheme.lower() == "bearer" else ""


async def principal(deps: EventToolDeps, ctx: Context) -> Principal:
    token = bearer_token(ctx)
    found = await deps.principals.resolve(token) if token else None
    if found is None:
        raise ToolError("unauthenticated: install the connector with your personal organizer token")
    return found


def _google(deps: EventToolDeps):
    if deps.distributor is None or deps.rsvp is None:
        raise ToolError("integration_not_connected: Google OAuth is not configured on the server")
    return deps.distributor, deps.rsvp


async def _run(coro):
    try:
        return await coro
    except WorkflowError as error:
        raise ToolError(str(error)) from None


def register_event_tools(mcp: FastMCP, deps: EventToolDeps) -> None:
    @mcp.tool(annotations=READ)
    async def get_event(event_id: EventId, ctx: Context) -> dict[str, Any]:
        """Read one of your events at its current revision, plus Go content already saved for it.

        Use `revision` as `expected_revision` when saving content. Facts marked unknown must stay
        unknown in anything you write.
        """
        who = await principal(deps, ctx)
        event = await _run(go_work.require_event(deps.store, who.owner_id, event_id))
        content = {}
        for kind in ContentKind:
            saved = await deps.store.latest_content(who.owner_id, event_id, event.revision, kind)
            if saved:
                content[kind.value] = {
                    "id": saved.id,
                    "state": saved.state,
                    "subject": saved.subject,
                    "body": saved.body,
                }
        snapshot = event.model_dump(mode="json", exclude={"owner_id"})
        snapshot["invitee_count"] = len(event.invitees)
        snapshot["invitees"] = [i.display_name or "guest" for i in event.invitees]  # no emails
        return {"event": snapshot, "content_for_this_revision": content}

    @mcp.tool(annotations=READ)
    async def list_go_work(ctx: Context) -> list[dict[str, Any]]:
        """List your events' work waiting for Go: content to write or RSVP replies to classify."""
        who = await principal(deps, ctx)
        items = await go_work.list_open_work(deps.store, who.owner_id)
        return [item.model_dump(mode="json", exclude={"owner_id"}) for item in items]

    @mcp.tool(annotations=WRITE)
    async def claim_go_work(
        work_id: Annotated[str, Field(max_length=64)], ctx: Context
    ) -> dict[str, Any]:
        """Mark a work item as running so the website shows Go is working on it."""
        who = await principal(deps, ctx)
        item = await _run(go_work.claim_work(deps.store, who.owner_id, work_id))
        return item.model_dump(mode="json", exclude={"owner_id"})

    @mcp.tool(annotations=WRITE)
    async def save_generated_content(
        event_id: EventId,
        expected_revision: Annotated[int, Field(ge=1)],
        kind: ContentKind,
        body: Body,
        ctx: Context,
        subject: Annotated[str | None, Field(max_length=200)] = None,
        work_id: Annotated[str | None, Field(max_length=64)] = None,
    ) -> dict[str, Any]:
        """Save prose you (Superhuman Go) wrote for an event revision, for organizer review.

        Kinds: description, summary (plain language), invitation, change_notice, document,
        and flyer assets: flyer_brief, flyer_copy, event_document,
        plain_language_summary, flyer_alt_text. Invitation and change_notice need a subject.
        Never include invitee emails or private dietary/accessibility details. Fails with
        revision_conflict if the event changed; re-read it and rewrite.
        """
        who = await principal(deps, ctx)
        saved = await _run(
            go_work.save_go_content(
                deps.store,
                who.owner_id,
                event_id=event_id,
                expected_revision=expected_revision,
                kind=kind,
                body=body,
                subject=subject,
                work_id=work_id,
            )
        )
        return saved.model_dump(mode="json")

    @mcp.tool(annotations=READ)
    async def preview_distribution(event_id: EventId, ctx: Context) -> dict[str, Any]:
        """Show what publishing/updating would do: Calendar create/update, Gmail draft action."""
        who = await principal(deps, ctx)
        distributor, _ = _google(deps)
        plan = await _run(distributor.preview(who.owner_id, event_id))
        return plan.model_dump(mode="json")

    @mcp.tool(annotations=SEND)
    async def execute_distribution(
        event_id: EventId, approval_id: Annotated[str, Field(max_length=64)], ctx: Context
    ) -> dict[str, Any]:
        """Execute an organizer approval made in the website: Calendar invite + Gmail send.

        Only works with an approval_id the organizer created for the current revision. Safe to
        retry: completed steps are reused, never repeated.
        """
        who = await principal(deps, ctx)
        distributor, _ = _google(deps)
        result = await _run(distributor.execute(who.owner_id, event_id, approval_id))
        return result.model_dump(mode="json")

    @mcp.tool(annotations=SYNC)
    async def sync_rsvps(event_id: EventId, ctx: Context) -> dict[str, Any]:
        """Pull guests' Calendar responses (Yes / Maybe / No). Email replies are not read."""
        who = await principal(deps, ctx)
        _, tracker = _google(deps)
        changed = await _run(tracker.sync_calendar(who.owner_id, event_id))
        return {"calendar_changes": changed}

    @mcp.tool(annotations=READ)
    async def list_rsvps(event_id: EventId, ctx: Context) -> list[dict[str, Any]]:
        """Current RSVP status per invitee, with conflicts flagged. Private notes are omitted."""
        who = await principal(deps, ctx)
        if deps.rsvp is None:
            raise ToolError("integration_not_connected: Google OAuth is not configured")
        rows = await _run(deps.rsvp.summary(who.owner_id, event_id))
        return [row.model_dump(mode="json", exclude={"private_note", "email"}) for row in rows]
