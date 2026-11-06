"""P-039 character-book binding -- a card's own lorebook travels with it.

A card's own lorebook travels with it: it is materialised on
character creation from the embedded ``character_book``, serialised
back for export, and merges with the world lorebook by DECLARED
precedence.

The binding is the single row that links one character to the
lorebook that was materialised (or otherwise chosen) for it, and it
records the precedence that orders that character book against a
world lorebook when the two are merged for a preview / activation.

Pure helpers in this module (precedence vocabulary, embedded-book
entry normalisation, and the entry-dict merge) carry no DB, I/O or
randomness: the same inputs always produce the same merged order
and the same shadowed list. The async service functions below them
are ownership-scoped in the same way as the character and lorebook
services: a character or lorebook the caller does not own is
indistinguishable from one that does not exist.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Character, CharacterBookBinding, Lorebook, LoreEntry
from runmal.lorebooks.groups import normalise_group_weight, normalise_inclusion_group
from runmal.lorebooks.logic import (
    DEFAULT_SELECTIVE_LOGIC,
    SELECTIVE_LOGICS,
    normalise_selective_logic,
    selective_logic_from_code,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.rng import normalise_probability
from runmal.lorebooks.service import entry_to_dict, lorebook_to_dict

__all__ = [
    "PRECEDENCE_CHARACTER_FIRST",
    "PRECEDENCE_WORLD_FIRST",
    "PRECEDENCE_PRIORITY",
    "PRECEDENCES",
    "DEFAULT_PRECEDENCE",
    "check_precedence",
    "normalise_precedence",
    "character_book_entries",
    "normalise_book_entry",
    "merge_entry_dicts",
    "binding_to_dict",
    "get_binding",
    "get_binding_row",
    "bind_book",
    "set_precedence",
    "unbind",
    "materialise_character_book",
    "serialise_bound_book",
    "merged_preview",
]

PRECEDENCE_CHARACTER_FIRST = "character_first"
PRECEDENCE_WORLD_FIRST = "world_first"
PRECEDENCE_PRIORITY = "priority"

PRECEDENCES = frozenset(
    {PRECEDENCE_CHARACTER_FIRST, PRECEDENCE_WORLD_FIRST, PRECEDENCE_PRIORITY}
)

DEFAULT_PRECEDENCE = PRECEDENCE_CHARACTER_FIRST

_POSITIONS = frozenset({"before_char", "after_char", "at_depth"})
_POSITION_BY_CODE = {0: "before_char", 1: "after_char", 4: "at_depth"}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def check_precedence(value) -> str:
    """Strict validation: return ``value`` if it is a canonical precedence.

    Mirrors the strict checkers in lorebooks/rng.py and logic.py:
    no defaulting, no case folding, no stripping -- anything that is
    not exactly one of the canonical names raises ValueError.
    """
    if isinstance(value, str) and value in PRECEDENCES:
        return value
    raise ValueError(
        f"invalid precedence: {value!r} (valid: {sorted(PRECEDENCES)})"
    )


def normalise_precedence(value) -> str:
    """Tolerant precedence normaliser: None -> default, else strict-ish.

    Strings are stripped and lower-cased before lookup; a string
    that does not name a precedence (and any non-string other than
    None) raises ValueError rather than silently inventing one.
    """
    if value is None:
        return DEFAULT_PRECEDENCE
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in PRECEDENCES:
            return candidate
    raise ValueError(
        f"invalid precedence: {value!r} (valid: {sorted(PRECEDENCES)})"
    )


def _as_int(value, default: int) -> int:
    """Tolerant int coercion, mirroring lorebooks/transfer._as_int.

    Defined locally rather than imported from transfer so this
    module does not pull in transfer (and, through it, the safety /
    import stack) -- no import cycle is created either way, but the
    local copy keeps the dependency surface to service/preview and
    the pure normalisers, exactly as logic.selective_logic_from_code
    mirrors the same discipline locally.
    """
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value)) if ("." in value or "e" in value.lower()) else int(value)
        except ValueError:
            return default
    return default


def _nonneg_int(value, default: int = 0) -> int:
    result = _as_int(value, default)
    return result if result >= 0 else default


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


def _bool_field(raw: dict, names, default: bool) -> bool:
    for name in names:
        if name in raw and raw[name] is not None:
            return bool(raw[name])
    return default


def character_book_entries(book) -> list:
    """Raw entries of an embedded character book, in either shape.

    List form (``entries: [...]``) returns a copy of the list;
    uid-dict form (``entries: {uid: {...}, ...}``, the world-info /
    character-card shape) returns the dict values. Anything else --
    a non-dict book, a missing ``entries``, or an ``entries`` of
    neither shape -- returns [].
    """
    if not isinstance(book, dict):
        return []
    entries = book.get("entries")
    if isinstance(entries, list):
        return list(entries)
    if isinstance(entries, dict):
        return list(entries.values())
    return []


def _normalise_position(value) -> str:
    if isinstance(value, str):
        candidate = value.strip().lower()
        return candidate if candidate in _POSITIONS else "before_char"
    if isinstance(value, bool):
        return "before_char"
    if isinstance(value, int):
        return _POSITION_BY_CODE.get(value, "before_char")
    if isinstance(value, float) and value.is_integer():
        return _POSITION_BY_CODE.get(int(value), "before_char")
    return "before_char"


def _normalise_selective_logic(raw: dict) -> str:
    for key in ("selective_logic", "selectiveLogic"):
        if key in raw and raw[key] is not None:
            value = raw[key]
            if isinstance(value, str) and value in SELECTIVE_LOGICS:
                return value
            if isinstance(value, str):
                stripped = value.strip()
                if stripped in SELECTIVE_LOGICS:
                    return stripped
                try:
                    int(stripped)
                except ValueError:
                    return normalise_selective_logic(value)
                return selective_logic_from_code(value)
            return selective_logic_from_code(value)
    return DEFAULT_SELECTIVE_LOGIC


def _priority_of_raw(raw: dict) -> int:
    for key in ("priority", "insertion_order", "order"):
        if key in raw and raw[key] is not None:
            return _as_int(raw[key], 100)
    return 100


def _prompt_count(raw: dict, native: str, alias: str) -> int:
    if native in raw and raw[native] is not None:
        return _nonneg_int(raw[native], 0)
    if alias in raw and raw[alias] is not None:
        return _nonneg_int(raw[alias], 0)
    return 0


def normalise_book_entry(raw: dict) -> dict:
    """Normalise one embedded character-book entry to the native shape.

    Accepts both the native field names and the world-info /
    character-card names (``key`` / ``keysecondary`` / ``comment`` /
    ``disable`` / ``order`` / ``selectiveLogic`` / ``group`` /
    ``groupWeight`` / ``caseSensitive`` / ``matchWholeWords`` /
    ``sticky`` / ``cooldown`` / ``delay``). Non-dict input raises
    ValueError. The result carries exactly the native entry fields
    that a LoreEntry row is built from in materialisation.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"character book entry must be an object: {raw!r}")
    if "enabled" in raw and raw["enabled"] is not None:
        enabled = bool(raw["enabled"])
    else:
        enabled = not bool(raw.get("disable", False))
    if raw.get("useProbability") is not None and not bool(raw.get("useProbability")):
        probability = 100
    else:
        probability = normalise_probability(raw.get("probability"))
    if "group_weight" in raw and raw["group_weight"] is not None:
        group_weight = normalise_group_weight(raw["group_weight"])
    elif "groupWeight" in raw and raw["groupWeight"] is not None:
        group_weight = normalise_group_weight(raw["groupWeight"])
    else:
        group_weight = normalise_group_weight(None)
    return {
        "name": _text(raw.get("name") or raw.get("comment") or ""),
        "content": _text(raw.get("content") or ""),
        "keys": _str_list(raw.get("keys") or raw.get("key")),
        "secondary_keys": _str_list(
            raw.get("secondary_keys") or raw.get("keysecondary")
        ),
        "selective_logic": _normalise_selective_logic(raw),
        "constant": bool(raw.get("constant", False)),
        "enabled": enabled,
        "priority": _priority_of_raw(raw),
        "position": _normalise_position(raw.get("position")),
        "case_sensitive": _bool_field(
            raw, ("case_sensitive", "caseSensitive"), False
        ),
        "whole_word": _bool_field(
            raw, ("whole_word", "matchWholeWords", "match_whole_words"), True
        ),
        "sticky_prompts": _prompt_count(raw, "sticky_prompts", "sticky"),
        "cooldown_prompts": _prompt_count(raw, "cooldown_prompts", "cooldown"),
        "delay_prompts": _prompt_count(raw, "delay_prompts", "delay"),
        "inclusion_group": normalise_inclusion_group(
            raw.get("inclusion_group") or raw.get("group") or ""
        ),
        "group_weight": group_weight,
        "probability": probability,
    }


