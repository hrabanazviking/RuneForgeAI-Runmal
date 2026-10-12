"""0010 — groups + group_members, chats.group_id, message speakers (S210).

Roadmap S210 gives group chats a durable data shape: a Group (the room)
references member characters in roster order; the room's transcript is an
ordinary chat row whose ``group_id`` points back at the group. Messages
gain explicit per-message speaker identity (``speaker_id`` = character id,
``speaker_name`` = display-name snapshot) so membership changes never
rewrite who historically said what (DATA_MODEL.md, "Groups").
"""

from __future__ import annotations

import sqlite3

REVISION = "0010"
DESCRIPTION = "groups, group_members, chat group link, message speaker identity"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE groups (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_groups_user ON groups(user_id);
        CREATE TABLE group_members (
            group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (group_id, character_id)
        );
        CREATE INDEX idx_group_members_group ON group_members(group_id);
        ALTER TABLE chats ADD COLUMN group_id TEXT REFERENCES groups(id) ON DELETE CASCADE;
        ALTER TABLE messages ADD COLUMN speaker_id TEXT;
        ALTER TABLE messages ADD COLUMN speaker_name TEXT;
        """
    )
