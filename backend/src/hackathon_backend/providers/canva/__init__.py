"""Custom Canva designs over an organizer-scoped MCP session, not Brand Templates."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field

from hackathon_backend.services.assets.models import (
    Approval,
    BoundaryModel,
    DesignRef,
    EventSnapshot,
    GoContent,
    Identifier,
    StaleRevisionError,
    require_scope,
)


class CanvaError(RuntimeError):
    """Safe machine code; raw upstream content may include private URLs or copy."""


class CanvaToolSession(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class CreationJob(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int
    generation_id: Identifier
    state: Literal["pending", "completed", "failed"]
    job_id: str | None = None
    continuation_token: str | None = Field(default=None, repr=False, exclude=True)
    next_poll_at: AwareDatetime | None = None
    polling_instructions: str | None = None
    failure_code: str | None = None
    design: DesignRef | None = None


class ElementMapping(BoundaryModel):
    role: Literal["title", "when", "location", "description"]
    element_id: str = Field(min_length=1)
    previous_text: str = Field(min_length=1)


class EditPreview(BoundaryModel):
    design: DesignRef
    target_revision: int
    transaction_id: str = Field(repr=False)
    digest: str
    created_at: AwareDatetime
    expected: dict[str, str]
    previous: dict[str, str]
    thumbnail_urls: tuple[str, ...] = ()


class VerifiedDesign(BoundaryModel):
    design: DesignRef
    state: Literal["verified", "needs_review"]
    missing_roles: tuple[str, ...]
    stale_roles: tuple[str, ...] = ()
    organizer_reviewed: bool = False


def _object(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        if result.get("isError"):
            raise CanvaError("canva_tool_failed")
        if "structuredContent" in result or "content" in result:
            result = result.get("structuredContent") or result.get("content")
        else:
            return result
    else:
        if getattr(result, "isError", False):
            raise CanvaError("canva_tool_failed")
        structured = getattr(result, "structuredContent", None)
        if structured:
            return structured
        result = getattr(result, "content", result)
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        text = "\n".join(
            item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            for item in result
        )
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            return {"text": text}
        if isinstance(value, dict):
            return value
    raise CanvaError("unexpected_canva_response")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return "\n".join(_text(v) for k, v in value.items() if k not in {"urls", "id"})
    return ""


def _canva_url(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or url.username
        or url.password
        or not (url.hostname == "canva.com" or (url.hostname or "").endswith(".canva.com"))
    ):
        raise CanvaError("invalid_canva_design_url")
    return value


def _preview_digest(
    transaction_id: str,
    revision: int,
    design_id: str,
    expected: dict,
    previous: dict,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "transaction_id": transaction_id,
                "revision": revision,
                "design_id": design_id,
                "expected": expected,
                "previous": previous,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


class CanvaMCPAdapter:
    """Member 3 supplies an authenticated session for exactly this organizer.

    Uses official MCP names. A host connector can inject an explicit name map.
    Create/commit are never retried here: Member 3 must claim a durable operation
    first, persist returned IDs, and reconcile an uncertain write before retrying.
    """

    def __init__(
        self,
        session: CanvaToolSession,
        *,
        owner_id: str,
        tool_names: dict[str, str] | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.tool_names = dict(tool_names or {})

    async def _call(self, name: str, **arguments: Any) -> dict[str, Any]:
        arguments.setdefault("user_intent", "Prepare and review the organizer's event flyer.")
        try:
            result = await self.session.call_tool(self.tool_names.get(name, name), arguments)
        except Exception:
            raise CanvaError("canva_transport_failed_reconcile_before_retry") from None
        return _object(result)

    def _scope(self, event: EventSnapshot, *content: GoContent) -> None:
        require_scope(event, self.owner_id, *content)

    def _design_scope(self, design: DesignRef, event: EventSnapshot) -> None:
        self._scope(event)
        if design.owner_id != self.owner_id or design.event_id != event.id:
            raise PermissionError("Design is outside the event/organizer scope")

    async def create_flyer(
        self,
        event: EventSnapshot,
        brief: GoContent,
        *,
        now: datetime | None = None,
    ) -> CreationJob:
        self._scope(event, brief)
        if brief.kind != "flyer_brief":
            raise ValueError("Expected a Go-written custom flyer brief")
        canonical = json.dumps(event.flyer_fields(), ensure_ascii=False)
        result = await self._call(
            "create-design",
            brief=f"{brief.body}\n\nCanonical event fields (use exactly):\n{canonical}",
            format="Flyer (Portrait A4)",
            user_intent="Create a custom event flyer from the organizer's Go-prepared brief.",
        )
        return self._creation_state(event, brief.generation_id, result, now or datetime.now(UTC))

    def _creation_state(
        self,
        event: EventSnapshot,
        generation_id: str,
        result: dict[str, Any],
        now: datetime,
    ) -> CreationJob:
        base = dict(
            owner_id=self.owner_id,
            event_id=event.id,
            event_revision=event.revision,
            generation_id=generation_id,
        )
        status = result.get("status")
        if status == "failed":
            code = result.get("failure", {}).get("code", "failed")
            safe_code = (
                code
                if code
                in {
                    "quota_exceeded",
                    "quota_cooldown",
                    "moderation_blocked",
                    "feature_disabled",
                    "throttled",
                    "invalid_input",
                    "internal_error",
                }
                else "creation_failed"
            )
            return CreationJob(**base, state="failed", failure_code=safe_code)
        if status == "completed":
            design = result.get("design", {})
            try:
                ref = DesignRef(
                    **base,
                    design_id=design["id"],
                    edit_url=_canva_url(design.get("edit_url") or design["url"]),
                    view_url=_canva_url(design["url"]),
                )
            except (KeyError, ValueError):
                raise CanvaError("incomplete_created_design") from None
            return CreationJob(**base, state="completed", design=ref, job_id=result.get("job_id"))
        if status not in {"pending", "in_progress", "polled_too_early"}:
            raise CanvaError("unexpected_creation_status")
        wait = result.get("polling_policy", {}).get("wait_seconds")
        if not isinstance(wait, (int, float)) or not 0 <= wait <= 3600:
            raise CanvaError("missing_creation_poll_policy")
        if not result.get("job_id") or not result.get("continuation_token"):
            raise CanvaError("missing_creation_job_handle")
        return CreationJob(
            **base,
            state="pending",
            job_id=result["job_id"],
            continuation_token=result["continuation_token"],
            next_poll_at=now + timedelta(seconds=wait),
            polling_instructions=result.get("polling_policy", {}).get("instructions"),
        )

    async def poll_creation(
        self,
        event: EventSnapshot,
        job: CreationJob,
        *,
        now: datetime | None = None,
    ) -> CreationJob:
        self._scope(event)
        if job.owner_id != self.owner_id or job.event_id != event.id:
            raise PermissionError("Job is outside the event/organizer scope")
        if job.event_revision != event.revision:
            raise StaleRevisionError("Creation job was superseded")
        if job.state != "pending" or not job.continuation_token:
            raise ValueError("Only pending creation jobs can be polled")
        now = now or datetime.now(UTC)
        if job.next_poll_at and now < job.next_poll_at:
            raise ValueError("Canva polling window has not elapsed")
        result = await self._call(
            "get-create-design-async-job",
            job_id=job.job_id,
            continuation_token=job.continuation_token,
            user_intent="Check completion of the requested custom event flyer.",
        )
        return self._creation_state(event, job.generation_id, result, now)

    async def stage_update(
        self,
        event: EventSnapshot,
        design: DesignRef,
        copy: GoContent,
        mappings: tuple[ElementMapping, ...],
        *,
        now: datetime | None = None,
    ) -> EditPreview:
        self._design_scope(design, event)
        self._scope(event, copy)
        if copy.kind != "flyer_copy":
            raise ValueError("Expected Go flyer copy")
        if design.event_revision >= event.revision:
            raise StaleRevisionError("Update needs a newer event revision")
        roles = [mapping.role for mapping in mappings]
        if len(set(roles)) != len(roles) or not {"title", "when", "location"} <= set(roles):
            raise ValueError("Map unique title, when and location roles at minimum")
        if len({m.element_id for m in mappings}) != len(mappings):
            raise ValueError("Map separate text elements; combined text needs manual review")
        opened = await self._call("start-editing-transaction", design_id=design.design_id)
        transaction_id = opened.get("transaction", {}).get("transaction_id")
        if not transaction_id:
            raise CanvaError("missing_edit_transaction")
        try:
            elements = {item["element_id"]: item for item in opened.get("richtexts", [])}
            for mapping in mappings:
                element = elements.get(mapping.element_id)
                if (
                    not element
                    or element.get("page_index") != 1
                    or (
                        " ".join(_text(element.get("regions", [])).split())
                        != " ".join(mapping.previous_text.split())
                    )
                ):
                    raise CanvaError("element_mapping_changed_manual_review_required")
            expected = {**event.flyer_fields(), "description": copy.body}
            result = await self._call(
                "perform-editing-operations",
                transaction_id=transaction_id,
                page_index=1,
                operations=[
                    {"type": "replace_text", "element_id": m.element_id, "text": expected[m.role]}
                    for m in mappings
                ],
            )
        except Exception:
            await self._call("cancel-editing-transaction", transaction_id=transaction_id)
            raise
        expected = {m.role: expected[m.role] for m in mappings}
        previous = {m.role: m.previous_text for m in mappings}
        digest = _preview_digest(
            transaction_id, event.revision, design.design_id, expected, previous
        )
        return EditPreview(
            design=design.model_copy(update={"generation_id": copy.generation_id}),
            target_revision=event.revision,
            transaction_id=transaction_id,
            digest=digest,
            created_at=now or datetime.now(UTC),
            expected=expected,
            previous=previous,
            thumbnail_urls=tuple(t["url"] for t in result.get("thumbnails", []) if "url" in t),
        )

    async def commit_update(
        self,
        event: EventSnapshot,
        preview: EditPreview,
        approval: Approval,
    ) -> VerifiedDesign:
        self._design_scope(preview.design, event)
        if preview.target_revision != event.revision:
            raise StaleRevisionError("Edit preview was superseded")
        if (
            approval.owner_id != self.owner_id
            or approval.event_id != event.id
            or approval.event_revision != event.revision
            or approval.preview_digest != preview.digest
            or preview.digest
            != _preview_digest(
                preview.transaction_id,
                event.revision,
                preview.design.design_id,
                preview.expected,
                preview.previous,
            )
            or approval.approved_at < preview.created_at
        ):
            raise PermissionError("Organizer must approve this exact preview before commit")
        await self._call("commit-editing-transaction", transaction_id=preview.transaction_id)
        design = preview.design.model_copy(update={"event_revision": event.revision})
        result = await self.verify_text(event, design, preview.expected, previous=preview.previous)
        return result.model_copy(update={"organizer_reviewed": result.state == "verified"})

    async def verify_text(
        self,
        event: EventSnapshot,
        design: DesignRef,
        expected: dict[str, str],
        *,
        previous: dict[str, str] | None = None,
    ) -> VerifiedDesign:
        self._design_scope(design, event)
        if design.event_revision != event.revision:
            raise StaleRevisionError("Design belongs to another revision")
        if any(expected.get(role) != value for role, value in event.flyer_fields().items()):
            raise ValueError("Verification must include the exact canonical event fields")
        result = await self._call(
            "get-design-content",
            design_id=design.design_id,
            content_types=["richtexts"],
            pages=[1],
        )
        actual = " ".join(_text(result).split())
        missing = tuple(
            role for role, text in expected.items() if " ".join(text.split()) not in actual
        )
        current = " ".join(" ".join(value.split()) for value in expected.values())
        stale = tuple(
            role
            for role, value in (previous or {}).items()
            if " ".join(value.split()) not in current
            and re.search(r"(?<!\w)" + re.escape(" ".join(value.split())) + r"(?!\w)", actual)
        )
        return VerifiedDesign(
            design=design,
            state="needs_review" if missing or stale else "verified",
            missing_roles=missing,
            stale_roles=stale,
        )

    async def export_png(self, event: EventSnapshot, design: VerifiedDesign) -> dict[str, str]:
        self._design_scope(design.design, event)
        if design.state != "verified" or design.design.event_revision != event.revision:
            raise StaleRevisionError("Only the verified current flyer can be exported")
        result = await self._call(
            "export-design",
            design_id=design.design.design_id,
            format="png",
            user_intent="Export the verified event flyer for private versioned Storage.",
        )
        job = result.get("job", {})
        if job.get("status") != "success" or len(job.get("urls", [])) != 1:
            raise CanvaError("export_not_ready_or_not_single_page")
        return {"export_id": job["id"], "download_url": job["urls"][0]}
