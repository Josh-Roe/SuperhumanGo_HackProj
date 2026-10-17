import asyncio
import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hackathon_backend.api import create_router
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError, TaskInput
from hackathon_backend.repositories.assets import SupabaseAssetStorage
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore
from hackathon_backend.services.assets.models import StaleRevisionError
from hackathon_backend.workflows.models import WorkItem, WorkKind

OWNER = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
EVENT = "00000000-0000-4000-8000-000000000003"
SETTINGS = Settings(supabase_url="https://example.supabase.co", supabase_publishable_key="public")


def run(awaitable):
    return asyncio.run(awaitable)


def test_repository_write_passes_verified_owner_and_atomic_idempotency_key():
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/organizer_write_record"
        assert request.headers["Authorization"] == "Bearer session"
        data = json.loads(request.content)
        assert data["p_owner"] == OWNER
        assert data["p_key"] == "request-1"
        assert data["p_kind"] == "tasks"
        assert "owner_id" not in data["p_data"]
        return httpx.Response(200, json={"id": EVENT, "revision": 1})

    db = Database(SETTINGS, token="session", transport=httpx.MockTransport(handler))
    result = run(
        OrganizerRepository(db, OWNER).create_task(TaskInput(title="Arrange chairs"), "request-1")
    )
    assert result["revision"] == 1


def test_repository_list_always_filters_owner_even_with_service_client():
    def handler(request):
        assert request.url.params["owner_id"] == "eq." + OWNER
        assert request.url.params["limit"] == "100"
        return httpx.Response(200, json=[])

    db = Database(SETTINGS, token="session", transport=httpx.MockTransport(handler))
    assert run(OrganizerRepository(db, OWNER).list_records("tasks", limit=1000)) == []


def test_revision_conflict_is_typed_and_does_not_leak_sql_details():
    def handler(_):
        return httpx.Response(400, json={"message": "revision_conflict", "details": "secret SQL"})

    db = Database(SETTINGS, token="session", transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as error:
        run(db.rpc("organizer_write_record"))
    assert error.value.code == "revision_conflict" and error.value.status == 409
    assert "secret SQL" not in str(error.value)


def test_content_review_uses_scoped_atomic_review_rpc():
    def handler(request):
        assert request.url.path.endswith("organizer_review_content")
        body = json.loads(request.content)
        assert body == {
            "p_owner": OWNER,
            "p_content": EVENT,
            "p_expected": 2,
            "p_body": None,
            "p_subject": None,
        }
        return httpx.Response(200, json={"state": "ready"})

    db = Database(SETTINGS, token="user", transport=httpx.MockTransport(handler))
    assert (
        run(OrganizerRepository(db, OWNER).review_content(EVENT, 2, None, None))["state"] == "ready"
    )


def test_api_rejects_forged_owner_and_requires_auth_and_idempotency():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"id": OWNER}))
    app = FastAPI()
    app.include_router(create_router(SETTINGS, transport=transport))
    with TestClient(app) as client:
        assert client.post("/api/tasks", json={"title": "x"}).status_code == 401
        headers = {"Authorization": "Bearer session", "Idempotency-Key": "x"}
        assert (
            client.post(
                "/api/tasks", headers=headers, json={"title": "x", "owner_id": OTHER}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/tasks", headers={"Authorization": "Bearer session"}, json={"title": "x"}
            ).status_code
            == 422
        )


def test_api_keeps_foreign_ids_indistinguishable_from_missing():
    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        assert request.url.params["owner_id"] == "eq." + OWNER
        return httpx.Response(200, json=[])

    app = FastAPI()
    app.include_router(create_router(SETTINGS, transport=httpx.MockTransport(handler)))
    with TestClient(app) as client:
        response = client.get(f"/api/tasks/{uuid4()}", headers={"Authorization": "Bearer session"})
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"


def test_public_configuration_contains_no_service_or_vault_secret():
    settings = Settings(
        supabase_url=SETTINGS.supabase_url,
        supabase_publishable_key="public",
        supabase_service_role_key="server-secret",
        credential_encryption_key="vault-key",
    )
    app = FastAPI()
    app.include_router(create_router(settings))
    with TestClient(app) as client:
        response = client.get("/api/config")
        assert "server-secret" not in response.text and "vault-key" not in response.text
        assert response.json()["supabase_publishable_key"] == "public"


def test_work_deduplication_propagates_canonical_id_to_protocol_caller():
    item = WorkItem(owner_id=OWNER, event_id=EVENT, event_revision=1, kind=WorkKind.PREPARE_CONTENT)
    canonical_id = str(uuid4())
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={**item.model_dump(mode="json"), "id": canonical_id})
    )
    run(SupabaseWorkflowStore(Database(SETTINGS, token="user", transport=transport)).put_work(item))
    assert item.id == canonical_id


def test_two_guests_reply_jobs_have_distinct_stable_idempotency_keys():
    keys = []

    def handler(request):
        item = json.loads(request.content)["p_data"]
        keys.append(item["payload"]["idempotency_key"])
        return httpx.Response(200, json=item)

    store = SupabaseWorkflowStore(
        Database(SETTINGS, token="user", transport=httpx.MockTransport(handler))
    )
    for reply_id in ("guest-a-message", "guest-b-message", "guest-a-message"):
        item = WorkItem(
            owner_id=OWNER,
            event_id=EVENT,
            event_revision=1,
            kind=WorkKind.CLASSIFY_REPLY,
            payload={"reply_id": reply_id},
        )
        run(store.put_work(item))
    assert keys[0] != keys[1]
    assert keys[0] == keys[2]


def test_private_asset_upload_is_immutable_and_verifies_existing_bytes():
    content = b"<html>Go supplied prose</html>"
    digest = hashlib.sha256(content).hexdigest()
    key = f"{OWNER}/events/{EVENT}/r1/event_document/{digest}.html"
    writes = []

    def handler(request):
        if request.url.path.endswith("organizer_event_json"):
            return httpx.Response(200, json={"id": EVENT, "owner_id": OWNER, "revision": 1})
        writes.append(request.method)
        if request.method == "POST":
            assert request.headers.get("x-upsert") is None
            return httpx.Response(409, json={})
        return httpx.Response(200, content=content)

    storage = SupabaseAssetStorage(
        Database(SETTINGS, token="user", transport=httpx.MockTransport(handler)), OWNER
    )
    result = run(storage.put_if_absent(key, content, "text/html; charset=utf-8", digest))
    assert result.sha256 == digest and writes == ["POST", "GET"]


def test_private_asset_rejects_foreign_scope_without_network():
    storage = SupabaseAssetStorage(Database(SETTINGS, token="user"), OWNER)
    digest = hashlib.sha256(b"test").hexdigest()
    with pytest.raises(PermissionError):
        run(
            storage.put_if_absent(
                f"{OTHER}/events/{EVENT}/r1/event_document/{digest}.html",
                b"test",
                "text/html; charset=utf-8",
                digest,
            )
        )


def test_private_asset_rejects_stale_revision_before_upload():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"revision": 2}))
    storage = SupabaseAssetStorage(Database(SETTINGS, token="user", transport=transport), OWNER)
    with pytest.raises(StaleRevisionError):
        run(storage.assert_current(OWNER, EVENT, 1))
