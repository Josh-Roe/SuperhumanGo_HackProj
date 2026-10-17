import asyncio
import base64
import json

import httpx
import pytest

from hackathon_backend.providers.google.gmail import GoogleGmailAPI
from hackathon_backend.providers.google.oauth import StaticTokenSource
from hackathon_backend.workflows.ports import ProviderError

TOKENS = StaticTokenSource({"owner-1": "ya29.secret-token"}, {"owner-1": "org@example.com"})
PREFIX = "/gmail/v1/users/me"


def api(handler):
    return GoogleGmailAPI(TOKENS, transport=httpx.MockTransport(handler))


def decode_raw(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def test_create_draft_encodes_raw_and_thread():
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == f"{PREFIX}/drafts"
        assert request.headers["authorization"] == "Bearer ya29.secret-token"
        body = json.loads(request.content)
        assert decode_raw(body["message"]["raw"]) == b"Subject: hi\r\n\r\nbody\xff"
        assert body["message"]["threadId"] == "t1"
        return httpx.Response(200, json={"id": "d1", "message": {"id": "m1", "threadId": "t1"}})

    result = asyncio.run(api(handler).create_draft("owner-1", b"Subject: hi\r\n\r\nbody\xff", "t1"))
    assert result["id"] == "d1"


def test_create_draft_without_thread_omits_thread_id():
    def handler(request):
        assert "threadId" not in json.loads(request.content)["message"]
        return httpx.Response(200, json={"id": "d1"})

    asyncio.run(api(handler).create_draft("owner-1", b"x", None))


def test_update_draft_put_and_404():
    def handler(request: httpx.Request):
        assert request.method == "PUT"
        if request.url.path == f"{PREFIX}/drafts/d1":
            assert json.loads(request.content)["id"] == "d1"
            return httpx.Response(200, json={"id": "d1"})
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})

    gmail = api(handler)
    assert asyncio.run(gmail.update_draft("owner-1", "d1", b"x", None)) == {"id": "d1"}
    with pytest.raises(ProviderError) as caught:
        asyncio.run(gmail.update_draft("owner-1", "gone", b"x", None))
    assert caught.value.status == 404


def test_get_draft_and_message_return_none_on_404():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/drafts/d1"):
            assert request.url.params["format"] == "minimal"
            return httpx.Response(200, json={"id": "d1"})
        if request.url.path.endswith("/messages/m1"):
            assert request.url.params["format"] == "metadata"
            return httpx.Response(200, json={"id": "m1", "labelIds": ["SENT"]})
        return httpx.Response(404)

    gmail = api(handler)

    async def run():
        assert await gmail.get_draft("owner-1", "d1") == {"id": "d1"}
        assert await gmail.get_draft("owner-1", "missing") is None
        assert (await gmail.get_message("owner-1", "m1"))["labelIds"] == ["SENT"]
        assert await gmail.get_message("owner-1", "missing") is None

    asyncio.run(run())


def test_send_draft_and_thread_listing():
    def handler(request: httpx.Request):
        if request.url.path == f"{PREFIX}/drafts/send":
            assert request.method == "POST"
            assert json.loads(request.content) == {"id": "d1"}
            return httpx.Response(200, json={"id": "m1", "threadId": "t1", "labelIds": ["SENT"]})
        assert request.url.path == f"{PREFIX}/threads/t1"
        assert request.url.params["format"] == "full"
        return httpx.Response(200, json={"id": "t1", "messages": [{"id": "m1"}, {"id": "m2"}]})

    gmail = api(handler)
    assert asyncio.run(gmail.send_draft("owner-1", "d1"))["threadId"] == "t1"
    messages = asyncio.run(gmail.list_thread_messages("owner-1", "t1"))
    assert [message["id"] for message in messages] == ["m1", "m2"]


def test_server_error_is_safe():
    def handler(request):
        return httpx.Response(500, text="ya29.secret-token internal")

    with pytest.raises(ProviderError) as caught:
        asyncio.run(api(handler).send_draft("owner-1", "d1"))
    assert caught.value.status == 500
    assert "secret" not in str(caught.value)
