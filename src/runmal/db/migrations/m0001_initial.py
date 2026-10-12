"""0001 — initial schema: users, characters, chats, messages + ownership."""

from __future__ import annotations

import sqlite3

REVISION = "0001"
DESCRIPTION = "initial schema: users, characters, chats, messages"

_DDL = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE chats (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    character_id TEXT REFERENCES characters(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX ix_characters_user_id ON characters(user_id);
CREATE INDEX ix_chats_user_id ON chats(user_id);
CREATE INDEX ix_messages_chat_id ON messages(chat_id);
"""


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
