"""PROVISIONAL 0036 -- message swipes + chat swipe settings (P-065).

PROVISIONAL 0036: this number is PROVISIONAL. The keeper
reconciles numbering at banking -- if reconciliation renumbers,
this module is renumbered (revision, filename, and registration)
by the keeper before this slice lands. Do not treat "0036" here
as final.

A message's swipe deck is the ordered list of alternate contents
for that one message; ``messages.content`` always mirrors the
active alternate (``content == swipes[swipe_id]``). The deck is
stored as ONE JSON column (``messages.swipes_json``) beside the
active index (``messages.swipe_id``) -- ``[]`` is the legacy /
no-deck default: a message that was never swiped reads its deck
as ``[content]``. Per-chat swipe behaviour (whether regeneration
on swipe is enabled, and with which parameter overrides) is ONE
validated JSON document in ``chats.swipe_settings_json``; ``{}``
is the no-settings default. See ``runmal.chats.swipes`` for the
pure deck contract.
"""

from __future__ import annotations

import sqlite3

REVISION = "0036"
DESCRIPTION = "message swipes + chat swipe settings P-065 PROVISIONAL"


def upgrade(conn: sqlite3.Connection) -> None:
    message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "swipes_json" not in message_columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN swipes_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )
    if "swipe_id" not in message_columns:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN swipe_id "
            "INTEGER NOT NULL DEFAULT 0"
        )
    chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "swipe_settings_json" not in chat_columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN swipe_settings_json "
            "TEXT NOT NULL DEFAULT '{}'"
        )
