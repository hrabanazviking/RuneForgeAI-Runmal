"""PROVISIONAL 0034 -- chats.authors_note_json (author's note depth, P-056).

PROVISIONAL 0034: this number is PROVISIONAL. P-055 banks in
parallel with its own migration claim, and the keeper reconciles
numbering at banking -- if P-055 takes 0034 first, this module is
renumbered (revision, filename, and registration) by the keeper
before either slice lands. Do not treat "0034" here as final.

The author's note itself is ONE validated canonical JSON document
(the aggregate built by ``runmal.prompt.authors_note``: text, depth,
frequency, enabled, role), so it is stored as ONE column --
splitting it across columns would invite partial writes that lose
carried fields. ``{}`` is the no-note default: an absent note and an
empty note are the same thing.
"""

from __future__ import annotations

import sqlite3

REVISION = "0034"
DESCRIPTION = "chats.authors_note_json (author's note depth P-056) PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "authors_note_json" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN authors_note_json "
            "TEXT NOT NULL DEFAULT '{}'"
        )
