"""SQLAlchemy connection management for the sales database."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import DB_PATH, DB_URL

_engine: Engine | None = None


def get_engine() -> Engine:
    """Create (and cache) the SQLAlchemy engine for the configured DB."""
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, pool_pre_ping=True)
    return _engine


def dispose_engine() -> None:
    """Release all pooled connections (required before deleting the DB file
    on Windows, where open connections lock the file)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _split_statements(sql: str) -> list[str]:
    """Split a schema script into individual statements (best-effort).

    Handles semicolon separators while ignoring semicolons inside string
    literals and line comments.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_str = False
    in_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_comment:
            if ch == "\n":
                in_comment = False
                buf.append(ch)
            i += 1
            continue
        if in_str:
            buf.append(ch)
            if ch == "'" and nxt == "'":
                buf.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_str = False
            i += 1
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == "-" and nxt == "-":
            in_comment = True
            buf.append(ch)
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def init_database(drop_existing: bool = False) -> Path:
    """Create the database file, applying ``schema.sql``."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if drop_existing and DB_PATH.exists():
        dispose_engine()  # release Windows file locks before deleting
        DB_PATH.unlink()
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    engine = get_engine()
    for stmt in _split_statements(schema_sql):
        with engine.begin() as conn:
            conn.execute(text(stmt))
    return DB_PATH


def table_exists(engine: Engine, name: str) -> bool:
    """Return True if ``name`` exists in the database."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": name},
        ).fetchone()
    return row is not None


def is_seeded(engine: Engine) -> bool:
    """Return True when the orders table exists and contains rows."""
    if not table_exists(engine, "orders"):
        return False
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()
    return bool(count and count > 0)


def ensure_database() -> Engine:
    """Initialise the DB if missing, then return the engine."""
    if not DB_PATH.exists() or not is_seeded(get_engine()):
        from app.database.seed import seed_database

        seed_database(regenerate=True)
    return get_engine()
