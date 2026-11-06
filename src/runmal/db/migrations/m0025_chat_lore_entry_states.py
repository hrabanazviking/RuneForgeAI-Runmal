"""0025 -- per-chat lore entry timed-effect state (P-033).

Runtime sticky/cooldown/delay counters for lore entries, scoped per
chat. The canonical entry definition (lore_entries, migrations
0004/0005) holds only the timing CONFIG; the live counters live
here, modelled separately per DATA_MODEL.md. Absence of a row is
the default state. Both FKs cascade: deleting a chat or an entry
takes its runtime state with it.
"""

from __future__ import annotations

import sqlite3

REVISION = "0025"
DESCRIPTION = "chat_lore_entry_states (per-chat timed-effect runtime state, P-033)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE chat_lore_entry_states (
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            entry_id TEXT NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
            sticky_remaining INTEGER NOT NULL DEFAULT 0,
            cooldown_remaining INTEGER NOT NULL DEFAULT 0,
            delay_remaining INTEGER NOT NULL DEFAULT 0,
            delay_armed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, entry_id)
        );
        CREATE INDEX idx_chat_lore_entry_states_entry
            ON chat_lore_entry_states(entry_id);
        """
    )
