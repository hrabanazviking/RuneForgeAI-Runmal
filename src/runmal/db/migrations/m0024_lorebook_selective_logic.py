"""0024 — lorebook selective logic (P-032).

Selective logic for lore entries: how an entry's secondary keys
combine when deciding activation. Adds the
``lore_entries.selective_logic`` column.

PROVISIONAL: REVISION "0024" is provisional — the keeper may
renumber at banking if P-031 takes 0024 first.
"""
from __future__ import annotations
import sqlite3

REVISION = "0024"
DESCRIPTION = "lore_entries selective_logic (selective logic P-032)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN selective_logic TEXT NOT NULL DEFAULT 'and_any'"
    )
