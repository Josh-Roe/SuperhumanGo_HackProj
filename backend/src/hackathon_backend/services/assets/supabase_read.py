"""Read bridge for Member 2's published SupabaseAssetStorage, without editing its repository."""

from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import httpx

from hackathon_backend.services.assets.attachments import AssetDeliveryError, AssetKind
from hackathon_backend.services.assets.models import AssetRecord, StaleRevisionError


class OrganizerAssets(Protocol):
    async def event_children(self, event_id: str, table: str) -> list[dict[str, Any]]: ...


class BoundAssetStorage(Protocol):
    owner_id: str
    repo: OrganizerAssets

    async def assert_current(self, owner_id: str, event_id: str, revision: int) -> None: ...

    async def signed_url(self, object_key: str, expires_in: int = 120) -> str: ...


class SupabaseAttachmentRepository:
    """Implements AttachmentRepository using existing public Storage methods.

    The caller supplies a principal-bound SupabaseAssetStorage and a dedicated
    unauthenticated HTTP client. Signed links remain transient server data.
    """

    def __init__(
        self, storage: BoundAssetStorage, client: httpx.AsyncClient, *, storage_origin: str
    ):
        parsed = urlsplit(storage_origin)
        if (
            not (
                parsed.scheme == "https"
                or (
                    parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                )
            )
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Expected the configured HTTPS or loopback Supabase origin")
        self.storage, self.client = storage, client
        self.origin = (
            parsed.scheme,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )

    def _scope(self, owner_id: str) -> None:
        if owner_id != self.storage.owner_id:
            raise PermissionError("Storage is outside the organizer scope")

    async def assert_current(self, owner_id: str, event_id: str, revision: int) -> None:
        self._scope(owner_id)
        try:
            await self.storage.assert_current(owner_id, event_id, revision)
        except Exception as error:
            if getattr(error, "code", None) in {"not_found", "forbidden"}:
                raise PermissionError("Event is outside the organizer scope") from None
            if getattr(error, "code", None) == "revision_conflict":
                raise StaleRevisionError("Event revision changed") from None
            raise

    async def current_asset(
        self, owner_id: str, event_id: str, kind: AssetKind
    ) -> AssetRecord | None:
        self._scope(owner_id)
        rows = await self.storage.repo.event_children(event_id, "artifacts")
        matches = [
            row
            for row in rows
            if row.get("is_current") is True and row.get("data", {}).get("kind") == kind
        ]
        if len(matches) > 1:
            raise AssetDeliveryError(
                "provider_failed", "Multiple current event assets need reconciliation"
            )
        return AssetRecord.model_validate(matches[0]["data"]) if matches else None

    async def read_bytes(self, owner_id: str, object_key: str, *, max_bytes: int) -> bytes:
        self._scope(owner_id)
        if not 0 < max_bytes <= 10_000_000:
            raise ValueError("Unsupported asset byte budget")
        if (
            self.client.auth is not None
            or self.client.cookies
            or "authorization" in self.client.headers
            or "cookie" in self.client.headers
            or "apikey" in self.client.headers
        ):
            raise ValueError("Signed object downloads require an unauthenticated HTTP client")
        url = await self.storage.signed_url(object_key)
        parsed = urlsplit(url)
        if (
            (
                parsed.scheme,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
            != self.origin
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path != f"/storage/v1/object/sign/event-assets/{quote(object_key, safe='/')}"
        ):
            raise AssetDeliveryError("provider_failed", "Storage returned an unexpected object URL")
        content = bytearray()
        async with self.client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                raise AssetDeliveryError("provider_failed", "Unable to download event asset")
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise AssetDeliveryError(
                        "needs_review", "Event asset exceeds attachment size limit"
                    )
        return bytes(content)
