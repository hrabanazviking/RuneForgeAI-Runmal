"""0018 — bridge idempotency keys (Campaign VI, S610).

BRIDGE_PROTOCOL §4 / INV-030: a retried bridge write carrying an
idempotency key must return the original result instead of
duplicating the turn. The store is per (credential, operation, key):
the request fingerprint detects conflicting reuse (same key,
different request), and the stored response is replayed verbatim.
"""

from __future__ import annotations

import sqlite3

REVISION = "0018"
DESCRIPTION = "bridge_idempotency_keys (retried-write deduplication store)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE bridge_idempotency_keys (
            credential_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status_code INTEGER NOT NULL DEFAULT 200,
            response_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (credential_id, operation, key)
        );
        """
    )
