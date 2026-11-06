"""0028 — lorebook entry probability (P-036).

Probability & RNG honesty: a lore entry's probabilistic gate
becomes stored data -- ``lore_entries.probability``, an integer
percent in 0..100 (the public world-info shape), default 100
(gate off: the entry always passes, no roll is made). The
seeded, inspectable roll itself lives in
``runmal.lorebooks.rng`` (pure, no schema).

PROVISIONAL: REVISION "0028" is provisional -- P-035 (entry
states, building concurrently from the same base) is expected
to take 0027 and banks FIRST; if it takes a different number,
the keeper renumbers this migration at P-036's banking (the
0026 precedent). In this tree the sequence runs 0026 -> 0028
until P-035 banks.
"""
from __future__ import annotations
import sqlite3

REVISION = "0028"
DESCRIPTION = "lore_entries probability percent (probability & RNG honesty P-036)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE lore_entries ADD COLUMN probability INTEGER NOT NULL DEFAULT 100"
    )
