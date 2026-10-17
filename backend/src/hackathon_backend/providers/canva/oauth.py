"""Canva MCP OAuth, PKCE and encrypted owner-scoped token refresh.

Endpoints/resource were verified from Canva's public OAuth metadata. This is a
single-process implementation: run one worker until shared state/refresh leases exist.
"""

import asyncio
import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError

AUTH_URL = "https://mcp.canva.com/authorize"
TOKEN_URL = "https://mcp.canva.com/token"
RESOURCE = "https://mcp.canva.com/mcp"
SCOPES = (
    "profile:read design:meta:read design:content:read design:content:write asset:read asset:write"
)


@dataclass(frozen=True)
class CanvaOAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str

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

    @classmethod
    def from_settings(cls, settings: Settings):
        if not all(
            (settings.canva_client_id, settings.canva_client_secret, settings.canva_redirect_uri)
        ):
            return None
        return cls(
            settings.canva_client_id, settings.canva_client_secret, settings.canva_redirect_uri
        )


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


def authorization_url(config: CanvaOAuthConfig, state: str, challenge: str) -> str:
    return (
        AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": config.redirect_uri,
                "response_type": "code",
                "state": state,
                "scope": SCOPES,
                "resource": RESOURCE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )


class CanvaVault(Protocol):
    async def get_secret(self, owner_id: str, provider: str) -> dict | None: ...
    async def put_secret(self, owner_id: str, provider: str, value: dict) -> None: ...


class CanvaTokens:
    def __init__(
        self,
        config: CanvaOAuthConfig,
        vault: CanvaVault,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.config, self.vault, self.transport, self.now = config, vault, transport, now
        self.locks: dict[str, asyncio.Lock] = {}

    async def _exchange(self, form: dict, prior: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client:
                response = await client.post(
                    TOKEN_URL,
                    auth=httpx.BasicAuth(self.config.client_id, self.config.client_secret),
                    data={**form, "resource": RESOURCE},
                )
        except httpx.RequestError:
            raise DomainError(
                "provider_failed", "Canva token service could not be reached", 502
            ) from None
        if response.status_code != 200:
            raise DomainError(
                "integration_not_connected",
                "Canva authorization failed; reconnect your account",
                503,
            )
        try:
            data = response.json()
            access = data["access_token"]
            expires = data["expires_in"]
            refresh = data.get("refresh_token") or (prior or {}).get("refresh_token")
            if (
                not isinstance(access, str)
                or not access
                or len(access) > 16384
                or any(c.isspace() for c in access)
                or data.get("token_type", "").lower() != "bearer"
                or isinstance(expires, bool)
                or not isinstance(expires, int)
                or not 0 < expires <= 31_536_000
                or (
                    refresh is not None
                    and (not isinstance(refresh, str) or not refresh or len(refresh) > 16384)
                )
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DomainError(
                "provider_failed", "Canva returned an invalid token response", 502
            ) from None
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": (self.now() + timedelta(seconds=expires)).isoformat(),
            "scope": str(data.get("scope", (prior or {}).get("scope", ""))),
        }

    async def authorize(self, owner_id: str, code: str, verifier: str) -> None:
        async with self.locks.setdefault(owner_id, asyncio.Lock()):
            record = await self._exchange(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": self.config.redirect_uri,
                }
            )
            await self.vault.put_secret(owner_id, "canva", record)

    async def access_token(self, owner_id: str) -> str | None:
        async with self.locks.setdefault(owner_id, asyncio.Lock()):
            record = await self.vault.get_secret(owner_id, "canva")
            if not record or not record.get("access_token"):
                return None
            try:
                expiry = datetime.fromisoformat(record["expires_at"])
                if expiry.tzinfo is None:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                # Legacy manually inserted tokens need reconnect; do not assume immortality.
                raise DomainError(
                    "integration_not_connected", "Reconnect Canva to renew its authorization", 503
                ) from None
            if expiry > self.now() + timedelta(seconds=60):
                return record["access_token"]
            if not record.get("refresh_token"):
                raise DomainError(
                    "integration_not_connected", "Canva authorization expired; reconnect", 503
                )
            fresh = await self._exchange(
                {"grant_type": "refresh_token", "refresh_token": record["refresh_token"]}, record
            )
            await self.vault.put_secret(owner_id, "canva", fresh)
            return fresh["access_token"]
