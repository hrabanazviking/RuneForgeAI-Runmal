"""PROVISIONAL 0038 -- message actions: variant history, pin, position (P-068).

PROVISIONAL 0038: this number is PROVISIONAL. 0037 belongs to
P-066 (branches, banked after this slice's base) and 0038 is
reserved for P-067 (checkpoints). The keeper reconciles numbering
at banking -- if reconciliation renumbers, this module is
renumbered (revision, filename, and registration) by the keeper
before this slice lands. Do not treat "0038" here as final.

Storage proof (why a migration is unavoidable): at base the
messages table holds only content + the P-065 swipe deck. There
is no column for an edit's replaced text (variant history), no
per-message pin flag, and no explicit order -- history order is
created_at alone, so a move could only be faked by rewriting
timestamps. All three are per-message durable state, so they
are stored per message:

- ``messages.variant_history_json`` TEXT NOT NULL DEFAULT '[]'
  -- ONE JSON document: replaced contents in edit order (see
  runmal.chats.actions). '[]' = never edited.
- ``messages.pinned`` INTEGER NOT NULL DEFAULT 0 -- the pin flag.
  The pin's memory record lives in the memories table (a real
  Memory row + MemorySource link, created by the service); this
  flag is the per-message display/state bit kept in step by the
  pin/unpin/delete service functions.
- ``messages.position`` INTEGER (nullable) -- explicit order
  inside the chat once materialised. NULL = legacy row: order
  by created_at (the pre-P-068 rule). The first move/delete in
  a chat materialises positions 0..n-1 for the whole chat.
"""

from __future__ import annotations

import sqlite3

REVISION = "0038"
DESCRIPTION = "message actions: variant history, pin, position P-068 PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "variant_history_json" not in columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN variant_history_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )
    if "pinned" not in columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN pinned "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "position" not in columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN position INTEGER"
        )
