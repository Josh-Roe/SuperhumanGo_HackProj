"""A11 Canva part: durable flyer job state with a fenced cross-process lease.

Supabase PostgREST is faked at the HTTP boundary (table row + the three RPCs from migration
20261017030000_canva_flyer_jobs.sql); Database, the store and the coordinator are real. Two
store instances stand in for two backend processes sharing one database.
"""

import json
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.fernet import Fernet
from test_assets_preparation import EVENT, OWNER, put_prose, workflow_event
from test_assets_storage import Storage
from test_workflow_asset_wiring import FakeCanva, png_client, run

from hackathon_backend.config import Settings
from hackathon_backend.repositories.transport import Database
from hackathon_backend.services.assets.requests import ASSET_PROSE_KINDS
from hackathon_backend.workflows.asset_wiring import (
    AssetCoordinator,
    FlyerState,
    SupabaseFlyerStateStore,
    VaultFlyerStateStore,
)
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.memory import InMemoryWorkflowStore

KEY = Fernet.generate_key().decode()
SETTINGS = Settings(supabase_url="https://example.supabase.co", supabase_service_role_key="srv")


class FlyerJobsTable:
    """Fake PostgREST for canva_flyer_jobs; lease expiry uses `self.now` (seconds)."""

    def __init__(self):
        self.rows, self.now = {}, 0.0

    def __call__(self, request):
        path = request.url.path
        if request.method == "GET" and path == "/rest/v1/canva_flyer_jobs":
            q = {
                k: v[0].removeprefix("eq.") for k, v in parse_qs(request.url.query.decode()).items()
            }
            row = self.rows.get((q["owner_id"], q["event_id"]))
            return httpx.Response(200, json=[{"ciphertext": row["ciphertext"]}] if row else [])
        name, p = path.removeprefix("/rest/v1/rpc/"), json.loads(request.content)
        key = (p["p_owner"], p["p_event"])
        row = self.rows.get(key)
        live = row is not None and row["holder"] is not None and row["expires"] > self.now
        if name == "canva_flyer_acquire":
            if (p["p_owner"], p["p_event"]) != (OWNER, EVENT):
                return httpx.Response(400, json={"message": "not_found"})
            if live and row["holder"] != p["p_holder"]:
                return httpx.Response(200, json=False)
            row = self.rows.setdefault(key, {"ciphertext": None})
            row.update(holder=p["p_holder"], expires=self.now + p["p_ttl_seconds"])
            return httpx.Response(200, json=True)
        if name == "canva_flyer_save":
            if not live or row["holder"] != p["p_holder"]:
                return httpx.Response(400, json={"message": "operation_in_progress"})
            row["ciphertext"] = p["p_ciphertext"]
            return httpx.Response(200, json=1)
        if name == "canva_flyer_release":
            if row and row["holder"] == p["p_holder"]:
                row.update(holder=None, expires=None)
            return httpx.Response(204)
        raise AssertionError(path)


async def no_sleep(_):
    pass


def process(table, legacy=None):
    database = Database(SETTINGS, admin=True, transport=httpx.MockTransport(table))
    return SupabaseFlyerStateStore(database, KEY, legacy=legacy, sleep=no_sleep)


def coordinator(flyers, canva):
    store = InMemoryWorkflowStore()
    store.put_event(workflow_event())
    coord = AssetCoordinator(
        store,
        storage_for=lambda owner: Storage(),
        canva=canva,
        flyers=flyers,
        client_factory=png_client,
    )
    return store, coord


def test_live_lease_in_one_process_blocks_another_and_state_survives_a_restart():
    async def flow():
        table, canva = FlyerJobsTable(), FakeCanva()
        first, second = process(table), process(table)
        store, coord = coordinator(second, canva)
        await put_prose(store, ASSET_PROSE_KINDS, reviewed=True)

        async with first.lease(OWNER, EVENT):
            with pytest.raises(WorkflowError, match="operation_in_progress"):
                await coord.start_flyer(OWNER, EVENT, 1)
        assert canva.names() == []

        started = await coord.start_flyer(OWNER, EVENT, 1)
        restarted = await process(table).get(OWNER, EVENT)
        return started, restarted, table

    started, restarted, table = run(flow())
    assert started["stage"] == restarted.stage == "pending"
    assert restarted.continuation_token == "private-poll-token"
    assert "private-poll-token" not in table.rows[(OWNER, EVENT)]["ciphertext"]
    assert table.rows[(OWNER, EVENT)]["holder"] is None  # released after the action


def test_holder_whose_lease_expired_cannot_overwrite_the_new_holders_state():
    async def flow():
        table = FlyerJobsTable()
        stale, fresh = process(table), process(table)
        async with stale.lease(OWNER, EVENT):
            table.now += 301  # stale holder stalled past LEASE_TTL_SECONDS
            async with fresh.lease(OWNER, EVENT):
                await fresh.put(
                    OWNER, FlyerState(event_id=EVENT, event_revision=1, stage="pending")
                )
                with pytest.raises(Exception, match="operation in progress"):
                    await stale.put(
                        OWNER, FlyerState(event_id=EVENT, event_revision=1, stage="failed")
                    )
        return (await fresh.get(OWNER, EVENT)).stage

    assert run(flow()) == "pending"


def test_flyer_started_in_the_legacy_vault_is_still_read():
    class Vault:
        def __init__(self):
            self.secrets = {}

        async def put_secret(self, owner_id, provider, value):
            self.secrets[(owner_id, provider)] = value

        async def get_secret(self, owner_id, provider):
            return self.secrets.get((owner_id, provider))

    async def flow():
        legacy = VaultFlyerStateStore(Vault())
        await legacy.put(
            OWNER,
            FlyerState(
                event_id=EVENT, event_revision=1, stage="pending", continuation_token="old-token"
            ),
        )
        return await process(FlyerJobsTable(), legacy=legacy).get(OWNER, EVENT)

    assert run(flow()).continuation_token == "old-token"
