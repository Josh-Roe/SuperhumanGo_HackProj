"""Member 4 composition over the actual trusted Go store and revisioned asset services.

Member 3 registers these methods after resolving an organizer principal. The host must
claim durable Canva operations/locks before writes and persist/reconcile returned jobs.
Nothing here invokes Go, creates organizer approvals, sends mail or invites guests.
"""

import asyncio
from typing import Any, Literal

from pydantic import Field, ValidationError

from hackathon_backend.providers.canva import (
    CanvaMCPAdapter,
    CreationJob,
    ExportReceipt,
    VerifiedDesign,
)
from hackathon_backend.services.assets.models import (
    AssetRecord,
    BoundaryModel,
    EventSnapshot,
    GoContent,
    require_scope,
)
from hackathon_backend.services.assets.queue import StoredGoAssetQueue
from hackathon_backend.services.assets.requests import (
    ASSET_PROSE_KINDS,
    ProseQueueReceipt,
    request_event_prose,
)
from hackathon_backend.services.assets.storage import AssetService, AssetStorage, ExportDownloader
from hackathon_backend.services.inclusion import InclusionInput, InclusionReport, check_inclusion
from hackathon_backend.workflows.asset_queue import load_go_content
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.models import ContentKind
from hackathon_backend.workflows.ports import WorkflowStore


class AssetPreparation(BoundaryModel):
    """Internal snapshot. Transport consumers use body-free preview_metadata()."""

    event: EventSnapshot = Field(exclude=True)
    contents: tuple[GoContent, ...] = Field(exclude=True, repr=False)
    missing_kinds: tuple[str, ...]
    unreviewed_kinds: tuple[str, ...]
    prose_state: Literal["awaiting_go", "needs_review", "reviewed"]

    def content_for(self, kind: str) -> GoContent | None:
        return next((item for item in self.contents if item.kind == kind), None)

    def preview_metadata(self) -> dict[str, Any]:
        return {
            "event_id": self.event.id,
            "event_revision": self.event.revision,
            "prose_state": self.prose_state,
            "missing_kinds": self.missing_kinds,
            "unreviewed_kinds": self.unreviewed_kinds,
            "generation_ids": {item.kind: item.generation_id for item in self.contents},
        }


class DocumentPreparation(BoundaryModel):
    event_id: str
    event_revision: int
    state: Literal["awaiting_go", "stored"]
    missing_kinds: tuple[str, ...] = ()
    asset: AssetRecord | None = Field(default=None, exclude=True)

    def preview_metadata(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_revision": self.event_revision,
            "state": self.state,
            "missing_kinds": self.missing_kinds,
            "asset": self.asset.preview_metadata() if self.asset else None,
        }


class FlyerCreationPreparation(BoundaryModel):
    job: CreationJob
    generation_ids: dict[str, str]


