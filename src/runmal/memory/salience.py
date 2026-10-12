"""Salience + decay (S406): retrieval strength over time.

Decay affects retrieval strength, never historical existence
(MEMORY_ARCHITECTURE.md §9). All time enters through an INJECTED clock
— a ``now`` datetime passed by the caller — never through scattered
wall-clock reads, so fake-clock tests are exact.

Strength model (deterministic, versioned as ``STRENGTH_MODEL``):

    age_days   = (now - created_at) in days, floored at 0
    decay      = exp(-DECAY_PER_DAY * age_days * (1 - stability))
    recall_boost = 1 + 0.15 * log1p(recall_count)
    strength   = salience * decay * recall_boost

Pinned memories (``pinned`` flag or state ``pinned``) and memories with
stability >= 0.999 do not decay. Relevant recall REINFORCES: recall
count rises and last-recalled is stamped (with the injected clock),
which lifts later strength through the boost term — but reinforcement
never revives an invalidated/superseded memory (state filters in
retrieval still apply first).
"""

from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory

STRENGTH_MODEL = "exp-decay-1"
DECAY_PER_DAY = 0.05
RECALL_BOOST = 0.15


def strength_multiplier(memory: Memory, now: datetime) -> float:
    """Retrieval-strength multiplier for one memory at ``now``."""
    if memory.pinned or memory.state == "pinned" or memory.stability >= 0.999:
        decay = 1.0
    else:
        created = memory.created_at
        if created is not None and created.tzinfo is None and now.tzinfo is not None:
            from datetime import UTC

            created = created.replace(tzinfo=UTC)
        age_days = max(0.0, (now - created).total_seconds() / 86400.0) if created else 0.0
        decay = math.exp(-DECAY_PER_DAY * age_days * (1.0 - memory.stability))
    boost = 1.0 + RECALL_BOOST * math.log1p(memory.recall_count)
    return memory.salience * decay * boost


async def strength_map(
    session: AsyncSession, user_id: str, now: datetime
) -> dict[str, float]:
    """Multipliers for every memory of a user, keyed by memory id.

    Plugs straight into ``RetrievalQuery.extra_scores`` (S403).
    """
    from runmal.memory.service import list_memories

    memories = await list_memories(session, user_id)
    return {m.id: strength_multiplier(m, now) for m in memories}


async def reinforce(session: AsyncSession, memory: Memory, now: datetime) -> Memory:
    """Record a relevant recall at ``now`` (injected clock)."""
    memory.recall_count += 1
    memory.last_recalled_at = now
    memory.last_confirmed_at = now
    await session.flush()
    return memory
