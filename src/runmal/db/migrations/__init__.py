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
    m0008_character_soft_delete,
    m0009_chat_preset,
    m0010_groups,
    m0011_speaker_policies,
    m0012_backend_profiles,
    m0013_embedding_activation,
    m0014_memory_core,
    m0015_voice_profiles,
    m0016_bridge_credentials,
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
    (
        m0008_character_soft_delete.REVISION,
        m0008_character_soft_delete.DESCRIPTION,
        m0008_character_soft_delete,
    ),
    (
        m0009_chat_preset.REVISION,
        m0009_chat_preset.DESCRIPTION,
        m0009_chat_preset,
    ),
    (
        m0010_groups.REVISION,
        m0010_groups.DESCRIPTION,
        m0010_groups,
    ),
    (
        m0011_speaker_policies.REVISION,
        m0011_speaker_policies.DESCRIPTION,
        m0011_speaker_policies,
    ),
    (
        m0012_backend_profiles.REVISION,
        m0012_backend_profiles.DESCRIPTION,
        m0012_backend_profiles,
    ),
    (
        m0013_embedding_activation.REVISION,
        m0013_embedding_activation.DESCRIPTION,
        m0013_embedding_activation,
    ),
    (
        m0014_memory_core.REVISION,
        m0014_memory_core.DESCRIPTION,
        m0014_memory_core,
    ),
    (
        m0015_voice_profiles.REVISION,
        m0015_voice_profiles.DESCRIPTION,
        m0015_voice_profiles,
    ),
    (
        m0016_bridge_credentials.REVISION,
        m0016_bridge_credentials.DESCRIPTION,
        m0016_bridge_credentials,
    ),
]
