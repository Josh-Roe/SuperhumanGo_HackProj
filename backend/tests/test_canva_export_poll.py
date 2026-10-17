"""A19: a pending Canva export is resumed by its job ID instead of requesting another export.

Canva HTTP (MCP session + Connect REST) is faked; coordinator, adapter and REST reader are real.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from test_assets_preparation import EVENT, OWNER, put_prose
from test_workflow_asset_wiring import LATER, FakeCanva, build, run

from hackathon_backend.providers.canva import CanvaMCPAdapter
from hackathon_backend.providers.canva.connect import CanvaConnectExports
from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS
from hackathon_backend.workflows.go_work import WorkflowError

PENDING = {"job": {"id": "export-123", "status": "in_progress"}}
SUCCESS = {
    "job": {
        "id": "export-123",
        "status": "success",
        "urls": ["https://export-download.canva.com/fixture.png?sig=private"],
    }
}


class ConnectApi:
    """Fake Canva Connect `GET /v1/exports/{id}` serving queued job states."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.requested = []

    def transport(self):
        def handle(request):
            self.requested.append((request.url.path, request.headers["authorization"]))
            return httpx.Response(200, json=self.bodies.pop(0))

        return httpx.MockTransport(handle)


class PollingCanva(FakeCanva):
    def __init__(self, api, export_result):
        super().__init__()
        self.session.responses["export-design"] = [export_result]
        self.exports = CanvaConnectExports("organizer-token", transport=api.transport())

    @asynccontextmanager
    async def open(self, owner_id):
        session, exports = self.session, self.exports
        yield SimpleNamespace(
            capabilities=lambda: SimpleNamespace(available_actions=self.actions, missing_tools=()),
            adapter=lambda *, owner_id: CanvaMCPAdapter(
                session, owner_id=owner_id, export_jobs=exports
            ),
        )


async def approved_flyer(canva):
    store, storage, coord, clock = build(canva)
    await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)
    await coord.start_flyer(OWNER, EVENT, 1)
    clock.now = LATER
    await coord.poll_flyer(OWNER, EVENT, 1)
    preview = await coord.preview_flyer(OWNER, EVENT, 1)
    clock.now += timedelta(seconds=1)
    await coord.approve_flyer(OWNER, EVENT, 1, preview["preview"]["digest"])
    return storage, coord


def test_second_export_call_polls_the_pending_job_instead_of_exporting_again():
    async def flow():
        api = ConnectApi(PENDING, SUCCESS)
        canva = PollingCanva(api, PENDING)
        storage, coord = await approved_flyer(canva)

        first = await coord.export_flyer(OWNER, EVENT, 1)
        assert first["stage"] == "exporting"
        assert first["export"] == {"export_id": "export-123", "state": "pending"}

        still = await coord.export_flyer(OWNER, EVENT, 1)
        assert still["stage"] == "exporting"
        done = await coord.export_flyer(OWNER, EVENT, 1)
        assert done["stage"] == "stored"
        assert storage.current["flyer_png"].canva_export_id == "export-123"

        assert canva.names().count("export-design") == 1
        assert api.requested == [("/rest/v1/exports/export-123", "Bearer organizer-token")] * 2

    run(flow())


def test_failed_pending_export_allows_a_fresh_export_request():
    async def flow():
        failed = {"job": {"id": "export-123", "status": "failed", "error": {"code": "x"}}}
        canva = PollingCanva(ConnectApi(failed), PENDING)
        canva.session.responses["export-design"].append(
            {**SUCCESS, "job": {**SUCCESS["job"], "id": "export-456"}}
        )
        storage, coord = await approved_flyer(canva)

        await coord.export_flyer(OWNER, EVENT, 1)
        with pytest.raises(WorkflowError, match="canva_export_failed"):
            await coord.export_flyer(OWNER, EVENT, 1)
        retried = await coord.export_flyer(OWNER, EVENT, 1)
        assert retried["stage"] == "stored"
        assert storage.current["flyer_png"].canva_export_id == "export-456"

    run(flow())
