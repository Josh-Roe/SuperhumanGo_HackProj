"""Member 4's GoPreparationQueue and trusted Go content loader, backed by the Go work queue.

Matches `services/assets/requests.py` structurally (duck-typed) so this module does not import
Member 4's code before the branches merge. Composition wraps receipts in `ProseQueueReceipt`.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel

from hackathon_backend.workflows import go_work
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind, Producer, WorkItem
from hackathon_backend.workflows.ports import WorkflowStore

ASSET_BATCH = "asset_prose"
ASSET_KINDS = (
    ContentKind.FLYER_BRIEF,
    ContentKind.FLYER_COPY,
    ContentKind.EVENT_DOCUMENT,
    ContentKind.PLAIN_LANGUAGE_SUMMARY,
    ContentKind.FLYER_ALT_TEXT,
)


class ProseRequestLike(Protocol):
    owner_id: str
    event_id: str
    event_revision: int
    kinds: tuple[str, ...]
    idempotency_key: str


class QueueReceipt(BaseModel):
    owner_id: str
    event_id: str
    event_revision: int
    operation_id: str
    state: Literal["queued", "awaiting_go"]


class GoAssetQueue:
    """Queue an asset-prose batch for Go. A receipt never means prose exists yet."""

    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    async def enqueue(self, request: ProseRequestLike) -> QueueReceipt:
        kinds = [ContentKind(k) for k in request.kinds]
        if not set(kinds) <= set(ASSET_KINDS):
            raise WorkflowError("needs_review", "unsupported asset prose kind")
        event = await go_work.require_event(self.store, request.owner_id, request.event_id)
        if event.revision != request.event_revision:
            raise WorkflowError("revision_conflict", "event changed; request prose for current")
        # Durable stores must make this check-and-insert atomic per idempotency key.
        states = go_work.OPEN_STATES | {"succeeded"}
        for item in await self.store.list_work(request.owner_id, states):
            if item.payload.get("idempotency_key") == request.idempotency_key:
                return _receipt(item)
        item = await go_work.enqueue_preparation(
            self.store, request.owner_id, request.event_id, kinds, batch=ASSET_BATCH
        )
        item = item.model_copy(
            update={"payload": {**item.payload, "idempotency_key": request.idempotency_key}}
        )
        await self.store.put_work(item)
        return _receipt(item)


def _receipt(item: WorkItem) -> QueueReceipt:
    return QueueReceipt(
        owner_id=item.owner_id,
        event_id=item.event_id,
        event_revision=item.event_revision,
        operation_id=item.id,
        state="awaiting_go" if item.state == "awaiting_go" else "queued",
    )


async def load_go_content(
    store: WorkflowStore, owner_id: str, event_id: str, revision: int, kind: ContentKind
) -> dict[str, Any] | None:
    """Fields for Member 4's `GoContent`, read from server records written by the Go MCP tool."""
    saved = await store.latest_content(owner_id, event_id, revision, kind)
    if saved is None or saved.producer != Producer.SUPERHUMAN_GO:
        return None
    return {
        "event_id": saved.event_id,
        "owner_id": owner_id,
        "event_revision": saved.event_revision,
        "producer": saved.producer.value,
        "generation_id": saved.id,
        "kind": saved.kind.value,
        "body": saved.body,
        "reviewed_by_organizer": saved.state == "ready",
    }
