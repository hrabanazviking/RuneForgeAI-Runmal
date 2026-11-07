"""0023 — character provenance (P-029).

Provenance on import: where a card came from and when, kept with
the character (creator credit survives in Runmal). Adds the
``provenance_json`` column holding the provenance record built by
runmal.characters.provenance.

PROVISIONAL: REVISION "0023" is provisional — the keeper may
renumber this migration at banking if P-028 takes 0023.
"""

from __future__ import annotations

import sqlite3

REVISION = "0023"
DESCRIPTION = "characters provenance_json (provenance on import)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE characters ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'"
    )
