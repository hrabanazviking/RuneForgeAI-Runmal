"""Migration runner (S103): apply pending migrations, record versions.

Uses raw sqlite3 so migrations never depend on the ORM layer.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from runmal.db.base import default_db_path
from runmal.db.migrations import MIGRATIONS


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def applied_revisions(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        _ensure_version_table(conn)
        rows = conn.execute("SELECT revision FROM schema_migrations ORDER BY revision").fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def current_revision(db_path: Path | None = None) -> str | None:
    path = db_path or default_db_path()
    if not path.exists():
        return None
    revisions = applied_revisions(path)
    return revisions[-1] if revisions else None


def migrate_to_head(db_path: Path | None = None) -> list[str]:
    """Apply all pending migrations in order. Returns newly applied revisions."""
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    applied: list[str] = []
    conn = sqlite3.connect(path)
    try:
        _ensure_version_table(conn)
        done = {row[0] for row in conn.execute("SELECT revision FROM schema_migrations")}
        for revision, _description, module in MIGRATIONS:
            if revision in done:
                continue
            module.upgrade(conn)  # type: ignore[attr-defined]
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (revision, _utcnow_iso()),
            )
            conn.commit()
            applied.append(revision)
    finally:
        conn.close()
    return applied
