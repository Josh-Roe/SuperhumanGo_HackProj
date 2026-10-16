"""Member 2 adapters integrated with Member 3's real MCP registration; HTTP is mocked."""

import json
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from hackathon_backend.auth.connectors import SupabasePrincipalResolver
from hackathon_backend.config import Settings
from hackathon_backend.main import create_app
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore

OWNER = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
EVENT = "00000000-0000-4000-8000-000000000003"


def test_go_mcp_uses_stored_principal_and_supabase_store_to_read_and_save():
    writes = []
    settings = Settings(
        supabase_url="https://example.supabase.co", supabase_service_role_key="server"
    )

    def http(request):
        assert request.headers["Authorization"] == "Bearer server"
        if request.url.path.endswith("connector_tokens"):
            return httpx.Response(200, json=[{"owner_id": OWNER}])
        payload = json.loads(request.content)
        assert payload["p_owner"] == OWNER
        if request.url.path.endswith("organizer_event_json"):
            return httpx.Response(
                200,
                json={
                    "id": EVENT,
                    "owner_id": OWNER,
                    "revision": 1,
                    "title": "Synthetic event",
                    "location": "Room A",
                    "starts_at": "2026-11-01T17:00:00-08:00",
                    "ends_at": "2026-11-01T19:00:00-08:00",
                    "timezone": "America/Los_Angeles",
                    "organizer_contact": "test@example.invalid",
                    "invitees": [],
                },
            )
        assert request.url.path.endswith("organizer_save_content")
        writes.append(payload)
        return httpx.Response(
            200, json={**payload["p_data"], "created_at": datetime.now(UTC).isoformat()}
        )

    db = Database(settings, admin=True, transport=httpx.MockTransport(http))
    deps = EventToolDeps(store=SupabaseWorkflowStore(db), principals=SupabasePrincipalResolver(db))
    with TestClient(create_app(settings, events=deps), base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer go_" + "x" * 43,
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "save_generated_content",
                    "arguments": {
                        "event_id": EVENT,
                        "expected_revision": 1,
                        "kind": "description",
                        "body": "Synthetic Go test output; no real Go session was used.",
                    },
                },
            },
        )
        assert response.status_code == 200
        content = response.json()["result"]["structuredContent"]
        assert content["producer"] == "superhuman_go"
        assert content["state"] == "needs_review"
        assert writes[0]["p_owner"] != OTHER
        assert writes[0]["p_expected"] == 1
