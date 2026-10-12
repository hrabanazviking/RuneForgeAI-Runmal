"""0007 — connection_profiles table (S211).

Named backend connections (backend kind, base URL, model) with a single
active profile per user. Secrets are never stored in profiles.
"""

from __future__ import annotations

import sqlite3

REVISION = "0007"
DESCRIPTION = "connection_profiles table"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE connection_profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            backend TEXT NOT NULL DEFAULT 'fake',
            base_url TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX idx_connections_user ON connection_profiles(user_id);
        CREATE UNIQUE INDEX idx_connections_user_name
            ON connection_profiles(user_id, name);
        """
    )
