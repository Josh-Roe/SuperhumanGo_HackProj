"""Production per-organizer Google OAuth connect, backed by Member 2's Supabase auth and vault.

`POST /api/google/connect` requires the organizer's Supabase session and returns Google's
consent URL. The OAuth `state` is random, single use, short-lived and bound to that owner_id.
`GET /api/google/callback` is Google's browser redirect (no bearer); the state alone identifies
the owner. The refresh token is encrypted into SupabaseCredentialVault and never returned.
When APP_URL is set the callback 303-redirects the browser to `APP_URL/?google=connected` or
`APP_URL/?google=error&reason=<invalid_state|denied|exchange_failed|no_refresh_token>` (no
tokens or emails in the URL); without APP_URL it returns the JSON/DomainError responses.

Limitation: pending states live in this process's memory, so a restart drops in-flight
consents and multiple backend replicas would need a shared state store.
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
from hackathon_backend.providers.google.oauth import (
    CredentialVault,
    GoogleOAuthConfig,
    authorization_url,
    exchange_code,
    id_token_claims,
)
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.vault import SupabaseCredentialVault
from hackathon_backend.workflows.ports import ProviderError

STATE_TTL_SECONDS = 600
MAX_PENDING_STATES = 1000
# DomainError code raised by the callback -> `reason` in the APP_URL redirect.
REDIRECT_REASONS = {
    "invalid_state": "invalid_state",
    "not_granted": "denied",
    "provider_failed": "exchange_failed",
    "no_refresh_token": "no_refresh_token",
}


def google_connect_configured(settings: Settings) -> bool:
    return all(
        (
            settings.supabase_url,
            settings.supabase_publishable_key,
            settings.supabase_service_role_key,
            settings.credential_encryption_key,
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_redirect_uri,
        )
    )


class OAuthStates:
    """In-memory, single-use, expiring OAuth states. Single-instance only (see module doc)."""

    def __init__(self, ttl: float = STATE_TTL_SECONDS, now: Callable[[], float] = time.monotonic):
        self._ttl, self._now = ttl, now
        self._pending: dict[str, tuple[str, float]] = {}

    def issue(self, owner_id: str) -> str:
        now = self._now()
        self._pending = {s: v for s, v in self._pending.items() if v[1] > now}
        if len(self._pending) >= MAX_PENDING_STATES:
            raise DomainError("rate_limited", "Too many pending Google connections", 503)
        state = secrets.token_urlsafe(32)
        self._pending[state] = (owner_id, now + self._ttl)
        return state

    def consume(self, state: str) -> str | None:
        entry = self._pending.pop(state, None) if state else None
        if entry is None or entry[1] <= self._now():
            return None
        return entry[0]


def google_connect_router(
    settings: Settings,
    vault: CredentialVault | None = None,
    *,
    states: OAuthStates | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> APIRouter:
    config = GoogleOAuthConfig(
        settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri
    )
    if vault is None:
        vault = SupabaseCredentialVault(
            Database(settings, admin=True), settings.credential_encryption_key
        )
    states = states or OAuthStates()  # in-memory: single backend instance only
    router = APIRouter(prefix="/api/google", route_class=DomainRoute, tags=["google"])

    async def owner(authorization: str | None) -> str:
        return (await authenticate(settings, authorization, transport)).owner_id

    @router.post("/connect")
    async def connect(authorization: Annotated[str | None, Header()] = None):
        state = states.issue(await owner(authorization))
        return {"authorization_url": authorization_url(config, state)}

    def to_app(**query: str) -> RedirectResponse:
        return RedirectResponse(f"{settings.app_url}/?{urlencode(query)}", status_code=303)

    @router.get("/callback")
    async def callback(state: str = "", code: str = "", error: str = ""):
        try:
            email = await complete(state, code, error)
        except DomainError as failure:
            reason = REDIRECT_REASONS.get(failure.code)
            if not settings.app_url or reason is None:
                raise
            return to_app(google="error", reason=reason)
        if settings.app_url:
            return to_app(google="connected")
        return {"connected": True, "email": email}

    async def complete(state: str, code: str, error: str) -> str:
        owner_id = states.consume(state)
        if owner_id is None:
            raise DomainError("invalid_state", "Invalid or expired OAuth state", 400)
        if error or not code:
            raise DomainError("not_granted", "Google authorization was not granted", 400)
        try:
            grant = await exchange_code(config, code, transport)
        except ProviderError:
            raise DomainError("provider_failed", "Google token exchange failed", 502) from None
        if not grant.refresh_token:
            raise DomainError(
                "no_refresh_token", "Google returned no refresh token; revoke access and retry", 400
            )
        try:
            email = id_token_claims(grant.id_token or "").get("email", "")
        except ProviderError:
            email = ""
        if not isinstance(email, str) or not email:
            raise DomainError("provider_failed", "Google did not return the account email", 502)
        await vault.put_refresh_token(owner_id, email, grant.refresh_token, grant.scope)
        return email

    @router.get("/status")
    async def status(authorization: Annotated[str | None, Header()] = None):
        email = await vault.get_account_email(await owner(authorization))
        return {"connected": email is not None, "email": email}

    return router
