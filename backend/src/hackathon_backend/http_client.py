"""Provider-neutral outbound JSON boundary; no provider or endpoint is preselected."""

from typing import Any
from urllib.parse import urlsplit

import httpx


class APIRequestError(RuntimeError):
    """Safe error message for a caller to map to its own API response."""


class JSONAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and not local)
        ):
            raise ValueError("API base URL must use HTTPS (HTTP allowed only on localhost)")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("API timeout must be greater than zero and at most 120 seconds")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {bearer_token}"} if bearer_token else {},
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> "JSONAPIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, *, json: Any = None) -> Any:
        parsed = urlsplit(path)
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or any(ord(character) < 32 for character in path)
            or parsed.scheme
            or parsed.netloc
        ):
            raise ValueError("API path must be relative to the configured base URL")
        try:
            response = await self._client.request(method, path, json=json)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise APIRequestError("External API request timed out") from None
        except httpx.HTTPStatusError as error:
            raise APIRequestError(
                f"External API returned status {error.response.status_code}"
            ) from None
        except httpx.RequestError:
            raise APIRequestError("External API request failed") from None
        try:
            return response.json()
        except ValueError:
            raise APIRequestError("External API returned invalid JSON") from None
