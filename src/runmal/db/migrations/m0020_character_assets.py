"""0020 — character assets table (P-023).

Character assets hold the bytes that belong to a character beyond the
card itself: the card art, expressions, backgrounds, images embedded
in a card, and whole asset packs. Each row records provenance
(source_type/source_uri/source_ext), a storage verdict (status),
image facts sniffed from the bytes (format/media_type/width/height),
byte_size + sha256, and where the bytes live on disk
(storage_relpath/thumbnail_relpath, always relative).
"""

from __future__ import annotations

import sqlite3

REVISION = "0020"
DESCRIPTION = "character_assets table (P-023 character assets)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_assets (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'embedded',
            name TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            source_uri TEXT NOT NULL DEFAULT '',
            source_ext TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'stored',
            detail TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT '',
            width INTEGER,
            height INTEGER,
            byte_size INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            storage_relpath TEXT,
            thumbnail_relpath TEXT,
            thumbnail_status TEXT NOT NULL DEFAULT 'not_applicable',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_character_assets_character_id
            ON character_assets(character_id);
        CREATE INDEX IF NOT EXISTS idx_character_assets_user_id
            ON character_assets(user_id);
        """
    )
