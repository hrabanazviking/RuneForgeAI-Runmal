"""0043 — the owner's default chat backend profile (W-12).

A chat answers through the backend profile pinned to it; until now
a chat with no pin had NO house-level fallback — generation fell
through to the offline fake default, and the webface (FIX-STUB)
had to refuse the turn because no mind was connected. The missing
piece was a place for "the profile this house uses when a chat
does not name its own" to live as DATA.

``default_chat_profile`` records, per owner, that one profile id —
the same one-row-per-owner shape as ``embedding_activation``
(m0013, S311), whose axis law this mirrors: setting or clearing
the default touches no chat row and no profile row. Generation
resolution becomes: the request's profile, else the chat's pin,
else this default, else the offline fake (which the surfaces
label, and which a deliberate fake-kind DEFAULT still reaches
honestly, as a chosen Demo).

The profile id is a plain id, integrity kept by the service
(runmal.backends.default_profile): a dangling id (the profile was
deleted) reads as "no default set", never as an error.
"""

from __future__ import annotations

import sqlite3

REVISION = "0043"
DESCRIPTION = "default_chat_profile (owner's default chat backend profile)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS default_chat_profile (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            profile_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )
