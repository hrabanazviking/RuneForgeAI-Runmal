"""0031 — character-book binding (P-039).

Character-book binding: a character may be bound to a lorebook --
``character_book_bindings`` records, for one character (unique),
the lorebook bound to it and the ``precedence`` that orders the
character book against other lore sources (default
``character_first``). Both sides cascade-delete with their row.

PROVISIONAL: REVISION "0031" is provisional -- P-037 is expected
to take 0029 and P-038 is expected to take 0030, and both bank
FIRST; if either takes a different number, the keeper
confirms/renumbers this migration at P-039's banking. In this
tree the sequence runs 0028 -> 0031 until P-037 and P-038 bank.
"""
from __future__ import annotations
import sqlite3

REVISION = "0031"
DESCRIPTION = "character_book_bindings table (character-book binding P-039)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_book_bindings (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL UNIQUE REFERENCES characters(id) ON DELETE CASCADE,
            lorebook_id TEXT NOT NULL REFERENCES lorebooks(id) ON DELETE CASCADE,
            precedence TEXT NOT NULL DEFAULT 'character_first',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_character_book_bindings_lorebook
            ON character_book_bindings(lorebook_id);
        """
    )