def _entry_id(entry: dict) -> str:
    return _text(entry.get("id") or "")


def _entry_name(entry: dict) -> str:
    return _text(entry.get("name") or "")


def _entry_priority(entry: dict) -> int:
    value = entry.get("priority")
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return _as_int(value, 0)


def _collision_key(entry: dict) -> str:
    return _entry_name(entry).strip().casefold()


def merge_entry_dicts(world_entries, character_entries, precedence) -> dict:
    """Merge world + character entry dicts by declared precedence. PURE.

    Inputs are entry_to_dict-shaped dicts (each with id / name /
    priority). Inputs are never mutated: every returned entry is a
    copy tagged with ``scope`` ("world" or "character").

    Collision key is the stripped, case-folded name for non-empty
    names; empty names never collide. When a name is present in
    BOTH scopes, exactly one entry for that name is kept:
    character_first keeps the character entry, world_first keeps
    the world entry, and priority keeps the higher-priority entry
    (a tie keeps the character entry, as declared). Every dropped
    entry of such a cross-scope collision is reported in
    ``shadowed`` with its kept/dropped provenance. Duplicate names
    within a single scope are not a cross-scope collision and are
    all kept.

    Winners are ordered deterministically and each winner gains
    ``precedence_rank`` equal to its index in the merged order:
    character_first sorts by (character scope first, -priority,
    name case-folded, id); world_first mirrors the scope rank;
    priority sorts by (-priority, character scope first, name
    case-folded, id).
    """
    precedence = normalise_precedence(precedence)
    tagged: list[dict] = []
    for scope, entries in (("world", world_entries), ("character", character_entries)):
        for entry in entries or []:
            copy = dict(entry)
            copy["scope"] = scope
            tagged.append(copy)

    def _scope_rank(entry: dict, first_scope: str) -> int:
        return 0 if entry["scope"] == first_scope else 1

    if precedence == PRECEDENCE_CHARACTER_FIRST:
        def rank_key(e):
            return (
                _scope_rank(e, "character"),
                -_entry_priority(e),
                _entry_name(e).casefold(),
                _entry_id(e),
            )
    elif precedence == PRECEDENCE_WORLD_FIRST:
        def rank_key(e):
            return (
                _scope_rank(e, "world"),
                -_entry_priority(e),
                _entry_name(e).casefold(),
                _entry_id(e),
            )
    else:  # PRECEDENCE_PRIORITY
        def rank_key(e):
            return (
                -_entry_priority(e),
                _scope_rank(e, "character"),
                _entry_name(e).casefold(),
                _entry_id(e),
            )

    groups: dict[str, list[int]] = {}
    for index, entry in enumerate(tagged):
        key = _collision_key(entry)
        if key:
            groups.setdefault(key, []).append(index)

    dropped_indexes: set[int] = set()
    shadowed: list[dict] = []
    for key in sorted(groups):
        indexes = groups[key]
        if len(indexes) < 2:
            continue
        members = [(i, tagged[i]) for i in indexes]
        if {m["scope"] for _, m in members} != {"world", "character"}:
            continue
        ordered = sorted(members, key=lambda pair: rank_key(pair[1]))
        winner = ordered[0][1]
        for loser_index, loser in ordered[1:]:
            dropped_indexes.add(loser_index)
            shadowed.append(
                {
                    "name": _entry_name(loser),
                    "kept_scope": winner["scope"],
                    "dropped_scope": loser["scope"],
                    "kept_id": _entry_id(winner),
                    "dropped_id": _entry_id(loser),
                    "reason": "name_collision",
                }
            )
    winners = [e for i, e in enumerate(tagged) if i not in dropped_indexes]
    winners.sort(key=rank_key)
    for rank, entry in enumerate(winners):
        entry["precedence_rank"] = rank
    return {"entries": winners, "shadowed": shadowed}


