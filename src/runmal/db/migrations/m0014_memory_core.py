"""0014 — living memory core tables (Campaign IV, S402).

Canonical memory records with full provenance (MEMORY_ARCHITECTURE.md
§2), many-to-many source evidence (§4), ingested chunks with embedding
provenance, rolling chat summaries (S404), and the FTS5 index used by
hybrid retrieval (S403). Derived vector state lives in the S401 vector
store; everything here is rebuildable from canonical messages (S415).
"""

from __future__ import annotations

import sqlite3

REVISION = "0014"
DESCRIPTION = "memories + sources + chunks + summaries + FTS5 (living memory core)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'semantic',
            content TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            predicate TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'active',
            salience REAL NOT NULL DEFAULT 0.5,
            stability REAL NOT NULL DEFAULT 0.5,
            pinned INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 1.0,
            scope TEXT NOT NULL DEFAULT 'user',
            witnesses_json TEXT NOT NULL DEFAULT '[]',
            character_id TEXT,
            chat_id TEXT,
            created_at TEXT NOT NULL,
            valid_from TEXT,
            valid_until TEXT,
            last_confirmed_at TEXT,
            recall_count INTEGER NOT NULL DEFAULT 0,
            last_recalled_at TEXT,
            supersedes_id TEXT,
            extractor_json TEXT NOT NULL DEFAULT '{}',
            embedding_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX idx_memories_user ON memories(user_id);
        CREATE INDEX idx_memories_state ON memories(user_id, state);

        CREATE TABLE memory_sources (
            memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL DEFAULT 'message',
            source_id TEXT NOT NULL DEFAULT '',
            chat_id TEXT,
            PRIMARY KEY (memory_id, source_kind, source_id)
        );
        CREATE INDEX idx_memory_sources_source ON memory_sources(source_id);

        CREATE TABLE memory_chunks (
            id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            dims INTEGER NOT NULL DEFAULT 0,
            version TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE chat_summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            chat_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            summary TEXT NOT NULL DEFAULT '',
            source_first_id TEXT,
            source_last_id TEXT,
            source_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_summaries_chat ON chat_summaries(chat_id, version);

        CREATE VIRTUAL TABLE memory_fts USING fts5(
            content, memory_id UNINDEXED, tokenize = 'unicode61'
        );
        """
    )
