"""0020 — library organisation (P-024).

Per-user library organisation for characters: ``character_organisation``
holds the favourite flag (and last-change time) for one character,
and ``character_tags`` holds that user's tags for a character, with
``tag_key`` as the normalised lookup form of the display ``tag``.
Both tables cascade-delete with their character.
"""

from __future__ import annotations

import sqlite3

REVISION = "0020"
DESCRIPTION = "character_organisation + character_tags tables (library favourites + tags)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_organisation (
            character_id TEXT PRIMARY KEY
                REFERENCES characters(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            is_favourite INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS character_tags (
            character_id TEXT NOT NULL
                REFERENCES characters(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            PRIMARY KEY (character_id, tag_key)
        );
        CREATE INDEX IF NOT EXISTS ix_character_tags_user_tag
            ON character_tags (user_id, tag_key);
        CREATE INDEX IF NOT EXISTS ix_character_tags_character
            ON character_tags (character_id);
        CREATE INDEX IF NOT EXISTS ix_character_organisation_user_fav
            ON character_organisation (user_id, is_favourite);
        """
    )
