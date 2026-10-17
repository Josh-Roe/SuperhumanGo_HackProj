"""Authenticated connect/status/verify endpoints; callback resolves only bound PKCE state."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from html import escape
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Header, Query, Request
from starlette.responses import HTMLResponse, RedirectResponse

from hackathon_backend.api import DomainRoute
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.providers.canva.oauth import CanvaOAuthStates, CanvaTokens, authorization_url
from hackathon_backend.providers.canva.session import connect_canva


def canva_connect_router(
    settings: Settings,
    tokens: CanvaTokens | None,
    resolve_owner: Callable[[str | None], Awaitable[str]],
    *,
    states: CanvaOAuthStates | None = None,
    connect=connect_canva,
) -> APIRouter:
    states = states or CanvaOAuthStates()

    class PrivateRoute(DomainRoute):
        def get_route_handler(self):
            original = super().get_route_handler()

            async def handler(request):
                response = await original(request)
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
                return response

            return handler

    router = APIRouter(prefix="/api/canva", tags=["canva"], route_class=PrivateRoute)
    Auth = Annotated[str | None, Header()]

    def require_tokens() -> CanvaTokens:
        if tokens is None:
            raise DomainError(
                "integration_not_connected", "Canva OAuth is not configured on this server", 503
            )
        return tokens

    @router.post("/connect")
    async def begin(authorization: Auth = None):
        owner = await resolve_owner(authorization)
        source = require_tokens()
        state, _ = states.issue(owner)
        origin = urlsplit(source.config.redirect_uri)
        # Navigate to backend first to bind an HttpOnly cookie. This works even when
        # /connect was proxied through Vercel, which deliberately strips Set-Cookie.
        start = f"{origin.scheme}://{origin.netloc}/api/canva/start"
        return {"authorization_url": start + "?" + urlencode({"state": state})}

    @router.get("/start")
    async def start(request: Request, state: Annotated[str, Query(max_length=256)] = ""):
        source = require_tokens()
        # Start only from our dashboard/backend. A forwarded bootstrap link must not
        # connect an unsuspecting browser's Canva account to another organizer.
        referer = urlsplit(request.headers.get("referer", ""))
        callback = urlsplit(source.config.redirect_uri)
        allowed = {settings.app_url, f"{callback.scheme}://{callback.netloc}"}
        if not referer.netloc or f"{referer.scheme}://{referer.netloc}" not in allowed:
            raise DomainError(
                "forbidden", "Start Canva connection from Event Workspace Settings", 403
            )
        cookie, challenge = states.bind_browser(state)
        response = RedirectResponse(
            authorization_url(source.config, state, challenge), status_code=302
        )
        response.set_cookie(
            "canva_oauth_" + state[:16],
            cookie,
            max_age=600,
            httponly=True,
            secure=source.config.redirect_uri.startswith("https://"),
            samesite="lax",
            path="/api/canva/callback",
        )
        return response

    @router.get("/callback")
    async def callback(
        request: Request,
        state: Annotated[str, Query(max_length=256)] = "",
        code: Annotated[str, Query(max_length=8192)] = "",
        error: Annotated[str, Query(max_length=256)] = "",
    ):
        pending = states.consume(state, request.cookies.get("canva_oauth_" + state[:16], ""))
        if error or not code:
            raise DomainError(
                "not_granted", "Canva authorization was not granted; start again", 400
            )
        await require_tokens().authorize(pending.owner_id, code, pending.verifier)
        dashboard = settings.app_url
        link = (
            f'<p><a href="{escape(dashboard, quote=True)}">Return to Event Workspace</a></p>'
            if dashboard
            else ""
        )
        response = HTMLResponse(
            '<!doctype html><html lang="en"><meta name="viewport" '
            'content="width=device-width, initial-scale=1">'
            "<title>Canva connected</title><main><h1>Canva connected</h1>"
            "<p>Your organizer account can now use the event flyer tools. "
            "You can close this tab.</p>" + link + "</main></html>",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
                ),
            },
        )

        response.delete_cookie("canva_oauth_" + state[:16], path="/api/canva/callback")
        return response

    @router.get("/status")
    async def status(authorization: Auth = None):
        owner = await resolve_owner(authorization)
        if tokens is None:
            return {"configured": False, "connected": False}
        record = await tokens.vault.get_secret(owner, "canva")
        usable = False
        if record and record.get("access_token"):
            try:
                usable = datetime.fromisoformat(record["expires_at"]) > tokens.now()
            except (KeyError, ValueError, TypeError):
                pass
        return {
            "configured": True,
            "connected": bool(
                record and record.get("access_token") and (usable or record.get("refresh_token"))
            ),
            "expires_at": record.get("expires_at") if record else None,
            "refresh_available": bool(record and record.get("refresh_token")),
        }

    @router.post("/verify")
    async def verify(authorization: Auth = None):
        owner = await resolve_owner(authorization)
        token = await require_tokens().access_token(owner)
        if not token:
            raise DomainError("integration_not_connected", "Connect your Canva account first", 503)
        try:
            async with connect(owner_id=owner, access_token=token) as session:
                caps = session.capabilities()
        except Exception:
            raise DomainError(
                "provider_failed", "Could not verify Canva access; reconnect or retry", 502
            ) from None
        return {
            "connected": True,
            "available_actions": caps.available_actions,
            "missing_tools": caps.missing_tools,
            "flyer_workflow_ready": all(
                k in caps.available_actions for k in ("create", "review", "export")
            ),
        }

    return router
