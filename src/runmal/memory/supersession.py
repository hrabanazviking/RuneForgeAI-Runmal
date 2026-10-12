"""Contradiction + supersession engine (S413).

Temporal truth (MEMORY_ARCHITECTURE.md §5, INV-017): facts sharing a
(subject, predicate) slot form a timeline, not a bag of simultaneously
true sentences.

``apply_fact`` classifies a new fact against the slot's current state:

- **duplicate** — an active fact with the same normalized content
  already holds the slot; the existing memory is returned unchanged.
- **superseded** — the new fact carries a later (or the slot's first)
  ``valid_from``: the old active fact becomes ``superseded`` with
  ``valid_until`` set, history preserved; the new fact becomes active
  and records ``supersedes_id``.
- **disputed** — a conflicting fact arrives with no temporal evidence
  to order them: both are marked ``disputed`` until a later temporal
  fact or user correction resolves the slot.

Current-state queries read only the active fact; historical queries
can still see superseded/disputed rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory
from runmal.memory import service
from runmal.memory.consolidation import normalize


@dataclass(frozen=True)
class ApplyResult:
    action: str  # "inserted" | "duplicate" | "superseded" | "disputed"
    memory_id: str
    superseded_id: str | None = None

    def to_dict(self) -> dict:
        return {"action": self.action, "memory_id": self.memory_id,
                "superseded_id": self.superseded_id}


def _same_slot(a_subject: str, a_pred: str, b_subject: str, b_pred: str) -> bool:
    return (a_subject.lower(), a_pred.lower()) == (b_subject.lower(), b_pred.lower())


async def slot_memories(
    session: AsyncSession, user_id: str, subject: str, predicate: str
) -> list[Memory]:
    rows = await service.list_memories(session, user_id)
    return [m for m in rows if _same_slot(subject, predicate, m.subject, m.predicate)]


async def current_fact(
    session: AsyncSession, user_id: str, subject: str, predicate: str
) -> Memory | None:
    for m in await slot_memories(session, user_id, subject, predicate):
        if m.state == "active":
            return m
    return None


async def apply_fact(
    session: AsyncSession,
    user_id: str,
    *,
    subject: str,
    predicate: str,
    content: str,
    valid_from: datetime | None = None,
    sources: tuple = (),
    extractor: dict | None = None,
    confidence: float = 0.9,
    **create_kw,
) -> ApplyResult:
    slot = await slot_memories(session, user_id, subject, predicate)
    active = [m for m in slot if m.state in ("active", "disputed")]
    for m in active:
        if normalize(m.content) == normalize(content):
            if m.state == "active":
                return ApplyResult("duplicate", m.id)
            if valid_from is not None:
                # Temporal evidence confirms a disputed claim: activate it
                # and supersede the other side of the dispute.
                m.state = "active"
                m.valid_from = valid_from
                for other in active:
                    if other.id != m.id and other.state == "disputed":
                        other.state = "superseded"
                        other.valid_until = valid_from
                await session.flush()
                return ApplyResult("duplicate", m.id)
    current = next((m for m in active if m.state == "active"), None)

    if current is not None and valid_from is None and current.valid_from is not None:
        # No temporal evidence to order the conflict -> dispute both.
        new = await service.create_memory(
            session, user_id, content=content, kind="semantic",
            subject=subject, predicate=predicate, state="disputed",
            valid_from=valid_from, sources=sources,
            extractor=extractor or {}, confidence=confidence, **create_kw)
        current.state = "disputed"
        await session.flush()
        return ApplyResult("disputed", new.id, current.id)

    new = await service.create_memory(
        session, user_id, content=content, kind="semantic",
        subject=subject, predicate=predicate, state="active",
        valid_from=valid_from, sources=sources,
        extractor=extractor or {}, confidence=confidence, **create_kw)
    if current is not None:
        current.state = "superseded"
        current.valid_until = valid_from
        new.supersedes_id = current.id
        await session.flush()
        return ApplyResult("superseded", new.id, current.id)
    # Resolve a disputed slot when a temporal fact finally arrives.
    if valid_from is not None:
        for m in active:
            if m.state == "disputed":
                m.state = "superseded"
                m.valid_until = valid_from
        await session.flush()
    return ApplyResult("inserted", new.id)
