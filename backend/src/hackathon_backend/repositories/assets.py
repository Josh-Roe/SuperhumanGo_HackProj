"""Member 4 AssetStorage and Member 3 AttachmentSource over private Supabase Storage."""

import hashlib
import re
from urllib.parse import quote
from uuid import UUID

from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.services.assets.models import AssetRecord, StaleRevisionError, StorageReceipt

BUCKET = "event-assets"
OBJECT_KEY = re.compile(
    r"(?P<owner>[0-9a-f-]{36})/events/(?P<event>[0-9a-f-]{36})/r(?P<revision>[1-9][0-9]*)/"
    r"(?P<kind>event_document|flyer_png)/(?P<hash>[0-9a-f]{64})\.(?P<suffix>html|png)"
)


class SupabaseAssetStorage:
    def __init__(self, database: Database, owner_id: str) -> None:
        self.db, self.owner_id = database, str(UUID(owner_id))
        self.repo = OrganizerRepository(database, self.owner_id)

    async def assert_current(self, owner_id: str, event_id: str, revision: int) -> None:
        if str(UUID(owner_id)) != self.owner_id:
            raise PermissionError("Asset is outside the organizer scope")
        event = await self.repo.get("events", event_id)
        if event["revision"] != revision:
            raise StaleRevisionError("Canonical event revision changed")

    async def put_if_absent(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> StorageReceipt:
        parts = OBJECT_KEY.fullmatch(object_key)
        if not parts or parts["owner"] != self.owner_id:
            raise PermissionError("Invalid organizer asset path")
        if content_type not in {"text/html; charset=utf-8", "image/png"}:
            raise ValueError("Unsupported artifact MIME type")
        expected_suffix = "html" if parts["kind"] == "event_document" else "png"
        if parts["suffix"] != expected_suffix or content_type.startswith("image/") != (
            expected_suffix == "png"
        ):
            raise ValueError("Asset path/MIME mismatch")
        if not 0 < len(content) <= 10_000_000:
            raise ValueError("Artifact is empty or exceeds 10 MB")
        digest = hashlib.sha256(content).hexdigest()
        if digest != sha256 or digest != parts["hash"]:
            raise ValueError("Artifact hash mismatch")
        await self.assert_current(self.owner_id, parts["event"], int(parts["revision"]))
        path = f"/storage/v1/object/{BUCKET}/{quote(object_key, safe='/')}"
        try:
            await self.db.request(
                "POST", path, headers={"Content-Type": content_type}, content=content
            )
        except DomainError as error:
            if error.code not in {"conflict", "invalid_request"}:
                raise
            # Storage can report an existing object as HTTP 400. Verify its bytes, never overwrite.
            existing = await self.db.request("GET", path, binary=True)
            if len(existing) != len(content) or hashlib.sha256(existing).hexdigest() != digest:
                raise DomainError("idempotency_conflict", "Existing object bytes differ") from None
        return StorageReceipt(object_key=object_key, sha256=digest, byte_length=len(content))

    async def publish_current(self, record: AssetRecord, *, expected_revision: int) -> None:
        if record.owner_id != self.owner_id:
            raise PermissionError("Asset is outside the organizer scope")
        parts = OBJECT_KEY.fullmatch(record.object_key)
        if (
            not parts
            or parts["owner"] != self.owner_id
            or parts["event"] != record.event_id
            or parts["hash"] != record.sha256
            or int(parts["revision"]) != record.event_revision
            or parts["kind"] != record.kind
            or record.event_revision != expected_revision
        ):
            raise ValueError("Asset metadata does not match object key")
        try:
            await self.db.rpc(
                "organizer_publish_asset",
                p_owner=self.owner_id,
                p_expected=expected_revision,
                p_data=record.model_dump(mode="json"),
            )
        except DomainError as error:
            if error.code == "revision_conflict":
                raise StaleRevisionError(error.message) from None
            raise

    async def current(self, event_id: str, kind: str) -> dict:
        event = await self.repo.get("events", event_id)
        rows = await self.db.rows(
            "artifacts",
            event_id=f"eq.{UUID(event_id)}",
            kind=f"eq.{kind}",
            event_revision=f"eq.{event['revision']}",
            is_current="eq.true",
        )
        if not rows:
            raise DomainError("not_found", "No current artifact at this revision", 404)
        record = AssetRecord.model_validate(rows[0]["data"])
        return {**record.preview_metadata(), "url": await self.signed_url(record.object_key)}

    async def signed_url(self, object_key: str, expires_in: int = 120) -> str:
        parts = OBJECT_KEY.fullmatch(object_key)
        if not parts or parts["owner"] != self.owner_id:
            raise PermissionError("Asset is outside the organizer scope")
        await self.repo.get("events", parts["event"])
        result = await self.db.request(
            "POST",
            f"/storage/v1/object/sign/{BUCKET}/{quote(object_key, safe='/')}",
            json={"expiresIn": min(max(expires_in, 1), 300)},
        )
        path = result.get("signedURL", "")
        if not path.startswith(f"/object/sign/{BUCKET}/"):
            raise DomainError("provider_failed", "Storage returned an invalid signed URL", 502)
        return f"{self.db.settings.supabase_url}/storage/v1{path}"


class SupabaseAttachmentSource:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def current_attachments(self, owner_id: str, event) -> list[tuple[str, str, bytes]]:
        if event.owner_id != owner_id:
            raise PermissionError("Event is outside the organizer scope")
        storage = SupabaseAssetStorage(self.db, owner_id)
        await storage.assert_current(owner_id, event.id, event.revision)
        rows = await storage.repo.event_children(event.id, "artifacts")
        files = []
        for row in rows:
            if not row["is_current"] or row["event_revision"] != event.revision:
                continue
            record = AssetRecord.model_validate(row["data"])
            if record.review_state != "reviewed":
                raise DomainError("needs_review", "Artifact needs organizer review")
            parts = OBJECT_KEY.fullmatch(record.object_key)
            if (
                not parts
                or parts["owner"] != str(UUID(owner_id))
                or parts["event"] != str(UUID(event.id))
            ):
                raise PermissionError("Artifact path is outside the event scope")
            content = await self.db.request(
                "GET",
                f"/storage/v1/object/{BUCKET}/{record.object_key}",
                binary=True,
            )
            if (
                len(content) != record.byte_length
                or hashlib.sha256(content).hexdigest() != record.sha256
            ):
                raise DomainError("provider_failed", "Stored artifact failed integrity check", 502)
            suffix = "png" if record.kind == "flyer_png" else "html"
            files.append(
                (f"{record.kind}-r{event.revision}.{suffix}", record.content_type, content)
            )
        return files
