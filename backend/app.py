"""Vercel's conventional FastAPI entrypoint; also compatible with uvicorn app:app."""

from hackathon_backend.main import app

__all__ = ["app"]
