"""PROVISIONAL 0039 -- chat metadata: summary, provenance, tags,
favourites (P-073).

PROVISIONAL 0039: this number is PROVISIONAL. P-072 (chat search,
team-01) takes no migration per its design, so 0039 is expected
to stand; the keeper composes final numbering at banking. Do not
treat "0039" here as final until the keeper confirms.

Storage proof (why a migration is unavoidable): at base a chat
holds a title and nothing else metadata-shaped. Tags must be
filterable and countable across chats at library scale, which a
JSON blob cannot do (the P-024 character-library lesson); a
summary is durable per-chat text; a favourite is durable
per-chat state. So:

- ``chats.summary`` TEXT NOT NULL DEFAULT '' -- the chat summary
  ('' = no summary yet). Editable; may be auto-generated.
- ``chats.metadata_json`` TEXT NOT NULL DEFAULT '{}' -- ONE JSON
  provenance document (runmal.chats.metadata): per-field source
  (manual|auto|unset), generator id, generation timestamp and
  the message count generation read. '{}' = never touched.
- ``chat_tags`` -- normalised tag rows mirroring character_tags
  (P-024): display ``tag`` + casefolded ``tag_key`` lookup form,
  PRIMARY KEY (chat_id, tag_key), cascade-delete with the chat.
- ``chat_organisation`` -- favourite flag per chat, mirroring
  character_organisation: PRIMARY KEY chat_id, cascade-delete.
"""

from __future__ import annotations

import sqlite3

REVISION = "0039"
DESCRIPTION = (
    "chat metadata: summary + provenance, chat_tags, "
    "chat_organisation (P-073) PROVISIONAL"
)


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "summary" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN summary TEXT NOT NULL DEFAULT ''"
        )
    if "metadata_json" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN metadata_json "
            "TEXT NOT NULL DEFAULT '{}'"
        )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_organisation (
            chat_id TEXT PRIMARY KEY
                REFERENCES chats(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            is_favourite INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_tags (
            chat_id TEXT NOT NULL
                REFERENCES chats(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            PRIMARY KEY (chat_id, tag_key)
        );
        CREATE INDEX IF NOT EXISTS ix_chat_tags_user_tag
            ON chat_tags (user_id, tag_key);
        CREATE INDEX IF NOT EXISTS ix_chat_tags_chat
            ON chat_tags (chat_id);
        CREATE INDEX IF NOT EXISTS ix_chat_organisation_user_fav
            ON chat_organisation (user_id, is_favourite);
        """
    )
