"""0027 — lorebook entry states (P-035).

Entry states for lore entries: every entry has exactly one
activation kind, derived from its flags (constant, else
vectorised, else selective). Adds the ``lore_entries.vectorised``
column; the kind itself is derived (``runmal.lorebooks.states``),
never stored.

PROVISIONAL: REVISION "0027" is provisional — P-036 builds
concurrently from the same base with a provisional later number;
the keeper reconciles this migration at P-035's banking.
"""
from __future__ import annotations
import sqlite3

REVISION = "0027"
DESCRIPTION = "lore_entries vectorised (entry states P-035)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN vectorised INTEGER NOT NULL DEFAULT 0"
    )
