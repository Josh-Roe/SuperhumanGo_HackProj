"""Gmail v1 adapter: drafts as the reviewable unit, sending only an existing draft."""

import base64
from typing import Any

import httpx

from hackathon_backend.providers.google._http import GoogleREST, segment
from hackathon_backend.providers.google.mime import message_header
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

    async def find_by_message_id(self, owner_id: str, rfc822_message_id: str) -> list[dict]:
        """Read-back for unknown create/send outcomes via the deterministic Message-ID header.

        Search may lag a just-written message; callers treat "found" as proof, never "absent"
        as proof that a send did not happen.
        """
        bare = rfc822_message_id.strip().strip("<>")
        query = {"q": f"rfc822msgid:{bare}", "includeSpamTrash": "false"}
        listing = await self._rest.request(owner_id, "GET", "/messages", params=query)
        drafts = await self._rest.request(owner_id, "GET", "/drafts", params=query)
        draft_ids = {
            draft.get("message", {}).get("id"): draft.get("id")
            for draft in (drafts or {}).get("drafts", []) or []
            if isinstance(draft, dict)
        }
        found = []
        for item in (listing or {}).get("messages", []) or []:
            message_id = item.get("id") if isinstance(item, dict) else None
            if not message_id:
                continue
            message = await self._rest.request(
                owner_id,
                "GET",
                f"/messages/{segment(message_id)}",
                params={"format": "metadata", "metadataHeaders": "Message-ID"},
                none_on_404=True,
            )
            if not message or "TRASH" in message.get("labelIds", []):
                continue
            header = message_header(message, "Message-ID") or ""
            if header.strip().strip("<>") != bare:
                continue
            found.append(
                {
                    "id": message_id,
                    "threadId": message.get("threadId"),
                    "labelIds": message.get("labelIds", []),
                    "draft_id": draft_ids.get(message_id),
                }
            )
        return found
