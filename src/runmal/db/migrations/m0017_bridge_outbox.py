"""0017 — durable bridge event outbox (Campaign VI, S609).

BRIDGE_PROTOCOL §5: bridges that may initiate/receive proactive
companion speech need more than request/response — a durable,
pollable event stream per chat with monotonically ordered ids,
per-credential checkpoints (ack), replay after disconnect, and
bounded retention. Events are integers under AUTOINCREMENT so ids
are strictly monotonic per database; a stream is one chat's rows.
"""

from __future__ import annotations

import sqlite3

REVISION = "0017"
DESCRIPTION = "bridge_events outbox + bridge_checkpoints (per-credential ack)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE bridge_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_bridge_events_chat ON bridge_events(chat_id, id);
        CREATE TABLE bridge_checkpoints (
            credential_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            last_event_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (credential_id, chat_id)
        );
        """
    )
