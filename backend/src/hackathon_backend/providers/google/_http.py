"""Shared authenticated JSON transport for Google REST APIs with token-safe error mapping."""

import re
from typing import Any
from urllib.parse import quote

import httpx

from hackathon_backend.workflows.ports import GoogleTokenSource, ProviderError

TIMEOUT_SECONDS = 15.0
_SAFE_REASON = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,63}$")


def segment(value: str) -> str:
    """Percent-encode one path segment (calendar IDs contain '@' and '#')."""
    if not value:
        raise ValueError("Google resource ID must not be empty")
    return quote(value, safe="")


def error_reason(response: httpx.Response) -> str | None:
    """Google's machine-readable reason/error code only; never free-form body text."""
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    candidates: list[Any] = []
    if isinstance(error, dict):
        errors = error.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            candidates.append(errors[0].get("reason"))
        candidates.append(error.get("status"))
    elif isinstance(error, str):
        candidates.append(error)
    for candidate in candidates:
        if isinstance(candidate, str) and _SAFE_REASON.match(candidate):
            return candidate
    return None


class GoogleREST:
    def __init__(
        self,
        service: str,
        base_url: str,
        tokens: GoogleTokenSource,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service = service
        self._base_url = base_url
        self._tokens = tokens
        self._transport = transport

    async def request(
        self,
        owner_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        none_on_404: bool = False,
    ) -> dict[str, Any] | None:
        token = await self._tokens.access_token(owner_id)
        request_headers = {"Authorization": f"Bearer {token}", **(headers or {})}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(TIMEOUT_SECONDS),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method, path, params=params, json=json, headers=request_headers
                )
        except httpx.TimeoutException:
            raise ProviderError(504, f"{self._service} request timed out") from None
        except httpx.RequestError:
            raise ProviderError(502, f"{self._service} request failed") from None
        if response.status_code == 404 and none_on_404:
            return None
        if not response.is_success:
            reason = error_reason(response)
            message = f"{self._service} returned status {response.status_code}"
            raise ProviderError(
                response.status_code, f"{message} ({reason})" if reason else message
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError(502, f"{self._service} returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise ProviderError(502, f"{self._service} returned an unexpected payload")
        return payload
