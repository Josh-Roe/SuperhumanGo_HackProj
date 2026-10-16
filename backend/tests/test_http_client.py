import asyncio

import httpx
import pytest

from hackathon_backend.http_client import APIRequestError, JSONAPIClient


def test_outbound_success_and_private_authorization():
    def upstream(request):
        assert request.url == "https://api.example.test/v1/lookup"
        assert request.headers["authorization"] == "Bearer server-only-secret"
        assert request.extensions["timeout"]["read"] == 3.0
        return httpx.Response(200, json={"result": "ok"})

    async def check():
        async with JSONAPIClient(
            "https://api.example.test/v1/",
            bearer_token="server-only-secret",
            timeout_seconds=3,
            transport=httpx.MockTransport(upstream),
        ) as client:
            assert await client.request("GET", "/lookup") == {"result": "ok"}

    asyncio.run(check())


@pytest.mark.parametrize("failure", ["timeout", "upstream", "invalid-json", "redirect"])
def test_outbound_failures_do_not_expose_credentials_or_upstream_body(failure):
    def upstream(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private URL and credential detail", request=request)
        if failure == "upstream":
            return httpx.Response(502, text="server-only-secret private upstream payload")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://attacker.example"})
        return httpx.Response(200, text="server-only-secret non-JSON payload")

    async def check():
        async with JSONAPIClient(
            "https://api.example.test", transport=httpx.MockTransport(upstream)
        ) as client:
            with pytest.raises(APIRequestError) as error:
                await client.request("GET", "/lookup")
            assert "server-only-secret" not in str(error.value)
            assert "private" not in str(error.value)
            assert "api.example.test" not in str(error.value)

    asyncio.run(check())


@pytest.mark.parametrize("path", ["https://evil.example", "//evil.example", "/\\evil", "lookup"])
def test_request_cannot_override_configured_host(path):
    async def check():
        async with JSONAPIClient("https://api.example.test") as client:
            with pytest.raises(ValueError, match="relative"):
                await client.request("GET", path)

    asyncio.run(check())


def test_base_url_and_timeout_validation():
    for url in ("http://remote.example", "https://secret@api.example", "ftp://api.example"):
        with pytest.raises(ValueError, match="HTTPS"):
            JSONAPIClient(url)
    with pytest.raises(ValueError, match="timeout"):
        JSONAPIClient("https://api.example.test", timeout_seconds=0)
