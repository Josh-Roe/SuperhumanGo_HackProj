"""One-write asset batch adapter for Member 3's existing Go work store.

The complete idempotency key must be present on the first durable write. Rewriting
an awaiting job's payload afterward does not update its durable deduplication key.
"""

from uuid import NAMESPACE_URL, uuid5

from hackathon_backend.services.assets.requests import (
    ASSET_PROSE_KINDS,
    ProseQueueReceipt,
    ProseRequest,
)
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import WorkItem, WorkKind
from hackathon_backend.workflows.ports import WorkflowStore


class StoredGoAssetQueue:
    """Only queues the five asset kinds; Go still claims/writes via Member 3's MCP tools."""

    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    async def enqueue(self, request: ProseRequest) -> ProseQueueReceipt:
        key = f"{request.owner_id}:{request.event_id}:r{request.event_revision}:go:asset-prose-v1"
        if request.kinds != ASSET_PROSE_KINDS or request.idempotency_key != key:
            raise WorkflowError("needs_review", "unexpected asset preparation batch")
        event = await self.store.get_event(request.owner_id, request.event_id)
        if event is None or event.owner_id != request.owner_id or event.id != request.event_id:
            raise WorkflowError("forbidden", "event not found for this organizer")
        if event.revision != request.event_revision:
            raise WorkflowError("revision_conflict", "event changed before queueing asset prose")
        states = {"awaiting_go", "running", "succeeded"}
        for prior in await self.store.list_work(request.owner_id, states):
            if (
                prior.event_id != request.event_id
                or prior.event_revision != request.event_revision
                or prior.kind != WorkKind.PREPARE_CONTENT
            ):
                continue
            same_batch = (
                prior.payload.get("batch") == "asset_prose"
                and tuple(prior.payload.get("kinds", ())) == request.kinds
            )
            if prior.payload.get("idempotency_key") == key or same_batch:
                return self._receipt(prior, request)
        item = WorkItem(
            id=str(uuid5(NAMESPACE_URL, f"urn:event-workspace:{key}")),
            owner_id=request.owner_id,
            event_id=request.event_id,
            event_revision=request.event_revision,
            kind=WorkKind.PREPARE_CONTENT,
            payload={"kinds": list(request.kinds), "batch": "asset_prose", "idempotency_key": key},
        )
        # Supabase validates current owner/revision and deduplicates atomically. Its adapter
        # updates item.id/state from the returned canonical row. No second payload write.
        await self.store.put_work(item)
        if item.state not in states:
            raise WorkflowError("needs_review", "existing asset batch requires reconciliation")
        return self._receipt(item, request)

    @staticmethod
    def _receipt(item: WorkItem, request: ProseRequest) -> ProseQueueReceipt:
        if item.owner_id != request.owner_id or item.event_id != request.event_id:
            raise WorkflowError("forbidden", "asset batch is outside the organizer/event scope")
        if item.event_revision != request.event_revision:
            raise WorkflowError("revision_conflict", "asset batch belongs to another revision")
        return ProseQueueReceipt(
            owner_id=item.owner_id,
            event_id=item.event_id,
            event_revision=item.event_revision,
            operation_id=item.id,
            state="awaiting_go" if item.state == "awaiting_go" else "queued",
        )
