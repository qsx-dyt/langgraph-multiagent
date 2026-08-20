"""Central configuration for the Multi-Agent SQL Analyst project."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root: parent of the ``app`` package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DB_PATH = Path(os.getenv("DB_PATH", ROOT_DIR / "data" / "sales.db"))
# SQLAlchemy URL; SQLite absolute paths need four leading slashes.
DB_URL = os.getenv("DB_URL", f"sqlite:///{DB_PATH.as_posix()}")

# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------
# Provider is one of "openai" (OpenAI-compatible), "fake", "mock".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)  # e.g. DeepSeek/Qwen endpoints

# --------------------------------------------------------------------------
# Workflow behaviour
# --------------------------------------------------------------------------
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))
MAX_REVIEW_RETRIES = int(os.getenv("MAX_REVIEW_RETRIES", "2"))
# Column names considered sensitive; queries touching them trigger HITL.
SENSITIVE_COLUMNS = tuple(
    os.getenv("SENSITIVE_COLUMNS", "customer_phone,customer_email,email,phone,salary,address")
    .replace(" ", "")
    .split(",")
)

# --------------------------------------------------------------------------
# Chart output
# --------------------------------------------------------------------------
CHARTS_DIR = ROOT_DIR / "charts"
CHART_STATIC_URL = "/charts"
# Web-safe filename length of the underlying Chinese fonts if available.
CHART_FONT = os.getenv("CHART_FONT", "")

# --------------------------------------------------------------------------
# LangSmith / tracing
# --------------------------------------------------------------------------
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "multi-agent-sql-analyst")
