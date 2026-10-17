from cryptography.fernet import Fernet
from fastapi import FastAPI

from hackathon_backend.api import create_router
from hackathon_backend.api.dependencies import create_tool_dependencies
from hackathon_backend.api.readiness import report
from hackathon_backend.config import Settings
from hackathon_backend.main import MCPBearerAuth


def settings(**overrides):
    values = {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "public",
        "supabase_service_role_key": "server-secret",
        "credential_encryption_key": Fernet.generate_key().decode(),
        "app_domain": "backend.example.com",
    }
    return Settings(**(values | overrides))


def test_readiness_reports_missing_registration_even_when_health_scaffold_is_alive(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "0")
    app = FastAPI()
    result = report(settings(), app)
    assert not result["configuration_ready"]
    assert "unregistered:/api/events" in result["blockers"]
    assert "server-secret" not in str(result)


def test_readiness_catches_routes_hidden_after_mcp_mount(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "0")
    config = settings()
    app = FastAPI()
    app.mount("/", FastAPI())
    app.include_router(create_router(config))
    result = report(config, app)
    assert "rest_routes_after_mcp_catchall" in result["blockers"]


def test_readiness_validates_secrets_and_rejects_development_mode(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "1")
    config = settings(credential_encryption_key="not-a-key", supabase_service_role_key="")
    app = FastAPI()
    app.include_router(create_router(config))
    result = report(config, app)
    assert "disable:WORKFLOW_DEV_MODE" in result["blockers"]
    assert "missing:SUPABASE_SERVICE_ROLE_KEY" in result["blockers"]
    assert "invalid:CREDENTIAL_ENCRYPTION_KEY" in result["blockers"]
    assert "not-a-key" not in str(result)


def test_configuration_readiness_does_not_claim_live_provider_verification(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "0")
    config = settings()
    app = FastAPI()
    app.include_router(create_router(config))
    app.add_middleware(MCPBearerAuth, token="", deps=create_tool_dependencies(config))
    result = report(config, app)
    assert result["configuration_ready"]
    assert result["live_provider_connections_verified"] is False


def test_rest_registration_alone_cannot_claim_persistent_go_is_ready(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DEV_MODE", "0")
    config = settings()
    app = FastAPI()
    app.include_router(create_router(config))
    result = report(config, app)
    assert "persistent_mcp_dependencies_not_registered" in result["blockers"]
