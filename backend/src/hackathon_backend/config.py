"""Environment configuration. Secrets never enter API response models."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    mcp_auth_token: str = field(default="", repr=False)
    app_domain: str = ""
    # Organizer dashboard origin (may differ from app_domain when the website is hosted apart).
    app_url: str = ""
    onnx_model_path: Path | None = None
    supabase_url: str = ""
    supabase_publishable_key: str = field(default="", repr=False)
    supabase_service_role_key: str = field(default="", repr=False)
    credential_encryption_key: str = field(default="", repr=False)
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    google_redirect_uri: str = ""

    def __post_init__(self) -> None:
        if self.app_domain and not re.fullmatch(
            r"(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?",
            self.app_domain,
        ):
            raise ValueError(
                "APP_DOMAIN must be a hostname with optional port, without scheme/path"
            )
        if self.app_url and not re.fullmatch(
            r"https://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?|http://(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?",
            self.app_url,
        ):
            raise ValueError("APP_URL must be an https origin (or local http), without path")

    @classmethod
    def from_env(cls) -> "Settings":
        model_path = os.getenv("ONNX_MODEL_PATH", "").strip()
        return cls(
            mcp_auth_token=os.getenv("MCP_AUTH_TOKEN", "").strip(),
            app_domain=(
                os.getenv("APP_DOMAIN") or os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
            ).strip(),
            app_url=os.getenv("APP_URL", "").strip().rstrip("/"),
            onnx_model_path=Path(model_path) if model_path else None,
            supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
            supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            credential_encryption_key=os.getenv("CREDENTIAL_ENCRYPTION_KEY", "").strip(),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
        )

    @property
    def allowed_hosts(self) -> list[str]:
        local = ["127.0.0.1", "localhost", "[::1]", "127.0.0.1:*", "localhost:*", "[::1]:*"]
        return [*local, self.app_domain] if self.app_domain else local

    @property
    def allowed_origins(self) -> list[str]:
        origins = [
            "http://localhost",
            "http://127.0.0.1",
            "http://[::1]",
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://[::1]:*",
        ]
        if self.app_domain:
            origins.append(f"https://{self.app_domain}")
        return origins
