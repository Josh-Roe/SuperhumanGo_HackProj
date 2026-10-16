from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackathon_backend.config import Settings
from hackathon_backend.main import create_app


@pytest.fixture
def client():
    with TestClient(
        create_app(Settings(mcp_auth_token="test-secret")), base_url="http://localhost"
    ) as c:
        yield c


def mcp_request(client, method, params=None, headers=None):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={
            "Authorization": "Bearer test-secret",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        },
    )


def test_health_and_status_do_not_disclose_credentials_or_paths(client):
    assert client.get("/api/health").json() == {"status": "ok", "service": "backend"}
    response = client.get("/api/status")
    assert response.json() == {
        "superhuman": {
            "transport": "mcp",
            "configured": True,
            "verified": False,
            "endpoint": "/mcp",
        },
        "model": {"configured": False, "runtime": "not_configured"},
    }
    assert "test-secret" not in response.text


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/nested"])
def test_mcp_fails_closed_without_configuration(method, path):
    with TestClient(create_app(Settings()), base_url="http://localhost") as client:
        assert client.request(method, path).status_code == 503
        assert client.get("/api/health").status_code == 200
        assert not client.get("/api/status").json()["superhuman"]["configured"]


@pytest.mark.parametrize("authorization", ["", "Basic test-secret", "Bearer wrong", "Bearer"])
def test_mcp_requires_valid_bearer(client, authorization):
    response = client.post("/mcp", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_streamable_mcp_initialize_list_and_call(client):
    initialized = mcp_request(
        client,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "Superhuman Go Hackathon"
    listed = mcp_request(client, "tools/list")
    assert listed.status_code == 200
    assert {tool["name"] for tool in listed.json()["result"]["tools"]} == {
        "workspace_status",
        "count_text",
    }
    assert all(
        tool["annotations"]["readOnlyHint"] is True for tool in listed.json()["result"]["tools"]
    )
    counted = mcp_request(
        client,
        "tools/call",
        {"name": "count_text", "arguments": {"text": "Hello team!\nLet's build."}},
    )
    assert counted.status_code == 200
    assert counted.json()["result"]["structuredContent"] == {"characters": 24, "words": 4}
    status = mcp_request(client, "tools/call", {"name": "workspace_status", "arguments": {}})
    assert status.json()["result"]["structuredContent"] == client.get("/api/status").json()


def test_tool_input_limit(client):
    response = mcp_request(
        client, "tools/call", {"name": "count_text", "arguments": {"text": "x" * 10_001}}
    )
    assert response.json()["result"]["isError"] is True


def test_mcp_rejects_untrusted_host_and_origin(client):
    assert (
        mcp_request(client, "tools/list", headers={"Host": "attacker.example"}).status_code == 421
    )
    assert (
        mcp_request(client, "tools/list", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )


def test_configured_deployment_host_and_origin():
    with TestClient(
        create_app(Settings(mcp_auth_token="test-secret", app_domain="demo.example")),
        base_url="https://demo.example",
    ) as client:
        assert (
            mcp_request(
                client, "tools/list", headers={"Origin": "https://demo.example"}
            ).status_code
            == 200
        )


@pytest.mark.parametrize("domain", ["https://example.com", "example.com/path", "*.example.com"])
def test_domain_rejects_schemes_paths_and_wildcards(domain):
    with pytest.raises(ValueError, match="APP_DOMAIN"):
        Settings(app_domain=domain)


def test_environment_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "credential-not-a-path")
    monkeypatch.setenv("APP_DOMAIN", "demo.example")
    monkeypatch.setenv("ONNX_MODEL_PATH", str(tmp_path / "model.onnx"))
    settings = Settings.from_env()
    assert settings.onnx_model_path == Path(tmp_path / "model.onnx")
    assert "credential-not-a-path" not in repr(settings)
