"""0006 — sampling_presets table (S207).

Named canonical parameter bags + prompt-template reference, owned per user.
"""

from __future__ import annotations

import sqlite3

REVISION = "0006"
DESCRIPTION = "sampling_presets table"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sampling_presets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}',
            template_ref TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX idx_presets_user ON sampling_presets(user_id);
        CREATE UNIQUE INDEX idx_presets_user_name ON sampling_presets(user_id, name);
        """
    )
