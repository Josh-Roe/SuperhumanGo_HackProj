"""Synthetic composition tests over the actual Member 3 store/Go loader; no live providers."""

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from test_assets_storage import Storage
from test_assets_support import PNG, event
from test_canva_mcp import Session, design, pending

from hackathon_backend.providers.canva import CanvaMCPAdapter, ExportReceipt, VerifiedDesign
from hackathon_backend.services.assets.preparation import EventAssetPreparationService
from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS
from hackathon_backend.services.assets.storage import ExportDownloader
from hackathon_backend.services.inclusion import Fact, InclusionInput, Source
from hackathon_backend.workflows.go_work import WorkflowError, save_go_content
from hackathon_backend.workflows.memory import InMemoryWorkflowStore
from hackathon_backend.workflows.models import ContentKind, EventSnapshot, Producer

OWNER, EVENT = "fixture-owner", "fixture-event"


def workflow_event(revision=1, **changes):
    return EventSnapshot(
        **event(revision, **changes).model_dump(), organizer_contact="organizer@example.invalid"
    )


def setup():
    store = InMemoryWorkflowStore()
    store.put_event(workflow_event())
    storage = Storage()
    return store, storage, EventAssetPreparationService(store, storage)


async def put_prose(store, kinds=ASSET_PROSE_KINDS, *, revision=1, reviewed=False):
    for kind in kinds:
        saved = await save_go_content(
            store,
            OWNER,
            event_id=EVENT,
            expected_revision=revision,
            kind=ContentKind(kind),
            body=f"SYNTHETIC Go-port fixture: {kind}, revision {revision}. <unsafe>",
        )
        if reviewed:
            store.content[saved.id] = saved.model_copy(update={"state": "ready"})


def test_read_is_not_generation_and_request_uses_actual_go_queue_without_duplicates():
    async def run():
        store, storage, service = setup()
        batch = await service.read(OWNER, EVENT, 1)
        assert batch.prose_state == "awaiting_go"
        assert batch.missing_kinds == ASSET_PROSE_KINDS
        assert not store.work and not storage.objects
        first = await service.request_prose(OWNER, EVENT, 1)
        again = await service.request_prose(OWNER, EVENT, 1)
        assert first.operation_id == again.operation_id and first.state == "awaiting_go"
        assert len(store.work) == 1
        assert store.work[first.operation_id].payload["kinds"] == list(ASSET_PROSE_KINDS)
        assert (await service.read(OWNER, EVENT, 1)).contents == ()

    asyncio.run(run())


def test_read_uses_current_trusted_content_and_exposes_body_free_prose_readiness():
    async def run():
        store, _, service = setup()
        await put_prose(store)
        batch = await service.read(OWNER, EVENT, 1)
        assert batch.prose_state == "needs_review" and not batch.missing_kinds
        assert batch.unreviewed_kinds == ASSET_PROSE_KINDS
        metadata = json.dumps(batch.preview_metadata())
        assert "generation_ids" in metadata and "SYNTHETIC" not in metadata
        assert "<unsafe>" not in batch.model_dump_json() + repr(batch)
        for key, item in store.content.items():
            store.content[key] = item.model_copy(update={"state": "ready"})
        assert (await service.read(OWNER, EVENT, 1)).prose_state == "reviewed"

    asyncio.run(run())


def test_non_go_latest_content_does_not_fall_back_to_an_older_go_version():
    async def run():
        store, _, service = setup()
        await put_prose(store)
        original = next(c for c in store.content.values() if c.kind == ContentKind.EVENT_DOCUMENT)
        alternate = original.model_copy(
            update={
                "id": "alternate-output",
                "producer": Producer.ORGANIZER,
                "created_at": original.created_at + timedelta(seconds=1),
            }
        )
        await store.save_content(OWNER, alternate, 1)
        batch = await service.read(OWNER, EVENT, 1)
        assert batch.missing_kinds == ("event_document",)
        assert (await service.prepare_document(OWNER, EVENT, 1)).state == "awaiting_go"

    asyncio.run(run())


