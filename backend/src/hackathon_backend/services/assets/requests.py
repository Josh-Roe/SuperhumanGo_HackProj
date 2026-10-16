"""Explicit handoff to Member 3's durable Superhuman Go queue; no inference API."""

from typing import Literal, Protocol

from hackathon_backend.services.assets.models import (
    BoundaryModel,
    EventSnapshot,
    Identifier,
    StaleRevisionError,
    require_scope,
)

ASSET_PROSE_KINDS = (
    "flyer_brief",
    "flyer_copy",
    "event_document",
    "plain_language_summary",
    "flyer_alt_text",
)


class ProseRequest(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int
    producer: Literal["superhuman_go"] = "superhuman_go"
    kinds: tuple[str, ...] = ASSET_PROSE_KINDS
    idempotency_key: str


class ProseQueueReceipt(BoundaryModel):
    owner_id: Identifier
    event_id: Identifier
    event_revision: int
    operation_id: Identifier
    state: Literal["queued", "awaiting_go"]


class GoPreparationQueue(Protocol):
    async def enqueue(self, request: ProseRequest) -> ProseQueueReceipt:
        """Atomically check current owner/revision and deduplicate the batch key."""
        ...


async def request_event_prose(
    event: EventSnapshot,
    queue: GoPreparationQueue,
    *,
    owner_id: str,
) -> ProseQueueReceipt:
    require_scope(event, owner_id)
    request = ProseRequest(
        owner_id=owner_id,
        event_id=event.id,
        event_revision=event.revision,
        idempotency_key=f"{owner_id}:{event.id}:r{event.revision}:go:asset-prose-v1",
    )
    receipt = await queue.enqueue(request)
    if receipt.owner_id != owner_id or receipt.event_id != event.id:
        raise PermissionError("Go queue receipt is outside the event/organizer scope")
    if receipt.event_revision != event.revision:
        raise StaleRevisionError("Go queue receipt belongs to another event revision")
    return receipt
