"""Authenticated connect/status/verify endpoints; callback resolves only bound PKCE state."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Header, Query, Request
from starlette.responses import HTMLResponse, RedirectResponse

from hackathon_backend.api import DomainRoute
from hackathon_backend.auth.identity import authenticate
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.providers.canva import CanvaError
from hackathon_backend.providers.canva.oauth import (
    CanvaOAuthConfig,
    CanvaOAuthStates,
    CanvaTokens,
    authorization_url,
)
from hackathon_backend.providers.canva.session import connect_canva


def canva_connect_router(
    settings: Settings,
    tokens: CanvaTokens | None = None,
    *,
    states: CanvaOAuthStates | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    resolve_owner: Callable[[str | None], Awaitable[str]] | None = None,
    connect=connect_canva,
) -> APIRouter:
    if tokens is None:
        from hackathon_backend.repositories.transport import Database
        from hackathon_backend.repositories.vault import SupabaseCredentialVault

        config = canva_oauth_config(settings)
        if config is None:
            raise ValueError("Configure Canva OAuth client credentials")
        tokens = CanvaTokens(
            SupabaseCredentialVault(
                Database(settings, admin=True), settings.credential_encryption_key
            ),
            config,
        )
    if resolve_owner is None:

        async def resolve_owner(authorization):
            return (await authenticate(settings, authorization, transport)).owner_id

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
        if tokens is None or tokens.config is None:
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
        dashboard = urlsplit(settings.app_url)
        allowed = {
            f"{dashboard.scheme}://{dashboard.netloc}",
            f"{callback.scheme}://{callback.netloc}",
        }
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
        failure = None
        try:
            pending = states.consume(state, request.cookies.get("canva_oauth_" + state[:16], ""))
            if error or not code:
                raise DomainError(
                    "not_granted", "Canva authorization was not granted; start again", 400
                )
            source = require_tokens()
            try:
                await source.authorize(pending.owner_id, code, pending.verifier)
            except CanvaError:
                raise DomainError(
                    "provider_failed", "Canva token exchange failed; reconnect", 502
                ) from None
        except DomainError as exc:
            failure = exc
        if failure is not None and not settings.app_url:
            raise failure
        if settings.app_url:
            reasons = {"invalid_state": "invalid_state", "not_granted": "denied"}
            query = (
                {"canva": "connected"}
                if failure is None
                else {"canva": "error", "reason": reasons.get(failure.code, "exchange_failed")}
            )
            response = RedirectResponse(settings.app_url + "/?" + urlencode(query), status_code=303)
        else:
            response = HTMLResponse(
                '<!doctype html><html lang="en"><title>Canva connected</title>'
                "<main><h1>Canva connected</h1><p>Return to Event Workspace.</p></main></html>",
                headers={
                    "Content-Security-Policy": (
                        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
                    )
                },
            )
        response.delete_cookie("canva_oauth_" + state[:16], path="/api/canva/callback")
        return response

    @router.get("/status")
    async def status(authorization: Auth = None):
        owner = await resolve_owner(authorization)
        if tokens is None:
            return {"configured": False, "connected": False}
        return {"configured": True, "connected": await tokens.connected(owner)}

    @router.post("/verify")
    async def verify(authorization: Auth = None):
        owner = await resolve_owner(authorization)
        try:
            token = await require_tokens().access_token(owner)
        except CanvaError:
            raise DomainError(
                "integration_not_connected", "Reconnect your Canva account", 503
            ) from None
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


def canva_oauth_config(settings: Settings) -> CanvaOAuthConfig | None:
    if not all(
        (settings.canva_client_id, settings.canva_client_secret, settings.canva_redirect_uri)
    ):
        return None
    return CanvaOAuthConfig(
        settings.canva_client_id, settings.canva_client_secret, settings.canva_redirect_uri
    )


def canva_connect_configured(settings: Settings) -> bool:
    return canva_oauth_config(settings) is not None and all(
        (
            settings.supabase_url,
            settings.supabase_publishable_key,
            settings.supabase_service_role_key,
            settings.credential_encryption_key,
        )
    )


PkceStates = CanvaOAuthStates
