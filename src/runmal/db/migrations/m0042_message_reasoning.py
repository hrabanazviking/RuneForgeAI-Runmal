"""PROVISIONAL 0042 -- message-level reasoning record (P-205).

PROVISIONAL 0042: this number is PROVISIONAL. It is taken by
P-205 (Part XIII reasoning record, team-01) on the P-204 base
(head 0041); P-204 took NO migration, so 0042 is free at
muster, but the keeper composes final numbering at banking.
Do not treat "0042" here as final until the keeper confirms.

Storage proof (why a migration is unavoidable): a message's
reasoning is durable per-message, per-swipe state -- alternates
of one message are produced by different generations and think
differently, exactly the grain argument m0040 proved for
provenance. It has nowhere to live: provenance_json is barred
by its own founding law (a provenance record never records
CONTENT; reasoning text IS content); swipes_json is barred by
the deck invariant (content == swipes[swipe_id]; the deck
holds answer texts only); variant_history_json holds replaced
ANSWER contents, a different fact; the S107 chat_events log is
a mutation journal, not message state, and strands on branch
copies; the chat row holds current mutable configuration, not
per-message snapshots; stream-only storage dies with the SSE
connection while the Assistant View judges history. So,
mirroring m0040 exactly:

- ``messages.reasoning_json`` TEXT NOT NULL DEFAULT '{}' --
  ONE JSON reasoning document per message
  (runmal.chats.reasoning): per-swipe reasoning records
  recorded at production time from what the producing road
  actually captured. '{}' = legacy, never recorded; readers
  surface it as an explicit not_recorded document, never as
  invented thinking.
"""

from __future__ import annotations

import sqlite3

REVISION = "0042"
DESCRIPTION = "message reasoning_json (P-205) PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "reasoning_json" not in columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN "
            "reasoning_json TEXT NOT NULL DEFAULT '{}'"
        )
