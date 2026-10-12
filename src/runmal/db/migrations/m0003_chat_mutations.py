"""0003 — message mutation timestamps + durable mutation event log."""

from __future__ import annotations

import sqlite3

REVISION = "0003"
DESCRIPTION = "message updated_at + chat_events table"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE messages ADD COLUMN updated_at TEXT;
        CREATE TABLE chat_events (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            message_id TEXT,
            kind TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_chat_events_chat ON chat_events(chat_id);
        """
    )