@pytest.mark.parametrize("kinds", [(), ("event_document",), ("plain_language_summary",)])
def test_missing_document_or_summary_never_renders_substitute_prose(kinds):
    async def run():
        store, storage, service = setup()
        await put_prose(store, kinds)
        result = await service.prepare_document(OWNER, EVENT, 1)
        assert result.state == "awaiting_go" and result.asset is None and result.missing_kinds
        assert not storage.objects and not store.work

    asyncio.run(run())


def test_document_stores_escaped_go_and_preserves_review_and_revision_history():
    async def run():
        store, storage, service = setup()
        await put_prose(store, ("event_document", "plain_language_summary"))
        first = await service.prepare_document(OWNER, EVENT, 1)
        assert first.asset.review_state == "needs_review"
        assert first.preview_metadata()["asset"]["review_state"] == "needs_review"
        assert "object_key" not in json.dumps(first.preview_metadata())
        old_bytes = storage.objects[first.asset.object_key]
        assert b"&lt;unsafe&gt;" in old_bytes and b"<unsafe>" not in old_bytes
        assert b"Fixture Room A" in old_bytes
        store.put_event(workflow_event(2, location="Fixture Room B"))
        storage.revision = 2
        waiting = await service.prepare_document(OWNER, EVENT, 2)
        assert waiting.state == "awaiting_go"  # revision 1 prose is never reused
        await put_prose(
            store, ("event_document", "plain_language_summary"), revision=2, reviewed=True
        )
        second = await service.prepare_document(OWNER, EVENT, 2)
        assert second.asset.review_state == "reviewed"
        assert first.asset.sha256 != second.asset.sha256
        assert storage.objects[first.asset.object_key] == old_bytes
        assert b"Fixture Room B" in storage.objects[second.asset.object_key]

    asyncio.run(run())


def test_document_with_only_one_reviewed_source_remains_needs_review():
    async def run():
        store, _, service = setup()
        await put_prose(store, ("event_document",), reviewed=True)
        await put_prose(store, ("plain_language_summary",))
        result = await service.prepare_document(OWNER, EVENT, 1)
        assert result.asset.review_state == "needs_review"
        bare = EventAssetPreparationService(store)
        with pytest.raises(WorkflowError, match="integration_not_connected"):
            await bare.prepare_document(OWNER, EVENT, 1)

    asyncio.run(run())


def test_foreign_or_stale_event_is_rejected_before_queue_or_storage():
    async def run():
        store, storage, service = setup()
        for owner, revision, code in [
            ("other-owner", 1, "forbidden"),
            (OWNER, 2, "revision_conflict"),
        ]:
            with pytest.raises(WorkflowError, match=code):
                await service.request_prose(owner, EVENT, revision)
        assert not store.work and not storage.objects

        # Even a faulty store returning a foreign record must fail closed.
        async def foreign(*args):
            return workflow_event(owner_id="other-owner")

        store.get_event = foreign
        with pytest.raises(WorkflowError, match="forbidden"):
            await service.read(OWNER, EVENT, 1)

    asyncio.run(run())


def test_revision_change_during_batch_read_invalidates_loaded_prose():
    async def run():
        store, _, service = setup()
        await put_prose(store)
        original = store.latest_content

        async def changed(*args):
            item = await original(*args)
            store.put_event(workflow_event(2))
            return item

        store.latest_content = changed
        with pytest.raises(WorkflowError, match="revision_conflict"):
            await service.read(OWNER, EVENT, 1)

    asyncio.run(run())


def test_missing_event_fields_return_a_safe_review_error():
    async def run():
        store, _, service = setup()
        store.put_event(workflow_event().model_copy(update={"location": ""}))
        with pytest.raises(WorkflowError, match="needs_review"):
            await service.read(OWNER, EVENT, 1)

    asyncio.run(run())


