"""Authenticated encryption for OAuth/Canva secrets, available to server processes only."""

import json
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.transport import Database


class SupabaseCredentialVault:
    def __init__(self, database: Database, encryption_key: str) -> None:
        if not database.admin or not encryption_key:
            raise DomainError("not_configured", "Server credential vault is not configured", 503)
        self.db = database
        try:
            self._cipher = Fernet(encryption_key.encode())
        except (ValueError, TypeError):
            raise DomainError("not_configured", "Vault encryption key is invalid", 503) from None

    async def put_secret(self, owner_id: str, provider: str, value: dict) -> None:
        owner_id = str(UUID(owner_id))
        envelope = {"owner_id": owner_id, "provider": provider, "value": value}
        ciphertext = self._cipher.encrypt(json.dumps(envelope).encode()).decode()
        await self.db.request(
            "POST",
            "/rest/v1/provider_secrets",
            params={"on_conflict": "owner_id,provider"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={"owner_id": owner_id, "provider": provider, "ciphertext": ciphertext},
        )

    async def get_secret(self, owner_id: str, provider: str) -> dict | None:
        owner_id = str(UUID(owner_id))
        rows = await self.db.rows(
            "provider_secrets",
            owner_id=f"eq.{owner_id}",
            provider=f"eq.{provider}",
        )
        if not rows:
            return None
        try:
            envelope = json.loads(self._cipher.decrypt(rows[0]["ciphertext"].encode()))
            if envelope["owner_id"] != owner_id or envelope["provider"] != provider:
                raise ValueError("Scope mismatch")
            return envelope["value"]
        except (InvalidToken, ValueError, KeyError):
            raise DomainError(
                "provider_failed", "Credential vault could not decrypt this record", 502
            ) from None

    async def put_refresh_token(
        self,
        owner_id: str,
        account_email: str,
        refresh_token: str,
        scopes: str,
    ) -> None:
        await self.put_secret(
            owner_id,
            "google",
            {
                "refresh_token": refresh_token,
                "account_email": account_email,
                "scopes": scopes,
            },
        )

    async def get_refresh_token(self, owner_id: str) -> str | None:
        record = await self.get_secret(owner_id, "google")
        return record.get("refresh_token") if record else None

    async def get_account_email(self, owner_id: str) -> str | None:
        record = await self.get_secret(owner_id, "google")
        return record.get("account_email") if record else None
