"""0030 -- lorebook entry placement (P-038).

Position & depth control: adds the at-depth companions to
``lore_entries`` -- a nullable ``depth`` (the S206 splice count;
NULL = undeclared, the placement default applies at compose
time) and a ``role`` naming the chat role an at_depth entry is
injected as, defaulting to 'system' for every existing row.
Existing rows read back depth NULL / role 'system' -- exactly
their old behaviour (no at_depth entry could be stored before
this slice; gate finding F1).

PROVISIONAL: REVISION "0030" is provisional -- P-037 (scan
depth & context windows, building concurrently from the same
base) is expected to take 0029 and banks FIRST; if it takes a
different number, the keeper renumbers this migration at
P-038's banking (the 0026/0028 precedent). In this tree the
sequence runs 0028 -> 0030 until P-037 banks.
"""
from __future__ import annotations

import sqlite3

REVISION = "0030"
DESCRIPTION = "lore_entries depth & role (position & depth control P-038)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE lore_entries ADD COLUMN depth INTEGER")
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN role TEXT NOT NULL DEFAULT 'system'"
    )