class EventAssetPreparationService:
    """Thin callable handoff; owner_id must come from the server's authenticated principal."""

    def __init__(self, store: WorkflowStore, storage: AssetStorage | None = None) -> None:
        self.store = store
        self.storage = storage

    async def _event(self, owner_id: str, event_id: str, expected_revision: int) -> EventSnapshot:
        saved = await self.store.get_event(owner_id, event_id)
        if saved is None or saved.owner_id != owner_id or saved.id != event_id:
            raise WorkflowError("forbidden", "event not found for this organizer")
        if saved.revision != expected_revision:
            raise WorkflowError(
                "revision_conflict", "event changed; reload before preparing assets"
            )
        try:
            return EventSnapshot.model_validate(
                {name: getattr(saved, name) for name in EventSnapshot.model_fields}
            )
        except ValidationError:
            # Do not echo validation inputs (including contact/venue text) into tool errors.
            raise WorkflowError(
                "needs_review", "confirm the event's required asset fields"
            ) from None

    async def read(self, owner_id: str, event_id: str, expected_revision: int) -> AssetPreparation:
        event = await self._event(owner_id, event_id, expected_revision)
        loaded = await asyncio.gather(
            *(
                load_go_content(self.store, owner_id, event_id, event.revision, ContentKind(kind))
                for kind in ASSET_PROSE_KINDS
            )
        )
        contents = []
        missing = []
        for kind, raw in zip(ASSET_PROSE_KINDS, loaded, strict=True):
            if raw is None:
                missing.append(kind)
                continue
            try:
                content = GoContent.model_validate(raw)
            except ValidationError:
                raise WorkflowError("needs_review", "stored Go asset content is invalid") from None
            require_scope(event, owner_id, content)
            if content.kind != kind:
                raise WorkflowError("needs_review", "stored Go content kind does not match")
            contents.append(content)
        # A revision change while reading five records invalidates the whole batch.
        await self._event(owner_id, event_id, expected_revision)
        unreviewed = tuple(item.kind for item in contents if not item.reviewed_by_organizer)
        return AssetPreparation(
            event=event,
            contents=tuple(contents),
            missing_kinds=tuple(missing),
            unreviewed_kinds=unreviewed,
            prose_state="awaiting_go"
            if missing
            else ("needs_review" if unreviewed else "reviewed"),
        )

    async def request_prose(
        self, owner_id: str, event_id: str, expected_revision: int
    ) -> ProseQueueReceipt:
        event = await self._event(owner_id, event_id, expected_revision)
        receipt = await request_event_prose(
            event, StoredGoAssetQueue(self.store), owner_id=owner_id
        )
        await self._event(owner_id, event_id, expected_revision)
        return ProseQueueReceipt.model_validate(receipt.model_dump())

    def _assets(self) -> AssetService:
        if self.storage is None:
            raise WorkflowError(
                "integration_not_connected", "private asset Storage is not configured"
            )
        return AssetService(self.storage)

    async def prepare_document(
        self, owner_id: str, event_id: str, expected_revision: int
    ) -> DocumentPreparation:
        batch = await self.read(owner_id, event_id, expected_revision)
        required = ("event_document", "plain_language_summary")
        missing = tuple(kind for kind in required if batch.content_for(kind) is None)
        if missing:
            return DocumentPreparation(
                event_id=event_id,
                event_revision=expected_revision,
                state="awaiting_go",
                missing_kinds=missing,
            )
        # Both prose records are mandatory here so plain language is never silently omitted.
        record = await self._assets().save_document(
            batch.event,
            batch.content_for("event_document"),
            owner_id=owner_id,
            summary=batch.content_for("plain_language_summary"),
        )
        return DocumentPreparation(
            event_id=event_id,
            event_revision=expected_revision,
            state="stored",
            asset=record,
        )

    async def inclusion(
        self, owner_id: str, event_id: str, expected_revision: int, facts: InclusionInput
    ) -> InclusionReport:
        batch = await self.read(owner_id, event_id, expected_revision)
        return check_inclusion(
            batch.event,
            facts,
            owner_id=owner_id,
            summary=batch.content_for("plain_language_summary"),
        )

    async def start_flyer(
        self, owner_id: str, event_id: str, expected_revision: int, canva: CanvaMCPAdapter
    ) -> FlyerCreationPreparation:
        """Host claims one durable create operation before calling; never blindly retry."""
        batch = await self.read(owner_id, event_id, expected_revision)
        brief, copy = batch.content_for("flyer_brief"), batch.content_for("flyer_copy")
        if brief is None or copy is None:
            raise WorkflowError("awaiting_go", "Go flyer brief and displayed copy are required")
        await self._event(owner_id, event_id, expected_revision)
        job = await canva.create_flyer(batch.event, brief, copy=copy)
        # Do not discard an actual provider job if the event advances during this call.
        # Persist it at its returned revision; the existing poller rejects stale snapshots.
        return FlyerCreationPreparation(
            job=job,
            generation_ids={brief.kind: brief.generation_id, copy.kind: copy.generation_id},
        )

    async def store_flyer_export(
        self,
        owner_id: str,
        event_id: str,
        expected_revision: int,
        design: VerifiedDesign,
        export: ExportReceipt,
        downloader: ExportDownloader,
    ) -> AssetRecord:
        batch = await self.read(owner_id, event_id, expected_revision)
        alt_text = batch.content_for("flyer_alt_text")
        if alt_text is None:
            raise WorkflowError("awaiting_go", "Go flyer accessible text is required")
        if export.design != design.design:
            raise WorkflowError("needs_review", "export does not match the verified flyer binding")
        if export.state != "completed" or not export.download_url:
            raise WorkflowError(
                "needs_review", "Canva export is not completed; reconcile its receipt"
            )
        if design.state != "verified":
            raise WorkflowError("needs_review", "flyer text requires verification")
        if design.design.event_revision != expected_revision:
            raise WorkflowError("revision_conflict", "flyer belongs to another event revision")
        if design.design.owner_id != owner_id or design.design.event_id != event_id:
            raise WorkflowError("forbidden", "flyer is outside the event/organizer scope")
        assets = self._assets()
        png = await downloader.png(export.download_url)
        await self._event(owner_id, event_id, expected_revision)
        return await assets.save_flyer(
            batch.event,
            design,
            png,
            owner_id=owner_id,
            export_id=export.export_id,
            alt_text=alt_text,
        )
