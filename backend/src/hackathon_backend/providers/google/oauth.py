"""Google OAuth 2.0 web-server flow helpers and token sources. Tokens never leave the server."""

import asyncio
import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from hackathon_backend.workflows.ports import IntegrationNotConnected, ProviderError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
)
TIMEOUT_SECONDS = 15.0
REFRESH_MARGIN = timedelta(seconds=60)
_SAFE_ERROR = re.compile(r"^[a-z_]{1,64}$")


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "GoogleOAuthConfig | None":
        values = [
            os.environ.get(name, "").strip()
            for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
        ]
        return cls(*values) if all(values) else None


@dataclass(frozen=True)
class TokenGrant:
    access_token: str = field(repr=False)
    expires_at: datetime
    scope: str = ""
    refresh_token: str | None = field(default=None, repr=False)
    id_token: str | None = field(default=None, repr=False)


def authorization_url(config: GoogleOAuthConfig, state: str, login_hint: str | None = None) -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def id_token_claims(id_token: str) -> dict[str, Any]:
    """Unverified JWT claims. Only safe for an id_token received directly from TOKEN_URL."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise ProviderError(502, "Google returned an invalid id_token") from None
    if not isinstance(claims, dict):
        raise ProviderError(502, "Google returned an invalid id_token")
    return claims


async def _token_request(
    form: dict[str, str], transport: httpx.AsyncBaseTransport | None
) -> TokenGrant:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS), follow_redirects=False, transport=transport
        ) as client:
            response = await client.post(TOKEN_URL, data=form)
    except httpx.TimeoutException:
        raise ProviderError(504, "Google token request timed out") from None
    except httpx.RequestError:
        raise ProviderError(502, "Google token request failed") from None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not response.is_success:
        error = payload.get("error") if isinstance(payload, dict) else None
        safe = error if isinstance(error, str) and _SAFE_ERROR.match(error) else None
        raise ProviderError(
            response.status_code, safe or f"Google token endpoint returned {response.status_code}"
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise ProviderError(502, "Google token endpoint returned an invalid payload")
    try:
        expires_in = int(payload.get("expires_in", 3600))
    except (TypeError, ValueError):
        expires_in = 3600
    return TokenGrant(
        access_token=payload["access_token"],
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        scope=str(payload.get("scope", "")),
        refresh_token=payload.get("refresh_token"),
        id_token=payload.get("id_token"),
    )


async def exchange_code(
    config: GoogleOAuthConfig, code: str, transport: httpx.AsyncBaseTransport | None = None
) -> TokenGrant:
    return await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
        },
        transport,
    )


async def refresh(
    config: GoogleOAuthConfig,
    refresh_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TokenGrant:
    return await _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        },
        transport,
    )


class CredentialVault(Protocol):
    """Member 2: server-side encrypted storage of each organizer's Google refresh token."""

    async def get_refresh_token(self, owner_id: str) -> str | None: ...

    async def put_refresh_token(
        self, owner_id: str, account_email: str, refresh_token: str, scopes: str
    ) -> None: ...

    async def get_account_email(self, owner_id: str) -> str | None: ...


class VaultTokenSource:
    """GoogleTokenSource that refreshes from the vault and caches access tokens in memory."""

    def __init__(
        self,
        config: GoogleOAuthConfig,
        vault: CredentialVault,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._vault = vault
        self._transport = transport
        self._cache: dict[str, tuple[str, datetime]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def __repr__(self) -> str:
        return f"VaultTokenSource(cached_owners={len(self._cache)})"

    def _fresh(self, owner_id: str) -> str | None:
        cached = self._cache.get(owner_id)
        if cached and cached[1] - REFRESH_MARGIN > datetime.now(UTC):
            return cached[0]
        return None

    def forget(self, owner_id: str) -> None:
        """Drop a cached token (e.g. after disconnect or a 401)."""
        self._cache.pop(owner_id, None)

    async def access_token(self, owner_id: str) -> str:
        token = self._fresh(owner_id)
        if token:
            return token
        async with self._locks.setdefault(owner_id, asyncio.Lock()):
            token = self._fresh(owner_id)
            if token:
                return token
            refresh_token = await self._vault.get_refresh_token(owner_id)
            if not refresh_token:
                raise IntegrationNotConnected("Google account not connected")
            try:
                grant = await refresh(self._config, refresh_token, self._transport)
            except ProviderError as error:
                if str(error) == "invalid_grant":
                    self.forget(owner_id)
                    raise IntegrationNotConnected(
                        "Google authorization expired or revoked"
                    ) from None
                raise
            self._cache[owner_id] = (grant.access_token, grant.expires_at)
            return grant.access_token

    async def account_email(self, owner_id: str) -> str:
        email = await self._vault.get_account_email(owner_id)
        if not email:
            raise IntegrationNotConnected("Google account not connected")
        return email


class StaticTokenSource:
    """Fixed tokens for tests and local development only."""

    def __init__(self, token_by_owner: dict[str, str], email_by_owner: dict[str, str]) -> None:
        self._tokens = dict(token_by_owner)
        self._emails = dict(email_by_owner)

    def __repr__(self) -> str:
        return f"StaticTokenSource(owners={sorted(self._tokens)})"

    async def access_token(self, owner_id: str) -> str:
        token = self._tokens.get(owner_id)
        if not token:
            raise IntegrationNotConnected("Google account not connected")
        return token

    async def account_email(self, owner_id: str) -> str:
        email = self._emails.get(owner_id)
        if not email:
            raise IntegrationNotConnected("Google account not connected")
        return email
