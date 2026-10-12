"""0012 — backend modality profiles + server-side secrets store (S306).

A backend profile (BACKEND_CONTRACT §10) composes one chat backend+model,
one embedding backend+model, and STT/TTS references. Secret VALUES never
live on the profile row: the profile stores only opaque secret references
(``chat_secret_ref`` / ``embedding_secret_ref``) and the values live in the
server-side ``secrets`` table, resolvable only by server code.

``chats.backend_profile_id`` lets a chat pin its selected profile (wired by
S307); nullable, so existing chats keep working unpinned.
"""

from __future__ import annotations

import sqlite3

REVISION = "0012"
DESCRIPTION = "backend_profiles + secrets tables; chats.backend_profile_id"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE backend_profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            chat_backend TEXT NOT NULL DEFAULT 'fake',
            chat_model TEXT NOT NULL DEFAULT '',
            embedding_backend TEXT NOT NULL DEFAULT '',
            embedding_model TEXT NOT NULL DEFAULT '',
            stt_ref TEXT NOT NULL DEFAULT '',
            tts_ref TEXT NOT NULL DEFAULT '',
            chat_secret_ref TEXT NOT NULL DEFAULT '',
            embedding_secret_ref TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX idx_backend_profiles_user ON backend_profiles(user_id);
        CREATE UNIQUE INDEX idx_backend_profiles_user_name
            ON backend_profiles(user_id, name);

        CREATE TABLE secrets (
            ref TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_secrets_user ON secrets(user_id);

        ALTER TABLE chats ADD COLUMN backend_profile_id TEXT;
        """
    )