def test_inclusion_keeps_source_unknowns_and_private_needs_out_of_findings():
    async def run():
        store, _, service = setup()
        await put_prose(store, ("plain_language_summary",), reviewed=True)
        source = Source(
            label="Synthetic venue check",
            confirmed_by="Test organizer",
            observed_at="2026-10-16T12:00:00Z",
        )
        report = await service.inclusion(
            OWNER,
            EVENT,
            1,
            InclusionInput(
                step_free_entrance=Fact(value="yes", source=source),
                food_served=Fact(value="yes", source=source),
                diet_source=source,
                required_diets=("PRIVATE-SYNTHETIC-REQUIREMENT",),
            ),
        )
        findings = {f.category: f for f in report.findings}
        assert findings["plain_language"].status == "recorded"
        assert findings["step_free_entrance"].sources == (source,)
        assert findings["captions"].status == "unknown"
        assert findings["diet"].status == "attention"
        assert "PRIVATE-SYNTHETIC" not in report.model_dump_json()
        assert report.audience == "organizer_private" and not report.certification

    asyncio.run(run())


def test_flyer_creation_requires_both_go_kinds_and_tracks_both_source_ids():
    async def run():
        store, _, service = setup()
        session = Session({"create-design": [pending()]})
        adapter = CanvaMCPAdapter(session, owner_id=OWNER)
        await put_prose(store, ("flyer_brief",))
        with pytest.raises(WorkflowError, match="awaiting_go"):
            await service.start_flyer(OWNER, EVENT, 1, adapter)
        assert not session.calls
        await put_prose(store, ("flyer_copy",))
        result = await service.start_flyer(OWNER, EVENT, 1, adapter)
        prompt = session.calls[0][1]["brief"]
        assert "Go-written flyer text (use exactly)" in prompt
        assert "flyer_copy, revision 1" in prompt and "Fixture Room A" in prompt
        assert set(result.generation_ids) == {"flyer_brief", "flyer_copy"}
        assert result.job.state == "pending"
        assert "private-poll-token" not in result.model_dump_json()
        foreign = CanvaMCPAdapter(Session({}), owner_id="other-owner")
        with pytest.raises(PermissionError):
            await service.start_flyer(OWNER, EVENT, 1, foreign)

    asyncio.run(run())


def test_provider_job_is_preserved_if_revision_changes_while_creating():
    async def run():
        store, _, service = setup()
        await put_prose(store, ("flyer_brief", "flyer_copy"))

        class AdvancingSession(Session):
            async def call_tool(self, name, arguments):
                store.put_event(workflow_event(2))
                return await super().call_tool(name, arguments)

        adapter = CanvaMCPAdapter(AdvancingSession({"create-design": [pending()]}), owner_id=OWNER)
        result = await service.start_flyer(OWNER, EVENT, 1, adapter)
        assert result.job.event_revision == 1 and result.job.job_id == "test-job"
        with pytest.raises(WorkflowError, match="revision_conflict"):
            await service.read(OWNER, EVENT, 1)

    asyncio.run(run())


def export_fixture(**changes):
    return ExportReceipt(
        **{
            "design": design(),
            "export_id": "synthetic-export",
            "state": "completed",
            "download_url": "https://export-download.canva.com/fixture.png",
            **changes,
        }
    )


def test_completed_export_download_and_storage_use_current_go_alt_and_exact_binding():
    async def run():
        store, storage, service = setup()
        await put_prose(store, ("flyer_alt_text",), reviewed=True)
        verified = VerifiedDesign(
            design=design(), state="verified", missing_roles=(), organizer_reviewed=True
        )

        def download(request):
            assert "authorization" not in request.headers
            return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG)

        async with httpx.AsyncClient(transport=httpx.MockTransport(download)) as client:
            saved = await service.store_flyer_export(
                OWNER, EVENT, 1, verified, export_fixture(), ExportDownloader(client)
            )
        assert storage.objects[saved.object_key] == PNG
        assert saved.canva_export_id == "synthetic-export" and saved.review_state == "reviewed"

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["pending", "foreign", "stale", "mismatch", "unverified"])
def test_bad_export_or_design_is_rejected_before_download(mode):
    async def run():
        store, storage, service = setup()
        await put_prose(store, ("flyer_alt_text",))
        binding = design()
        if mode == "foreign":
            binding = binding.model_copy(update={"owner_id": "other-owner"})
        if mode == "stale":
            binding = binding.model_copy(update={"event_revision": 2})
        verified = VerifiedDesign(
            design=binding,
            state="needs_review" if mode == "unverified" else "verified",
            missing_roles=(),
        )
        receipt = export_fixture(
            design=binding, state="pending" if mode == "pending" else "completed"
        )
        if mode == "mismatch":
            receipt = receipt.model_copy(
                update={"design": design().model_copy(update={"design_id": "other-design"})}
            )

        class NoDownload:
            async def png(self, url):
                pytest.fail("Invalid binding must not cause a download")

        with pytest.raises(WorkflowError):
            await service.store_flyer_export(OWNER, EVENT, 1, verified, receipt, NoDownload())
        assert not storage.objects

    asyncio.run(run())


