"""Guided-pipeline MCP tools: Go walks the organizer from event details to sent invitations.

`event_progress` tells Go which stage comes next. `approve_draft`, `save_inclusion_facts` and
`send_invitations` record what the organizer confirmed in the Go chat (user decision
2026-10-16: approval happens in Go). The organizer is resolved from the bearer token each call.
"""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, ValidationError

from hackathon_backend.mcp_tools.event_tools import (
    READ,
    SEND,
    WRITE,
    Body,
    EventId,
    EventToolDeps,
    _run,
    principal,
)
from hackathon_backend.services.inclusion import InclusionInput
from hackathon_backend.workflows import pipeline
from hackathon_backend.workflows.models import utcnow
from hackathon_backend.workflows.pipeline import ChatApprovals

Revision = Annotated[int, Field(ge=1)]
Answer = Literal["yes", "no", "unknown"] | None
FACTS = ("step_free_entrance", "elevator", "food_served", "captions", "loud_sound", "strobes")


def register_pipeline_tools(mcp: FastMCP, deps: EventToolDeps, approvals: ChatApprovals) -> None:
    @mcp.tool(annotations=READ)
    async def event_progress(event_id: EventId, ctx: Context) -> dict[str, Any]:
        """Where an event is in the pipeline: details, writing, review, inclusion, flyer, send,
        rsvps. Call it at the start and after every step; work on `next_stage`."""
        who = await principal(deps, ctx)
        return await _run(
            pipeline.event_progress(deps.store, approvals, deps.distributor, who.owner_id, event_id)
        )

    @mcp.tool(annotations=WRITE)
    async def approve_draft(
        content_id: Annotated[str, Field(min_length=1, max_length=64)],
        expected_revision: Revision,
        ctx: Context,
        subject: Annotated[str | None, Field(max_length=200)] = None,
        body: Body | None = None,
    ) -> dict[str, Any]:
        """Mark a draft approved after the organizer read it in chat and said it is good.

        Pass subject/body only when the organizer asked for changes; the edited text is saved as
        the organizer's version. Approving does not send anything.
        """
        who = await principal(deps, ctx)
        saved = await _run(
            approvals.mark_ready(who.owner_id, content_id, expected_revision, body, subject)
        )
        keys = ("id", "kind", "state", "event_revision", "subject")
        return {key: saved.get(key) for key in keys}

    @mcp.tool(annotations=WRITE)
    async def save_inclusion_facts(
        event_id: EventId,
        ctx: Context,
        step_free_entrance: Answer = None,
        elevator: Answer = None,
        food_served: Answer = None,
        captions: Answer = None,
        loud_sound: Answer = None,
        strobes: Answer = None,
        diet_options: Annotated[list[str] | None, Field(max_length=20)] = None,
    ) -> dict[str, Any]:
        """Save the organizer's own answers about the venue and event. Omitted answers keep their
        saved value. Use "unknown" when the organizer does not know; never guess."""
        who = await principal(deps, ctx)
        row = await _run(approvals.inclusion_facts(who.owner_id, event_id)) or {}
        facts = dict(row.get("facts") or {})
        source = {
            "label": "Organizer answer in Superhuman Go chat",
            "observed_at": utcnow().isoformat(),
            "confirmed_by": "organizer",
        }
        answers = (step_free_entrance, elevator, food_served, captions, loud_sound, strobes)
        for name, value in zip(FACTS, answers, strict=True):
            if value is not None:
                facts[name] = {"value": value, "source": None if value == "unknown" else source}
        if diet_options is not None:
            facts["diet_options"] = [option.strip()[:100] for option in diet_options]
            facts["diet_source"] = source if diet_options else None
        try:
            checked = InclusionInput.model_validate(facts).model_dump(mode="json")
        except ValidationError as error:
            raise ToolError(f"invalid_request: {error.errors()[0]['msg']}") from None
        saved = await _run(
            approvals.save_inclusion(who.owner_id, event_id, row.get("version", 0), checked)
        )
        summary = {name: checked[name]["value"] for name in FACTS}
        return {"version": saved["version"], **summary, "diet_options": checked["diet_options"]}

    @mcp.tool(annotations=SEND)
    async def send_invitations(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Send the approved invitation (or change notice) for this revision: Calendar invite
        plus Gmail email to every guest. Only after the organizer says to send in this chat.
        Safe to retry: completed steps are reused, never repeated."""
        who = await principal(deps, ctx)
        if deps.distributor is None:
            raise ToolError("integration_not_connected: Google OAuth is not configured")
        return await _run(
            pipeline.send_invitations(
                deps.store,
                approvals,
                deps.distributor,
                who.owner_id,
                event_id,
                expected_revision,
            )
        )
