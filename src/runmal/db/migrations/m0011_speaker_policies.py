"""0011 — speaker policy configuration + per-member settings (S211).

Groups gain their speaker-policy configuration (DATA_MODEL.md: "A Group
references member characters and a speaker-policy configuration"):
``speaker_policy`` names the policy (manual/natural/list/pooled) and
``speaker_config`` carries its JSON parameters (e.g. the list order).
Members gain the per-member knobs the policies read: ``talkativeness``
(0.0-1.0 weight for the natural policy) and ``muted`` (never selected).
"""

from __future__ import annotations

import sqlite3

REVISION = "0011"
DESCRIPTION = "group speaker policy config + member talkativeness/muted"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE groups ADD COLUMN speaker_policy TEXT NOT NULL DEFAULT 'natural';
        ALTER TABLE groups ADD COLUMN speaker_config TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE group_members ADD COLUMN talkativeness REAL NOT NULL DEFAULT 0.5;
        ALTER TABLE group_members ADD COLUMN muted INTEGER NOT NULL DEFAULT 0;
        """
    )
