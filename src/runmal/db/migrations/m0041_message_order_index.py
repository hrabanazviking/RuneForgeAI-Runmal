"""PROVISIONAL 0041 -- composite message order index (P-077).

PROVISIONAL 0041: this number is PROVISIONAL. It is taken by
P-077 (long-chat performance, team-03) on the P-075 base
(head 0040); P-076 banked ahead of this slice took NO
migration, so 0041 is free at muster, but the keeper composes
final numbering at banking -- if reconciliation renumbers,
this module is renumbered (revision, filename, and
registration) by the keeper before this slice lands. Do not
treat "0041" here as final.

Storage proof (why a migration is unavoidable): P-077's
append fast path verifies, on every append, that a chat's
materialised positions are exactly dense 0..N-1 (count /
count(position) / min / max / count-distinct over the chat's
messages). Without an index covering position, that
aggregate -- and the paged history road's ORDER BY -- run
over ix_messages_chat_id (chat_id only): every row's position
is fetched by a full table-row lookup scattered across the
whole messages table, and SQLite plans show TEMP B-TREE for
both count(DISTINCT) and the paged ORDER BY (measured on the
P-077 bench corpus, 10k messages: aggregate ~14 ms of the
16.76 ms append, append-at-10k / append-at-1k = 4.03 against
the BUDGET-P077 ratio gate of 2.0; the absolute append gate
of 200 ms passes either way). No code-only formulation
avoids the per-row lookups: any exact density proof must at
least stream the positions, and only a covering index makes
that stream index-only and ordered. The design named this
exact candidate (chat_id, position, created_at, id) for
this exact EXPLAIN trigger. With the index the aggregate is
a covering-index stream (~3 ms at 10k) and the density proof
stays exact -- no probabilistic shortcut is taken.

- ``ix_messages_chat_position`` ON messages
  (chat_id, position, created_at, id) -- the display-order
  index: serves the append density aggregate, the paged
  history road, and _ordered_messages' ORDER BY.
"""

from __future__ import annotations

import sqlite3

REVISION = "0041"
DESCRIPTION = "composite message order index (chat_id, position, created_at, id) (P-077) PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(messages)")}
    if "ix_messages_chat_position" not in indexes:
        conn.execute(
            "CREATE INDEX ix_messages_chat_position "
            "ON messages(chat_id, position, created_at, id)"
        )
