"""Environment configuration. Secrets never enter API response models."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    mcp_auth_token: str = field(default="", repr=False)
    app_domain: str = ""
    onnx_model_path: Path | None = None

    def __post_init__(self) -> None:
        if self.app_domain and not re.fullmatch(
            r"(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?",
            self.app_domain,
        ):
            raise ValueError(
                "APP_DOMAIN must be a hostname with optional port, without scheme/path"
            )

    @classmethod
    def from_env(cls) -> "Settings":
        model_path = os.getenv("ONNX_MODEL_PATH", "").strip()
        return cls(
            mcp_auth_token=os.getenv("MCP_AUTH_TOKEN", "").strip(),
            app_domain=os.getenv("APP_DOMAIN", "").strip(),
            onnx_model_path=Path(model_path) if model_path else None,
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
