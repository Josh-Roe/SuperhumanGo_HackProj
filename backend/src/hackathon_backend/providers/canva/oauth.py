"""Canva MCP OAuth (Authorization Code + PKCE) and per-organizer token refresh.

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
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from hackathon_backend.domain.models import DomainError
from hackathon_backend.providers.canva import CanvaError

# Developer Portal clients use the resource and authorization server advertised by
# api.canva.com/.well-known/oauth-protected-resource/connect/v1/mcp.
AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/auth/v1/oauth/token"
RESOURCE = "https://api.canva.com/connect/v1/mcp"
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

    def __post_init__(self):
        parsed = urlsplit(self.redirect_uri)
        if (
            (
                parsed.scheme != "https"
                and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
            )
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use the registered HTTPS Canva callback (or loopback HTTP)")
        if not self.client_id or not self.client_secret:
            raise ValueError("Configure Canva OAuth client credentials")


@dataclass(frozen=True)
class PendingConsent:
    owner_id: str
    verifier: str = field(repr=False)
    expires: float
    browser_hash: str | None = field(default=None, repr=False)


class CanvaOAuthStates:
    """Bounded, single-use, ten-minute PKCE state. Restart cancels pending consents."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self.now = now
        self.pending: dict[str, PendingConsent] = {}

    def issue(self, owner_id: str) -> tuple[str, str]:
        now = self.now()
        self.pending = {k: v for k, v in self.pending.items() if v.expires > now}
        if len(self.pending) >= 1000:
            raise DomainError("rate_limited", "Too many pending Canva connections", 503)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        self.pending[state] = PendingConsent(owner_id, verifier, now + 600)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return state, challenge

    def bind_browser(self, state: str) -> tuple[str, str]:
        found = self.pending.get(state)
        if found is None or found.expires <= self.now() or found.browser_hash is not None:
            raise DomainError(
                "invalid_state", "Invalid or expired Canva connection; start again", 400
            )
        cookie = secrets.token_urlsafe(32)
        self.pending[state] = replace(
            found, browser_hash=hashlib.sha256(cookie.encode()).hexdigest()
        )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(found.verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return cookie, challenge

    def consume(self, state: str, browser_cookie: str = "") -> PendingConsent:
        found = self.pending.pop(state, None)
        if (
            found is None
            or found.expires <= self.now()
            or found.browser_hash is None
            or not browser_cookie
            or not secrets.compare_digest(
                found.browser_hash, hashlib.sha256(browser_cookie.encode()).hexdigest()
            )
        ):
            raise DomainError(
                "invalid_state", "Invalid or expired Canva connection; start again", 400
            )
        return found


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
        "code_challenge_method": "S256",
        "scope": " ".join(config.scopes),
        "response_type": "code",
        "client_id": config.client_id,
        "resource": RESOURCE,
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
                TOKEN_URL,
                data={**form, "resource": RESOURCE},
                headers={"Authorization": f"Basic {basic}"},
            )
    except httpx.HTTPError:
        raise CanvaError("canva_token_request_failed") from None
    if response.status_code != 200:
        raise CanvaError("canva_token_rejected")
    try:
        body = response.json()
        access, refresh = body["access_token"], body.get("refresh_token")
        expires_in = body["expires_in"]
        if (
            not isinstance(access, str)
            or not access
            or len(access) > 16384
            or any(c.isspace() for c in access)
            or body.get("token_type", "").lower() != "bearer"
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or not 0 < expires_in <= 31_536_000
            or (
                refresh is not None
                and (not isinstance(refresh, str) or not refresh or len(refresh) > 16384)
            )
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CanvaError("canva_token_rejected") from None
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": now + expires_in,
        "scope": body.get("scope") if isinstance(body.get("scope"), str) else "",
        "resource": RESOURCE,
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
        await self.vault.put_secret(owner_id, CANVA_SECRET, {**grant, "resource": RESOURCE})

    async def authorize(self, owner_id: str, code: str, verifier: str) -> None:
        if self.config is None:
            raise CanvaError("canva_oauth_not_configured")
        async with self._locks.setdefault(owner_id, asyncio.Lock()):
            grant = await exchange_code(self.config, code, verifier, self._transport, self._now)
            await self.save_grant(owner_id, grant)

    async def connected(self, owner_id: str) -> bool:
        record = await self.vault.get_secret(owner_id, CANVA_SECRET) or {}
        if self.config is not None and record.get("resource") != RESOURCE:
            return False  # Unknown/REST audience: organizer must reconnect to MCP.
        expiry = record.get("expires_at")
        fresh = (
            isinstance(expiry, (int, float))
            and not isinstance(expiry, bool)
            and expiry > self._now()
        )
        return bool(
            record.get("access_token")
            and (fresh or record.get("refresh_token") or (self.config is None and expiry is None))
        )

    async def access_token(self, owner_id: str) -> str | None:
        """None when not connected. Raises CanvaError when a needed refresh fails."""
        async with self._locks.setdefault(owner_id, asyncio.Lock()):
            record = await self.vault.get_secret(owner_id, CANVA_SECRET) or {}
            if record and (
                record.get("resource") not in (None, RESOURCE)
                or (self.config is not None and record.get("resource") != RESOURCE)
            ):
                raise CanvaError("canva_mcp_reconnect_required")
            token = record.get("access_token")
            expires_at = record.get("expires_at")
            fresh = (
                isinstance(token, str)
                and bool(token)
                and (
                    (
                        isinstance(expires_at, (int, float))
                        and not isinstance(expires_at, bool)
                        and expires_at - REFRESH_MARGIN_SECONDS > self._now()
                    )
                    or (self.config is None and expires_at is None)
                )
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
            grant["refresh_token"] = grant.get("refresh_token") or refresh
            await self.save_grant(owner_id, grant)
            return grant["access_token"]
