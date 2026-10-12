"""0013 — independent embedding activation + re-embedding jobs (S311).

The ACTIVE embedding profile is its own axis (ADR-0001): switching it must
not touch any chat/profile chat fields. ``embedding_activation`` records,
per owner, which profile supplies embeddings and the provenance key of the
space it produces. ``reembedding_jobs`` is the migration hook's ledger: a
row is scheduled whenever the active provenance changes, while retrieval
keeps degrading to the FTS fallback until the job completes.
"""

from __future__ import annotations

import sqlite3

REVISION = "0013"
DESCRIPTION = "embedding_activation + reembedding_jobs (independent embedding profiles)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE embedding_activation (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            profile_id TEXT NOT NULL DEFAULT '',
            provenance_key TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE reembedding_jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            from_key TEXT NOT NULL DEFAULT '',
            to_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'scheduled',
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_reembedding_jobs_user ON reembedding_jobs(user_id);
        """
    )
