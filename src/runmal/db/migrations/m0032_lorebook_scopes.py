"""0032 — lorebook scopes (P-040).

Lore scopes: a lorebook may be assigned to a layer of a chat's
world -- ``lorebook_scopes`` records, for one lorebook, the
``scope_kind`` (global / character / persona / chat), the
``owner_id`` that scopes it ('' for global; a character id for
character and persona scopes; a chat id for chat scopes), an
optional per-scope ``token_budget`` (NULL = unlimited; 0 mutes
the layer) and a ``position`` ordering the book inside its
layer. The triple (lorebook, scope kind, owner) is unique:
re-assigning updates the row. Lorebook, character and chat
sides cascade-delete with their rows; owner integrity for
character/persona/chat owners is kept by the service layer
(the owner id space is shared, as with chats.preset_id).
"""
from __future__ import annotations
import sqlite3

REVISION = "0032"
DESCRIPTION = "lorebook_scopes table (global/persona/chat lore scopes P-040)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lorebook_scopes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            lorebook_id TEXT NOT NULL REFERENCES lorebooks(id) ON DELETE CASCADE,
            scope_kind TEXT NOT NULL DEFAULT 'global',
            owner_id TEXT NOT NULL DEFAULT '',
            token_budget INTEGER,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lorebook_scopes_triple
            ON lorebook_scopes(lorebook_id, scope_kind, owner_id);
        CREATE INDEX IF NOT EXISTS idx_lorebook_scopes_lookup
            ON lorebook_scopes(user_id, scope_kind, owner_id);
        CREATE INDEX IF NOT EXISTS idx_lorebook_scopes_lorebook
            ON lorebook_scopes(lorebook_id);
        """
    )
