"""FastAPI entry point (backend only, no frontend).

Exposes a minimal JSON API for programmatic use; all demos run via the
CLI (``python -m scripts.demo``) so no browser/frontend is required.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.database.connection import ensure_database

app = FastAPI(
    title="LangGraph Multi-Agent SQL Analyst",
    description="Multi-agent natural-language SQL data analysis backend (no frontend).",
    version="1.0.0",
)

# Ensure the database exists on startup (idempotent).
ensure_database()

app.include_router(router)
