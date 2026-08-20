"""Read-only SQL tools exposed to the SQL Agent.

Security model:
- only SELECT / WITH queries are allowed (DML/DDL blocked before execution)
- comments and quoted identifiers are stripped before keyword validation
- query results are capped to keep context small
- the DB connection itself only grants the agent read access
"""
from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import text as sql_text

from app.config import MAX_SQL_RETRIES, SENSITIVE_COLUMNS
from app.database.connection import get_engine

MAX_ROWS = 500

# Keywords that would mutate the database.
_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "REPLACE", "PRAGMA", "VACUUM",
}
# Only these top-level statements are allowed.
_ALLOWED_FIRST_KEYWORDS = {"SELECT", "WITH"}

_comment_re = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_string_re = re.compile(r"'([^']|'')*'")


def normalize_sql(query: str) -> str:
    """Strip comments, string literals and whitespace so keyword checks
    cannot be bypassed by hiding words inside comments or quotes."""
    q = _comment_re.sub(" ", query)
    q = _string_re.sub("''", q)
    return " ".join(q.split())


def validate_sql(query: str) -> str:
    """Return a cleaned, read-only-normalized SQL string or raise ValueError."""
    if not query or not query.strip():
        raise ValueError("SQL query is empty.")
    cleaned = normalize_sql(query)
    tokens = cleaned.split()
    if not tokens:
        raise ValueError("SQL query is empty after normalization.")
    first = tokens[0].upper()
    if first not in _ALLOWED_FIRST_KEYWORDS:
        raise ValueError(
            f"Only read-only SQL is allowed (SELECT/WITH), got '{first}'."
        )
    forbidden = _FORBIDDEN_KEYWORDS & set(t.upper() for t in tokens)
    if forbidden:
        raise ValueError(
            f"Forbidden SQL keyword(s): {', '.join(sorted(forbidden))}. "
            "Only read-only queries are allowed."
        )
    return cleaned


def detect_sensitive_columns(query: str) -> list[str]:
    """Return sensitive column names referenced by the query."""
    lowered = query.lower()
    hits = [c for c in SENSITIVE_COLUMNS if c and c.lower() in lowered]
    return hits


def execute_readonly_query(query: str) -> list[dict[str, Any]]:
    """Validate and execute a read-only query, returning a list of row dicts."""
    validate_sql(query)
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(sql_text(query))
        cols = list(result.keys())
        rows = [dict(zip(cols, row)) for row in result.fetchmany(MAX_ROWS)]
    return rows


@tool
def list_tables() -> str:
    """List all tables available in the sales database."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sql_text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        ).fetchall()
    names = [r[0] for r in rows]
    return "Tables: " + ", ".join(names)


@tool
def get_schema(table_name: str) -> str:
    """Get the column schema for one table, e.g. get_schema(table_name='orders')."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name or ""):
        return f"Invalid table name: {table_name!r}."
    engine = get_engine()
    with engine.connect() as conn:
        # PRAGMA does not accept bound parameters in SQLite; table_name is
        # validated against a strict identifier pattern so f-string is safe.
        rows = conn.execute(sql_text(f'PRAGMA table_info("{table_name}")')).fetchall()
    if not rows:
        return f"No table named '{table_name}'."
    cols = ", ".join(f"{r[1]} ({r[2]})" for r in rows)
    return f"Table {table_name} columns: {cols}"


@tool
def execute_sql(query: str) -> str:
    """Execute a read-only SQL query (SELECT/WITH only) and return the results
    as a compact string. DML/DDL statements are rejected."""
    try:
        rows = execute_readonly_query(query)
    except ValueError as exc:
        return f"SQL_REJECTED: {exc}"
    except Exception as exc:  # noqa: BLE001 - surfaced to the LLM for fixing
        return f"SQL_ERROR: {type(exc).__name__}: {exc}"
    if not rows:
        return "EMPTY_RESULT: the query returned no rows."
    cols = list(rows[0].keys())
    lines = [" | ".join(str(c) for c in cols)]
    for row in rows[:50]:
        lines.append(" | ".join(str(row[c]) for c in cols))
    if len(rows) > 50:
        lines.append(f"... and {len(rows) - 50} more rows")
    return "\n".join(lines)


# Registry used by the SQL Agent.
SQL_TOOLS = [list_tables, get_schema, execute_sql]
SQL_MAX_RETRIES = MAX_SQL_RETRIES
