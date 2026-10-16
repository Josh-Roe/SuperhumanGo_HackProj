"""Member 3 WorkflowStore adapter. Owner checks also apply to service-role callers."""

from typing import Any
from uuid import UUID

from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import (
    Approval,
    CalendarBinding,
    ContentKind,
    EventSnapshot,
    GeneratedContent,
    GmailBinding,
    InboundReply,
    Operation,
    RSVPObservation,
    WorkItem,
)
from hackathon_backend.workflows.ports import RevisionConflict


def uid(value: str) -> str:
    return str(UUID(value))


class SupabaseWorkflowStore:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def get_event(self, owner_id: str, event_id: str) -> EventSnapshot | None:
        try:
            return EventSnapshot.model_validate(
                await OrganizerRepository(self.db, owner_id).get("events", event_id),
            )
        except DomainError as error:
            if error.code == "not_found":
                return None
            raise

    async def _require(self, owner_id: str, event_id: str) -> EventSnapshot:
        event = await self.get_event(owner_id, event_id)
        if event is None:
            raise WorkflowError("forbidden", "Event not found for organizer")
        return event

    async def list_work(self, owner_id: str, states: set[str]) -> list[WorkItem]:
        rows = await self.db.rows("go_work", owner_id=f"eq.{uid(owner_id)}", limit=500)
        return [WorkItem.model_validate(r["data"]) for r in rows if r["state"] in states]

    async def get_work(self, owner_id: str, work_id: str) -> WorkItem | None:
        rows = await self.db.rows(
            "go_work", owner_id=f"eq.{uid(owner_id)}", id=f"eq.{uid(work_id)}"
        )
        return WorkItem.model_validate(rows[0]["data"]) if rows else None

    async def put_work(self, item: WorkItem) -> None:
        try:
            row = await self.db.rpc(
                "organizer_put_work",
                p_owner=uid(item.owner_id),
                p_data=item.model_dump(mode="json"),
            )
        except DomainError as error:
            raise WorkflowError(error.code, error.message) from None
        # Protocol returns None; propagate the canonical ID on deduped inserts to the caller.
        canonical = WorkItem.model_validate(row)
        item.id, item.created_at, item.state = canonical.id, canonical.created_at, canonical.state

    async def save_content(
        self,
        owner_id: str,
        content: GeneratedContent,
        expected_revision: int,
    ) -> GeneratedContent:
        try:
            row = await self.db.rpc(
                "organizer_save_content",
                p_owner=uid(owner_id),
                p_expected=expected_revision,
                p_data=content.model_dump(mode="json"),
            )
        except DomainError as error:
            if error.code == "revision_conflict":
                raise RevisionConflict(error.message) from None
            raise WorkflowError(error.code, error.message) from None
        return GeneratedContent.model_validate(row)

    async def get_content(self, owner_id: str, content_id: str) -> GeneratedContent | None:
        rows = await self.db.rows("generated_content", id=f"eq.{uid(content_id)}")
        if not rows or await self.get_event(owner_id, rows[0]["event_id"]) is None:
            return None
        return GeneratedContent.model_validate(rows[0])

    async def latest_content(
        self,
        owner_id: str,
        event_id: str,
        revision: int,
        kind: ContentKind,
    ) -> GeneratedContent | None:
        await self._require(owner_id, event_id)
        rows = await self.db.rows(
            "generated_content",
            event_id=f"eq.{uid(event_id)}",
            event_revision=f"eq.{revision}",
            kind=f"eq.{kind.value}",
            state="neq.superseded",
            order="created_at.desc,id.desc",
            limit=1,
        )
        return GeneratedContent.model_validate(rows[0]) if rows else None

    async def get_approval(self, owner_id: str, approval_id: str) -> Approval | None:
        rows = await self.db.rows(
            "approvals", owner_id=f"eq.{uid(owner_id)}", id=f"eq.{uid(approval_id)}"
        )
        return Approval.model_validate(rows[0]) if rows else None

    async def get_operation(self, owner_id: str, idempotency_key: str) -> Operation | None:
        rows = await self.db.rows("operations", idempotency_key=f"eq.{idempotency_key}")
        if not rows or await self.get_event(owner_id, rows[0]["event_id"]) is None:
            return None
        return Operation.model_validate(rows[0]["data"])

    async def put_operation(self, owner_id: str, operation: Operation) -> None:
        try:
            row = await self.db.rpc(
                "organizer_put_operation",
                p_owner=uid(owner_id),
                p_data=operation.model_dump(mode="json"),
            )
        except DomainError as error:
            raise WorkflowError(error.code, error.message) from None
        result = Operation.model_validate(row)
        operation.id, operation.attempts = result.id, result.attempts

    async def list_operations(self, owner_id: str, event_id: str) -> list[Operation]:
        await self._require(owner_id, event_id)
        return [
            Operation.model_validate(r["data"])
            for r in await self.db.rows(
                "operations",
                event_id=f"eq.{uid(event_id)}",
                order="created_at",
                limit=500,
            )
        ]

    async def reconcile_operation(
        self,
        owner_id: str,
        key: str,
        attempt: int,
        outcome: str,
        receipt: dict[str, Any],
    ) -> Operation:
        """Server worker only, after provider read-back. Never expose as a Go approval tool.

        `outcome` is succeeded or not_applied; ambiguous provider state stays blocked.
        """
        if not self.db.admin:
            raise WorkflowError("forbidden", "Only the server can reconcile provider operations")
        row = await self.db.rpc(
            "organizer_reconcile_operation",
            p_owner=uid(owner_id),
            p_key=key,
            p_attempt=attempt,
            p_outcome=outcome,
            p_receipt=receipt,
        )
        return Operation.model_validate(row)

    async def _binding(self, owner_id: str, event_id: str, provider: str) -> dict[str, Any] | None:
        await self._require(owner_id, event_id)
        rows = await self.db.rows(
            "provider_bindings",
            owner_id=f"eq.{uid(owner_id)}",
            event_id=f"eq.{uid(event_id)}",
            provider=f"eq.{provider}",
        )
        return rows[0]["data"] if rows else None

    async def _put_binding(self, owner_id: str, provider: str, binding: Any) -> None:
        event = await self._require(owner_id, binding.event_id)
        if binding.event_revision > event.revision:
            raise RevisionConflict("Binding targets a stale revision")
        await self.db.request(
            "POST",
            "/rest/v1/provider_bindings",
            params={"on_conflict": "owner_id,event_id,provider"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={
                "owner_id": uid(owner_id),
                "event_id": uid(binding.event_id),
                "provider": provider,
                "event_revision": binding.event_revision,
                "data": binding.model_dump(mode="json"),
            },
        )

    async def get_calendar_binding(self, owner_id: str, event_id: str) -> CalendarBinding | None:
        data = await self._binding(owner_id, event_id, "calendar")
        return CalendarBinding.model_validate(data) if data else None

    async def put_calendar_binding(self, owner_id: str, binding: CalendarBinding) -> None:
        await self._put_binding(owner_id, "calendar", binding)

    async def get_gmail_binding(self, owner_id: str, event_id: str) -> GmailBinding | None:
        data = await self._binding(owner_id, event_id, "gmail")
        return GmailBinding.model_validate(data) if data else None

    async def put_gmail_binding(self, owner_id: str, binding: GmailBinding) -> None:
        await self._put_binding(owner_id, "gmail", binding)

    async def add_rsvp(self, owner_id: str, observation: RSVPObservation) -> None:
        await self._require(owner_id, observation.event_id)
        # Append observations; dedupe exact source/status/observed_at without losing conflicts.
        await self.db.rpc(
            "organizer_record_rsvp",
            p_owner=uid(owner_id),
            p_data=observation.model_dump(mode="json"),
        )

    async def list_rsvps(self, owner_id: str, event_id: str) -> list[RSVPObservation]:
        await self._require(owner_id, event_id)
        rows = await self.db.rows(
            "rsvps", event_id=f"eq.{uid(event_id)}", order="observed_at", limit=500
        )
        return [RSVPObservation.model_validate(r["data"]) for r in rows]

    async def get_reply(self, owner_id: str, message_id: str) -> InboundReply | None:
        rows = await self.db.rows(
            "inbound_replies",
            owner_id=f"eq.{uid(owner_id)}",
            id=f"eq.{message_id}",
        )
        return InboundReply.model_validate(rows[0]["data"]) if rows else None

    async def put_reply(self, reply: InboundReply) -> None:
        await self._require(reply.owner_id, reply.event_id)
        await self.db.request(
            "POST",
            "/rest/v1/inbound_replies",
            params={"on_conflict": "owner_id,id"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={
                "owner_id": uid(reply.owner_id),
                "id": reply.id,
                "event_id": uid(reply.event_id),
                "data": reply.model_dump(mode="json"),
            },
        )
