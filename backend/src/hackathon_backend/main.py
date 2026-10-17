"""Public health/status API plus bearer-protected Streamable HTTP MCP tools.

Member 3 owns composition here: event tools for Superhuman Go and other members' routers.
"""

import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from hackathon_backend.config import Settings
from hackathon_backend.inference import OnnxRunner
from hackathon_backend.mcp_tools.event_tools import EventToolDeps, register_event_tools
from hackathon_backend.workflows.dev import DevWorkflow, dev_router, dev_workflow_from_env


class SuperhumanStatus(BaseModel):
    transport: str = "mcp"
    configured: bool
    verified: bool = False
    endpoint: str = "/mcp"


class ModelStatus(BaseModel):
    configured: bool
    runtime: str


class WorkspaceStatus(BaseModel):
    superhuman: SuperhumanStatus
    model: ModelStatus


class MCPBearerAuth:
    """Protect every MCP method/path without consuming the streaming request body."""

    def __init__(self, app: ASGIApp, token: str, deps: EventToolDeps | None = None) -> None:
        self.app = app
        self._token = token.encode()
        self._deps = deps

    async def _valid(self, credential: bytes) -> bool:
        if self._token and secrets.compare_digest(credential, self._token):
            return True  # deployment token: scaffold tools only; event tools re-check per call
        if self._deps is None or not credential:
            return False
        return await self._deps.principals.resolve(credential.decode(errors="replace")) is not None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            if not self._token and self._deps is None:
                response = JSONResponse({"detail": "MCP authentication is not configured"}, 503)
                await response(scope, receive, send)
                return
            headers = dict(scope.get("headers", []))
            scheme, _, credential = headers.get(b"authorization", b"").partition(b" ")
            if scheme.lower() != b"bearer" or not await self._valid(credential):
                response = JSONResponse(
                    {"detail": "Bearer authentication required"},
                    401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(
    settings: Settings | None = None,
    events: EventToolDeps | None = None,
    dev: DevWorkflow | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if dev is not None:
        events = dev.deps
    runner = OnnxRunner(settings.onnx_model_path)
    mcp = FastMCP(
        "Superhuman Go Hackathon",
        instructions=(
            "Event organizer tools for Superhuman Go. Go writes event prose and classifies RSVP "
            "replies; these tools read authorized events, store Go's output for organizer review, "
            "and execute only organizer-approved Calendar/Gmail distribution."
        ),
        stateless_http=True,
        json_response=True,
        max_request_body_size=1_048_576,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
        ),
    )

    def status() -> WorkspaceStatus:
        configured = runner.configured
        return WorkspaceStatus(
            superhuman=SuperhumanStatus(configured=bool(settings.mcp_auth_token)),
            model=ModelStatus(
                configured=configured,
                runtime="onnxruntime-cpu" if configured else "not_configured",
            ),
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    def workspace_status() -> WorkspaceStatus:
        """Report local configuration readiness; connection to Superhuman Go is unverified."""
        return status()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    def count_text(text: Annotated[str, Field(max_length=10_000)]) -> dict[str, int]:
        """Count characters and whitespace-separated words; a deterministic utility, not AI."""
        return {"characters": len(text), "words": len(text.split())}

    if events is not None:
        register_event_tools(mcp, events)

    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Superhuman Go Hackathon API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(MCPBearerAuth, token=settings.mcp_auth_token, deps=events)
    if dev is not None:
        app.include_router(dev_router(dev))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "backend"}

    @app.get("/api/status", response_model=WorkspaceStatus)
    def workspace_api_status() -> WorkspaceStatus:
        return status()

    # FastMCP itself owns /mcp. Mounting at / preserves the public path without a redirect.
    app.mount("/", mcp_app)
    return app


app = create_app(dev=dev_workflow_from_env())
