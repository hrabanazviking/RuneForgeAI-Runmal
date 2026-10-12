"""0005 — lore entry activation timing config (S203).

Adds sticky_prompts / cooldown_prompts / delay_prompts to lore_entries.
These are *configuration* (how many prompts), not runtime counters: the
counters themselves stay out of the canonical entry definition per
DATA_MODEL.md and live in the activation engine's explicit state mapping.
"""

from __future__ import annotations

import sqlite3

REVISION = "0005"
DESCRIPTION = "lore entry activation timing config"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE lore_entries ADD COLUMN sticky_prompts INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE lore_entries ADD COLUMN cooldown_prompts INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE lore_entries ADD COLUMN delay_prompts INTEGER NOT NULL DEFAULT 0;
        """
    )
