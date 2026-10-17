import asyncio
import hashlib
import json
import struct
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hackathon_backend.api import create_router
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.main import MCPBearerAuth
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.repositories.assets import SupabaseAttachmentSource
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.workflows.go_work import WorkflowError

OWNER, OTHER, EVENT, ASSET, GENERATION = (str(uuid4()) for _ in range(5))
SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_publishable_key="public",
    supabase_service_role_key="server-only",
)
NOW = datetime.now(UTC).isoformat()
HEADERS = {"Authorization": "Bearer user-session"}


def saved_event(revision=1):
    return {
        "id": EVENT,
        "owner_id": OWNER,
        "revision": revision,
        "status": "draft",
        "organizer_contact": "organizer@example.invalid",
        "title": "Synthetic event",
        "location": "Room A",
        "starts_at": "2026-11-01T18:00:00Z",
        "ends_at": "2026-11-01T19:00:00Z",
        "timezone": "UTC",
        "created_at": NOW,
        "updated_at": NOW,
    }


def client_for(handler, deps=None):
    app = FastAPI()
    app.include_router(create_router(SETTINGS, transport=httpx.MockTransport(handler), events=deps))
    return TestClient(app)


def test_workspace_contains_real_revisioned_rows_and_excludes_worker_secrets():
    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("organizer_event_json"):
            assert json.loads(request.content)["p_owner"] == OWNER
            return httpx.Response(200, json=saved_event())
        if request.url.path.endswith("go_work"):
            assert request.url.params["owner_id"] == "eq." + OWNER
            return httpx.Response(
                200,
                json=[
                    {
                        "id": GENERATION,
                        "event_revision": 1,
                        "kind": "prepare_content",
                        "state": "awaiting_go",
                        "payload": {"continuation": "secret"},
                    }
                ],
            )
        if request.url.path.endswith("generated_content"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": GENERATION,
                        "event_id": EVENT,
                        "event_revision": 1,
                        "kind": "flyer_copy",
                        "producer": "superhuman_go",
                        "body": "Fixture",
                        "state": "needs_review",
                        "created_at": NOW,
                    }
                ],
            )
        return httpx.Response(200, json=[])

    with client_for(handler) as client:
        response = client.get(f"/api/events/{EVENT}/workspace", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["event"]["id"] == EVENT
    assert data["work"][0]["state"] == "awaiting_go"
    assert data["generated_content"][0]["kind"] == "flyer_copy"
    assert data["artifacts"] == [] and data["calendar"] is None
    assert "secret" not in response.text and "payload" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_workspace_rejects_revision_race_and_foreign_event_before_children():
    calls = 0

    def handler(request):
        nonlocal calls
        if request.url.path.endswith("organizer_event_json"):
            calls += 1
            return httpx.Response(200, json=saved_event(1 if calls == 1 else 2))
        return httpx.Response(200, json=[])

    repo = OrganizerRepository(
        Database(SETTINGS, token="user", transport=httpx.MockTransport(handler)), OWNER
    )
    with pytest.raises(DomainError, match="Event changed"):
        asyncio.run(repo.workspace(EVENT))

    def foreign(request):
        assert request.url.path.endswith("organizer_event_json")
        return httpx.Response(200, json=None)

    repo = OrganizerRepository(
        Database(SETTINGS, admin=True, transport=httpx.MockTransport(foreign)), OTHER
    )
    with pytest.raises(DomainError) as caught:
        asyncio.run(repo.workspace(EVENT))
    assert caught.value.status == 404


def test_artifact_review_forwards_verified_owner_revision_and_exact_hash_to_server():
    digest = "a" * 64
    writes = []

    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("organizer_event_json"):
            assert request.headers["authorization"] == "Bearer user-session"
            return httpx.Response(200, json=saved_event())
        assert request.url.path.endswith("organizer_review_asset")
        assert request.headers["authorization"] == "Bearer server-only"
        writes.append(json.loads(request.content))
        return httpx.Response(200, json={"id": ASSET, "review_state": "reviewed"})

    with client_for(handler) as client:
        response = client.post(
            f"/api/events/{EVENT}/artifacts/{ASSET}/review",
            headers=HEADERS,
            json={"expected_revision": 1, "sha256": digest},
        )
    assert response.status_code == 200
    assert writes == [
        {"p_owner": OWNER, "p_event": EVENT, "p_asset": ASSET, "p_expected": 1, "p_hash": digest}
    ]


def test_distribution_endpoints_use_verified_owner_and_never_create_approvals():
    class Distributor:
        async def execute(self, owner_id, event_id, approval_id):
            assert (owner_id, event_id, approval_id) == (OWNER, EVENT, ASSET)
            return {
                "event_id": EVENT,
                "event_revision": 1,
                "operations": [],
                "calendar_link": None,
                "sent": False,
            }

    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        assert request.url.path.endswith("organizer_event_json")
        return httpx.Response(200, json=saved_event())

    deps = EventToolDeps(store=None, principals=None, distributor=Distributor())
    with client_for(handler, deps) as client:
        url = f"/api/events/{EVENT}/distribution/execute"
        assert (
            client.post(url, json={"expected_revision": 1, "approval_id": ASSET}).status_code == 401
        )
        stale = client.post(
            url, headers=HEADERS, json={"expected_revision": 2, "approval_id": ASSET}
        )
        assert stale.status_code == 409
        response = client.post(
            url, headers=HEADERS, json={"expected_revision": 1, "approval_id": ASSET}
        )
        assert response.status_code == 200
        assert response.json()["sent"] is False


def test_rest_reuses_member3_registered_distribution_instance():
    class SharedDistributor:
        async def preview(self, owner_id, event_id):
            assert (owner_id, event_id) == (OWNER, EVENT)
            return {
                "event_id": EVENT,
                "event_revision": 1,
                "calendar_action": "create",
                "calendar_event_id": None,
                "gmail_action": "create_draft",
                "required_content_kind": "invitation",
                "invitee_count": 0,
                "blockers": ["shared-policy"],
            }

    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        assert request.url.path.endswith("organizer_event_json")
        return httpx.Response(200, json=saved_event())

    app = FastAPI()
    app.include_router(create_router(SETTINGS, transport=httpx.MockTransport(handler)))
    app.add_middleware(
        MCPBearerAuth,
        token="",
        deps=EventToolDeps(store=None, principals=None, distributor=SharedDistributor()),
    )
    with TestClient(app) as client:
        result = client.post(
            f"/api/events/{EVENT}/distribution/preview",
            headers=HEADERS,
            json={"expected_revision": 1},
        )
    assert result.status_code == 200
    assert result.json()["blockers"] == ["shared-policy"]


def test_supabase_attachments_require_both_files():
    content = b"<!doctype html><p>Go document fixture</p>"
    digest = hashlib.sha256(content).hexdigest()
    record = {
        "owner_id": OWNER,
        "event_id": EVENT,
        "event_revision": 1,
        "kind": "event_document",
        "object_key": f"{OWNER}/events/{EVENT}/r1/event_document/{digest}.html",
        "sha256": digest,
        "byte_length": len(content),
        "content_type": "text/html; charset=utf-8",
        "go_generation_id": GENERATION,
        "review_state": "reviewed",
        "created_at": NOW,
    }

    def handler(request):
        if request.url.path.endswith("organizer_event_json"):
            return httpx.Response(200, json=saved_event())
        return httpx.Response(
            200, json=[{"id": ASSET, "kind": "event_document", "is_current": True, "data": record}]
        )

    source = SupabaseAttachmentSource(
        Database(SETTINGS, admin=True, transport=httpx.MockTransport(handler))
    )
    event = type("Event", (), {"owner_id": OWNER, "id": EVENT, "revision": 1})()
    with pytest.raises(WorkflowError) as caught:
        asyncio.run(source.current_attachments(OWNER, event))
    assert (
        caught.value.code == "needs_review"
    )  # document alone must not send a flyerless invitation


@pytest.mark.parametrize("corrupt", [False, True])
def test_supabase_private_bytes_feed_member4_attachment_validation(corrupt):
    files = {
        "flyer_png": b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 120, 160),
        "event_document": b"<!doctype html><p>Synthetic Go document</p>",
    }
    rows = []
    for kind, content in files.items():
        digest = hashlib.sha256(content).hexdigest()
        suffix = "png" if kind == "flyer_png" else "html"
        record = {
            "owner_id": OWNER,
            "event_id": EVENT,
            "event_revision": 1,
            "kind": kind,
            "object_key": f"{OWNER}/events/{EVENT}/r1/{kind}/{digest}.{suffix}",
            "sha256": digest,
            "byte_length": len(content),
            "content_type": "image/png" if suffix == "png" else "text/html; charset=utf-8",
            "go_generation_id": GENERATION,
            "review_state": "reviewed",
            "created_at": NOW,
            "canva_design_id": "synthetic-design" if suffix == "png" else None,
            "canva_export_id": "synthetic-export" if suffix == "png" else None,
            "canva_generation_id": GENERATION if suffix == "png" else None,
        }
        rows.append({"id": str(uuid4()), "kind": kind, "is_current": True, "data": record})

    def handler(request):
        assert request.headers["authorization"] == "Bearer server-only"
        if request.url.path.endswith("organizer_event_json"):
            assert json.loads(request.content)["p_owner"] == OWNER
            return httpx.Response(200, json=saved_event())
        if request.url.path.endswith("artifacts"):
            assert request.url.params["event_id"] == "eq." + EVENT
            return httpx.Response(200, json=rows)
        kind = "flyer_png" if "/flyer_png/" in request.url.path else "event_document"
        return httpx.Response(200, content=b"broken" if corrupt else files[kind])

    source = SupabaseAttachmentSource(
        Database(SETTINGS, admin=True, transport=httpx.MockTransport(handler))
    )
    event = type("Event", (), {"owner_id": OWNER, "id": EVENT, "revision": 1})()
    if corrupt:
        with pytest.raises(WorkflowError) as caught:
            asyncio.run(source.current_attachments(OWNER, event))
        assert caught.value.code == "provider_failed"
    else:
        loaded = asyncio.run(source.current_attachments(OWNER, event))
        assert [mime for _, mime, _ in loaded] == ["image/png", "text/html"]
        assert [body for _, _, body in loaded] == list(files.values())


