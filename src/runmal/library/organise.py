"""Library organisation service (P-024).

Per-user organisation of the character library: a favourite flag and
tags for every character. Tags live in two places that every write
keeps in step: normalised rows in ``character_tags`` (the queryable
form, keyed by the casefolded ``tag_key``) and the ``tags`` list inside
the stored card JSON (the portable form). Characters created before
this slice have no organisation row; they are seeded lazily from their
card tags on first contact, so the library view is always complete.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import import_card
from runmal.cards.exporter import export_json
from runmal.db.models import Character, CharacterOrganisation, CharacterTag

__all__ = [
    "MAX_TAG_LEN",
    "MAX_TAGS_PER_CARD",
    "normalise_tag",
    "normalise_tags",
    "get_organisation",
    "set_tags",
    "add_tags",
    "remove_tag",
    "set_favourite",
    "list_library",
    "list_tags",
]

MAX_TAG_LEN = 64
MAX_TAGS_PER_CARD = 50


# -- Tag normalisation ---------------------------------------------------


def normalise_tag(raw) -> tuple[str, str]:
    """Normalise one tag to its ``(display, key)`` pair.

    The display form is the raw string with runs of whitespace
    collapsed to single spaces and the ends trimmed; the key is its
    casefold, so ``"Sci Fi"``, ``"sci  fi"`` and ``"SCI FI"`` are the
    same tag. Raises ValueError for a non-string, an empty result, a
    display longer than MAX_TAG_LEN, or control characters.
    """
    if not isinstance(raw, str):
        raise ValueError(f"tag must be a string, got {type(raw).__name__}")
    display = " ".join(str(raw).split())
    if not display:
        raise ValueError("tag must not be empty")
    if len(display) > MAX_TAG_LEN:
        raise ValueError(f"tag exceeds {MAX_TAG_LEN} characters: {display!r}")
    if any(unicodedata.category(ch) == "Cc" for ch in display):
        raise ValueError(f"tag contains control characters: {display!r}")
    return display, display.casefold()


def normalise_tags(raw_list) -> list[tuple[str, str]]:
    """Normalise a list of tags, deduped by key (first display wins).

    Raises ValueError when the input is not a list of strings, when
    any item is invalid, or when more than MAX_TAGS_PER_CARD distinct
    tags remain after dedupe.
    """
    if not isinstance(raw_list, list):
        raise ValueError("tags must be a list of strings")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw_list:
        if not isinstance(item, str):
            raise ValueError("tags must be a list of strings")
        display, key = normalise_tag(item)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((display, key))
    if len(pairs) > MAX_TAGS_PER_CARD:
        raise ValueError(f"at most {MAX_TAGS_PER_CARD} tags per character")
    return pairs


# -- Card JSON <-> tag rows ----------------------------------------------


def _card_tags(card_json: str) -> list[str]:
    """The raw tag strings stored in a character's card JSON.

    Parsed through the card importer; on any failure falls back to a
    plain JSON read of ``data.tags`` (or top-level ``tags``), and to
    an empty list when neither yields a list of strings.
    """
    try:
        card = import_card(card_json.encode(), "card.json")
        return list(card.tags)
    except Exception:
        pass
    try:
        obj = json.loads(card_json)
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    data = obj.get("data")
    candidates = []
    if isinstance(data, dict):
        candidates.append(data.get("tags"))
    candidates.append(obj.get("tags"))
    for tags in candidates:
        if isinstance(tags, list):
            return [tag for tag in tags if isinstance(tag, str)]
    return []


def _rewrite_card_tags(character, display_tags) -> None:
    """Rewrite the stored card JSON's tag list in place.

    Re-export goes through the card exporter, which overlays the
    known fields on the card's raw mapping, so unknown fields survive
    (INV-009). An unparseable stored card raises ValueError - the
    tags are never silently dropped.
    """
    try:
        card = import_card(character.card_json.encode(), "card.json")
    except Exception as exc:
        raise ValueError(
            f"stored card for character {character.id} cannot be parsed"
        ) from exc
    card.tags = list(display_tags)
    character.card_json = export_json(card, "2").decode("utf-8")


def _seed_pairs(card_json: str) -> list[tuple[str, str]]:
    """Normalised (display, key) pairs for a card's tags.

    Invalid card tags are skipped rather than failing the seed: a
    legacy card must never make its character unorganisable.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in _card_tags(card_json):
        try:
            display, key = normalise_tag(raw)
        except ValueError:
            continue
        if key in seen:
            continue
        seen.add(key)
        pairs.append((display, key))
        if len(pairs) >= MAX_TAGS_PER_CARD:
            break
    return pairs


