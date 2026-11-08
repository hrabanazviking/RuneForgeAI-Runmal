"""PROVISIONAL 0040 -- message-level provenance (P-075).

PROVISIONAL 0040: this number is PROVISIONAL. P-074 (data bank,
team-03) banks before this slice and may take a migration of
its own; the keeper composes final numbering at banking. Do
not treat "0040" here as final until the keeper confirms.

Storage proof (why a migration is unavoidable): a message's
production record is durable per-message state. It cannot ride
the chat row -- chats.preset_id / chats.backend_profile_id are
the chat's CURRENT, mutable configuration, not a per-message
snapshot. It cannot ride variant_history_json (edit history
only), swipes_json (the deck's texts only), or the ChatEvent
log (a mutation journal, not message state: several roads
construct Message rows directly -- groupchat store, branch
copies -- and a copied message's events live in the SOURCE
chat). So, mirroring characters.provenance_json (0023) and
chats.metadata_json (0039):

- ``messages.provenance_json`` TEXT NOT NULL DEFAULT '{}' --
  ONE JSON provenance document per message
  (runmal.chats.provenance): per-swipe production records
  (origin / model / preset / lore / generation) recorded at
  production time from what the producing road actually knew.
  '{}' = legacy, never recorded; readers surface it as an
  explicit unknown document, never as invented facts.
"""

from __future__ import annotations

import sqlite3

REVISION = "0040"
DESCRIPTION = "message provenance_json (P-075) PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "provenance_json" not in columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN "
            "provenance_json TEXT NOT NULL DEFAULT '{}'"
        )
