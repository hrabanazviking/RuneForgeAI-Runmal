"""Canonical memory record helpers (MEMORY_ARCHITECTURE.md §2).

The ORM rows live in ``runmal.db.models`` (Memory, MemorySource,
MemoryChunk, ChatSummary); this module owns the JSON provenance shapes
and the dict serialization used by services, the browser UI and traces.
"""

from __future__ import annotations

import json

MEMORY_KINDS = ("nucleus", "episodic", "semantic", "summary")
MEMORY_STATES = ("active", "superseded", "disputed", "historical", "invalidated", "pinned")
SCOPES = ("user", "global", "character", "chat", "witnesses")


def memory_to_dict(m) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "kind": m.kind,
        "content": m.content,
        "subject": m.subject,
        "predicate": m.predicate,
        "state": m.state,
        "salience": m.salience,
        "stability": m.stability,
        "pinned": bool(m.pinned),
        "confidence": m.confidence,
        "scope": m.scope,
        "witnesses": json.loads(m.witnesses_json or "[]"),
        "character_id": m.character_id,
        "chat_id": m.chat_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "valid_from": m.valid_from.isoformat() if m.valid_from else None,
        "valid_until": m.valid_until.isoformat() if m.valid_until else None,
        "recall_count": m.recall_count,
        "last_recalled_at": m.last_recalled_at.isoformat() if m.last_recalled_at else None,
        "supersedes_id": m.supersedes_id,
        "extractor": json.loads(m.extractor_json or "{}"),
        "embedding": json.loads(m.embedding_json or "{}"),
    }


def source_to_dict(s) -> dict:
    return {
        "memory_id": s.memory_id,
        "source_kind": s.source_kind,
        "source_id": s.source_id,
        "chat_id": s.chat_id,
    }
