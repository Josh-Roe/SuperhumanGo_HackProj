"""Per-organizer Canva Connect OAuth (Authorization Code + PKCE), mirroring google_connect.

`POST /api/canva/connect` requires the organizer's Supabase session and returns Canva's
consent URL. The OAuth `state` is random, single use, short-lived and bound to that owner_id
and its PKCE code_verifier (which never leaves the server). `GET /api/canva/callback` is
Canva's browser redirect; the state alone identifies the owner. Tokens are encrypted into the
vault as provider `canva` and never returned. With APP_URL set the callback 303-redirects to
`APP_URL/?canva=connected` or `APP_URL/?canva=error&reason=<invalid_state|denied|
exchange_failed>`; without APP_URL it returns JSON/DomainError responses.
`GET /api/canva/status` → `{connected}`.

Limitation (same as Google): pending states live in this process's memory, so a restart drops
in-flight consents and multiple replicas would need a shared state store.
"""

import secrets
import time
from collections.abc import Callable
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header
from fastapi.responses import RedirectResponse

from hackathon_backend.api import DomainRoute
from hackathon_backend.auth.identity import authenticate
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.providers.canva import CanvaError
from hackathon_backend.providers.canva.oauth import (
    CanvaOAuthConfig,
    CanvaTokens,
    authorization_url,
    exchange_code,
    pkce_pair,
)

STATE_TTL_SECONDS = 600
MAX_PENDING_STATES = 1000
REDIRECT_REASONS = {
    "invalid_state": "invalid_state",
    "not_granted": "denied",
    "provider_failed": "exchange_failed",
}


def canva_oauth_config(settings: Settings) -> CanvaOAuthConfig | None:
    if not (settings.canva_client_id and settings.canva_client_secret):
        return None
    if not settings.canva_redirect_uri:
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


class PkceStates:
    """In-memory, single-use, expiring `state → (owner_id, code_verifier)`. Single instance."""

    def __init__(self, ttl: float = STATE_TTL_SECONDS, now: Callable[[], float] = time.monotonic):
        self._ttl, self._now = ttl, now
        self._pending: dict[str, tuple[str, str, float]] = {}

    def issue(self, owner_id: str, verifier: str) -> str:
        now = self._now()
        self._pending = {s: v for s, v in self._pending.items() if v[2] > now}
        if len(self._pending) >= MAX_PENDING_STATES:
            raise DomainError("rate_limited", "Too many pending Canva connections", 503)
        state = secrets.token_urlsafe(32)
        self._pending[state] = (owner_id, verifier, now + self._ttl)
        return state

    def consume(self, state: str) -> tuple[str, str] | None:
        entry = self._pending.pop(state, None) if state else None
        if entry is None or entry[2] <= self._now():
            return None
        return entry[0], entry[1]


def canva_connect_router(
    settings: Settings,
    tokens: CanvaTokens | None = None,
    *,
    states: PkceStates | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> APIRouter:
    config = canva_oauth_config(settings)
    if config is None:
        raise ValueError("CANVA_CLIENT_ID, CANVA_CLIENT_SECRET and CANVA_REDIRECT_URI are required")
    if tokens is None:
        from hackathon_backend.repositories.transport import Database
        from hackathon_backend.repositories.vault import SupabaseCredentialVault

        vault = SupabaseCredentialVault(
            Database(settings, admin=True), settings.credential_encryption_key
        )
        tokens = CanvaTokens(vault, config)
    states = states or PkceStates()
    router = APIRouter(prefix="/api/canva", route_class=DomainRoute, tags=["canva"])

    async def owner(authorization: str | None) -> str:
        return (await authenticate(settings, authorization, transport)).owner_id

    @router.post("/connect")
    async def connect(authorization: Annotated[str | None, Header()] = None):
        owner_id = await owner(authorization)
        verifier, challenge = pkce_pair()
        state = states.issue(owner_id, verifier)
        return {"authorization_url": authorization_url(config, state, challenge)}

    def to_app(**query: str) -> RedirectResponse:
        return RedirectResponse(f"{settings.app_url}/?{urlencode(query)}", status_code=303)

    @router.get("/callback")
    async def callback(state: str = "", code: str = "", error: str = ""):
        try:
            await complete(state, code, error)
        except DomainError as failure:
            reason = REDIRECT_REASONS.get(failure.code)
            if not settings.app_url or reason is None:
                raise
            return to_app(canva="error", reason=reason)
        if settings.app_url:
            return to_app(canva="connected")
        return {"connected": True}

    async def complete(state: str, code: str, error: str) -> None:
        pending = states.consume(state)
        if pending is None:
            raise DomainError("invalid_state", "Invalid or expired OAuth state", 400)
        if error or not code:
            raise DomainError("not_granted", "Canva authorization was not granted", 400)
        owner_id, verifier = pending
        try:
            grant = await exchange_code(config, code, verifier, transport)
        except CanvaError:
            raise DomainError("provider_failed", "Canva token exchange failed", 502) from None
        await tokens.save_grant(owner_id, grant)

    @router.get("/status")
    async def status(authorization: Annotated[str | None, Header()] = None):
        return {"connected": await tokens.connected(await owner(authorization))}

    return router
