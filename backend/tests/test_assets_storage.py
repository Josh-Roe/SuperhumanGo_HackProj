import asyncio

import httpx
import pytest
from test_assets_support import PNG, event, go
from test_canva_mcp import design

from hackathon_backend.providers.canva import VerifiedDesign
from hackathon_backend.services.assets.documents import render_event_document
from hackathon_backend.services.assets.models import StaleRevisionError, StorageReceipt
from hackathon_backend.services.assets.storage import AssetService, ExportDownloader


class Storage:
    """Test double, not a Supabase integration."""

    def __init__(self):
        self.revision = 1
        self.objects = {}
        self.current = {}
        self.advance_during_upload = False
        self.bad_receipt = False

    async def assert_current(self, owner_id, event_id, revision):
        assert owner_id == "fixture-owner" and event_id == "fixture-event"
        if revision != self.revision:
            raise StaleRevisionError("Event moved")

    async def put_if_absent(self, object_key, content, content_type, sha256):
        existing = self.objects.setdefault(object_key, content)
        assert existing == content
        if self.advance_during_upload:
            self.revision += 1
        return StorageReceipt(
            object_key=object_key,
            sha256="0" * 64 if self.bad_receipt else sha256,
            byte_length=len(content),
        )

    async def publish_current(self, record, *, expected_revision):
        await self.assert_current(record.owner_id, record.event_id, expected_revision)
        self.current[record.kind] = record


def test_document_escapes_prose_and_renders_canonical_fields():
    snapshot = event(title='Fixture <script>alert("x")</script>')
    document = go(snapshot, "event_document", body='<img src=x onerror="boom">\nSecond line')
    summary = go(snapshot, "plain_language_summary", body="Synthetic summary & details")
    html = render_event_document(
        snapshot, document, owner_id=snapshot.owner_id, summary=summary
    ).decode()
    assert '<html lang="en" dir="auto">' in html
    assert "<script>" not in html and "<img" not in html
    assert "&lt;img" in html and "summary &amp; details" in html
    assert snapshot.flyer_fields()["when"] in html
    assert "Event revision 1" in html and "Superhuman Go" in html
    with pytest.raises(ValueError, match="document"):
        render_event_document(snapshot, go(snapshot), owner_id=snapshot.owner_id)
    with pytest.raises(PermissionError):
        render_event_document(snapshot, document, owner_id="another-owner")
    with pytest.raises(StaleRevisionError):
        render_event_document(event(2), document, owner_id=snapshot.owner_id)


def test_document_revisions_preserve_bytes_and_replace_only_current_pointer():
    async def run():
        storage = Storage()
        service = AssetService(storage)
        first = await service.save_document(
            event(), go(event(), "event_document"), owner_id="fixture-owner"
        )
        again = await service.save_document(
            event(), go(event(), "event_document"), owner_id="fixture-owner"
        )
        assert again.object_key == first.object_key and len(storage.objects) == 1
        storage.revision = 2
        second = await service.save_document(
            event(2, location="Fixture Room B"),
            go(event(2), "event_document", reviewed_by_organizer=True),
            owner_id="fixture-owner",
        )
        assert first.sha256 != second.sha256 and first.object_key != second.object_key
        assert b"Fixture Room A" in storage.objects[first.object_key]
        assert b"Fixture Room B" in storage.objects[second.object_key]
        assert storage.current["event_document"] == second
        assert first.review_state == "needs_review" and second.review_state == "reviewed"
        assert "object_key" not in second.preview_metadata()

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["stale", "bad_receipt"])
def test_upload_race_or_bad_receipt_cannot_publish_current(mode):
    storage = Storage()
    storage.advance_during_upload = mode == "stale"
    storage.bad_receipt = mode == "bad_receipt"
    with pytest.raises(StaleRevisionError if mode == "stale" else RuntimeError):
        asyncio.run(
            AssetService(storage).save_document(
                event(), go(event(), "event_document"), owner_id="fixture-owner"
            )
        )
    assert not storage.current


def test_flyer_needs_current_verified_design_and_go_alt_text():
    async def run():
        storage = Storage()
        service = AssetService(storage)
        verified = VerifiedDesign(
            design=design(), state="verified", missing_roles=(), organizer_reviewed=True
        )
        record = await service.save_flyer(
            event(),
            verified,
            PNG,
            owner_id="fixture-owner",
            export_id="fixture-export",
            alt_text=go(event(), "flyer_alt_text", reviewed_by_organizer=True),
        )
        assert record.canva_export_id == "fixture-export" and record.review_state == "reviewed"
        assert record.canva_generation_id == "synthetic-test-fixture"
        for bad in [
            verified.model_copy(update={"state": "needs_review"}),
            verified.model_copy(update={"design": design(event(2))}),
        ]:
            with pytest.raises(StaleRevisionError):
                await service.save_flyer(
                    event(),
                    bad,
                    PNG,
                    owner_id="fixture-owner",
                    export_id="fixture-export",
                    alt_text=go(event(), "flyer_alt_text"),
                )
        with pytest.raises(ValueError, match="alt text"):
            await service.save_flyer(
                event(),
                verified,
                PNG,
                owner_id="fixture-owner",
                export_id="fixture-export",
                alt_text=go(event()),
            )
        with pytest.raises(ValueError, match="PNG"):
            await service.save_flyer(
                event(),
                verified,
                b"not png",
                owner_id="fixture-owner",
                export_id="fixture-export",
                alt_text=go(event(), "flyer_alt_text"),
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "http://export-download.canva.com/a.png",
        "https://example.com/a.png",
        "https://export-download.canva.com.evil.example/a.png",
        "https://user:secret@export-download.canva.com/a.png",
        "https://127.0.0.1/a.png",
    ],
)
def test_export_downloader_rejects_untrusted_urls_without_requests(url):
    async def run():
        def handler(request):
            pytest.fail("Untrusted URL reached HTTP transport")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await ExportDownloader(client).png(url)

    asyncio.run(run())


@pytest.mark.parametrize("case", ["success", "redirect", "html", "size", "auth", "invalid_png"])
def test_export_download_validation(case):
    async def run():
        def handler(request):
            assert "authorization" not in request.headers
            return httpx.Response(
                302 if case == "redirect" else 200,
                headers={
                    "content-type": "text/html" if case == "html" else "image/png",
                    "location": "https://example.com/redirect",
                },
                content=b"invalid" if case == "invalid_png" else PNG,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "test-only"} if case == "auth" else {},
        ) as client:
            downloader = ExportDownloader(client, max_bytes=1 if case == "size" else 1000)
            if case == "success":
                assert await downloader.png("https://export-download.canva.com/a.png") == PNG
            else:
                with pytest.raises(RuntimeError if case == "redirect" else ValueError):
                    await downloader.png("https://export-download.canva.com/a.png")

    asyncio.run(run())
