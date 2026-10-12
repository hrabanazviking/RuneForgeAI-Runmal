"""0002 — store the imported card JSON and avatar reference on characters."""

from __future__ import annotations

import sqlite3

REVISION = "0002"
DESCRIPTION = "character card_json + avatar_asset columns"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE characters ADD COLUMN card_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE characters ADD COLUMN avatar_asset TEXT;
        """
    )
