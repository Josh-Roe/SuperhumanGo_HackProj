"""Native hosted entrypoint. Composition stays in Member 3's main.create_app."""

import os

import uvicorn

from hackathon_backend.api.readiness import report
from hackathon_backend.config import Settings


def main() -> None:
    # Render supplies its stable hostname, without scheme/path. A manual hostname
    # takes precedence for custom domains and other hosts.
    if not os.environ.get("APP_DOMAIN") and os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
        os.environ["APP_DOMAIN"] = os.environ["RENDER_EXTERNAL_HOSTNAME"]
    from hackathon_backend.main import app

    readiness = report(Settings.from_env(), app)
    if not readiness["configuration_ready"]:
        raise SystemExit("Backend deployment is incomplete: " + ", ".join(readiness["blockers"]))
    uvicorn.run(
        "hackathon_backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        workers=1,
        # Keep the default trusted proxy policy; do not trust arbitrary internet IPs.
        access_log=False,
    )


if __name__ == "__main__":
    main()
