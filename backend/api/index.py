"""Vercel FastAPI service entrypoint; routes retain the original /api/... path."""
from app.main import app

__all__ = ["app"]
