"""0026 — lorebook inclusion groups (P-034).

Inclusion groups for lore entries: entries sharing a group label
are mutually exclusive, resolved by group weight / priority,
deterministically. Adds the ``lore_entries.inclusion_group`` and
``lore_entries.group_weight`` columns.

PROVISIONAL: REVISION "0026" is provisional — P-033 (timed
effects, building concurrently) is expected to take 0025, and if
it does not, or takes a different number, the keeper renumbers
this migration at P-034's banking (the 0024 precedent).
"""
from __future__ import annotations
import sqlite3

REVISION = "0026"
DESCRIPTION = "lore_entries inclusion_group + group_weight (inclusion groups P-034)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN inclusion_group TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN group_weight INTEGER NOT NULL DEFAULT 100"
    )
