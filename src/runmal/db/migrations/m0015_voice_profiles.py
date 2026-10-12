"""0015 — per-character voice profiles (Campaign V, S512).

A character's voice is a REFERENCE (TTS backend + voice + params), never
a hard-coded engine (VOICE_ARCHITECTURE §8). Stored apart from backend
profiles on purpose: switching a persona's voice must not touch the
chat/embedding composition (BACKEND_CONTRACT §1, S512 acceptance).
"""

from __future__ import annotations

import sqlite3

REVISION = "0015"
DESCRIPTION = "character_voice_profiles table (per-character TTS references)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE character_voice_profiles (
            character_id TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tts_backend TEXT NOT NULL DEFAULT '',
            voice_id TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'en-us',
            params_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_voice_profiles_user ON character_voice_profiles(user_id);
        """
    )
