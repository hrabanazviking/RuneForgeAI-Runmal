"""0016 — bridge credentials (Campaign VI, S601).

Per-bridge credentials for the versioned bridge API (BRIDGE_PROTOCOL
§2, INV-029): each bridge holds its own scoped, revocable token. Only
the SHA-256 hash of the token is stored — the plaintext is shown once
at creation and never persisted (INV-023).
"""

from __future__ import annotations

import sqlite3

REVISION = "0016"
DESCRIPTION = "bridge_credentials table (scoped revocable bridge tokens, hashed)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE bridge_credentials (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL UNIQUE,
            scopes_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            revoked_at TEXT,
            last_used_at TEXT
        );
        CREATE INDEX idx_bridge_credentials_user ON bridge_credentials(user_id);
        CREATE INDEX idx_bridge_credentials_hash ON bridge_credentials(token_hash);
        """
    )
