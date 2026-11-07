"""0033 — preset bundles + overrides (P-054).

Preset bundles: a bundle is one saveable/shareable unit gathering
a sampler bag, a prompt layout, instruct/context template
selections, the legacy template reference and the P-021
prompts/prompt_order carriage — stored as ONE validated canonical
JSON document in ``bundle_json`` (the bundle is an aggregate;
splitting it across columns would invite partial writes that lose
carried fields, the exact failure this slice's honesty contract
forbids). Name is unique per owner, like sampling_presets.

Preset overrides: one row assigns ONE bundle to ONE character or
chat (``scope_kind`` + ``owner_id``) with a partial delta in
``overrides_json``. The (user_id, scope_kind, owner_id) triple is unique:
a character or chat has at most one active bundle assignment;
re-assigning replaces the row. Character/chat owner integrity is
kept by the service layer (the owner id space is shared, as with
chats.preset_id and lorebook_scopes); the bundle side cascades.
"""
from __future__ import annotations
import sqlite3

REVISION = "0033"
DESCRIPTION = "preset_bundles + preset_overrides tables (preset bundles P-054)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS preset_bundles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            bundle_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_preset_bundles_user_name
            ON preset_bundles(user_id, name);
        CREATE INDEX IF NOT EXISTS idx_preset_bundles_user
            ON preset_bundles(user_id);
        CREATE TABLE IF NOT EXISTS preset_overrides (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bundle_id TEXT NOT NULL REFERENCES preset_bundles(id) ON DELETE CASCADE,
            scope_kind TEXT NOT NULL DEFAULT 'chat',
            owner_id TEXT NOT NULL DEFAULT '',
            overrides_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_preset_overrides_scope_owner
            ON preset_overrides(user_id, scope_kind, owner_id);
        CREATE INDEX IF NOT EXISTS idx_preset_overrides_user
            ON preset_overrides(user_id);
        CREATE INDEX IF NOT EXISTS idx_preset_overrides_bundle
            ON preset_overrides(bundle_id);
        """
    )
