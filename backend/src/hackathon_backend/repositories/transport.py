"""Supabase HTTP boundary. Never log tokens, provider payloads, or raw upstream errors."""

from typing import Any
from urllib.parse import urlsplit

import httpx

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError


class Database:
    def __init__(
        self,
        settings: Settings,
        *,
        token: str | None = None,
        admin: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = urlsplit(settings.supabase_url)
        if (
            not url.hostname
            or (
                url.scheme != "https"
                and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"})
            )
            or url.path not in ("", "/")
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise DomainError("not_configured", "Configure the HTTPS Supabase project URL", 503)
        key = settings.supabase_service_role_key if admin else settings.supabase_publishable_key
        if not key:
            raise DomainError("not_configured", "Supabase credentials are missing", 503)
        self.settings, self.admin, self.transport = settings, admin, transport
        self._key, self._token = key, key if admin else token

    def __repr__(self) -> str:
        return f"Database(admin={self.admin})"

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        binary = kwargs.pop("binary", False)
        headers = {"apikey": self._key, **kwargs.pop("headers", {})}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.supabase_url,
                timeout=15,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError:
            raise DomainError(
                "provider_unavailable", "Supabase could not be reached", 503
            ) from None
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            code = payload.get("message", "") if isinstance(payload, dict) else ""
            known = {
                "revision_conflict",
                "idempotency_conflict",
                "operation_in_progress",
                "needs_review",
                "not_found",
                "forbidden",
                "reconciliation_required",
            }
            if code in known:
                status = 404 if code == "not_found" else 403 if code == "forbidden" else 409
                raise DomainError(code, code.replace("_", " "), status)
            if response.status_code == 401:
                raise DomainError("unauthenticated", "Session is invalid or expired", 401)
            if response.status_code == 403:
                raise DomainError("forbidden", "Access denied", 403)
            if response.status_code == 409:
                raise DomainError("conflict", "The record already exists", 409)
            if response.status_code == 400:
                raise DomainError(
                    "invalid_request", "Database validation rejected the request", 422
                )
            raise DomainError("provider_failed", "Supabase request failed", 502)
        if not response.content:
            return None
        if binary:
            return response.content
        try:
            return response.json()
        except ValueError:
            raise DomainError("provider_failed", "Supabase returned invalid JSON", 502) from None

    async def rpc(self, name: str, **params: Any) -> Any:
        return await self.request("POST", f"/rest/v1/rpc/{name}", json=params)

    async def download(self, path: str, *, max_bytes: int) -> bytes:
        """Bound private object reads while streaming, before buffering the body."""
        if not path.startswith("/storage/v1/object/") or not 0 < max_bytes <= 10_000_000:
            raise ValueError("Invalid private object download")
        headers = {"apikey": self._key}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.supabase_url,
                timeout=15,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                async with client.stream("GET", path, headers=headers) as response:
                    if response.status_code != 200:
                        raise DomainError(
                            "provider_failed", "Unable to load private event asset", 502
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise DomainError("needs_review", "Event asset exceeds the byte limit")
                    return bytes(content)
        except httpx.RequestError:
            raise DomainError(
                "provider_unavailable", "Private Storage could not be reached", 503
            ) from None

    async def rows(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        return await self.request("GET", f"/rest/v1/{table}", params=filters)
