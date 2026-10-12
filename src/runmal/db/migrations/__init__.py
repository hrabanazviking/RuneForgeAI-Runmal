"""Versioned migrations, oldest first. Each module exposes:

REVISION: str — zero-padded ordering key, e.g. "0001"
DESCRIPTION: str — human summary
upgrade(conn) — apply DDL on a raw sqlite3 connection (committed by runner)
"""

from __future__ import annotations

from runmal.db.migrations import (
    m0001_initial,
    m0002_character_card_columns,
    m0003_chat_mutations,
    m0004_lorebooks,
    m0005_lore_activation,
    m0006_presets,
    m0007_connections,
)

MIGRATIONS: list[tuple[str, str, object]] = [
    (m0001_initial.REVISION, m0001_initial.DESCRIPTION, m0001_initial),
    (
        m0002_character_card_columns.REVISION,
        m0002_character_card_columns.DESCRIPTION,
        m0002_character_card_columns,
    ),
    (
        m0003_chat_mutations.REVISION,
        m0003_chat_mutations.DESCRIPTION,
        m0003_chat_mutations,
    ),
    (
        m0004_lorebooks.REVISION,
        m0004_lorebooks.DESCRIPTION,
        m0004_lorebooks,
    ),
    (
        m0005_lore_activation.REVISION,
        m0005_lore_activation.DESCRIPTION,
        m0005_lore_activation,
    ),
    (
        m0006_presets.REVISION,
        m0006_presets.DESCRIPTION,
        m0006_presets,
    ),
    (
        m0007_connections.REVISION,
        m0007_connections.DESCRIPTION,
        m0007_connections,
    ),
]
