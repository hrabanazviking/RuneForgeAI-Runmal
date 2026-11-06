"""0019 — preset interop carriage (P-021).

Sampling presets gain the import/export interop carriage:
``source_format`` records where a preset came from ('native',
'st-text' or 'st-chat'; hand-made presets stay 'native') and
``interop_json`` stores the lossless original as
``{"raw": <complete original object>, "prompts": [...],
"prompt_order": [...]}`` so an imported file can be re-exported
without losing the parts Rúnmál does not model natively.
"""

from __future__ import annotations

import sqlite3

REVISION = "0019"
DESCRIPTION = "sampling_presets source_format + interop_json columns"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE sampling_presets ADD COLUMN source_format TEXT NOT NULL DEFAULT 'native';
        ALTER TABLE sampling_presets ADD COLUMN interop_json TEXT NOT NULL DEFAULT '{}';
        """
    )
