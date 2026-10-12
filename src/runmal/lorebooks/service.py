"""Lorebook + lore entry CRUD, ownership-scoped (S201).

Entries always resolve through their parent book: an entry is addressable
only via a book the caller owns. Keys are stored as JSON text and validated
as string lists at the boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Lorebook, LoreEntry

VALID_POSITIONS = frozenset({"before_char", "after_char"})


def _now() -> datetime:
    return datetime.now(UTC)


def _encode_keys(keys: list[str] | None) -> str:
    if keys is None:
        return "[]"
    if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
        raise ValueError("keys must be a list of strings")
    return json.dumps(keys)


def _decode_keys(raw: str) -> list[str]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stored keys are not valid JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise ValueError("stored keys are not a list")
    return [str(k) for k in decoded]


def _check_prompts(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be an integer >= 0")
    return value


def _check_position(position: str) -> str:
    if position not in VALID_POSITIONS:
        raise ValueError(f"invalid position: {position!r} (valid: {sorted(VALID_POSITIONS)})")
    return position


def lorebook_to_dict(book: Lorebook, entry_count: int = 0) -> dict:
    return {
        "id": book.id,
        "name": book.name,
        "description": book.description,
        "scan_depth": book.scan_depth,
        "token_budget": book.token_budget,
        "created_at": book.created_at.isoformat(),
        "entry_count": entry_count,
    }


def entry_to_dict(entry: LoreEntry) -> dict:
    return {
        "id": entry.id,
        "lorebook_id": entry.lorebook_id,
        "name": entry.name,
        "content": entry.content,
        "keys": _decode_keys(entry.keys_json),
        "secondary_keys": _decode_keys(entry.secondary_keys_json),
        "priority": entry.priority,
        "position": entry.position,
        "enabled": bool(entry.enabled),
        "constant": bool(entry.constant),
        "case_sensitive": bool(entry.case_sensitive),
        "whole_word": bool(entry.whole_word),
        "sticky_prompts": int(entry.sticky_prompts),
        "cooldown_prompts": int(entry.cooldown_prompts),
        "delay_prompts": int(entry.delay_prompts),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def _get_owned_book(session: AsyncSession, user_id: str, book_id: str) -> Lorebook | None:
    result = await session.execute(
        select(Lorebook).where(Lorebook.id == book_id, Lorebook.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _get_owned_entry(
    session: AsyncSession, user_id: str, book_id: str, entry_id: str
) -> LoreEntry | None:
    if await _get_owned_book(session, user_id, book_id) is None:
        return None
    result = await session.execute(
        select(LoreEntry).where(LoreEntry.id == entry_id, LoreEntry.lorebook_id == book_id)
    )
    return result.scalar_one_or_none()


async def create_lorebook(
    session: AsyncSession,
    user_id: str,
    name: str,
    description: str = "",
    scan_depth: int = 4,
    token_budget: int | None = None,
) -> Lorebook:
    if not name:
        raise ValueError("lorebook name must not be empty")
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1")
    book = Lorebook(
        user_id=user_id,
        name=name,
        description=description,
        scan_depth=scan_depth,
        token_budget=token_budget,
    )
    session.add(book)
    await session.commit()
    return book


async def list_lorebooks(session: AsyncSession, user_id: str) -> list[tuple[Lorebook, int]]:
    result = await session.execute(
        select(Lorebook, func.count(LoreEntry.id))
        .outerjoin(LoreEntry, LoreEntry.lorebook_id == Lorebook.id)
        .where(Lorebook.user_id == user_id)
        .group_by(Lorebook.id)
        .order_by(Lorebook.created_at)
    )
    return [(book, count) for book, count in result.all()]


async def get_lorebook(session: AsyncSession, user_id: str, book_id: str) -> Lorebook | None:
    return await _get_owned_book(session, user_id, book_id)


async def update_lorebook(
    session: AsyncSession,
    user_id: str,
    book_id: str,
    name: str | None = None,
    description: str | None = None,
    scan_depth: int | None = None,
    token_budget: int | None = None,
) -> Lorebook | None:
    book = await _get_owned_book(session, user_id, book_id)
    if book is None:
        return None
    if name is not None:
        if not name:
            raise ValueError("lorebook name must not be empty")
        book.name = name
    if description is not None:
        book.description = description
    if scan_depth is not None:
        if scan_depth < 1:
            raise ValueError("scan_depth must be >= 1")
        book.scan_depth = scan_depth
    if token_budget is not None:
        if token_budget < 1:
            raise ValueError("token_budget must be >= 1")
        book.token_budget = token_budget
    await session.commit()
    return book


async def delete_lorebook(session: AsyncSession, user_id: str, book_id: str) -> bool:
    if await _get_owned_book(session, user_id, book_id) is None:
        return False
    # Entries go with the book (FK cascade).
    await session.execute(delete(Lorebook).where(Lorebook.id == book_id))
    await session.commit()
    return True


async def create_entry(
    session: AsyncSession,
    user_id: str,
    book_id: str,
    name: str = "",
    content: str = "",
    keys: list[str] | None = None,
    secondary_keys: list[str] | None = None,
    priority: int = 100,
    position: str = "before_char",
    enabled: bool = True,
    constant: bool = False,
    case_sensitive: bool = False,
    whole_word: bool = True,
    sticky_prompts: int = 0,
    cooldown_prompts: int = 0,
    delay_prompts: int = 0,
) -> LoreEntry:
    if await _get_owned_book(session, user_id, book_id) is None:
        raise KeyError(book_id)
    entry = LoreEntry(
        lorebook_id=book_id,
        user_id=user_id,
        name=name,
        content=content,
        keys_json=_encode_keys(keys),
        secondary_keys_json=_encode_keys(secondary_keys),
        priority=priority,
        position=_check_position(position),
        enabled=enabled,
        constant=constant,
        case_sensitive=case_sensitive,
        whole_word=whole_word,
        sticky_prompts=_check_prompts("sticky_prompts", sticky_prompts),
        cooldown_prompts=_check_prompts("cooldown_prompts", cooldown_prompts),
        delay_prompts=_check_prompts("delay_prompts", delay_prompts),
    )
    session.add(entry)
    await session.commit()
    return entry


async def list_entries(session: AsyncSession, user_id: str, book_id: str) -> list[LoreEntry] | None:
    if await _get_owned_book(session, user_id, book_id) is None:
        return None
    result = await session.execute(
        select(LoreEntry)
        .where(LoreEntry.lorebook_id == book_id)
        .order_by(LoreEntry.priority.desc(), LoreEntry.created_at)
    )
    return list(result.scalars().all())


async def get_entry(
    session: AsyncSession, user_id: str, book_id: str, entry_id: str
) -> LoreEntry | None:
    return await _get_owned_entry(session, user_id, book_id, entry_id)


async def update_entry(
    session: AsyncSession,
    user_id: str,
    book_id: str,
    entry_id: str,
    **fields,
) -> LoreEntry | None:
    entry = await _get_owned_entry(session, user_id, book_id, entry_id)
    if entry is None:
        return None
    if "name" in fields:
        entry.name = fields["name"]
    if "content" in fields:
        entry.content = fields["content"]
    if "keys" in fields:
        entry.keys_json = _encode_keys(fields["keys"])
    if "secondary_keys" in fields:
        entry.secondary_keys_json = _encode_keys(fields["secondary_keys"])
    if "priority" in fields:
        entry.priority = int(fields["priority"])
    if "position" in fields:
        entry.position = _check_position(fields["position"])
    for flag in ("enabled", "constant", "case_sensitive", "whole_word"):
        if flag in fields:
            setattr(entry, flag, bool(fields[flag]))
    for knob in ("sticky_prompts", "cooldown_prompts", "delay_prompts"):
        if knob in fields:
            setattr(entry, knob, _check_prompts(knob, fields[knob]))
    entry.updated_at = _now()
    await session.commit()
    return entry


async def delete_entry(session: AsyncSession, user_id: str, book_id: str, entry_id: str) -> bool:
    if await _get_owned_entry(session, user_id, book_id, entry_id) is None:
        return False
    await session.execute(delete(LoreEntry).where(LoreEntry.id == entry_id))
    await session.commit()
    return True
