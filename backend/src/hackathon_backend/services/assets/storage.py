"""Immutable bytes and compare-and-set current pointers for Member 2's Storage adapter."""

import hashlib
import struct
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from hackathon_backend.providers.canva import VerifiedDesign
from hackathon_backend.services.assets.models import (
    AssetRecord,
    EventSnapshot,
    GoContent,
    StaleRevisionError,
    StorageReceipt,
    require_scope,
)


class AssetStorage(Protocol):
    """Owner-aware implementation belongs to Member 2; never a browser service-role key."""

    async def assert_current(self, owner_id: str, event_id: str, revision: int) -> None: ...

    async def put_if_absent(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> StorageReceipt: ...

    async def publish_current(self, record: AssetRecord, *, expected_revision: int) -> None:
        """Atomic ownership/revision CAS; raise StaleRevisionError if the event moved."""
        ...


class ExportDownloader:
    """Download only Canva export bytes, with no auth headers or redirects."""

    def __init__(self, client: httpx.AsyncClient, *, max_bytes: int = 10_000_000) -> None:
        self.client = client
        self.max_bytes = max_bytes

    async def png(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "export-download.canva.com"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Expected an official Canva export download URL")
        # A dedicated client must be unauthenticated: never forward API bearer headers to a CDN.
        if (
            "authorization" in self.client.headers
            or "cookie" in self.client.headers
            or self.client.auth is not None
            or self.client.cookies
        ):
            raise ValueError("Export downloads require an unauthenticated HTTP client")
        data = bytearray()
        async with self.client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                raise RuntimeError("Canva export download failed")
            if response.headers.get("content-type", "").split(";")[0] != "image/png":
                raise ValueError("Canva export is not PNG")
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > self.max_bytes:
                    raise ValueError("Canva export exceeds the allowed size")
        validate_png(bytes(data))
        return bytes(data)


def validate_png(data: bytes) -> None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("Expected PNG export bytes")
    width, height = struct.unpack(">II", data[16:24])
    if not 0 < width <= 16_000 or not 0 < height <= 16_000 or width * height > 50_000_000:
        raise ValueError("Unsupported PNG dimensions")


class AssetService:
    def __init__(self, storage: AssetStorage) -> None:
        self.storage = storage

    async def save_document(
        self,
        event: EventSnapshot,
        document: GoContent,
        *,
        owner_id: str,
        summary: GoContent | None = None,
    ) -> AssetRecord:
        from hackathon_backend.services.assets.documents import render_event_document

        content = render_event_document(event, document, owner_id=owner_id, summary=summary)
        return await self._save(
            event,
            content,
            owner_id=owner_id,
            kind="event_document",
            content_type="text/html; charset=utf-8",
            go_content=document,
            reviewed=document.reviewed_by_organizer
            and (summary is None or summary.reviewed_by_organizer),
        )

    async def save_flyer(
        self,
        event: EventSnapshot,
        design: VerifiedDesign,
        png: bytes,
        *,
        owner_id: str,
        export_id: str,
        alt_text: GoContent,
    ) -> AssetRecord:
        return await self._save(
            event,
            png,
            owner_id=owner_id,
            kind="flyer_png",
            content_type="image/png",
            go_content=alt_text,
            design=design,
            export_id=export_id,
            reviewed=alt_text.reviewed_by_organizer and design.organizer_reviewed,
        )

    async def _save(
        self,
        event: EventSnapshot,
        content: bytes,
        *,
        owner_id: str,
        kind: str,
        content_type: str,
        go_content: GoContent,
        design: VerifiedDesign | None = None,
        export_id: str | None = None,
        reviewed: bool = False,
    ) -> AssetRecord:
        require_scope(event, owner_id, go_content)
        if kind == "event_document":
            if go_content.kind != "event_document" or content_type != "text/html; charset=utf-8":
                raise ValueError("Event documents require Go document prose and HTML rendering")
        elif kind == "flyer_png":
            if go_content.kind != "flyer_alt_text" or content_type != "image/png":
                raise ValueError("Flyer exports require Go alt text")
            if (
                not design
                or design.state != "verified"
                or design.design.event_revision != event.revision
            ):
                raise StaleRevisionError("Only the verified current flyer can be stored")
            if design.design.owner_id != owner_id or design.design.event_id != event.id:
                raise PermissionError("Design is outside the event/organizer scope")
            if not export_id:
                raise ValueError("Flyer exports require the actual Canva export job ID")
            validate_png(content)
        else:
            raise ValueError("Unsupported artifact kind")
        if not content or len(content) > 10_000_000:
            raise ValueError("Artifact is empty or too large")
        await self.storage.assert_current(owner_id, event.id, event.revision)
        digest = hashlib.sha256(content).hexdigest()
        suffix = "html" if kind == "event_document" else "png"
        key = f"{owner_id}/events/{event.id}/r{event.revision}/{kind}/{digest}.{suffix}"
        receipt = await self.storage.put_if_absent(key, content, content_type, digest)
        if (
            receipt.object_key != key
            or receipt.sha256 != digest
            or receipt.byte_length != len(content)
        ):
            raise RuntimeError("Storage receipt does not match the requested artifact")
        record = AssetRecord(
            owner_id=owner_id,
            event_id=event.id,
            event_revision=event.revision,
            kind=kind,
            object_key=key,
            sha256=digest,
            byte_length=len(content),
            content_type=content_type,
            go_generation_id=go_content.generation_id,
            review_state="reviewed" if reviewed else "needs_review",
            created_at=datetime.now(UTC),
            canva_design_id=design.design.design_id if design else None,
            canva_export_id=export_id,
            canva_generation_id=design.design.generation_id if design else None,
        )
        # This must compare the canonical event's revision atomically, not just a local snapshot.
        await self.storage.publish_current(record, expected_revision=event.revision)
        return record
