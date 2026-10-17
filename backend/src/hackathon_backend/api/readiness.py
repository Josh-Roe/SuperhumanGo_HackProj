"""Deployment gates. A running health scaffold is not a persistent organizer service."""

import json
import os

from cryptography.fernet import Fernet
from fastapi import FastAPI

from hackathon_backend.auth.connectors import SupabasePrincipalResolver
from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore

REQUIRED_PATHS = {
    "/api/config",
    "/api/events",
    "/api/tasks",
    "/api/connectors",
    "/api/events/{event_id}/workspace",
    "/api/events/{event_id}/distribution/execute",
}


def report(settings: Settings, app: FastAPI) -> dict:
    """No network writes, secret values, or assertions about live account grants."""
    blockers = []
    for name in (
        "supabase_url",
        "supabase_publishable_key",
        "supabase_service_role_key",
        "credential_encryption_key",
        "app_domain",
    ):
        if not getattr(settings, name):
            blockers.append(f"missing:{name.upper()}")
    if settings.credential_encryption_key:
        try:
            Fernet(settings.credential_encryption_key.encode())
        except (ValueError, TypeError):
            blockers.append("invalid:CREDENTIAL_ENCRYPTION_KEY")
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            Database(settings, admin=True)
        except DomainError:
            blockers.append("invalid:SUPABASE_URL")
    if settings.app_domain.split(":")[0] in {"localhost", "127.0.0.1", "["}:
        blockers.append("public_hostname_required:APP_DOMAIN")
    if os.environ.get("WORKFLOW_DEV_MODE", "0") != "0":
        blockers.append("disable:WORKFLOW_DEV_MODE")
    paths = app.openapi().get("paths", {})
    blockers.extend(f"unregistered:{path}" for path in sorted(REQUIRED_PATHS - paths.keys()))
    if any(path.startswith("/api/dev/") for path in paths):
        blockers.append("development_routes_registered")
    # A router listed after the MCP catch-all is unreachable despite appearing in OpenAPI.
    catchall = next(
        (i for i, route in enumerate(app.routes) if getattr(route, "path", None) == ""),
        len(app.routes),
    )

    def route_paths(route):
        path = getattr(route, "path", None)
        if isinstance(path, str):
            yield path
        # Current FastAPI retains included routers instead of flattening them.
        included = getattr(route, "original_router", None)
        if included is not None:
            prefix = getattr(getattr(route, "include_context", None), "prefix", "")
            for child in included.routes:
                yield from (prefix + path for path in route_paths(child))

    if any(
        i > catchall and REQUIRED_PATHS.intersection(route_paths(route))
        for i, route in enumerate(app.routes)
    ):
        blockers.append("rest_routes_after_mcp_catchall")
    deps = next(
        (
            middleware.kwargs.get("deps")
            for middleware in app.user_middleware
            if middleware.cls.__name__ == "MCPBearerAuth"
        ),
        None,
    )
    store, principals = getattr(deps, "store", None), getattr(deps, "principals", None)
    if not isinstance(store, SupabaseWorkflowStore) or not isinstance(
        principals, SupabasePrincipalResolver
    ):
        blockers.append("persistent_mcp_dependencies_not_registered")
    elif (
        store.db.settings.supabase_url != settings.supabase_url
        or principals.db.settings.supabase_url != settings.supabase_url
    ):
        blockers.append("mcp_and_rest_database_mismatch")
    return {
        "configuration_ready": not blockers,
        "blockers": blockers,
        "live_provider_connections_verified": False,
    }


def main() -> None:
    from hackathon_backend.main import app

    result = report(Settings.from_env(), app)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["configuration_ready"] else 1)


if __name__ == "__main__":
    main()
