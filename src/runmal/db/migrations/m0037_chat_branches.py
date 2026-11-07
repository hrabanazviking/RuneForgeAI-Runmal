"""PROVISIONAL 0037 -- chat branches (branches, P-066).

PROVISIONAL 0037: this number is PROVISIONAL. 0036 is RESERVED
for P-065 (swipes deepened, team-03), which banks BEFORE this
slice, and the keeper reconciles numbering at banking -- if
reconciliation renumbers, this module is renumbered (revision,
filename, and registration) by the keeper before this slice
lands. Do not treat "0037" here as final.

A branch is a chat in its own right (its own row, its own copied
messages), so its lineage is stored on the chat row itself:

- ``branch_parent_id``: the chat this one forked from (or, for a
  merge branch, the merge target). A PLAIN id, deliberately no
  foreign key: deleting a parent must never cascade into a
  branch -- branching is never destructive (P-066 law).
- ``branch_fork_message_id``: the message id IN THE PARENT at
  which the fork was taken (the last message copied), or NULL
  for a whole-chat fork / a root chat.
- ``branch_fork_index``: how many messages were copied from the
  parent (the prefix length). Merge-back uses it to find the
  branch's divergent suffix.
- ``branch_kind``: 'root' (an ordinary chat), 'fork', or 'merge'.
- ``branch_merge_of_json``: for merge branches, the JSON list of
  source chat ids that were merged; '[]' otherwise.
"""

from __future__ import annotations

import sqlite3

REVISION = "0037"
DESCRIPTION = "chat branches (branches P-066) PROVISIONAL"

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("branch_parent_id", "TEXT"),
    ("branch_fork_message_id", "TEXT"),
    ("branch_fork_index", "INTEGER"),
    ("branch_kind", "TEXT NOT NULL DEFAULT 'root'"),
    ("branch_merge_of_json", "TEXT NOT NULL DEFAULT '[]'"),
)


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    for name, ddl in _COLUMNS:
        if name not in columns:
            conn.execute(f"ALTER TABLE chats ADD COLUMN {name} {ddl}")
