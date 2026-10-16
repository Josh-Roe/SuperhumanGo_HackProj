import asyncio
import hashlib
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest
from test_assets_storage import Storage
from test_assets_support import PNG, event, go
from test_canva_mcp import design

from hackathon_backend.providers.canva import VerifiedDesign
from hackathon_backend.services.assets.attachments import (
    AssetDeliveryError,
    RevisionedAttachmentSource,
)
from hackathon_backend.services.assets.storage import AssetService


class Repository(Storage):
    def __init__(self):
        super().__init__()
        self.reads = []
        self.advance_during_read = False

    async def current_asset(self, owner_id, event_id, kind):
        return self.current.get(kind)

    async def read_bytes(self, owner_id, object_key, *, max_bytes):
        self.reads.append((owner_id, object_key, max_bytes))
        if self.advance_during_read:
            self.revision += 1
        return self.objects[object_key]


async def prepared():
    repository = Repository()
    service = AssetService(repository)
    await service.save_flyer(
        event(),
        VerifiedDesign(
            design=design(),
            state="verified",
            missing_roles=(),
            organizer_reviewed=True,
        ),
        PNG,
        owner_id="fixture-owner",
        export_id="synthetic-export",
        alt_text=go(event(), "flyer_alt_text", reviewed_by_organizer=True),
    )
    await service.save_document(
        event(), go(event(), "event_document", reviewed_by_organizer=True), owner_id="fixture-owner"
    )
    return repository


def test_current_reviewed_flyer_and_document_round_trip_as_mime():
    async def run():
        repository = await prepared()
        source = RevisionedAttachmentSource(repository, kinds=("flyer_png", "event_document"))
        files = await source.current_attachments("fixture-owner", event())
        message = EmailMessage(policy=policy.SMTP)
        message.set_content("SYNTHETIC attachment integration fixture; no email is sent.")
        for filename, mime, content in files:
            main, sub = mime.split("/")
            message.add_attachment(content, maintype=main, subtype=sub, filename=filename)
        decoded = list(
            BytesParser(policy=policy.default).parsebytes(message.as_bytes()).iter_attachments()
        )
        assert [item.get_content_type() for item in decoded] == ["image/png", "text/html"]
        assert decoded[0].get_payload(decode=True) == PNG
        assert b"Fixture Room A" in decoded[1].get_payload(decode=True)
        assert decoded[0].get_filename() == "event-fixture-event-r1-flyer.png"
        assert len(repository.reads) == 2

    asyncio.run(run())


def test_default_is_flyer_only_and_owner_mismatch_never_reads_storage():
    async def run():
        repository = await prepared()
        source = RevisionedAttachmentSource(repository)
        with pytest.raises(AssetDeliveryError) as caught:
            await source.current_attachments("other-owner", event())
        assert caught.value.code == "forbidden" and not repository.reads
        files = await source.current_attachments("fixture-owner", event())
        assert len(files) == 1 and files[0][1] == "image/png"

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing", "needs_review"),
        ("unreviewed", "needs_review"),
        ("old_revision", "revision_conflict"),
        ("other_owner", "forbidden"),
        ("other_event", "forbidden"),
        ("wrong_kind", "provider_failed"),
        ("wrong_path", "provider_failed"),
        ("bad_mime", "provider_failed"),
        ("no_export_id", "needs_review"),
        ("oversize", "needs_review"),
        ("bad_hash", "provider_failed"),
        ("bad_length", "provider_failed"),
        ("race", "revision_conflict"),
        ("invalid_png", "provider_failed"),
    ],
)
def test_rejects_unsafe_stale_unreviewed_or_missing_assets(mutation, code):
    async def run():
        repository = await prepared()
        record = repository.current["flyer_png"]
        updates = {
            "unreviewed": {"review_state": "needs_review"},
            "old_revision": {"event_revision": 2},
            "other_owner": {"owner_id": "another-owner"},
            "other_event": {"event_id": "another-event"},
            "wrong_kind": {"kind": "event_document"},
            "wrong_path": {"object_key": "https://example.com/private.png"},
            "bad_mime": {"content_type": "text/html"},
            "no_export_id": {"canva_export_id": None},
            "bad_length": {"byte_length": len(PNG) + 1},
        }.get(mutation, {})
        repository.current["flyer_png"] = record.model_copy(update=updates)
        if mutation == "missing":
            repository.current.pop("flyer_png")
        elif mutation == "bad_hash":
            repository.objects[record.object_key] = PNG[:-1] + b"x"
        elif mutation == "race":
            repository.advance_during_read = True
        elif mutation == "invalid_png":
            data = b"invalid png"
            digest = hashlib.sha256(data).hexdigest()
            key = record.object_key.replace(record.sha256, digest)
            repository.current["flyer_png"] = record.model_copy(
                update={
                    "object_key": key,
                    "sha256": digest,
                    "byte_length": len(data),
                }
            )
            repository.objects[key] = data
        source = RevisionedAttachmentSource(
            repository, max_file_bytes=1 if mutation == "oversize" else 10000
        )
        with pytest.raises(AssetDeliveryError) as caught:
            await source.current_attachments("fixture-owner", event())
        assert caught.value.code == code
        assert record.object_key not in str(caught.value)

    asyncio.run(run())


def test_total_budget_and_injected_workflow_error():
    class WorkflowError(Exception):
        def __init__(self, code, message):
            self.code = code
            super().__init__(message)

    async def run():
        repository = await prepared()
        source = RevisionedAttachmentSource(
            repository,
            kinds=("flyer_png", "event_document"),
            max_total_bytes=len(PNG),
            error_factory=WorkflowError,
        )
        with pytest.raises(WorkflowError) as caught:
            await source.current_attachments("fixture-owner", event())
        assert caught.value.code == "needs_review"

    asyncio.run(run())
