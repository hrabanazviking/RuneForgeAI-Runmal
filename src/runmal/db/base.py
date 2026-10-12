"""Engine/session construction with the Rúnmál SQLite policy (S103).

Policy: foreign_keys=ON, journal_mode=WAL, busy_timeout=5000ms,
synchronous=NORMAL. Enforced on every connection via event listener.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from runmal.auth import data_dir

BUSY_TIMEOUT_MS = 5000


def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def default_db_path() -> Path:
    return data_dir() / "runmal.db"


def create_db_engine(db_path: Path | None = None) -> AsyncEngine:
    path = db_path or default_db_path()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
