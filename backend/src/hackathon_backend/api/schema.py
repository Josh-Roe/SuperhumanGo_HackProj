"""Export the exact Member 2 OpenAPI contract without running a server or accessing accounts.

Run: uv run --project backend python -m hackathon_backend.api.schema
"""

import json

from fastapi import FastAPI

from hackathon_backend.api import create_router
from hackathon_backend.config import Settings


def schema() -> dict:
    app = FastAPI(title="Organizer backend contract", version="0.2.0")
    app.include_router(create_router(Settings()))
    return app.openapi()


if __name__ == "__main__":
    print(json.dumps(schema(), indent=2))