def binding_to_dict(binding, lorebook=None, entry_count=None) -> dict:
    """JSON-shaped binding record, with lorebook summary when given."""
    result = {
        "id": getattr(binding, "id", None),
        "character_id": getattr(binding, "character_id", None),
        "lorebook_id": getattr(binding, "lorebook_id", None),
        "precedence": getattr(binding, "precedence", None) or DEFAULT_PRECEDENCE,
        "created_at": _iso(getattr(binding, "created_at", None)),
        "updated_at": _iso(getattr(binding, "updated_at", None)),
    }
    if lorebook is not None:
        result["lorebook"] = lorebook_to_dict(
            lorebook, entry_count if entry_count is not None else 0
        )
    elif entry_count is not None:
        result["entry_count"] = entry_count
    return result


async def _get_owned_character(session: AsyncSession, user_id: str, character_id: str):
    """Local mirror of characters/service.get_character (live rows only)."""
    result = await session.execute(
        select(Character).where(
            Character.id == character_id,
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _get_owned_book(session: AsyncSession, user_id: str, book_id: str):
    result = await session.execute(
        select(Lorebook).where(Lorebook.id == book_id, Lorebook.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _list_entries_service_order(session: AsyncSession, book_id: str) -> list:
    """Entries in lorebooks/service.list_entries order."""
    result = await session.execute(
        select(LoreEntry)
        .where(LoreEntry.lorebook_id == book_id)
        .order_by(LoreEntry.priority.desc(), LoreEntry.created_at)
    )
    return list(result.scalars().all())


async def get_binding(session: AsyncSession, user_id: str, character_id: str):
    """The character's binding, or None (unowned character / no binding)."""
    if await _get_owned_character(session, user_id, character_id) is None:
        return None
    return await get_binding_row(session, character_id)


async def get_binding_row(session: AsyncSession, character_id: str):
    """The binding row for a character, with no ownership check (internal)."""
    result = await session.execute(
        select(CharacterBookBinding).where(
            CharacterBookBinding.character_id == character_id
        )
    )
    return result.scalar_one_or_none()


async def bind_book(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    lorebook_id: str,
    precedence=None,
    *,
    commit: bool = True,
):
    """Bind (or re-bind) a character to a lorebook, upserting the binding."""
    character = await _get_owned_character(session, user_id, character_id)
    if character is None:
        raise ValueError("character not found")
    book = await _get_owned_book(session, user_id, lorebook_id)
    if book is None:
        raise ValueError("lorebook not found")
    normalised = normalise_precedence(precedence)
    binding = await get_binding_row(session, character_id)
    if binding is None:
        binding = CharacterBookBinding(
            character_id=character_id,
            lorebook_id=lorebook_id,
            precedence=normalised,
        )
        session.add(binding)
    else:
        binding.lorebook_id = lorebook_id
        binding.precedence = normalised
        binding.updated_at = _now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return binding


async def set_precedence(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    precedence,
    *,
    commit: bool = True,
):
    """Update a bound character's precedence; None when there is no binding."""
    normalised = normalise_precedence(precedence)
    binding = await get_binding(session, user_id, character_id)
    if binding is None:
        return None
    binding.precedence = normalised
    binding.updated_at = _now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return binding


async def unbind(
    session: AsyncSession, user_id: str, character_id: str, *, commit: bool = True
) -> bool:
    """Delete the binding row only; the lorebook itself survives."""
    binding = await get_binding(session, user_id, character_id)
    if binding is None:
        return False
    await session.execute(
        delete(CharacterBookBinding).where(CharacterBookBinding.id == binding.id)
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return True


async def materialise_character_book(
    session: AsyncSession, user_id: str, character, book, precedence=None
):
    """Materialise an embedded character book into a real lorebook + binding.

    Returns None when the book carries no (usable) entries. Creates
    the Lorebook, one LoreEntry per normalised embedded entry, and
    the binding, flushing but NEVER committing -- the caller owns
    the transaction (this runs inside character creation).
    """
    normalised_precedence = normalise_precedence(precedence)
    raw_entries = character_book_entries(book)
    normalised_entries = [
        normalise_book_entry(raw) for raw in raw_entries if isinstance(raw, dict)
    ]
    if not normalised_entries:
        return None
    if isinstance(book, dict):
        book_name = _text(book.get("name") or "")
        description = _text(book.get("description") or "")
        scan_depth_raw = book.get("scan_depth")
        token_budget_raw = book.get("token_budget")
    else:
        book_name = ""
        description = ""
        scan_depth_raw = None
        token_budget_raw = None
    if not book_name:
        character_name = _text(getattr(character, "name", "") or "character")
        book_name = f"{character_name} \u2014 character book"
    scan_depth = _as_int(scan_depth_raw, 4)
    if scan_depth < 1:
        scan_depth = 4
    if token_budget_raw is None:
        token_budget = None
    else:
        parsed_budget = _as_int(token_budget_raw, 0)
        token_budget = parsed_budget if parsed_budget >= 1 else None
    lorebook = Lorebook(
        user_id=user_id,
        name=book_name[:200],
        description=description,
        scan_depth=scan_depth,
        token_budget=token_budget,
    )
    session.add(lorebook)
    await session.flush()
    for fields in normalised_entries:
        session.add(
            LoreEntry(
                lorebook_id=lorebook.id,
                user_id=user_id,
                name=fields["name"][:200],
                content=fields["content"],
                keys_json=json.dumps(fields["keys"]),
                secondary_keys_json=json.dumps(fields["secondary_keys"]),
                selective_logic=fields["selective_logic"],
                inclusion_group=fields["inclusion_group"],
                group_weight=fields["group_weight"],
                probability=fields["probability"],
                priority=fields["priority"],
                position=fields["position"],
                enabled=fields["enabled"],
                constant=fields["constant"],
                case_sensitive=fields["case_sensitive"],
                whole_word=fields["whole_word"],
                sticky_prompts=fields["sticky_prompts"],
                cooldown_prompts=fields["cooldown_prompts"],
                delay_prompts=fields["delay_prompts"],
            )
        )
    await session.flush()
    character_id = getattr(character, "id", character)
    binding = await get_binding_row(session, character_id)
    if binding is None:
        binding = CharacterBookBinding(
            character_id=character_id,
            lorebook_id=lorebook.id,
            precedence=normalised_precedence,
        )
        session.add(binding)
    else:
        binding.lorebook_id = lorebook.id
        binding.precedence = normalised_precedence
        binding.updated_at = _now()
    await session.flush()
    return binding


async def serialise_bound_book(session: AsyncSession, binding) -> dict:
    """Serialise a binding's lorebook back to the character_book shape."""
    if binding is None:
        raise ValueError("lorebook not found")
    result = await session.execute(
        select(Lorebook).where(Lorebook.id == binding.lorebook_id)
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise ValueError("lorebook not found")
    entries_result = await session.execute(
        select(LoreEntry)
        .where(LoreEntry.lorebook_id == book.id)
        .order_by(LoreEntry.created_at)
    )
    entries = list(entries_result.scalars().all())
    serialised_entries = []
    for index, entry in enumerate(entries):
        data = entry_to_dict(entry)
        serialised_entries.append(
            {
                "keys": data["keys"],
                "secondary_keys": data["secondary_keys"],
                "content": data["content"],
                "comment": data["name"],
                "name": data["name"],
                "enabled": data["enabled"],
                "insertion_order": data["priority"],
                "priority": data["priority"],
                "case_sensitive": data["case_sensitive"],
                "whole_word": data["whole_word"],
                "constant": data["constant"],
                "selective_logic": data["selective_logic"],
                "position": data["position"],
                "id": index,
            }
        )
    return {
        "name": book.name,
        "description": book.description,
        "scan_depth": book.scan_depth,
        "token_budget": book.token_budget,
        "recursive_scanning": False,
        "extensions": {},
        "entries": serialised_entries,
    }


async def merged_preview(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    world_lorebook_id: str,
    messages,
    scan_depth=None,
    token_budget=None,
    seed=None,
):
    """Preview activation over the merged world + character books.

    None when the character is not owned by the caller. Raises
    ValueError("character has no bound lorebook") when the owned
    character has no binding, and ValueError("lorebook not found")
    when the world lorebook is not owned by the caller.
    """
    character = await _get_owned_character(session, user_id, character_id)
    if character is None:
        return None
    binding = await get_binding_row(session, character_id)
    if binding is None:
        raise ValueError("character has no bound lorebook")
    world_book = await _get_owned_book(session, user_id, world_lorebook_id)
    if world_book is None:
        raise ValueError("lorebook not found")
    character_book = await _get_owned_book(session, user_id, binding.lorebook_id)
    if character_book is None:
        raise ValueError("lorebook not found")
    world_rows = await _list_entries_service_order(session, world_book.id)
    character_rows = await _list_entries_service_order(session, character_book.id)
    merged = merge_entry_dicts(
        [entry_to_dict(row) for row in world_rows],
        [entry_to_dict(row) for row in character_rows],
        getattr(binding, "precedence", None) or DEFAULT_PRECEDENCE,
    )
    orm_by_id = {str(row.id): row for row in list(world_rows) + list(character_rows)}
    scope_by_id = {
        _entry_id(entry): entry["scope"] for entry in merged["entries"]
    }
    winners = [
        orm_by_id[_entry_id(entry)]
        for entry in merged["entries"]
        if _entry_id(entry) in orm_by_id
    ]
    if scan_depth is not None:
        effective_scan_depth = scan_depth
    elif getattr(world_book, "scan_depth", None) is not None:
        effective_scan_depth = world_book.scan_depth
    else:
        effective_scan_depth = character_book.scan_depth
    if token_budget is not None:
        effective_token_budget = token_budget
    elif getattr(world_book, "token_budget", None) is not None:
        effective_token_budget = world_book.token_budget
    else:
        effective_token_budget = character_book.token_budget
    result = preview_activation(
        winners, messages, effective_scan_depth, effective_token_budget, seed=seed
    )
    for row in result.get("entries", []):
        row["scope"] = scope_by_id.get(_text(row.get("entry_id") or ""))
    result["precedence"] = getattr(binding, "precedence", None) or DEFAULT_PRECEDENCE
    result["character_lorebook_id"] = binding.lorebook_id
    result["world_lorebook_id"] = world_lorebook_id
    result["shadowed"] = merged["shadowed"]
    result["merged"] = True
    return result
