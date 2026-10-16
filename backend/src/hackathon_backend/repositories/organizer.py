"""Canonical event/task services used by both the website and custom Go tools."""

from typing import Any, Literal
from uuid import UUID

from hackathon_backend.domain.models import (
    DomainError,
    EventInput,
    EventUpdate,
    TaskInput,
    TaskUpdate,
)
from hackathon_backend.repositories.transport import Database


class OrganizerRepository:
    def __init__(self, database: Database, owner_id: str) -> None:
        self.db, self.owner_id = database, str(UUID(owner_id))

    async def list_records(
        self,
        kind: Literal["events", "tasks"],
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if kind not in {"events", "tasks"}:
            raise ValueError("Unsupported record kind")
        filters = (
            {"select": "*,invitees(id,email,display_name)", "invitees.active": "eq.true"}
            if kind == "events"
            else {}
        )
        rows = await self.db.rows(
            kind,
            owner_id=f"eq.{self.owner_id}",
            order="updated_at.desc,id.desc",
            limit=min(max(limit, 1), 100),
            offset=max(0, offset),
            **filters,
        )
        return rows

    async def get(self, kind: Literal["events", "tasks"], record_id: str) -> dict[str, Any]:
        record_id = str(UUID(record_id))
        if kind == "events":
            row = await self.db.rpc(
                "organizer_event_json",
                p_owner=self.owner_id,
                p_id=record_id,
            )
        else:
            rows = await self.db.rows(kind, id=f"eq.{record_id}", owner_id=f"eq.{self.owner_id}")
            row = rows[0] if rows else None
        if row is None:
            raise DomainError("not_found", "Record not found", 404)
        return row

    async def create_event(self, payload: EventInput, key: str) -> dict[str, Any]:
        return await self._write("events", payload, key=key)

    async def update_event(self, event_id: str, payload: EventUpdate) -> dict[str, Any]:
        return await self._write("events", payload, record_id=event_id)

    async def create_task(self, payload: TaskInput, key: str) -> dict[str, Any]:
        return await self._write("tasks", payload, key=key)

    async def update_task(self, task_id: str, payload: TaskUpdate) -> dict[str, Any]:
        return await self._write("tasks", payload, record_id=task_id)

    async def _write(
        self,
        kind: str,
        payload: EventInput | TaskInput,
        *,
        key: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.db.rpc(
            "organizer_write_record",
            p_owner=self.owner_id,
            p_kind=kind,
            p_id=str(UUID(record_id)) if record_id else None,
            p_expected=getattr(payload, "expected_revision", None),
            p_key=key,
            p_data=payload.model_dump(mode="json", exclude={"expected_revision"}),
        )

    async def revisions(self, kind: str, record_id: str) -> list[dict[str, Any]]:
        await self.get(kind, record_id)
        return await self.db.rows(
            "record_versions",
            owner_id=f"eq.{self.owner_id}",
            kind=f"eq.{kind}",
            record_id=f"eq.{UUID(record_id)}",
            order="revision.desc",
            limit=100,
        )

    async def review_content(
        self,
        content_id: str,
        revision: int,
        body: str | None,
        subject: str | None,
    ) -> dict[str, Any]:
        return await self.db.rpc(
            "organizer_review_content",
            p_owner=self.owner_id,
            p_content=str(UUID(content_id)),
            p_expected=revision,
            p_body=body,
            p_subject=subject,
        )

    async def approve(
        self,
        event_id: str,
        revision: int,
        content_id: str,
        action: str,
        acknowledged: bool,
    ) -> dict[str, Any]:
        return await self.db.rpc(
            "organizer_approve",
            p_owner=self.owner_id,
            p_event=str(UUID(event_id)),
            p_expected=revision,
            p_content=str(UUID(content_id)),
            p_action=action,
            p_acknowledged=acknowledged,
        )

    async def event_children(self, event_id: str, table: str) -> list[dict[str, Any]]:
        if table not in {
            "generated_content",
            "operations",
            "rsvps",
            "artifacts",
            "inclusion_facts",
        }:
            raise ValueError("Unsupported event child table")
        await self.get("events", event_id)
        return await self.db.rows(table, event_id=f"eq.{UUID(event_id)}", limit=500)
