"""Memory nucleus (S408): curated core memory slot.

The nucleus is the compact, deliberately curated set of identity/core
facts for a character or for the user (MEMORY_ARCHITECTURE.md §1 class
1). Nucleus memories are pinned, maximally stable, and rendered as ONE
``memory_nucleus`` prompt slot (PROMPT_COMPOSER.md §2 baseline order,
right after persona) so the S214 Prompt Trace shows their inclusion
and budget behavior like any other slot.

Curation replaces the set atomically for a (user, character) pair:
previous nucleus rows for that pair are removed; user-level nucleus
(character_id=None) and character-level nucleus coexist, and a
character's effective nucleus is user-level + their own rows.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory
from runmal.memory import service
from runmal.prompt.slots import Slot, make_slot


async def set_nucleus(
    session: AsyncSession, user_id: str, character_id: str | None,
    entries: list[str],
) -> list[Memory]:
    q = delete(Memory).where(
        Memory.user_id == user_id, Memory.kind == "nucleus",
        Memory.character_id == character_id if character_id is not None
        else Memory.character_id.is_(None))
    await session.execute(q)
    await session.flush()
    out = []
    for entry in entries:
        m = await service.create_memory(
            session, user_id, content=entry, kind="nucleus",
            state="pinned", pinned=True, stability=1.0, salience=1.0,
            scope="character" if character_id else "user",
            character_id=character_id,
            extractor={"kind": "user_edit", "curated": True})
        out.append(m)
    return out


async def get_nucleus(
    session: AsyncSession, user_id: str, character_id: str | None = None
) -> list[Memory]:
    q = select(Memory).where(Memory.user_id == user_id, Memory.kind == "nucleus")
    rows = list(await session.scalars(q.order_by(Memory.created_at, Memory.id)))
    if character_id is None:
        return [m for m in rows if m.character_id is None]
    return [m for m in rows if m.character_id in (None, character_id)]


def nucleus_slot(memories: list[Memory], character_id: str | None = None) -> Slot | None:
    """Render nucleus memories as the composer's memory_nucleus slot."""
    if not memories:
        return None
    content = "\n".join(f"- {m.content}" for m in memories)
    return make_slot(
        "memory_nucleus", "system", content,
        id=f"nucleus/{character_id or 'user'}",
        priority=900, required=False,
        provenance=f"nucleus:{character_id or 'user'}")
