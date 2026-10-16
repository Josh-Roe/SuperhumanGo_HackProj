import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hackathon_backend.providers.google import oauth
from hackathon_backend.providers.google.oauth import (
    SCOPES,
    GoogleOAuthConfig,
    StaticTokenSource,
    TokenGrant,
    VaultTokenSource,
    authorization_url,
    exchange_code,
    id_token_claims,
    refresh,
)
from hackathon_backend.workflows.ports import IntegrationNotConnected, ProviderError

CONFIG = GoogleOAuthConfig("client-id", "client-secret-value", "https://app.test/oauth/callback")


class FakeVault:
    def __init__(self, refresh_token=None, email=None):
        self.refresh_token = refresh_token
        self.email = email
        self.reads = 0

    async def get_refresh_token(self, owner_id):
        self.reads += 1
        return self.refresh_token

    async def put_refresh_token(self, owner_id, account_email, refresh_token, scopes):
        self.refresh_token, self.email = refresh_token, account_email

    async def get_account_email(self, owner_id):
        return self.email


def test_from_env(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    assert GoogleOAuthConfig.from_env() is None
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "shh-secret")
    assert GoogleOAuthConfig.from_env() is None
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://app.test/cb")
    config = GoogleOAuthConfig.from_env()
    assert config == GoogleOAuthConfig("id", "shh-secret", "https://app.test/cb")
    assert "shh-secret" not in repr(config)


def test_authorization_url():
    url = authorization_url(CONFIG, "state-123", login_hint="org@example.com")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == oauth.AUTH_URL
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query["scope"].split(" ") == list(SCOPES)
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["include_granted_scopes"] == "true"
    assert query["response_type"] == "code"
    assert query["state"] == "state-123"
    assert query["login_hint"] == "org@example.com"
    assert query["redirect_uri"] == CONFIG.redirect_uri
    assert "client-secret" not in url


def test_exchange_code_and_grant_repr_hides_tokens():
    def handler(request: httpx.Request):
        assert str(request.url) == oauth.TOKEN_URL
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["code"] == ["auth-code"]
        assert form["redirect_uri"] == [CONFIG.redirect_uri]
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.access-secret",
                "refresh_token": "1//refresh-secret",
                "expires_in": 3599,
                "scope": " ".join(SCOPES),
                "id_token": "h.e.s",
            },
        )

    grant = asyncio.run(exchange_code(CONFIG, "auth-code", httpx.MockTransport(handler)))
    assert grant.access_token == "ya29.access-secret"
    assert grant.refresh_token == "1//refresh-secret"
    assert grant.expires_at > datetime.now(UTC) + timedelta(minutes=59)
    text = repr(grant)
    assert "secret" not in text and "h.e.s" not in text


def test_refresh_errors_are_safe():
    def handler(request):
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["refresh_token"]
        return httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "1//refresh-secret bad"}
        )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(refresh(CONFIG, "1//refresh-secret", httpx.MockTransport(handler)))
    assert caught.value.status == 400
    assert str(caught.value) == "invalid_grant"

    def broken(request):
        return httpx.Response(500, text="1//refresh-secret")

    with pytest.raises(ProviderError) as caught:
        asyncio.run(refresh(CONFIG, "1//refresh-secret", httpx.MockTransport(broken)))
    assert "secret" not in str(caught.value)


def test_id_token_claims():
    payload = base64.urlsafe_b64encode(json.dumps({"email": "a@x.com"}).encode()).decode()
    assert id_token_claims(f"h.{payload.rstrip('=')}.s")["email"] == "a@x.com"
    with pytest.raises(ProviderError):
        id_token_claims("garbage")


def test_vault_token_source_caches_and_dedupes_refresh():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"access_token": f"tok-{len(calls)}", "expires_in": 3600})

    vault = FakeVault("1//refresh-secret", "org@example.com")
    source = VaultTokenSource(CONFIG, vault, httpx.MockTransport(handler))

    async def run():
        tokens = await asyncio.gather(*(source.access_token("owner-1") for _ in range(5)))
        assert set(tokens) == {"tok-1"}
        assert await source.access_token("owner-1") == "tok-1"
        assert await source.account_email("owner-1") == "org@example.com"

    asyncio.run(run())
    assert len(calls) == 1
    assert "tok-1" not in repr(source)


def test_vault_token_source_refreshes_near_expiry():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"access_token": f"tok-{count}", "expires_in": 30})

    source = VaultTokenSource(CONFIG, FakeVault("rt", "o@x.com"), httpx.MockTransport(handler))
    assert asyncio.run(source.access_token("o")) == "tok-1"
    assert asyncio.run(source.access_token("o")) == "tok-2"  # 30s < 60s margin


def test_vault_token_source_not_connected_and_revoked():
    def revoked(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    empty = VaultTokenSource(CONFIG, FakeVault(), httpx.MockTransport(revoked))
    with pytest.raises(IntegrationNotConnected):
        asyncio.run(empty.access_token("o"))
    with pytest.raises(IntegrationNotConnected):
        asyncio.run(empty.account_email("o"))
    source = VaultTokenSource(CONFIG, FakeVault("rt"), httpx.MockTransport(revoked))
    with pytest.raises(IntegrationNotConnected):
        asyncio.run(source.access_token("o"))


def test_static_token_source():
    source = StaticTokenSource({"o": "static-secret"}, {"o": "o@x.com"})
    assert asyncio.run(source.access_token("o")) == "static-secret"
    assert asyncio.run(source.account_email("o")) == "o@x.com"
    assert "static-secret" not in repr(source)
    with pytest.raises(IntegrationNotConnected):
        asyncio.run(source.access_token("other"))
    assert "secret" not in repr(TokenGrant("secret-a", datetime.now(UTC), "", "secret-r"))
