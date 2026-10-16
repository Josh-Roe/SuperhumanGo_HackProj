"""Runs when Member 3's branch is present; verified using a temporary source overlay.

All content/accounts are synthetic. This is not a live Go, Gmail or Supabase test.
"""

import asyncio
from email import policy
from email.parser import BytesParser

import pytest
from test_assets_attachments import prepared
from test_assets_support import PNG, event

from hackathon_backend.services.assets.attachments import RevisionedAttachmentSource
from hackathon_backend.services.assets.models import GoContent
from hackathon_backend.services.assets.requests import request_event_prose

models = pytest.importorskip(
    "hackathon_backend.workflows.models", reason="Member 3 branch not merged"
)


def workflow_event():
    return models.EventSnapshot(
        **event().model_dump(), organizer_contact="organizer@example.invalid"
    )


def test_actual_member3_distributor_embeds_exact_reviewed_flyer_bytes():
    from hackathon_backend.workflows.distribution import Distributor

    class Tokens:
        async def account_email(self, owner_id):
            assert owner_id == "fixture-owner"
            return "organizer@example.invalid"

    async def run():
        repository = await prepared()
        distributor = Distributor(
            None, None, None, Tokens(), attachments=RevisionedAttachmentSource(repository)
        )
        content = models.GeneratedContent(
            event_id=event().id,
            event_revision=1,
            kind=models.ContentKind.INVITATION,
            body="SYNTHETIC invitation fixture; never sent.",
            producer=models.Producer.SUPERHUMAN_GO,
            state="ready",
        )
        mime = await distributor._mime("fixture-owner", workflow_event(), content, None)
        message = BytesParser(policy=policy.default).parsebytes(mime)
        (attachment,) = message.iter_attachments()
        assert attachment.get_payload(decode=True) == PNG
        assert attachment.get_filename() == "event-fixture-event-r1-flyer.png"
        assert message["X-Event-Revision"] == "fixture-event/1"

    asyncio.run(run())


def test_actual_member3_go_queue_and_content_loader_match_asset_contracts():
    from hackathon_backend.workflows.asset_queue import GoAssetQueue, load_go_content
    from hackathon_backend.workflows.go_work import save_go_content
    from hackathon_backend.workflows.memory import InMemoryWorkflowStore

    async def run():
        store = InMemoryWorkflowStore()
        store.put_event(workflow_event())
        queue = GoAssetQueue(store)
        first = await request_event_prose(event(), queue, owner_id="fixture-owner")
        again = await request_event_prose(event(), queue, owner_id="fixture-owner")
        assert first.operation_id == again.operation_id and first.state == "awaiting_go"
        await save_go_content(
            store,
            "fixture-owner",
            event_id=event().id,
            expected_revision=1,
            kind=models.ContentKind.FLYER_BRIEF,
            body="SYNTHETIC content-loader compatibility fixture.",
        )
        raw = await load_go_content(
            store, "fixture-owner", event().id, 1, models.ContentKind.FLYER_BRIEF
        )
        loaded = GoContent.model_validate(raw)
        assert loaded.kind == "flyer_brief" and not loaded.reviewed_by_organizer

    asyncio.run(run())


def test_actual_member2_storage_write_read_bridge_and_member3_attachment_contract():
    pytest.importorskip(
        "hackathon_backend.repositories.assets", reason="Member 2 branch not present"
    )
    import json

    import httpx
    from hackathon_backend.repositories.assets import SupabaseAssetStorage
    from hackathon_backend.repositories.transport import Database
    from test_assets_support import go
    from test_canva_mcp import design

    from hackathon_backend.config import Settings
    from hackathon_backend.providers.canva import VerifiedDesign
    from hackathon_backend.services.assets.storage import AssetService
    from hackathon_backend.services.assets.supabase_read import SupabaseAttachmentRepository

    owner = "11111111-1111-4111-8111-111111111111"
    snapshot = event(id="22222222-2222-4222-8222-222222222222", owner_id=owner)
    artifacts, objects = [], {}

    def database_server(request):
        path = request.url.path
        if path.endswith("/organizer_event_json"):
            return httpx.Response(200, json={"revision": 1})
        if path.endswith("/organizer_publish_asset"):
            record = json.loads(request.content)["p_data"]
            artifacts.append({"is_current": True, "event_revision": 1, "data": record})
            return httpx.Response(200, json={})
        if path.endswith("/artifacts"):
            return httpx.Response(200, json=artifacts)
        if "/object/sign/" in path:
            return httpx.Response(
                200,
                json={"signedURL": path.removeprefix("/storage/v1") + "?token=synthetic-signature"},
            )
        if "/object/event-assets/" in path:
            objects[path.removeprefix("/storage/v1/object/event-assets/")] = request.content
            return httpx.Response(200, json={})
        pytest.fail(f"Unexpected synthetic Storage request: {path}")

    def download_server(request):
        assert "authorization" not in request.headers and "apikey" not in request.headers
        key = request.url.path.removeprefix("/storage/v1/object/sign/event-assets/")
        return httpx.Response(200, headers={"content-type": "image/png"}, content=objects[key])

    async def run():
        database = Database(
            Settings(
                supabase_url="https://fixture.supabase.co",
                supabase_service_role_key="synthetic-service-key",
            ),
            admin=True,
            transport=httpx.MockTransport(database_server),
        )
        storage = SupabaseAssetStorage(database, owner)
        record = await AssetService(storage).save_flyer(
            snapshot,
            VerifiedDesign(
                design=design(snapshot), state="verified", missing_roles=(), organizer_reviewed=True
            ),
            PNG,
            owner_id=owner,
            export_id="synthetic-export",
            alt_text=go(snapshot, "flyer_alt_text", reviewed_by_organizer=True),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(download_server)) as client:
            bridge = SupabaseAttachmentRepository(
                storage, client, storage_origin="https://fixture.supabase.co"
            )
            files = await RevisionedAttachmentSource(bridge).current_attachments(owner, snapshot)
        assert files[0][2] == PNG and artifacts[0]["data"]["sha256"] == record.sha256

    asyncio.run(run())
