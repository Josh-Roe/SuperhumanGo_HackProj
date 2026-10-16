"""Resolve user sessions at Supabase Auth, never by decoding unverified claims."""

from dataclasses import dataclass, field
from uuid import UUID

import httpx

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.transport import Database


@dataclass(frozen=True)
class Identity:
    owner_id: str
    token: str = field(repr=False)


async def authenticate(
    settings: Settings,
    authorization: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Identity:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise DomainError("unauthenticated", "A Supabase session is required", 401)
    user = await Database(settings, token=token, transport=transport).request(
        "GET", "/auth/v1/user"
    )
    try:
        owner_id = str(UUID(user["id"]))
    except (KeyError, TypeError, ValueError):
        raise DomainError("unauthenticated", "Supabase returned an invalid identity", 401) from None
    if user.get("is_anonymous"):
        raise DomainError("forbidden", "Sign in with an organizer account", 403)
    return Identity(owner_id, token)