def test_private_download_limits_bytes_and_rejects_redirects_without_following():
    paths = []

    def handler(request):
        paths.append(str(request.url))
        if request.url.path.endswith("redirect"):
            return httpx.Response(302, headers={"Location": "https://evil.invalid"})
        return httpx.Response(200, content=b"123456")

    database = Database(SETTINGS, admin=True, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError, match="byte limit"):
        asyncio.run(database.download("/storage/v1/object/event-assets/file", max_bytes=5))
    with pytest.raises(DomainError, match="Unable to load"):
        asyncio.run(database.download("/storage/v1/object/event-assets/redirect", max_bytes=5))
    assert len(paths) == 2 and all("evil" not in path for path in paths)


def test_inclusion_save_authorizes_user_then_versions_facts_using_server_credentials():
    writes = []

    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("organizer_event_json"):
            assert request.headers["authorization"] == "Bearer user-session"
            return httpx.Response(200, json=saved_event())
        assert request.url.path.endswith("organizer_save_inclusion")
        assert request.headers["authorization"] == "Bearer server-only"
        writes.append(json.loads(request.content))
        return httpx.Response(200, json=saved_event(2))

    with client_for(handler) as client:
        url = f"/api/events/{EVENT}/inclusion/revision"
        response = client.put(url, headers=HEADERS, json={"expected_revision": 1, "facts": {}})
        assert response.status_code == 200 and response.json()["revision"] == 2
        forged = client.put(
            url, headers=HEADERS, json={"expected_revision": 1, "facts": {}, "owner_id": OTHER}
        )
        assert forged.status_code == 422
    assert len(writes) == 1 and writes[0]["p_owner"] == OWNER
    assert writes[0]["p_inputs"]["step_free_entrance"]["value"] == "unknown"


def test_inclusion_read_runs_actual_member4_checker_without_claiming_unknown_facts():
    def handler(request):
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("organizer_event_json"):
            return httpx.Response(200, json=saved_event())
        return httpx.Response(200, json=[])

    with client_for(handler) as client:
        response = client.get(f"/api/events/{EVENT}/inclusion/revision", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["facts_saved"] is False
    assert data["report"]["audience"] == "organizer_private"
    assert data["report"]["certification"] is False
    assert any(f["status"] == "unknown" for f in data["report"]["findings"])
