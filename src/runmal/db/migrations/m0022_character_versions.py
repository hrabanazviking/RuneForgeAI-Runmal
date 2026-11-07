"""0022 — character versioning (P-025).

Duplicate & version handling for characters: ``version_no`` numbers
successive versions within a lineage, ``lineage_id`` groups the
versions of one character together, and ``content_hash`` records a
hash of the character's content so duplicates and unchanged copies
can be recognised.
"""

from __future__ import annotations

import sqlite3

REVISION = "0022"
DESCRIPTION = "characters version_no + lineage_id + content_hash (duplicate & version handling)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE characters ADD COLUMN version_no INTEGER NOT NULL DEFAULT 1"
    )
    conn.execute("ALTER TABLE characters ADD COLUMN lineage_id TEXT")
    conn.execute(
        "ALTER TABLE characters ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_characters_user_lineage "
        "ON characters (user_id, lineage_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_characters_user_name "
        "ON characters (user_id, name)"
    )