def test_revision_change_during_export_download_prevents_upload():
    async def run():
        store, storage, service = setup()
        await put_prose(store, ("flyer_alt_text",))
        verified = VerifiedDesign(design=design(), state="verified", missing_roles=())

        class ChangingDownload:
            async def png(self, url):
                store.put_event(workflow_event(2))
                return PNG

        with pytest.raises(WorkflowError, match="revision_conflict"):
            await service.store_flyer_export(
                OWNER, EVENT, 1, verified, export_fixture(), ChangingDownload()
            )
        assert not storage.objects

    asyncio.run(run())


def test_actual_supabase_queue_gets_complete_key_in_one_write_and_reuses_canonical_job():
    from hackathon_backend.config import Settings
    from hackathon_backend.repositories.transport import Database
    from hackathon_backend.repositories.workflow import SupabaseWorkflowStore

    owner = "11111111-1111-4111-8111-111111111111"
    event_id = "22222222-2222-4222-8222-222222222222"
    snapshot = workflow_event(id=event_id, owner_id=owner)
    work, writes = [], []

    def server(request):
        if request.url.path.endswith("/organizer_event_json"):
            return httpx.Response(200, json=snapshot.model_dump(mode="json"))
        if request.url.path.endswith("/go_work"):
            return httpx.Response(
                200, json=[{"state": item["state"], "data": item} for item in work]
            )
        if request.url.path.endswith("/organizer_put_work"):
            data = json.loads(request.content)["p_data"]
            expected_key = f"{owner}:{event_id}:r1:go:asset-prose-v1"
            assert data["payload"]["idempotency_key"] == expected_key
            assert data["state"] == "awaiting_go"
            writes.append(data)
            if not work:
                work.append(data)
            return httpx.Response(200, json=work[0])
        pytest.fail(f"Unexpected mocked Supabase path: {request.url.path}")

    async def run():
        database = Database(
            Settings(
                supabase_url="https://fixture.supabase.co",
                supabase_service_role_key="synthetic-service-key",
            ),
            admin=True,
            transport=httpx.MockTransport(server),
        )
        service = EventAssetPreparationService(SupabaseWorkflowStore(database))
        first = await service.request_prose(owner, event_id, 1)
        second = await service.request_prose(owner, event_id, 1)
        assert first.operation_id == second.operation_id
        assert len(work) == 1 and len(writes) == 1  # no post-insert payload rewrite/supersession

    asyncio.run(run())


def test_existing_running_asset_batch_is_reused_without_superseding_it():
    from hackathon_backend.workflows.models import WorkItem, WorkKind

    async def run():
        store, _, service = setup()
        existing = WorkItem(
            owner_id=OWNER,
            event_id=EVENT,
            event_revision=1,
            kind=WorkKind.PREPARE_CONTENT,
            state="running",
            payload={"batch": "asset_prose", "kinds": list(ASSET_PROSE_KINDS)},
        )
        await store.put_work(existing)
        receipt = await service.request_prose(OWNER, EVENT, 1)
        assert receipt.operation_id == existing.id and receipt.state == "queued"
        assert store.work[existing.id].state == "running" and len(store.work) == 1

    asyncio.run(run())
