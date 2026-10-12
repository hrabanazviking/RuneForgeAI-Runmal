"""Deduplication + consolidation (S412).

A consolidation pass finds duplicate/refined semantic memories —
same normalized statement, or same subject+predicate with highly
similar content — and merges them into one canonical memory while
PRESERVING all provenance (INV-018, MEMORY_ARCH §10):

- every source link of a merged memory is re-pointed to the canonical
  memory (the many-to-many source table dedups naturally);
- the canonical keeps the strongest confidence/salience;
- merged rows are not deleted: they become ``historical`` with a
  ``merged_into`` marker in their extractor provenance, and leave the
  FTS index so retrieval stops double-counting them;
- the pass is IDEMPOTENT: merged rows are no longer active, so a
  second run over unchanged input merges nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory
from runmal.memory import service

SIMILARITY_THRESHOLD = 0.6
MERGEABLE_STATES = ("active", "pinned")


def normalize(text_: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text_.lower())).strip()


def token_similarity(a: str, b: str) -> float:
    ta, tb = set(normalize(a).split()), set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def are_duplicates(a: Memory, b: Memory) -> bool:
    if normalize(a.content) == normalize(b.content):
        return True
    if a.subject and a.predicate and b.subject and b.predicate:
        if (a.subject.lower(), a.predicate.lower()) == (
            b.subject.lower(), b.predicate.lower()
        ):
            return token_similarity(a.content, b.content) >= SIMILARITY_THRESHOLD
    return False


@dataclass
class ConsolidationReport:
    merged: list[tuple[str, str]] = field(default_factory=list)  # (from, into)
    groups: int = 0

    def to_dict(self) -> dict:
        return {"merged": [{"from": f, "into": t} for f, t in self.merged],
                "groups": self.groups}


def _groups(memories: list[Memory]) -> list[list[Memory]]:
    groups: list[list[Memory]] = []
    for memory in memories:
        placed = False
        for group in groups:
            if any(are_duplicates(memory, other) for other in group):
                group.append(memory)
                placed = True
                break
        if not placed:
            groups.append([memory])
    return [g for g in groups if len(g) > 1]


async def consolidate(session: AsyncSession, user_id: str) -> ConsolidationReport:
    memories = [
        m for m in await service.list_memories(session, user_id)
        if m.state in MERGEABLE_STATES and m.kind in ("semantic", "episodic")
    ]
    memories.sort(key=lambda m: (m.created_at, m.id))
    report = ConsolidationReport()
    for group in _groups(memories):
        canonical = group[0]
        report.groups += 1
        for dup in group[1:]:
            for source in await service.list_sources(session, dup.id):
                await service.add_source(
                    session, canonical.id, source.source_kind,
                    source.source_id, source.chat_id)
            canonical.confidence = max(canonical.confidence, dup.confidence)
            canonical.salience = max(canonical.salience, dup.salience)
            extractor = json.loads(dup.extractor_json or "{}")
            extractor["merged_into"] = canonical.id
            dup.extractor_json = json.dumps(extractor)
            dup.state = "historical"
            await session.execute(
                text("DELETE FROM memory_fts WHERE memory_id = :mid"),
                {"mid": dup.id})
            report.merged.append((dup.id, canonical.id))
        await session.flush()
    return report
