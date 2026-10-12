"""0004 — lorebooks + lore_entries tables (S201).

Lorebook owns book-level scanning/budget/default settings; lore entries hold
activation metadata (keys, priority, position), content, enabled state and
provenance. Runtime activation counters (sticky/cooldown) are deliberately
NOT columns here -- DATA_MODEL.md models them separately (S203).
"""

from __future__ import annotations

import sqlite3

REVISION = "0004"
DESCRIPTION = "lorebooks + lore_entries tables"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE lorebooks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            scan_depth INTEGER NOT NULL DEFAULT 4,
            token_budget INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_lorebooks_user ON lorebooks(user_id);
        CREATE TABLE lore_entries (
            id TEXT PRIMARY KEY,
            lorebook_id TEXT NOT NULL REFERENCES lorebooks(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            keys_json TEXT NOT NULL DEFAULT '[]',
            secondary_keys_json TEXT NOT NULL DEFAULT '[]',
            priority INTEGER NOT NULL DEFAULT 100,
            position TEXT NOT NULL DEFAULT 'before_char',
            enabled INTEGER NOT NULL DEFAULT 1,
            constant INTEGER NOT NULL DEFAULT 0,
            case_sensitive INTEGER NOT NULL DEFAULT 0,
            whole_word INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX idx_lore_entries_book ON lore_entries(lorebook_id);
        CREATE INDEX idx_lore_entries_user ON lore_entries(user_id);
        """
    )
