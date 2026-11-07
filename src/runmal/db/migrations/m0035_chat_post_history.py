"""PROVISIONAL 0035 -- chats.post_history_json (post-history instructions, P-057).

PROVISIONAL 0035: this number is PROVISIONAL. P-056 holds
provisional 0034 (chats.authors_note_json) and banks BEFORE this
slice, and the keeper reconciles numbering at banking -- if
reconciliation renumbers, this module is renumbered (revision,
filename, and registration) by the keeper before this slice lands.
Do not treat "0035" here as final.

The post-history instructions themselves are ONE validated
canonical JSON document (the aggregate built by
``runmal.prompt.post_history``: text, enabled, role), so they are
stored as ONE column -- splitting them across columns would invite
partial writes that lose carried fields. ``{}`` is the
no-instructions default: absent instructions and empty instructions
are the same thing.
"""

from __future__ import annotations

import sqlite3

REVISION = "0035"
DESCRIPTION = "chats.post_history_json (post-history instructions P-057) PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "post_history_json" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN post_history_json "
            "TEXT NOT NULL DEFAULT '{}'"
        )