# -- Row helpers -----------------------------------------------------------


async def _get_character(
    session: AsyncSession, user_id: str, character_id: str
) -> Character | None:
    result = await session.execute(
        select(Character).where(
            Character.id == character_id,
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _get_org(
    session: AsyncSession, character_id: str
) -> CharacterOrganisation | None:
    result = await session.execute(
        select(CharacterOrganisation).where(
            CharacterOrganisation.character_id == character_id
        )
    )
    return result.scalar_one_or_none()


def _new_org(character: Character, is_favourite: bool = False):
    return CharacterOrganisation(
        character_id=character.id,
        user_id=character.user_id,
        is_favourite=is_favourite,
        updated_at=datetime.now(UTC),
    )


def _insert_tags(session: AsyncSession, character: Character, pairs) -> None:
    for display, key in pairs:
        session.add(
            CharacterTag(
                character_id=character.id,
                user_id=character.user_id,
                tag=display,
                tag_key=key,
            )
        )


async def _ensure_org(session: AsyncSession, character: Character):
    """Return ``(org, created)``: create the org row when missing.

    A freshly created row is seeded with the character's card tags.
    Flushes but never commits; the caller owns the transaction.
    """
    org = await _get_org(session, character.id)
    if org is not None:
        return org, False
    org = _new_org(character)
    session.add(org)
    _insert_tags(session, character, _seed_pairs(character.card_json))
    await session.flush()
    return org, True


async def _seed_missing(session: AsyncSession, user_id: str) -> None:
    """Seed organisation rows for every unorganised character.

    Covers all of the user's non-deleted characters that lack a
    CharacterOrganisation row. Commits at the end when (and only
    when) anything was inserted.
    """
    result = await session.execute(
        select(Character).where(
            Character.user_id == user_id, Character.deleted_at.is_(None)
        )
    )
    characters = list(result.scalars().all())
    if not characters:
        return
    existing = await session.execute(
        select(CharacterOrganisation.character_id).where(
            CharacterOrganisation.user_id == user_id
        )
    )
    have = set(existing.scalars().all())
    inserted = False
    for character in characters:
        if character.id in have:
            continue
        session.add(_new_org(character))
        _insert_tags(session, character, _seed_pairs(character.card_json))
        inserted = True
    if inserted:
        await session.flush()
        await session.commit()


async def _tag_displays(session: AsyncSession, character_id: str) -> list[str]:
    result = await session.execute(
        select(CharacterTag.tag)
        .where(CharacterTag.character_id == character_id)
        .order_by(CharacterTag.tag_key)
    )
    return list(result.scalars().all())


async def _existing_pairs(
    session: AsyncSession, character: Character
) -> list[tuple[str, str]]:
    """The character's current (display, key) pairs.

    From the tag rows when an organisation row exists; a character
    without one conceptually holds its card tags, so those seed pairs
    are its current tags.
    """
    org = await _get_org(session, character.id)
    if org is None:
        return _seed_pairs(character.card_json)
    result = await session.execute(
        select(CharacterTag.tag, CharacterTag.tag_key)
        .where(CharacterTag.character_id == character.id)
        .order_by(CharacterTag.tag_key)
    )
    return [(tag, key) for tag, key in result.all()]


async def _org_dict(
    session: AsyncSession, character: Character, org
) -> dict:
    return {
        "character_id": character.id,
        "name": character.name,
        "tags": await _tag_displays(session, character.id),
        "is_favourite": bool(org.is_favourite) if org is not None else False,
    }


async def _apply_tags(
    session: AsyncSession, character: Character, pairs
) -> None:
    """Replace a character's tags everywhere and commit.

    The card JSON is rewritten first: if the stored card cannot be
    parsed the ValueError leaves the tag rows untouched.
    """
    _rewrite_card_tags(character, [display for display, _ in pairs])
    org = await _get_org(session, character.id)
    if org is None:
        session.add(_new_org(character))
    else:
        org.updated_at = datetime.now(UTC)
    await session.execute(
        delete(CharacterTag).where(
            CharacterTag.character_id == character.id
        )
    )
    _insert_tags(session, character, pairs)
    await session.flush()
    await session.commit()


# -- Public API ------------------------------------------------------------


async def get_organisation(
    session: AsyncSession, user_id: str, character_id: str
) -> dict | None:
    """One character's organisation, or None when not found.

    Missing, soft-deleted, and other users' characters all read as
    None. A character without an organisation row is seeded from its
    card tags first.
    """
    character = await _get_character(session, user_id, character_id)
    if character is None:
        return None
    org, created = await _ensure_org(session, character)
    result = await _org_dict(session, character, org)
    if created:
        await session.commit()
    return result


async def set_tags(
    session: AsyncSession, user_id: str, character_id: str, tags
) -> dict | None:
    """Replace a character's tags; returns the fresh organisation."""
    pairs = normalise_tags(tags)
    character = await _get_character(session, user_id, character_id)
    if character is None:
        return None
    await _apply_tags(session, character, pairs)
    return await get_organisation(session, user_id, character_id)


async def add_tags(
    session: AsyncSession, user_id: str, character_id: str, tags
) -> dict | None:
    """Add tags to a character's existing set (union by key)."""
    new_pairs = normalise_tags(tags)
    character = await _get_character(session, user_id, character_id)
    if character is None:
        return None
    merged = await _existing_pairs(session, character)
    seen = {key for _, key in merged}
    for display, key in new_pairs:
        if key not in seen:
            seen.add(key)
            merged.append((display, key))
    if len(merged) > MAX_TAGS_PER_CARD:
        raise ValueError(f"at most {MAX_TAGS_PER_CARD} tags per character")
    await _apply_tags(session, character, merged)
    return await get_organisation(session, user_id, character_id)


async def remove_tag(
    session: AsyncSession, user_id: str, character_id: str, tag
) -> dict | None:
    """Remove one tag by key; removing an absent tag is a no-op."""
    _, key = normalise_tag(tag)
    character = await _get_character(session, user_id, character_id)
    if character is None:
        return None
    kept = [
        pair
        for pair in await _existing_pairs(session, character)
        if pair[1] != key
    ]
    await _apply_tags(session, character, kept)
    return await get_organisation(session, user_id, character_id)


async def set_favourite(
    session: AsyncSession, user_id: str, character_id: str, is_favourite: bool
) -> dict | None:
    """Set a character's favourite flag, seeding it when needed."""
    character = await _get_character(session, user_id, character_id)
    if character is None:
        return None
    org, _created = await _ensure_org(session, character)
    org.is_favourite = bool(is_favourite)
    org.updated_at = datetime.now(UTC)
    await session.commit()
    return await get_organisation(session, user_id, character_id)


def _like_pattern(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


async def list_library(
    session: AsyncSession,
    user_id: str,
    *,
    q=None,
    tags=None,
    tag_mode: str = "any",
    favourites_only: bool = False,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """A filtered, sorted, paginated page of the user's library.

    Returns ``{"total": int, "items": [...]}`` where total counts
    every character matching the filters, not just the page.
    """
    await _seed_missing(session, user_id)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(200, limit))
    offset = max(0, offset)

    conditions = [
        Character.user_id == user_id,
        Character.deleted_at.is_(None),
    ]
    if favourites_only:
        conditions.append(CharacterOrganisation.is_favourite == True)  # noqa: E712
    if tags:
        keys: list[str] = []
        seen_keys: set[str] = set()
        for raw in tags:
            _, key = normalise_tag(raw)
            if key not in seen_keys:
                seen_keys.add(key)
                keys.append(key)
        if keys:
            if tag_mode == "all":
                tag_subquery = (
                    select(CharacterTag.character_id)
                    .where(
                        CharacterTag.user_id == user_id,
                        CharacterTag.tag_key.in_(keys),
                    )
                    .group_by(CharacterTag.character_id)
                    .having(
                        func.count(func.distinct(CharacterTag.tag_key))
                        == len(keys)
                    )
                )
            else:
                tag_subquery = select(CharacterTag.character_id).where(
                    CharacterTag.user_id == user_id,
                    CharacterTag.tag_key.in_(keys),
                )
            conditions.append(Character.id.in_(tag_subquery))
    if q is not None and str(q).strip():
        pattern = _like_pattern(str(q).strip().casefold())
        tag_q_subquery = select(CharacterTag.character_id).where(
            CharacterTag.user_id == user_id,
            or_(
                func.lower(CharacterTag.tag).like(pattern, escape="\\"),
                CharacterTag.tag_key.like(pattern, escape="\\"),
            ),
        )
        conditions.append(
            or_(
                func.lower(Character.name).like(pattern, escape="\\"),
                Character.id.in_(tag_q_subquery),
            )
        )

    count_result = await session.execute(
        select(func.count(Character.id))
        .select_from(Character)
        .outerjoin(
            CharacterOrganisation,
            CharacterOrganisation.character_id == Character.id,
        )
        .where(*conditions)
    )
    total = int(count_result.scalar_one())

    if sort == "name_desc":
        order_by = [func.lower(Character.name).desc(), Character.created_at]
    elif sort == "newest":
        order_by = [Character.created_at.desc(), Character.id]
    elif sort == "oldest":
        order_by = [Character.created_at, Character.id]
    elif sort == "favourites_first":
        order_by = [
            func.coalesce(CharacterOrganisation.is_favourite, False).desc(),
            func.lower(Character.name),
            Character.created_at,
        ]
    else:  # "name" and any unknown value
        order_by = [func.lower(Character.name), Character.created_at]

    result = await session.execute(
        select(Character, CharacterOrganisation)
        .outerjoin(
            CharacterOrganisation,
            CharacterOrganisation.character_id == Character.id,
        )
        .where(*conditions)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()

    tags_by_id: dict[str, list[str]] = {
        character.id: [] for character, _org in rows
    }
    if tags_by_id:
        tag_result = await session.execute(
            select(CharacterTag.character_id, CharacterTag.tag)
            .where(CharacterTag.character_id.in_(list(tags_by_id)))
            .order_by(CharacterTag.tag_key)
        )
        for character_id, tag in tag_result.all():
            tags_by_id.setdefault(character_id, []).append(tag)

    items = []
    for character, org in rows:
        created_at = character.created_at
        items.append(
            {
                "id": character.id,
                "name": character.name,
                "created_at": (
                    created_at.isoformat()
                    if hasattr(created_at, "isoformat")
                    else str(created_at)
                ),
                "has_avatar": bool(character.avatar_asset),
                "tags": tags_by_id.get(character.id, []),
                "is_favourite": bool(org.is_favourite)
                if org is not None
                else False,
            }
        )
    return {"total": total, "items": items}


async def list_tags(session: AsyncSession, user_id: str) -> list[dict]:
    """Every tag in the user's library with its character count.

    Display form is the minimum stored tag per key (deterministic);
    sorted by count descending, then key ascending.
    """
    await _seed_missing(session, user_id)
    result = await session.execute(
        select(
            CharacterTag.tag_key,
            func.min(CharacterTag.tag),
            func.count(),
        )
        .where(CharacterTag.user_id == user_id)
        .group_by(CharacterTag.tag_key)
        .order_by(func.count().desc(), CharacterTag.tag_key)
    )
    return [
        {"tag": tag, "tag_key": tag_key, "count": int(count)}
        for tag_key, tag, count in result.all()
    ]
