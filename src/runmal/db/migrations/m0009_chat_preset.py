"""0009 — chats.preset_id: the sampling preset applied to a chat (S306)."""

from __future__ import annotations

import sqlite3

REVISION = "0009"
DESCRIPTION = "chats preset_id column"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE chats ADD COLUMN preset_id TEXT")
