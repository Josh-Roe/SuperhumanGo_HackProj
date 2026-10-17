"""Per-organizer Go connector tokens. Plain tokens are returned only at issuance."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from hackathon_backend.repositories.transport import Database
from hackathon_backend.workflows.models import Principal


class SupabasePrincipalResolver:
    def __init__(self, database: Database) -> None:
        if not database.admin:
            raise ValueError("Connector resolution requires a server-side database client")
        self.db = database

    async def resolve(self, connector_token: str) -> Principal | None:
        if not connector_token.startswith("go_") or not 40 <= len(connector_token) <= 200:
            return None
        rows = await self.db.rows(
            "connector_tokens",
            token_hash=f"eq.{hashlib.sha256(connector_token.encode()).hexdigest()}",
            revoked_at="is.null",
            expires_at=f"gt.{datetime.now(UTC).isoformat()}",
            limit=1,
        )
        return Principal(owner_id=rows[0]["owner_id"]) if rows else None


async def issue_connector(database: Database, owner_id: str, label: str, days: int) -> dict:
    token = "go_" + secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=days)
    rows = await database.request(
        "POST",
        "/rest/v1/connector_tokens",
        headers={"Prefer": "return=representation"},
        json={
            "owner_id": str(UUID(owner_id)),
            "label": label,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": expires.isoformat(),
        },
    )
    return {"id": rows[0]["id"], "token": token, "expires_at": expires.isoformat()}
