import asyncio

import pytest
from test_assets_support import event

from hackathon_backend.services.assets.models import StaleRevisionError
from hackathon_backend.services.assets.requests import ProseQueueReceipt, request_event_prose


def test_requests_go_batch_without_claiming_generated_output():
    class Queue:
        async def enqueue(self, request):
            assert request.producer == "superhuman_go"
            assert {
                "flyer_brief",
                "flyer_copy",
                "event_document",
                "plain_language_summary",
                "flyer_alt_text",
            } == set(request.kinds)
            assert request.idempotency_key == "fixture-owner:fixture-event:r1:go:asset-prose-v1"
            return ProseQueueReceipt(
                owner_id=request.owner_id,
                event_id=request.event_id,
                event_revision=request.event_revision,
                operation_id="fixture-op",
                state="awaiting_go",
            )

    receipt = asyncio.run(request_event_prose(event(), Queue(), owner_id="fixture-owner"))
    assert receipt.state == "awaiting_go"
    with pytest.raises(PermissionError):
        asyncio.run(request_event_prose(event(), Queue(), owner_id="another-owner"))


@pytest.mark.parametrize("other", ["owner", "revision"])
def test_rejects_mismatched_go_queue_receipts(other):
    class Queue:
        async def enqueue(self, request):
            return ProseQueueReceipt(
                owner_id="another-owner" if other == "owner" else request.owner_id,
                event_id=request.event_id,
                event_revision=2 if other == "revision" else 1,
                operation_id="fixture-op",
                state="queued",
            )

    with pytest.raises(PermissionError if other == "owner" else StaleRevisionError):
        asyncio.run(request_event_prose(event(), Queue(), owner_id="fixture-owner"))
