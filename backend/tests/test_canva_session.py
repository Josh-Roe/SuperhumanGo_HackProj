import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from hackathon_backend.providers.canva import CanvaError, CanvaMCPAdapter
from hackathon_backend.providers.canva.session import (
    WORKFLOW_TOOLS,
    DiscoveredCanvaSession,
    connect_canva,
)


class Session:
    def __init__(self, pages):
        self.pages = list(pages)
        self.cursors = []
        self.calls = []

    async def list_tools(self, cursor=None):
        self.cursors.append(cursor)
        return self.pages.pop(0)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"status": "pending"}


@pytest.mark.parametrize("naming", ["canonical", "underscore", "connector"])
def test_tool_discovery_maps_real_names_and_reports_missing_exports(naming):
    async def run():
        names = sorted(
            {name for names in WORKFLOW_TOOLS.values() for name in names} - {"export-design"}
        )

        def actual(name):
            suffix = name.replace("-", "_")
            return (
                name
                if naming == "canonical"
                else (suffix if naming == "underscore" else f"mcp__codex_apps__canva_{suffix}")
            )

        session = Session(
            [
                {"tools": [{"name": actual(name)} for name in names[:3]], "nextCursor": "page-2"},
                SimpleNamespace(
                    tools=[SimpleNamespace(name=actual(name)) for name in names[3:]],
                    nextCursor=None,
                ),
            ]
        )
        scoped = await DiscoveredCanvaSession.discover(session, owner_id="fixture-owner")
        assert session.cursors == [None, "page-2"]
        assert scoped.capabilities().available_actions == ("create", "review", "edit")
        assert scoped.capabilities().missing_tools == ("export-design",)
        await scoped.call_tool("get-design", {"design_id": "fixture"})
        assert session.calls[-1][0] == actual("get-design")
        with pytest.raises(CanvaError, match="unavailable"):
            await scoped.call_tool("export-design", {})
        with pytest.raises(PermissionError):
            scoped.adapter(owner_id="another-owner")
        with pytest.raises(PermissionError):
            CanvaMCPAdapter(scoped, owner_id="another-owner")
        assert scoped.adapter(owner_id="fixture-owner").owner_id == "fixture-owner"

    asyncio.run(run())


@pytest.mark.parametrize(
    "pages,code",
    [
        ([{"tools": [{"name": "get-design"}, {"name": "get_design"}]}], "ambiguous"),
        ([{"tools": [{"name": None}]}], "inventory"),
        (
            [{"tools": [], "nextCursor": "repeat"}, {"tools": [], "nextCursor": "repeat"}],
            "pagination",
        ),
    ],
)
def test_invalid_tool_inventory_fails_before_any_provider_operation(pages, code):
    session = Session(pages)
    with pytest.raises(CanvaError, match=code):
        asyncio.run(DiscoveredCanvaSession.discover(session, owner_id="fixture-owner"))
    assert not session.calls


def test_read_only_or_empty_account_never_claims_write_capabilities():
    scoped = asyncio.run(
        DiscoveredCanvaSession.discover(Session([{"tools": []}]), owner_id="fixture-owner")
    )
    assert not scoped.capabilities().available_actions


@pytest.mark.parametrize("token", ["", "bad\ntoken", "bad token"])
def test_connection_rejects_invalid_token_before_network(token):
    async def run():
        async with connect_canva(owner_id="fixture-owner", access_token=token):
            pytest.fail("Invalid token opened a connection")

    with pytest.raises(ValueError):
        asyncio.run(run())


def test_real_mcp_sdk_http_handshake_discovery_call_and_close_with_fake_server():
    requests = []

    def server(request):
        assert str(request.url) == "https://mcp.canva.com/mcp"
        assert request.headers["authorization"] == "Bearer synthetic-test-token"
        requests.append(request.method)
        if request.method in {"DELETE", "GET"}:
            return httpx.Response(200 if request.method == "DELETE" else 405)
        payload = json.loads(request.content)
        if payload["method"].startswith("notifications/"):
            return httpx.Response(202)
        if payload["method"] == "initialize":
            result = {
                "protocolVersion": payload["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Synthetic Canva Fixture", "version": "1"},
            }
        elif payload["method"] == "tools/list":
            result = {"tools": [{"name": "get-design", "inputSchema": {"type": "object"}}]}
        elif payload["method"] == "tools/call":
            assert payload["params"]["name"] == "get-design"
            result = {"content": [{"type": "text", "text": "Synthetic test result"}]}
        else:
            pytest.fail(f"Unexpected MCP method: {payload['method']}")
        return httpx.Response(
            200,
            headers={"mcp-session-id": "synthetic-session"},
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )

    async def run():
        async with connect_canva(
            owner_id="fixture-owner",
            access_token="synthetic-test-token",
            transport=httpx.MockTransport(server),
        ) as scoped:
            assert scoped.tool_names == {"get-design": "get-design"}
            # MCP credentials must not be reused at the REST export endpoint.
            assert scoped.adapter(owner_id="fixture-owner").export_jobs is None
            result = await scoped.call_tool("get-design", {"design_id": "D-synthetic"})
            assert result.content[0].text == "Synthetic test result"

    asyncio.run(run())
    assert requests.count("POST") >= 4 and "DELETE" in requests
