"""Member 4 acceptance of the registered Member 3 host. All account traffic is synthetic.

Uses actual app/registration, encrypted vault, Canva adapter, Storage and MIME; the
workflow store, Auth HTTP responses, Canva session and Google APIs are test doubles.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_assets_support import PNG, event
from test_go_mcp_tools import call, ok
from test_workflow_asset_wiring import FakeCanva
from workflow_fakes import FakeCalendar, FakeGmail

from hackathon_backend import main
from hackathon_backend.auth import identity
from hackathon_backend.config import Settings
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.providers.canva import session as canva_session
from hackathon_backend.providers.google.oauth import StaticTokenSource
from hackathon_backend.repositories import transport as database_module
from hackathon_backend.repositories.assets import SupabaseAssetStorage
from hackathon_backend.repositories.vault import SupabaseCredentialVault
from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS
from hackathon_backend.workflows import asset_wiring
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver, InMemoryWorkflowStore
from hackathon_backend.workflows.models import Approval, EventSnapshot, Invitee
from hackathon_backend.workflows.rsvp import RSVPTracker

OWNER = "11111111-1111-4111-8111-111111111111"
EVENT = "22222222-2222-4222-8222-222222222222"
BASE = f"/api/events/{EVENT}/assets"
SESSION = {"Authorization": "Bearer synthetic-session"}


@pytest.fixture
def registered(monkeypatch):
    settings = Settings(
        supabase_url="https://fixture.supabase.co",
        supabase_publishable_key="synthetic-public",
        supabase_service_role_key="synthetic-service",
        credential_encryption_key=Fernet.generate_key().decode(),
        mcp_auth_token="synthetic-deploy",
    )
    snapshot = event(id=EVENT, owner_id=OWNER)
    store = InMemoryWorkflowStore()
    store.put_event(
        EventSnapshot(
            **snapshot.model_dump(),
            organizer_contact="organizer@example.invalid",
            invitees=[Invitee(id="synthetic-invitee", email="guest@example.invalid")],
        )
    )
    rows, objects, secrets, downloads = [], {}, {}, []

    def server(request):
        path = request.url.path
        if request.url.host == "export-download.canva.com":
            assert "authorization" not in request.headers and "apikey" not in request.headers
            return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)
        assert request.url.host == "fixture.supabase.co"
        if path == "/auth/v1/user":
            assert request.headers["authorization"] == "Bearer synthetic-session"
            assert request.headers["apikey"] == "synthetic-public"
            return httpx.Response(200, json={"id": OWNER})
        if path.endswith("/provider_secrets"):
            if request.method == "POST":
                item = json.loads(request.content)
                secrets[(item["owner_id"], item["provider"])] = item
                return httpx.Response(200, json={})
            key = (request.url.params["owner_id"][3:], request.url.params["provider"][3:])
            return httpx.Response(200, json=[secrets[key]] if key in secrets else [])
        if path.endswith("/organizer_event_json"):
            assert json.loads(request.content)["p_owner"] == OWNER
            return httpx.Response(200, json={"revision": store.events[EVENT].revision})
        if path.endswith("/organizer_publish_asset"):
            data = json.loads(request.content)["p_data"]
            for row in rows:
                if row["data"]["kind"] == data["kind"]:
                    row["is_current"] = False
            rows.append(
                {"is_current": True, "event_revision": data["event_revision"], "data": data}
            )
            return httpx.Response(200, json={})
        if path.endswith("/artifacts"):
            return httpx.Response(200, json=rows)
        if "/object/sign/" in path and request.method == "POST":
            assert request.headers["authorization"] == "Bearer synthetic-service"
            return httpx.Response(
                200,
                json={"signedURL": path.removeprefix("/storage/v1") + "?token=synthetic-signature"},
            )
        if "/object/sign/" in path:
            assert "authorization" not in request.headers and "apikey" not in request.headers
            key = path.removeprefix("/storage/v1/object/sign/event-assets/")
            downloads.append(key)
            return httpx.Response(200, content=objects[key])
        if "/object/event-assets/" in path:
            assert request.method == "POST"
            key = path.removeprefix("/storage/v1/object/event-assets/")
            objects[key] = request.content
            return httpx.Response(200, json={})
        pytest.fail(f"Unexpected synthetic request: {path}")

    transport = httpx.MockTransport(server)
    actual_database = database_module.Database

    def database(settings, **kwargs):
        kwargs["transport"] = kwargs.get("transport") or transport
        return actual_database(settings, **kwargs)

    monkeypatch.setattr(database_module, "Database", database)
    monkeypatch.setattr(identity, "Database", database)
    monkeypatch.setattr(
        asset_wiring,
        "_download_client",
        lambda: httpx.AsyncClient(transport=transport, trust_env=False),
    )
    canva = FakeCanva()

    @asynccontextmanager
    async def connect(*, owner_id, access_token):
        assert owner_id == OWNER and access_token == "synthetic-canva-token"
        async with canva.open(owner_id) as session:
            yield session

    monkeypatch.setattr(canva_session, "connect_canva", connect)
    vault = SupabaseCredentialVault(
        database(settings, admin=True), settings.credential_encryption_key
    )
    asyncio.run(vault.put_secret(OWNER, "canva", {"access_token": "synthetic-canva-token"}))
    principals = InMemoryPrincipalResolver()
    connector = principals.issue(OWNER)
    foreign = principals.issue("33333333-3333-4333-8333-333333333333")
    calendar, gmail = FakeCalendar(), FakeGmail()
    tokens = StaticTokenSource(
        {OWNER: "synthetic-google-token"}, {OWNER: "organizer@example.invalid"}
    )
    distributor = Distributor(store, calendar, gmail, tokens)
    deps = EventToolDeps(
        store, principals, distributor, RSVPTracker(store, calendar, gmail, tokens)
    )
    app = main.create_app(settings, events=deps)  # actual main.py and register_asset_services
    with TestClient(app, base_url="http://localhost") as client:
        yield (
            client,
            connector,
            foreign,
            store,
            canva,
            rows,
            objects,
            secrets,
            calendar,
            gmail,
            vault,
        )


def generate_and_review(client, connector, store, revision):
    args = {"event_id": EVENT, "expected_revision": revision}
    first = ok(call(client, connector, "request_asset_prose", args))
    assert first == ok(call(client, connector, "request_asset_prose", args))
    work = first["operation_id"]
    ok(call(client, connector, "claim_go_work", {"work_id": work}))
    for kind in ASSET_PROSE_KINDS:
        saved = ok(
            call(
                client,
                connector,
                "save_generated_content",
                {
                    **args,
                    "kind": kind,
                    "body": f"Synthetic Go-port fixture {kind} r{revision} <unsafe>",
                    "work_id": work,
                },
            )
        )
        assert saved["producer"] == "superhuman_go" and saved["state"] == "needs_review"
        # Simulated authenticated organizer content review, distinct from Go's authority.
        item = store.content[saved["id"]]
        store.content[item.id] = item.model_copy(update={"state": "ready"})
    assert store.work[work].state == "succeeded"
    document = ok(call(client, connector, "prepare_event_document", args))
    assert document["state"] == "stored" and document["asset"]["review_state"] == "reviewed"
    assert "object_key" not in str(document)
    return args


def start_flyer(client, connector, args):
    first = ok(call(client, connector, "start_canva_flyer", args))
    assert first == ok(call(client, connector, "start_canva_flyer", args))
    assert first["stage"] == "pending" and "private-poll-token" not in str(first)
    return first


def test_registered_go_document_canva_export_storage_and_mime_delivery(registered):
    client, token, _, store, canva, rows, objects, secrets, calendar, gmail, vault = registered
    args = generate_and_review(client, token, store, 1)
    start_flyer(client, token, args)
    state = asyncio.run(vault.get_secret(OWNER, f"canva_flyer:{EVENT}"))
    state["job"]["next_poll_at"] = "2020-01-01T00:00:00Z"
    asyncio.run(vault.put_secret(OWNER, f"canva_flyer:{EVENT}", state))
    assert ok(call(client, token, "poll_canva_flyer", args))["stage"] == "created"
    preview = ok(call(client, token, "preview_canva_flyer", args))
    blocked = call(client, token, "export_canva_flyer", args)
    assert blocked["isError"] and "needs_review" in str(blocked)
    response = client.post(
        BASE + "/flyer/approve",
        headers=SESSION,
        json={"expected_revision": 1, "preview_digest": preview["preview"]["digest"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "approved"
    exported = ok(call(client, token, "export_canva_flyer", args))
    assert exported["stage"] == "stored" and exported["asset"]["review_state"] == "reviewed"
    assert exported["asset"]["canva_export_id"] == "export-synthetic"
    assert exported["asset"]["canva_generation_id"]
    assert exported["asset"]["go_generation_id"]
    assert exported["asset"]["created_at"]
    assert "object_key" not in str(exported["asset"])
    assert ok(call(client, token, "export_canva_flyer", args)) == exported
    assert canva.names().count("create-design") == canva.names().count("export-design") == 1
    assert len(objects) == 2 and len(rows) == 2
    assert b"&lt;unsafe&gt;" in next(b for k, b in objects.items() if k.endswith(".html"))
    assert "synthetic-canva-token" not in json.dumps(
        list(secrets.values())
    )  # actual vault encrypts it
    assert "private-poll-token" not in str(exported) and "sig=private" not in str(exported)
    saved = ok(
        call(
            client,
            token,
            "save_generated_content",
            {
                **args,
                "kind": "invitation",
                "body": "Synthetic reviewed invitation",
                "subject": "Synthetic invite",
            },
        )
    )
    store.content[saved["id"]] = store.content[saved["id"]].model_copy(update={"state": "ready"})
    approval = Approval(
        id="synthetic-approval",
        event_id=EVENT,
        event_revision=1,
        action="publish",
        invitation_content_id=saved["id"],
    )
    store.put_approval(approval)
    sent = ok(
        call(client, token, "execute_distribution", {"event_id": EVENT, "approval_id": approval.id})
    )
    assert sent["sent"] and len(calendar.calls) == len(gmail.sent) == 1
    (attachment,) = gmail.sent[0]["parsed"].iter_attachments()
    assert attachment.get_payload(decode=True) == PNG
    ok(call(client, token, "execute_distribution", {"event_id": EVENT, "approval_id": approval.id}))
    assert len(gmail.sent) == 1
    storage = SupabaseAssetStorage(vault.db, OWNER)
    current = asyncio.run(storage.current(EVENT, "event_document"))
    assert current["url"].startswith("https://fixture.supabase.co/storage/v1/object/sign/")


def test_actual_registered_transport_auth_and_inclusion_unknowns(registered):
    client, token, foreign, _, _, _, _, _, _, _, _ = registered
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=SESSION).status_code == 200
    for credential, code in [(foreign, "forbidden"), ("synthetic-deploy", "unauthenticated")]:
        result = call(client, credential, "get_event_assets", {"event_id": EVENT})
        assert result["isError"] and code in str(result)
    response = client.post(
        BASE + "/inclusion", headers=SESSION, json={"expected_revision": 1, "facts": {}}
    )
    assert response.status_code == 200
    assert any(f["status"] == "unknown" for f in response.json()["findings"])


def test_started_unexported_flyer_blocks_actual_registered_distribution(registered):
    client, token, _, store, _, _, _, _, calendar, gmail, _ = registered
    args = generate_and_review(client, token, store, 1)
    start_flyer(client, token, args)
    saved = ok(
        call(
            client,
            token,
            "save_generated_content",
            {
                **args,
                "kind": "invitation",
                "body": "Synthetic invite",
                "subject": "Synthetic",
            },
        )
    )
    store.content[saved["id"]] = store.content[saved["id"]].model_copy(update={"state": "ready"})
    approval = Approval(
        id="synthetic-approval",
        event_id=EVENT,
        event_revision=1,
        action="publish",
        invitation_content_id=saved["id"],
    )
    store.put_approval(approval)
    result = call(
        client, token, "execute_distribution", {"event_id": EVENT, "approval_id": approval.id}
    )
    assert result["isError"] and "needs_review" in str(result)
    assert not calendar.calls and not gmail.drafts and not gmail.sent


def test_changed_location_renders_new_document_and_keeps_prior_bytes(registered):
    client, token, _, store, _, rows, objects, _, _, _, _ = registered
    generate_and_review(client, token, store, 1)
    old_objects = dict(objects)
    current = store.events[EVENT]
    store.put_event(current.model_copy(update={"revision": 2, "location": "Fixture Room B"}))
    waiting = ok(
        call(client, token, "prepare_event_document", {"event_id": EVENT, "expected_revision": 2})
    )
    assert waiting["state"] == "awaiting_go" and objects == old_objects
    generate_and_review(client, token, store, 2)
    assert len(objects) == 2
    for key, value in old_objects.items():
        assert objects[key] == value and b"Fixture Room A" in value
    current_rows = [r for r in rows if r["is_current"]]
    assert len(current_rows) == 1 and current_rows[0]["event_revision"] == 2
    assert b"Fixture Room B" in objects[current_rows[0]["data"]["object_key"]]
