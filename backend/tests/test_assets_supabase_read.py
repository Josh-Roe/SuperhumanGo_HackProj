import asyncio

import httpx
import pytest
from test_assets_support import PNG

from hackathon_backend.services.assets.attachments import AssetDeliveryError
from hackathon_backend.services.assets.supabase_read import SupabaseAttachmentRepository

KEY = "fixture-owner/events/fixture-event/r1/flyer_png/fixture.png"
URL = f"https://fixture.supabase.co/storage/v1/object/sign/event-assets/{KEY}?token=synthetic"


class Storage:
    owner_id = "fixture-owner"

    def __init__(self, url=URL):
        self.url = url

    async def signed_url(self, object_key):
        assert object_key == KEY
        return self.url


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("fixture.supabase.co", "evil.example"),
        URL.replace("https:", "http:"),
        URL.replace(KEY, "another-object"),
        URL.replace("fixture.supabase.co", "user:secret@fixture.supabase.co"),
        URL + "#fragment",
    ],
)
def test_signed_url_rejects_wrong_origin_object_or_credentials_without_network(url):
    async def run():
        def handler(request):
            pytest.fail("Untrusted signed URL reached transport")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bridge = SupabaseAttachmentRepository(
                Storage(url), client, storage_origin="https://fixture.supabase.co"
            )
            with pytest.raises(AssetDeliveryError):
                await bridge.read_bytes("fixture-owner", KEY, max_bytes=1000)

    asyncio.run(run())


@pytest.mark.parametrize("case", ["success", "oversize", "redirect", "auth", "apikey", "owner"])
def test_signed_object_reader_enforces_scope_no_auth_redirects_and_byte_budget(case):
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                302 if case == "redirect" else 200,
                headers={"location": "https://evil.example/redirect"},
                content=PNG,
            )

        headers = (
            {"Authorization": "test-only"}
            if case == "auth"
            else ({"apikey": "test-only"} if case == "apikey" else {})
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers=headers
        ) as client:
            bridge = SupabaseAttachmentRepository(
                Storage(), client, storage_origin="https://fixture.supabase.co"
            )
            if case == "success":
                assert await bridge.read_bytes("fixture-owner", KEY, max_bytes=1000) == PNG
            else:
                error = (
                    PermissionError
                    if case == "owner"
                    else (ValueError if case in {"auth", "apikey"} else AssetDeliveryError)
                )
                with pytest.raises(error):
                    await bridge.read_bytes(
                        "other-owner" if case == "owner" else "fixture-owner",
                        KEY,
                        max_bytes=1 if case == "oversize" else 1000,
                    )
        if case in {"auth", "apikey", "owner"}:
            assert not calls
        assert len(calls) <= 1

    asyncio.run(run())
