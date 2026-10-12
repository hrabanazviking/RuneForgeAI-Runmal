"""0008 — characters.deleted_at for soft delete / undo (S303).

Deletion becomes recoverable: the row is stamped, hidden from lists, and
can be restored. A recoverable copy is always retained (backup policy).
"""

from __future__ import annotations

import sqlite3

REVISION = "0008"
DESCRIPTION = "characters soft-delete column"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE characters ADD COLUMN deleted_at TEXT")
