"""Member 3 asset composition over Member 4 services with synthetic fakes; no network."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP
from starlette.routing import Mount
from test_assets_preparation import EVENT, OWNER, put_prose, workflow_event
from test_assets_storage import Storage
from test_assets_support import NOW, PNG, event
from test_canva_mcp import Session, design, pending

from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.providers.canva import CanvaMCPAdapter
from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS
from hackathon_backend.workflows.asset_wiring import (
    AssetCoordinator,
    FlyerRequiredPolicy,
    MemoryFlyerStateStore,
    VaultCanvaSessions,
    VaultFlyerStateStore,
    register_assets,
)
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.memory import InMemoryWorkflowStore

# Member 4's create_flyer stamps next_poll_at from wall time; poll comfortably after it.
LATER = datetime.now(UTC) + timedelta(hours=1)


def run(coro):
    return asyncio.run(coro)


def canva_responses():
    metadata = {
        "design": {
            "id": "D-synthetic",
            "updated_at": 100,
            "page_count": 1,
            "thumbnail": {"url": "https://media.canva.com/synthetic-preview"},
        }
    }
    text = {"text": "\n".join(event().flyer_fields().values())}
    return {
        "create-design": [pending()],
        "get-create-design-async-job": [
            {
                "status": "completed",
                "job_id": "test-job",
                "design": {
                    "id": "D-synthetic",
                    "edit_url": design().edit_url,
                    "url": design().view_url,
                },
            }
        ],
        "get-design": [metadata] * 4,
        "get-design-content": [text] * 4,
        "export-design": [
            {
                "job": {
                    "status": "success",
                    "id": "export-synthetic",
                    "urls": ["https://export-download.canva.com/fixture.png?sig=private"],
                }
            }
        ],
    }


class FakeCanva:
    def __init__(self, *, actions=("create", "review", "edit", "export"), connected=True):
        self.session = Session(canva_responses())
        self.actions = actions
        self.is_connected = connected
        self.opened = 0

    async def connected(self, owner_id):
        return self.is_connected

    @asynccontextmanager
    async def open(self, owner_id):
        if not self.is_connected:
            raise WorkflowError("integration_not_connected", "Canva is not connected")
        self.opened += 1
        session = self.session
        actions = self.actions
        yield SimpleNamespace(
            capabilities=lambda: SimpleNamespace(
                available_actions=actions, missing_tools=() if len(actions) == 4 else ("x",)
            ),
            adapter=lambda *, owner_id: CanvaMCPAdapter(session, owner_id=owner_id),
        )

    def names(self):
        return [name for name, _ in self.session.calls]


def png_client():
    def download(request):
        assert "authorization" not in request.headers
        assert request.url.host == "export-download.canva.com"
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG)

    return httpx.AsyncClient(transport=httpx.MockTransport(download))


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def build(canva=None, storage=None):
    store = InMemoryWorkflowStore()
    store.put_event(workflow_event())
    storage = storage if storage is not None else Storage()
    clock = Clock()
    coordinator = AssetCoordinator(
        store,
        storage_for=lambda owner: storage,
        canva=canva,
        flyers=MemoryFlyerStateStore(),
        client_factory=png_client,
        clock=clock,
    )
    return store, storage, coordinator, clock


def test_full_flyer_flow_go_prose_canva_review_export_storage():
    async def flow():
        canva = FakeCanva()
        store, storage, coord, clock = build(canva)
        queued = await coord.request_prose(OWNER, EVENT, 1)
        assert queued["state"] == "awaiting_go"
        with pytest.raises(WorkflowError, match="awaiting_go"):
            await coord.start_flyer(OWNER, EVENT, 1)
        assert canva.names() == []
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)

        started = await coord.start_flyer(OWNER, EVENT, 1)
        again = await coord.start_flyer(OWNER, EVENT, 1)
        assert started["stage"] == again["stage"] == "pending"
        assert canva.names().count("create-design") == 1  # never a second design
        assert "private-poll-token" not in repr(started) + repr(again)

        clock.now = LATER
        polled = await coord.poll_flyer(OWNER, EVENT, 1)
        assert polled["stage"] == "created" and polled["design"]["design_id"] == "D-synthetic"
        assert canva.session.calls[-1][1]["continuation_token"] == "private-poll-token"

        with pytest.raises(WorkflowError, match="needs_review"):
            await coord.export_flyer(OWNER, EVENT, 1)  # not approved yet
        preview = await coord.preview_flyer(OWNER, EVENT, 1)
        digest = preview["preview"]["digest"]
        assert preview["stage"] == "previewed" and len(digest) == 64
        with pytest.raises(WorkflowError, match="needs_review"):
            await coord.approve_flyer(OWNER, EVENT, 1, "0" * 64)
        clock.now += timedelta(seconds=1)
        approved = await coord.approve_flyer(OWNER, EVENT, 1, digest)
        assert approved["stage"] == "approved" and approved["verified"]["organizer_reviewed"]

        stored = await coord.export_flyer(OWNER, EVENT, 1)
        assert stored["stage"] == "stored" and stored["asset"]["kind"] == "flyer_png"
        assert stored["asset"]["review_state"] == "reviewed"
        (record,) = [storage.current["flyer_png"]]
        assert storage.objects[record.object_key] == PNG
        assert record.canva_export_id == "export-synthetic"
        assert "sig=private" not in repr(stored)
        exports = canva.names().count("export-design")
        assert (await coord.export_flyer(OWNER, EVENT, 1))["stage"] == "stored"
        assert canva.names().count("export-design") == exports  # idempotent

        status = await coord.status(OWNER, EVENT)
        assert status["flyer_required_for_invitations"] is True
        assert status["canva"] == "connected" and status["prose"]["prose_state"] == "reviewed"

    run(flow())


def test_missing_canva_fails_closed_without_claiming_success():
    async def flow():
        store, _, coord, _ = build(canva=None)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        with pytest.raises(WorkflowError) as raised:
            await coord.start_flyer(OWNER, EVENT, 1)
        assert raised.value.code == "integration_not_connected"
        assert await coord.flyers.get(OWNER, EVENT) is None  # nothing required, nothing faked
        status = await coord.status(OWNER, EVENT)
        assert status["canva"] == "integration_not_connected" and status["flyer"] is None

        disconnected = FakeCanva(connected=False)
        store, _, coord, _ = build(disconnected)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        with pytest.raises(WorkflowError, match="integration_not_connected"):
            await coord.start_flyer(OWNER, EVENT, 1)
        limited = FakeCanva(actions=("review",))
        store, _, coord, _ = build(limited)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        with pytest.raises(WorkflowError, match="integration_not_connected"):
            await coord.start_flyer(OWNER, EVENT, 1)
        assert limited.names() == []

    run(flow())


def test_interrupted_create_is_not_blindly_retried_and_abandon_lifts_requirement():
    async def flow():
        canva = FakeCanva()
        canva.session.responses["create-design"] = [RuntimeError("connection lost")]

        async def broken(name, arguments):
            canva.session.calls.append((name, arguments))
            raise RuntimeError("connection lost")

        canva.session.call_tool = broken
        store, _, coord, _ = build(canva)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        with pytest.raises(WorkflowError):
            await coord.start_flyer(OWNER, EVENT, 1)
        with pytest.raises(WorkflowError, match="needs_review"):
            await coord.start_flyer(OWNER, EVENT, 1)
        assert canva.names() == ["create-design"]
        policy = FlyerRequiredPolicy(coord.flyers)
        snapshot = store.events[EVENT]
        assert await policy.requires_attachments(OWNER, snapshot) is True
        abandoned = await coord.abandon_flyer(OWNER, EVENT, 1)
        assert abandoned["stage"] == "abandoned" and abandoned["prior_attempts"] == 1
        assert await policy.requires_attachments(OWNER, snapshot) is False

    run(flow())


def test_stale_revision_and_foreign_owner_are_rejected():
    async def flow():
        canva = FakeCanva()
        store, _, coord, _ = build(canva)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
        await coord.start_flyer(OWNER, EVENT, 1)
        with pytest.raises(WorkflowError, match="revision_conflict"):
            await coord.poll_flyer(OWNER, EVENT, 2)
        with pytest.raises(WorkflowError, match="forbidden"):
            await coord.status("other-owner", EVENT)
        with pytest.raises(WorkflowError, match="needs_review"):
            await coord.preview_flyer("other-owner", EVENT, 1)

    run(flow())


class FakeVault:
    def __init__(self):
        self.secrets = {}

    async def put_secret(self, owner_id, provider, value):
        self.secrets[(owner_id, provider)] = value

    async def get_secret(self, owner_id, provider):
        return self.secrets.get((owner_id, provider))


def test_vault_state_keeps_continuation_token_server_side_and_sessions_need_token():
    async def flow():
        vault = FakeVault()
        flyers = VaultFlyerStateStore(vault)
        from hackathon_backend.workflows.asset_wiring import FlyerState

        state = FlyerState(
            event_id=EVENT, event_revision=1, stage="pending", continuation_token="secret-poll"
        )
        await flyers.put(OWNER, state)
        assert vault.secrets[(OWNER, f"canva_flyer:{EVENT}")]["continuation_token"]
        loaded = await flyers.get(OWNER, EVENT)
        assert loaded.continuation_token == "secret-poll"
        assert "secret-poll" not in repr(loaded.public()) + repr(loaded)

        opened = []

        @asynccontextmanager
        async def connect(*, owner_id, access_token):
            opened.append(access_token)
            yield SimpleNamespace()

        sessions = VaultCanvaSessions(vault, connect=connect)
        assert await sessions.connected(OWNER) is False
        with pytest.raises(WorkflowError, match="integration_not_connected"):
            async with sessions.open(OWNER):
                pass
        await vault.put_secret(OWNER, "canva", {"access_token": "canva-token"})
        assert await sessions.connected(OWNER) is True
        async with sessions.open(OWNER):
            pass
        assert opened == ["canva-token"]

    run(flow())


class FakeDistributor:
    attachments = None
    attachment_policy = None


def composed(canva=None):
    store, storage, coord, clock = build(canva)
    app = FastAPI()
    mcp = FastMCP("test")
    app.router.routes.append(Mount("/", app=mcp.streamable_http_app()))
    deps = EventToolDeps(store=store, principals=None, distributor=FakeDistributor())

    async def resolve_owner(authorization):
        if authorization != "Bearer organizer":
            from hackathon_backend.domain.models import DomainError

            raise DomainError("unauthenticated", "sign in", 401)
        return OWNER

    source = object()
    register_assets(app, mcp, deps, coord, resolve_owner, attachments=source)
    return app, mcp, deps, store, coord, clock, source


def test_registration_tools_routes_and_distributor_wiring():
    app, mcp, deps, *_ , source = composed(FakeCanva())
    tools = {tool.name for tool in run(mcp.list_tools())}
    assert {
        "get_event_assets",
        "request_asset_prose",
        "prepare_event_document",
        "start_canva_flyer",
        "poll_canva_flyer",
        "preview_canva_flyer",
        "export_canva_flyer",
    } <= tools
    assert not any("approve" in name or "abandon" in name for name in tools)  # organizer-only
    routes = app.router.routes
    mount = next(i for i, route in enumerate(routes) if isinstance(route, Mount))
    assert mount == len(routes) - 1  # asset routes were placed ahead of the MCP catch-all
    schema = app.openapi()["paths"]
    assert "/api/events/{event_id}/assets/flyer/approve" in schema
    assert "/api/events/{event_id}/assets/inclusion" in schema
    assert deps.distributor.attachments is source
    assert isinstance(deps.distributor.attachment_policy, FlyerRequiredPolicy)


def test_rest_routes_require_organizer_and_approve_exact_preview():
    canva = FakeCanva()
    app, _, _, store, coord, clock, _ = composed(canva)
    run(put_prose(store, ASSET_PROSE_KINDS, reviewed=True))
    client = TestClient(app)
    base = f"/api/events/{EVENT}/assets"
    auth = {"Authorization": "Bearer organizer"}
    assert client.get(base).status_code == 401
    assert client.get(base, headers=auth).status_code == 200
    started = client.post(f"{base}/flyer", json={"expected_revision": 1}, headers=auth)
    assert started.status_code == 200 and started.json()["stage"] == "pending"
    clock.now = LATER
    polled = client.post(f"{base}/flyer/poll", json={"expected_revision": 1}, headers=auth)
    assert polled.status_code == 200 and polled.json()["stage"] == "created"
    preview = client.post(f"{base}/flyer/preview", json={"expected_revision": 1}, headers=auth)
    digest = preview.json()["preview"]["digest"]
    wrong = client.post(
        f"{base}/flyer/approve",
        json={"expected_revision": 1, "preview_digest": "0" * 64},
        headers=auth,
    )
    assert wrong.status_code == 409 and wrong.json()["detail"]["code"] == "needs_review"
    clock.now += timedelta(seconds=1)
    ok = client.post(
        f"{base}/flyer/approve",
        json={"expected_revision": 1, "preview_digest": digest},
        headers=auth,
    )
    assert ok.status_code == 200 and ok.json()["stage"] == "approved"
    assert ok.headers["cache-control"] == "no-store"
    stale = client.post(f"{base}/flyer/export", json={"expected_revision": 2}, headers=auth)
    assert stale.json()["detail"]["code"] == "revision_conflict"


def test_rest_missing_canva_returns_503_integration_not_connected():
    app, _, _, store, *_ = composed(None)
    run(put_prose(store, ASSET_PROSE_KINDS, reviewed=True))
    response = TestClient(app).post(
        f"/api/events/{EVENT}/assets/flyer",
        json={"expected_revision": 1},
        headers={"Authorization": "Bearer organizer"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "integration_not_connected"
