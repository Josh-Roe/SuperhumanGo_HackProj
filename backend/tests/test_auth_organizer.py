import asyncio
import hashlib
import json

import httpx
import pytest
from cryptography.fernet import Fernet

from hackathon_backend.auth.connectors import SupabasePrincipalResolver, issue_connector
from hackathon_backend.auth.identity import authenticate
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.vault import SupabaseCredentialVault

OWNER = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_publishable_key="publishable",
    supabase_service_role_key="server-secret",
)


def run(awaitable):
    return asyncio.run(awaitable)


def test_auth_verifies_session_with_server_and_ignores_request_owner():
    def handler(request):
        assert request.url.path == "/auth/v1/user"
        assert request.headers["Authorization"] == "Bearer opaque-user-session"
        assert request.headers["apikey"] == "publishable"
        return httpx.Response(200, json={"id": OWNER, "user_metadata": {"owner_id": OTHER}})

    identity = run(
        authenticate(SETTINGS, "Bearer opaque-user-session", httpx.MockTransport(handler))
    )
    assert identity.owner_id == OWNER
    assert "opaque-user-session" not in repr(identity)


@pytest.mark.parametrize("header", [None, "", "Basic token", "Bearer", "Bearer "])
def test_auth_rejects_absent_credentials_before_network(header):
    with pytest.raises(DomainError, match="session") as error:
        run(authenticate(SETTINGS, header))
    assert error.value.status == 401


def test_auth_rejects_expired_session_and_sanitizes_upstream_error():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(401, json={"message": "private-token"})
    )
    with pytest.raises(DomainError) as error:
        run(authenticate(SETTINGS, "Bearer expired", transport))
    assert error.value.code == "unauthenticated"
    assert "private-token" not in str(error.value)


def test_auth_rejects_anonymous_organizer():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"id": OWNER, "is_anonymous": True})
    )
    with pytest.raises(DomainError) as error:
        run(authenticate(SETTINGS, "Bearer anonymous", transport))
    assert error.value.code == "forbidden"


def test_connector_issue_stores_hash_only_and_resolution_filters_revocation_expiry():
    stored = {}

    def handler(request):
        if request.method == "POST":
            stored.update(json.loads(request.content))
            return httpx.Response(201, json=[{"id": OWNER}])
        assert request.url.params["token_hash"] == "eq." + stored["token_hash"]
        assert request.url.params["revoked_at"] == "is.null"
        assert request.url.params["expires_at"].startswith("gt.")
        assert request.headers["Authorization"] == "Bearer server-secret"
        return httpx.Response(200, json=[{"owner_id": OWNER}])

    transport = httpx.MockTransport(handler)
    issued = run(
        issue_connector(Database(SETTINGS, token="user", transport=transport), OWNER, "Go", 30)
    )
    assert issued["token"].startswith("go_")
    assert stored["token_hash"] == hashlib.sha256(issued["token"].encode()).hexdigest()
    assert issued["token"] not in json.dumps(stored)
    resolver = SupabasePrincipalResolver(Database(SETTINGS, admin=True, transport=transport))
    assert run(resolver.resolve(issued["token"])).owner_id == OWNER
    assert run(resolver.resolve("deployment-token")) is None


def test_connector_revoked_or_expired_is_not_a_principal():
    db = Database(
        SETTINGS, admin=True, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
    )
    assert run(SupabasePrincipalResolver(db).resolve("go_" + "x" * 43)) is None


def test_vault_encrypts_tokens_and_detects_cross_owner_ciphertext_swap():
    stored = {}

    def handler(request):
        if request.method == "POST":
            stored.update(json.loads(request.content))
            return httpx.Response(201)
        return httpx.Response(200, json=[stored])

    db = Database(SETTINGS, admin=True, transport=httpx.MockTransport(handler))
    vault = SupabaseCredentialVault(db, Fernet.generate_key().decode())
    run(vault.put_refresh_token(OWNER, "organizer@example.org", "sensitive-refresh", "gmail"))
    assert "sensitive-refresh" not in stored["ciphertext"]
    assert "organizer@example.org" not in stored["ciphertext"]
    assert run(vault.get_refresh_token(OWNER)) == "sensitive-refresh"
    with pytest.raises(DomainError, match="decrypt"):
        run(vault.get_refresh_token(OTHER))


def test_vault_fails_closed_without_server_key_or_encryption_key():
    with pytest.raises(DomainError):
        SupabaseCredentialVault(Database(SETTINGS, token="user"), "")
