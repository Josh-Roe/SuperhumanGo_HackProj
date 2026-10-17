"""Organizer-bound Canva MCP session, discovery and server-side connection factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import TypeAdapter

from hackathon_backend.providers.canva import CanvaError, CanvaMCPAdapter, ExportJobReader
from hackathon_backend.services.assets.models import BoundaryModel, Identifier

CANVA_MCP_URL = "https://api.canva.com/connect/v1/mcp"
WORKFLOW_TOOLS = {
    "create": ("create-design", "get-create-design-async-job", "get-design"),
    "review": ("get-design", "get-design-content"),
    "edit": (
        "start-editing-transaction",
        "perform-editing-operations",
        "commit-editing-transaction",
        "cancel-editing-transaction",
        "get-design-content",
    ),
    "export": ("export-design",),
}


class DiscoverableSession(Protocol):
    async def list_tools(self, cursor: str | None = None) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class CanvaCapabilities(BoundaryModel):
    owner_id: Identifier
    available_actions: tuple[str, ...]
    missing_tools: tuple[str, ...]


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


class DiscoveredCanvaSession:
    def __init__(
        self,
        session: DiscoverableSession,
        *,
        owner_id: str,
        tool_names: dict[str, str],
        export_jobs: ExportJobReader | None = None,
    ) -> None:
        self._session = session
        self._export_jobs = export_jobs
        self.owner_id = TypeAdapter(Identifier).validate_python(owner_id)
        self._tool_names = dict(tool_names)

    @classmethod
    async def discover(
        cls,
        session: DiscoverableSession,
        *,
        owner_id: str,
        export_jobs: ExportJobReader | None = None,
    ) -> "DiscoveredCanvaSession":
        TypeAdapter(Identifier).validate_python(owner_id)
        names: set[str] = set()
        cursor = None
        seen: set[str] = set()
        try:
            for _ in range(100):
                page = (
                    await session.list_tools(cursor=cursor)
                    if cursor
                    else await session.list_tools()
                )
                for tool in _field(page, "tools", []):
                    name = _field(tool, "name")
                    if not isinstance(name, str):
                        raise CanvaError("invalid_canva_tool_inventory")
                    names.add(name)
                cursor = _field(page, "nextCursor")
                if not cursor:
                    break
                if not isinstance(cursor, str) or cursor in seen:
                    raise CanvaError("invalid_canva_tool_pagination")
                seen.add(cursor)
            else:
                raise CanvaError("canva_tool_inventory_too_large")
        except CanvaError:
            raise
        except Exception:
            raise CanvaError("canva_discovery_failed") from None
        mapping = {}
        for canonical in {name for group in WORKFLOW_TOOLS.values() for name in group}:
            suffix = canonical.replace("-", "_")
            aliases = {canonical, suffix, f"mcp__codex_apps__canva_{suffix}"}
            matches = names & aliases
            if len(matches) > 1:
                raise CanvaError("ambiguous_canva_tool_alias")
            if matches:
                mapping[canonical] = matches.pop()
        return cls(session, owner_id=owner_id, tool_names=mapping, export_jobs=export_jobs)

    @property
    def tool_names(self) -> dict[str, str]:
        return dict(self._tool_names)

    def capabilities(self) -> CanvaCapabilities:
        required = {name for group in WORKFLOW_TOOLS.values() for name in group}
        return CanvaCapabilities(
            owner_id=self.owner_id,
            available_actions=tuple(
                action
                for action, group in WORKFLOW_TOOLS.items()
                if all(name in self._tool_names for name in group)
            ),
            missing_tools=tuple(sorted(required - self._tool_names.keys())),
        )

    def adapter(self, *, owner_id: str) -> CanvaMCPAdapter:
        if owner_id != self.owner_id:
            raise PermissionError("Canva session is outside the current organizer scope")
        return CanvaMCPAdapter(self, owner_id=owner_id, export_jobs=self._export_jobs)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        actual = self._tool_names.get(name)
        if actual is None:
            raise CanvaError("canva_required_tool_unavailable")
        return await self._session.call_tool(actual, arguments)


@asynccontextmanager
async def connect_canva(
    *,
    owner_id: str,
    access_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[DiscoveredCanvaSession]:
    """Use an already-authorized fresh token from Member 2's server-side vault.

    Does not register an OAuth client, reuse this chat's grant, refresh tokens,
    install a Go connector or authorize a caller. No arbitrary endpoint parameter
    is accepted: the token is sent only to Canva's documented remote MCP server.
    """
    TypeAdapter(Identifier).validate_python(owner_id)
    if not access_token or any(c.isspace() for c in access_token):
        raise ValueError("Expected a server-held Canva OAuth access token")
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=httpx.Timeout(60, read=300),
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        async with streamable_http_client(CANVA_MCP_URL, http_client=client) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(minutes=5)
            ) as session:
                await session.initialize()
                yield await DiscoveredCanvaSession.discover(
                    session,
                    owner_id=owner_id,
                    # MCP grants are audience-bound. Do not send them to the REST API;
                    # pending exports need an explicitly authorized reader.
                )
