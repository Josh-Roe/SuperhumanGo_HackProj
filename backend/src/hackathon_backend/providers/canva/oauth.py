"""Canva Connect OAuth (Authorization Code + PKCE) and per-organizer token refresh.

Each organizer connects their own Canva account. Tokens live only in the encrypted server
vault as provider `canva`: `{access_token, refresh_token, expires_at, scope}`. Readers that
only know `{access_token}` keep working. Canva refresh tokens are single use, so every
refresh stores the rotated refresh token, and refreshes are serialized per organizer.
"""

import asyncio
import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from hackathon_backend.providers.canva import CanvaError

AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
CANVA_SECRET = "canva"
# Create/read/edit designs and export them; scopes must also be enabled on the Canva app.
DEFAULT_SCOPES = (
    "design:meta:read",
    "design:content:read",
    "design:content:write",
    "asset:read",
    "asset:write",
)
REFRESH_MARGIN_SECONDS = 60


@dataclass(frozen=True)
class CanvaOAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    scopes: tuple[str, ...] = DEFAULT_SCOPES


class SecretVault(Protocol):
    async def put_secret(self, owner_id: str, provider: str, value: dict) -> None: ...

    async def get_secret(self, owner_id: str, provider: str) -> dict | None: ...


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(config: CanvaOAuthConfig, state: str, code_challenge: str) -> str:
    query = {
        "code_challenge": code_challenge,
        "code_challenge_method": "s256",
        "scope": " ".join(config.scopes),
        "response_type": "code",
        "client_id": config.client_id,
        "state": state,
        "redirect_uri": config.redirect_uri,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


async def _token_request(
    config: CanvaOAuthConfig,
    form: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
    now: float,
) -> dict[str, Any]:
    basic = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30), follow_redirects=False, trust_env=False, transport=transport
        ) as client:
            response = await client.post(
                TOKEN_URL, data=form, headers={"Authorization": f"Basic {basic}"}
            )
    except httpx.HTTPError:
        raise CanvaError("canva_token_request_failed") from None
    if response.status_code != 200:
        raise CanvaError("canva_token_rejected")
    try:
        body = response.json()
    except ValueError:
        raise CanvaError("canva_token_rejected") from None
    access, refresh = body.get("access_token"), body.get("refresh_token")
    expires_in = body.get("expires_in")
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise CanvaError("canva_token_rejected")
    if not isinstance(expires_in, (int, float)) or expires_in <= 0:
        raise CanvaError("canva_token_rejected")
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": now + float(expires_in),
        "scope": body.get("scope") if isinstance(body.get("scope"), str) else "",
    }


async def exchange_code(
    config: CanvaOAuthConfig,
    code: str,
    code_verifier: str,
    transport: httpx.AsyncBaseTransport | None = None,
    now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": config.redirect_uri,
    }
    return await _token_request(config, form, transport, now())


class CanvaTokens:
    """Fresh per-organizer access tokens from the vault, refreshing shortly before expiry."""

    def __init__(
        self,
        vault: SecretVault,
        config: CanvaOAuthConfig | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.vault, self.config = vault, config
        self._transport, self._now = transport, now
        self._locks: dict[str, asyncio.Lock] = {}

    async def save_grant(self, owner_id: str, grant: dict[str, Any]) -> None:
        await self.vault.put_secret(owner_id, CANVA_SECRET, dict(grant))

    async def connected(self, owner_id: str) -> bool:
        record = await self.vault.get_secret(owner_id, CANVA_SECRET) or {}
        return bool(record.get("access_token") or record.get("refresh_token"))

    async def access_token(self, owner_id: str) -> str | None:
        """None when not connected. Raises CanvaError when a needed refresh fails."""
        async with self._locks.setdefault(owner_id, asyncio.Lock()):
            record = await self.vault.get_secret(owner_id, CANVA_SECRET) or {}
            token = record.get("access_token")
            expires_at = record.get("expires_at")
            fresh = isinstance(token, str) and bool(token) and (
                not isinstance(expires_at, (int, float))  # legacy {access_token} record
                or expires_at - REFRESH_MARGIN_SECONDS > self._now()
            )
            if fresh:
                return token
            refresh = record.get("refresh_token")
            if not isinstance(refresh, str) or not refresh:
                return None
            if self.config is None:
                raise CanvaError("canva_oauth_not_configured")
            grant = await _token_request(
                self.config,
                {"grant_type": "refresh_token", "refresh_token": refresh},
                self._transport,
                self._now(),
            )
            await self.save_grant(owner_id, grant)
            return grant["access_token"]
