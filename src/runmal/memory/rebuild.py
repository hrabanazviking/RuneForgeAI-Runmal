"""Full rebuild / reindex (S415).

Derived memory state — vector indexes, FTS rows, chunks, and extracted
memories themselves — is NOT the source of truth (MEMORY_ARCH §11).
Canonical truth is: persisted messages, curated nucleus/user-edit
memories, and the provenance snapshot (memory rows + source links).

``rebuild_memory`` therefore:

1. snapshots every memory + its source links (the provenance record);
2. destroys ALL derived state: the vector store is cleared, FTS rows
   and chunk rows are deleted, derived memory rows are removed
   (nucleus + user-edited memories are canonical and survive);
3. re-derives from canonical messages: the deterministic extractor
   re-runs over every chat's persisted history, and extracted facts
   are matched back to the snapshot so temporal state (active /
   superseded / disputed, valid ranges, supersedes links) is restored;
4. restores any remaining snapshotted memories verbatim from their
   provenance (document-derived episodics, summaries) with sources;
5. re-embeds every restored memory's content as chunks under the
   CURRENT embedding backend — which may be a different profile/space
   than before the rebuild (embedding-profile change is supported by
   construction: old vectors are gone, new ones carry new provenance).

After a rebuild, the S414 evaluation corpus must remain semantically
correct against the rebuilt store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import EmbeddingBackend
from runmal.chats.service import get_history, list_chats
from runmal.db.models import Memory, MemoryChunk
from runmal.memory import service
from runmal.memory.extraction import FakeExtractor
from runmal.memory.vectorstore import VectorStore

CANONICAL_EXTRACTOR_KINDS = ("user_edit",)  # curated rows survive destruction


@dataclass
class RebuildReport:
    snapshotted: int = 0
    destroyed_memories: int = 0
    extracted_candidates: int = 0
    restored_from_extraction: int = 0
    restored_from_snapshot: int = 0
    reembedded_chunks: int = 0
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"snapshotted": self.snapshotted,
                "destroyed_memories": self.destroyed_memories,
                "extracted_candidates": self.extracted_candidates,
                "restored_from_extraction": self.restored_from_extraction,
                "restored_from_snapshot": self.restored_from_snapshot,
                "reembedded_chunks": self.reembedded_chunks,
                "provenance": self.provenance}


def _snapshot(memory: Memory, sources) -> dict:
    return {
        "id": memory.id, "kind": memory.kind, "content": memory.content,
        "subject": memory.subject, "predicate": memory.predicate,
        "state": memory.state, "salience": memory.salience,
        "stability": memory.stability, "pinned": bool(memory.pinned),
        "confidence": memory.confidence, "scope": memory.scope,
        "witnesses": json.loads(memory.witnesses_json or "[]"),
        "character_id": memory.character_id, "chat_id": memory.chat_id,
        "valid_from": memory.valid_from, "valid_until": memory.valid_until,
        "supersedes_id": memory.supersedes_id,
        "extractor": json.loads(memory.extractor_json or "{}"),
        "sources": [{"source_kind": s.source_kind, "source_id": s.source_id,
                     "chat_id": s.chat_id} for s in sources],
    }


def _is_canonical(snap: dict) -> bool:
    return snap["kind"] == "nucleus" or snap["extractor"].get("kind") in (
        CANONICAL_EXTRACTOR_KINDS)


async def rebuild_memory(
    session: AsyncSession,
    user_id: str,
    backend: EmbeddingBackend,
    store: VectorStore,
    *,
    extractor=None,
) -> RebuildReport:
    extractor = extractor or FakeExtractor()
    report = RebuildReport()

    # 1. Snapshot provenance.
    memories = await service.list_memories(session, user_id)
    snaps = []
    for m in memories:
        sources = await service.list_sources(session, m.id)
        snaps.append(_snapshot(m, sources))
    report.snapshotted = len(snaps)
    derived = [s for s in snaps if not _is_canonical(s)]
    canonical_ids = {s["id"] for s in snaps if _is_canonical(s)}

    # 2. Destroy derived state.
    store.clear()
    for snap in derived:
        await session.execute(
            text("DELETE FROM memory_fts WHERE memory_id = :mid"),
            {"mid": snap["id"]})
        await session.execute(
            delete(MemoryChunk).where(MemoryChunk.memory_id == snap["id"]))
        await session.execute(delete(Memory).where(Memory.id == snap["id"]))
        report.destroyed_memories += 1
    await session.flush()

    # 3. Re-derive from canonical messages.
    chats = await list_chats(session, user_id)
    candidates = []
    for chat, _count in chats:
        history = await get_history(session, user_id, chat.id) or []
        for cand in await extractor.extract(history):
            candidates.append((chat.id, cand))
    report.extracted_candidates = len(candidates)

    restored_ids: dict[str, str] = {}  # old id -> new id
    remaining = list(derived)
    for chat_id, cand in candidates:
        match = next(
            (s for s in remaining
             if s["content"] == cand.content
             and any(src["source_id"] == cand.source_message_id
                     for src in s["sources"])),
            None)
        if match is None:
            continue
        remaining.remove(match)
        new = await _restore(session, user_id, match, restored_ids)
        restored_ids[match["id"]] = new.id
        report.restored_from_extraction += 1

    # 4. Restore everything else verbatim from provenance.
    for snap in remaining:
        new = await _restore(session, user_id, snap, restored_ids)
        restored_ids[snap["id"]] = new.id
        report.restored_from_snapshot += 1

    # Fix supersedes links now that all ids are known.
    id_map = {**{cid: cid for cid in canonical_ids}, **restored_ids}
    all_now = await service.list_memories(session, user_id)
    by_content = {s["id"]: s for s in snaps}
    for m in all_now:
        snap = by_content.get(m.id) or next(
            (s for s in snaps if restored_ids.get(s["id"]) == m.id), None)
        if snap and snap["supersedes_id"] in id_map:
            m.supersedes_id = id_map[snap["supersedes_id"]]
    await session.flush()

    # 5. Re-embed every memory under the CURRENT backend/profile.
    prov = None
    for m in all_now:
        if not m.content:
            continue
        result = await backend.embed([m.content])
        prov = result.provenance
        chunk = await service.add_chunk(session, m, 0, m.content, prov)
        store.insert(prov, chunk.id, result.vectors[0])
        m.embedding_json = json.dumps(prov.to_dict())
        report.reembedded_chunks += 1
    await session.flush()
    report.provenance = prov.to_dict() if prov else {}
    return report


async def _restore(session, user_id, snap: dict, id_map: dict) -> Memory:
    memory = await service.create_memory(
        session, user_id, content=snap["content"], kind=snap["kind"],
        subject=snap["subject"], predicate=snap["predicate"],
        state=snap["state"], salience=snap["salience"],
        stability=snap["stability"], pinned=snap["pinned"],
        confidence=snap["confidence"], scope=snap["scope"],
        witnesses=tuple(snap["witnesses"]), character_id=snap["character_id"],
        chat_id=snap["chat_id"], valid_from=snap["valid_from"],
        valid_until=snap["valid_until"], extractor=snap["extractor"],
        sources=tuple((s["source_kind"], s["source_id"], s["chat_id"])
                      for s in snap["sources"]))
    return memory
