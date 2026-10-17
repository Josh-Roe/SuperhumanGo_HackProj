"""Canva Connect REST reads that the remote MCP server does not expose.

The MCP `export-design` tool returns Connect's asynchronous export `job` shape
(`{"job": {"id", "status": "in_progress|success|failed", "urls"}}`) but documents no
status-check tool. A pending export is therefore resumed with Connect's
`GET /v1/exports/{exportId}` using the same organizer-held OAuth access token, instead
of requesting a second export.
"""

import re
from typing import Any

import httpx

from hackathon_backend.providers.canva import CanvaError

CANVA_API = "https://api.canva.com/rest/v1"
_EXPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CanvaConnectExports:
    def __init__(
        self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not access_token or any(c.isspace() for c in access_token):
            raise ValueError("Expected a server-held Canva OAuth access token")
        self._token = access_token
        self._transport = transport

    async def get_export(self, export_id: str) -> dict[str, Any]:
        if not _EXPORT_ID.fullmatch(export_id or ""):
            raise CanvaError("invalid_export_job_id")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{CANVA_API}/exports/{export_id}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError:
            raise CanvaError("canva_export_poll_failed") from None
        if response.status_code in (401, 403):
            raise CanvaError("canva_export_poll_unauthorized")
        if response.status_code == 404:
            raise CanvaError("canva_export_job_not_found")
        if response.status_code != 200:
            raise CanvaError("canva_export_poll_failed")
        try:
            body = response.json()
        except ValueError:
            raise CanvaError("unexpected_canva_response") from None
        if not isinstance(body, dict):
            raise CanvaError("unexpected_canva_response")
        return body
