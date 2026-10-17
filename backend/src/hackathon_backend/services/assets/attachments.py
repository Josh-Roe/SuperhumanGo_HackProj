"""Reviewed revision-bound MIME files for Member 3's AttachmentSource port.

Does not send mail, fetch signed URLs or import Member 3's unmerged modules.
Member 2 implements the owner-scoped read repository; Member 3 may inject its
WorkflowError as error_factory when composing the distributor.
"""

import hashlib
from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import ValidationError

from hackathon_backend.services.assets.models import AssetRecord, StaleRevisionError
from hackathon_backend.services.assets.storage import validate_png

AssetKind = Literal["flyer_png", "event_document"]


class AttachmentEvent(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def owner_id(self) -> str: ...

    @property
    def revision(self) -> int: ...


class AttachmentRepository(Protocol):
    async def assert_current(self, owner_id: str, event_id: str, revision: int) -> None: ...

    async def current_asset(
        self,
        owner_id: str,
        event_id: str,
        kind: AssetKind,
    ) -> AssetRecord | None:
        """Return the current pointer under validated ownership, not an older fallback."""
        ...

    async def read_bytes(self, owner_id: str, object_key: str, *, max_bytes: int) -> bytes:
        """Authorize the object and bound bytes while reading, before allocation."""
        ...


class AssetDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RevisionedAttachmentSource:
    """Conforms structurally to workflows.ports.AttachmentSource.

    Missing/unreviewed required files fail closed rather than silently sending a
    flyerless email. Default is the flyer; opt into the rendered document explicitly.
    """

    def __init__(
        self,
        repository: AttachmentRepository,
        *,
        kinds: tuple[AssetKind, ...] = ("flyer_png",),
        max_file_bytes: int = 10_000_000,
        max_total_bytes: int = 15_000_000,
        error_factory: Callable[[str, str], Exception] = AssetDeliveryError,
    ) -> None:
        if (
            not kinds
            or len(set(kinds)) != len(kinds)
            or any(kind not in {"flyer_png", "event_document"} for kind in kinds)
        ):
            raise ValueError("Choose unique flyer/document attachment kinds")
        if not 0 < max_file_bytes <= 10_000_000 or not 0 < max_total_bytes <= 15_000_000:
            raise ValueError("Attachment limits must fit the supported byte budget")
        self.repository = repository
        self.kinds = kinds
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.error_factory = error_factory

    async def current_attachments(
        self,
        owner_id: str,
        event: AttachmentEvent,
    ) -> list[tuple[str, str, bytes]]:
        if event.owner_id != owner_id:
            raise self.error_factory("forbidden", "Event is outside the organizer scope")
        try:
            return await self._load(owner_id, event)
        except AssetDeliveryError as failure:
            raise self.error_factory(failure.code, str(failure)) from None
        except StaleRevisionError:
            raise self.error_factory(
                "revision_conflict", "Event changed while loading assets"
            ) from None
        except PermissionError:
            raise self.error_factory("forbidden", "Asset is outside the organizer scope") from None
        except Exception:
            # No Storage keys, signed URLs, credentials or raw repository errors in API replies.
            raise self.error_factory(
                "provider_failed", "Unable to load reviewed event assets"
            ) from None

    async def _load(self, owner_id: str, event: AttachmentEvent) -> list[tuple[str, str, bytes]]:
        await self.repository.assert_current(owner_id, event.id, event.revision)
        files: list[tuple[str, str, bytes]] = []
        total = 0
        for kind in self.kinds:
            record = await self.repository.current_asset(owner_id, event.id, kind)
            if record is None:
                raise AssetDeliveryError("needs_review", "Required current event asset is missing")
            try:
                # Revalidate a repository object's fields, including model_copy-created instances.
                record = AssetRecord.model_validate(record.model_dump())
            except (ValidationError, AttributeError):
                raise AssetDeliveryError(
                    "provider_failed", "Invalid event asset metadata"
                ) from None
            if record.owner_id != owner_id or record.event_id != event.id:
                raise PermissionError
            if record.event_revision != event.revision:
                raise StaleRevisionError
            if record.kind != kind:
                raise AssetDeliveryError("provider_failed", "Unexpected event asset kind")
            if record.review_state != "reviewed":
                raise AssetDeliveryError("needs_review", "Event asset still needs organizer review")
            suffix, mime = (
                ("png", "image/png")
                if kind == "flyer_png"
                else ("html", "text/html; charset=utf-8")
            )
            expected_key = (
                f"{owner_id}/events/{event.id}/r{event.revision}/{kind}/{record.sha256}.{suffix}"
            )
            if record.object_key != expected_key or record.content_type != mime:
                raise AssetDeliveryError("provider_failed", "Unexpected event asset path or type")
            if kind == "flyer_png" and not (
                record.canva_design_id and record.canva_export_id and record.canva_generation_id
            ):
                raise AssetDeliveryError("needs_review", "Flyer export provenance is incomplete")
            if record.byte_length > self.max_file_bytes:
                raise AssetDeliveryError(
                    "needs_review", "Event asset exceeds attachment size limit"
                )
            content = await self.repository.read_bytes(
                owner_id,
                record.object_key,
                max_bytes=self.max_file_bytes,
            )
            if (
                not isinstance(content, bytes)
                or len(content) != record.byte_length
                or len(content) > self.max_file_bytes
                or hashlib.sha256(content).hexdigest() != record.sha256
            ):
                raise AssetDeliveryError("provider_failed", "Event asset integrity check failed")
            if kind == "flyer_png":
                validate_png(content)
            else:
                content.decode("utf-8")
            total += len(content)
            if total > self.max_total_bytes:
                raise AssetDeliveryError(
                    "needs_review", "Event attachments exceed total size limit"
                )
            label = "flyer" if kind == "flyer_png" else "details"
            # IDs are validated in AssetRecord, so titles cannot inject a MIME filename/header.
            filename = f"event-{record.event_id}-r{record.event_revision}-{label}.{suffix}"
            files.append((filename, mime.split(";")[0], content))
        await self.repository.assert_current(owner_id, event.id, event.revision)
        return files
