"""Gmail v1 adapter: drafts as the reviewable unit, sending only an existing draft."""

import base64
from typing import Any

import httpx

from hackathon_backend.providers.google._http import GoogleREST, segment
from hackathon_backend.workflows.ports import GoogleTokenSource

GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


def _message(raw_mime: bytes, thread_id: str | None) -> dict[str, Any]:
    message: dict[str, Any] = {"raw": base64.urlsafe_b64encode(raw_mime).decode("ascii")}
    if thread_id:
        message["threadId"] = thread_id
    return {"message": message}


class GoogleGmailAPI:
    def __init__(
        self, tokens: GoogleTokenSource, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._rest = GoogleREST("Gmail", GMAIL_BASE_URL, tokens, transport)

    async def create_draft(self, owner_id: str, raw_mime: bytes, thread_id: str | None) -> dict:
        result = await self._rest.request(
            owner_id, "POST", "/drafts", json=_message(raw_mime, thread_id)
        )
        assert result is not None
        return result

    async def update_draft(
        self, owner_id: str, draft_id: str, raw_mime: bytes, thread_id: str | None
    ) -> dict:
        """Raises ProviderError(404) if the draft was sent or deleted."""
        result = await self._rest.request(
            owner_id,
            "PUT",
            f"/drafts/{segment(draft_id)}",
            json={"id": draft_id, **_message(raw_mime, thread_id)},
        )
        assert result is not None
        return result

    async def get_draft(self, owner_id: str, draft_id: str) -> dict | None:
        return await self._rest.request(
            owner_id,
            "GET",
            f"/drafts/{segment(draft_id)}",
            params={"format": "minimal"},
            none_on_404=True,
        )

    async def send_draft(self, owner_id: str, draft_id: str) -> dict:
        """Returns the sent message resource: {id, threadId, labelIds}."""
        result = await self._rest.request(owner_id, "POST", "/drafts/send", json={"id": draft_id})
        assert result is not None
        return result

    async def get_message(self, owner_id: str, message_id: str) -> dict | None:
        return await self._rest.request(
            owner_id,
            "GET",
            f"/messages/{segment(message_id)}",
            params={"format": "metadata"},
            none_on_404=True,
        )

    async def list_thread_messages(self, owner_id: str, thread_id: str) -> list[dict]:
        result = await self._rest.request(
            owner_id, "GET", f"/threads/{segment(thread_id)}", params={"format": "full"}
        )
        messages = (result or {}).get("messages", [])
        return [message for message in messages if isinstance(message, dict)]
