"""Mutation sync (S409): chat mutations maintain derived memory.

Consumes the S107 mutation events (``message.edited``,
``message.deleted``, ``chat.renamed`` and chat deletion) and maintains
memory provenance accordingly (INV-015/INV-016, MEMORY_ARCH §4/§11):

- A message that supported a memory is edited/deleted -> that source
  link is removed and the memory's support is recomputed.
- Removing ONE of several sources preserves the fact: the memory stays
  active and its confidence is recomputed from remaining evidence
  (``confidence = remaining / original`` support count, tracked via the
  ``support_total`` extractor-side bookkeeping kept in this module's
  recompute — stored on the memory's extractor JSON under
  ``support_total`` the first time sync sees the memory).
- Removing ALL support invalidates the derived memory
  (state -> ``invalidated``); it is never silently deleted, so the
  provenance graph (S411) can still explain what happened.
- Chat deletion invalidates memories whose every source lived in that
  chat; character rename events rewrite matching subject names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import ChatEvent, Memory, MemorySource
from runmal.memory import service


@dataclass
class SyncReport:
    sources_removed: int = 0
    memories_preserved: list[str] = field(default_factory=list)
    memories_invalidated: list[str] = field(default_factory=list)
    memories_rewritten: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"sources_removed": self.sources_removed,
                "memories_preserved": self.memories_preserved,
                "memories_invalidated": self.memories_invalidated,
                "memories_rewritten": self.memories_rewritten}


async def _recompute_support(
    session: AsyncSession, memory: Memory, report: SyncReport,
    original_total: int | None = None,
) -> None:
    extractor = json.loads(memory.extractor_json or "{}")
    remaining = await service.list_sources(session, memory.id)
    total = extractor.get("support_total") or original_total
    if total is None:
        total = max(len(remaining), 1)
    extractor["support_total"] = total
    if not remaining:
        if memory.state != "invalidated":
            memory.state = "invalidated"
            report.memories_invalidated.append(memory.id)
    else:
        memory.confidence = round(len(remaining) / total, 6)
        if memory.id not in report.memories_preserved:
            report.memories_preserved.append(memory.id)
    memory.extractor_json = json.dumps(extractor)
    await session.flush()


async def _drop_message_sources(
    session: AsyncSession, message_id: str, report: SyncReport
) -> None:
    rows = list(await session.scalars(
        select(MemorySource).where(
            MemorySource.source_kind == "message",
            MemorySource.source_id == message_id)))
    # Original support counts BEFORE removal (confidence denominator).
    originals: dict[str, int] = {}
    for row in rows:
        originals[row.memory_id] = len(
            await service.list_sources(session, row.memory_id))
    affected = []
    for row in rows:
        affected.append(row.memory_id)
        await session.execute(
            delete(MemorySource).where(
                MemorySource.memory_id == row.memory_id,
                MemorySource.source_kind == "message",
                MemorySource.source_id == message_id))
        report.sources_removed += 1
    await session.flush()
    for memory_id in affected:
        memory = await session.get(Memory, memory_id)
        if memory is not None:
            await _recompute_support(
                session, memory, report, originals.get(memory_id))


async def apply_events(
    session: AsyncSession, user_id: str, events: list[ChatEvent]
) -> SyncReport:
    """Apply S107 mutation events to derived memory, in event order."""
    report = SyncReport()
    for event in events:
        data = json.loads(event.data or "{}")
        if event.kind in ("message.deleted", "message.edited"):
            if event.message_id:
                await _drop_message_sources(session, event.message_id, report)
        elif event.kind == "chat.deleted":
            rows = list(await session.scalars(
                select(MemorySource).where(MemorySource.chat_id == event.chat_id)))
            originals = {}
            for r in rows:
                originals[r.memory_id] = len(
                    await service.list_sources(session, r.memory_id))
            ids = sorted({r.memory_id for r in rows})
            for row in rows:
                await session.execute(
                    delete(MemorySource).where(
                        MemorySource.memory_id == row.memory_id,
                        MemorySource.source_kind == row.source_kind,
                        MemorySource.source_id == row.source_id))
                report.sources_removed += 1
            await session.flush()
            for memory_id in ids:
                memory = await session.get(Memory, memory_id)
                if memory is not None and memory.user_id == user_id:
                    await _recompute_support(
                        session, memory, report, originals.get(memory_id))
        elif event.kind == "character.renamed":
            old, new = data.get("old_name"), data.get("new_name")
            if old and new:
                memories = await service.list_memories(session, user_id)
                for memory in memories:
                    if memory.subject == old:
                        memory.subject = new
                        memory.content = memory.content.replace(old, new)
                        report.memories_rewritten.append(memory.id)
                await session.flush()
    return report


async def sync_chat_events(
    session: AsyncSession, user_id: str, chat_id: str
) -> SyncReport:
    """Convenience: load a chat's S107 events and apply them."""
    events = list(await session.scalars(
        select(ChatEvent).where(ChatEvent.chat_id == chat_id)
        .order_by(ChatEvent.created_at, ChatEvent.id)))
    owned = list(await session.scalars(
        select(Memory.id).where(Memory.user_id == user_id, Memory.chat_id == chat_id)))
    if not owned and not events:
        return SyncReport()
    return await apply_events(session, user_id, events)
