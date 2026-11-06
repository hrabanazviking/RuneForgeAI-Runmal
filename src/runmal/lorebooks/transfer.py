"""Lorebook import/export (S304).

Export is Rúnmál's native shape. Import accepts two shapes:

1. **Native** -- ``{"name": ..., "entries": [{...entry fields...}]}`` (what
   export produces; round-trips exactly).
2. **World-info** -- the common SillyTavern-style lorebook shape:
   ``{"entries": {"<uid>": {"key": [...], "keysecondary": [...],
   "content": ..., "comment": <name>, "constant": bool, "disable": bool,
   "order": int, "position": int}}}`` (``entries`` may also be a list).
   Field mapping: key->keys, keysecondary->secondary_keys,
   comment->name, order->priority, disable->not enabled,
   position 0->before_char / 1->after_char / 4->at_depth (anything
   else -> before_char, via placement.normalise_position),
   caseSensitive->case_sensitive, matchWholeWords->whole_word,
   sticky/cooldown/delay -> sticky/cooldown/delay_prompts (P-005),
   selectiveLogic->selective_logic (P-032, codes per
   runmal.lorebooks.logic), group->inclusion_group and
   groupWeight->group_weight (P-034, tolerant coercions per
   runmal.lorebooks.groups; the group string is ONE label),
   vectorized->vectorised (P-035; the native spelling is
   vectorised, and legacy native files may spell it
   "vectorized" - accepted as alias on the native leg).
   probability->probability (P-036, integer percent per
   runmal.lorebooks.rng; an explicit useProbability=false folds
   to 100 -- the gate is off -- because the store carries the
   effective percent, not the flag; the file layer in
   interop.py preserves the flag itself verbatim),
   depth->depth and role->role (P-038, via
   runmal.lorebooks.placement: depth tolerantly an int >= 0 or
   None when undeclared; the world-info role CODE maps to the
   stored role NAME, 0->system / 1->user / 2->assistant, any
   other value -> system; native entries carry depth + the
   role name directly).
   Numeric fields coerce tolerantly: explicit nulls and numeric
   strings in real files mean the default / the number, never a
   crash (P-005). Fields with no Rúnmál home yet (recursion
   flags, groupOverride/useGroupScoring) are still dropped;
   the P-005 corpus test pins that set exactly.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Lorebook, LoreEntry
from runmal.lorebooks import service
from runmal.lorebooks.groups import normalise_group_weight, normalise_inclusion_group
from runmal.lorebooks.logic import normalise_selective_logic, selective_logic_from_code
from runmal.lorebooks.placement import (
    check_depth,
    check_role,
    normalise_depth,
    normalise_position,
    normalise_role,
)
from runmal.lorebooks.rng import DEFAULT_PROBABILITY, normalise_probability
from runmal.safety import SafetyError, validate_json_tree


def export_book(book: dict, entries: list[dict]) -> dict:
    """Serialize a book + its entries (API dicts) to the native shape."""
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": book["name"],
        "description": book.get("description", ""),
        "scan_depth": book.get("scan_depth", 4),
        "token_budget": book.get("token_budget"),
        "entries": [
            {
                "name": e["name"],
                "content": e["content"],
                "keys": e["keys"],
                "secondary_keys": e["secondary_keys"],
                "selective_logic": normalise_selective_logic(e.get("selective_logic")),
                "inclusion_group": normalise_inclusion_group(e.get("inclusion_group")),
                "group_weight": normalise_group_weight(e.get("group_weight")),
                "probability": normalise_probability(e.get("probability")),
                "priority": e["priority"],
                "position": e["position"],
                "depth": normalise_depth(e.get("depth")),
                "role": normalise_role(e.get("role")),
                "enabled": e["enabled"],
                "constant": e["constant"],
                "vectorised": bool(e.get("vectorised", False)),
                "case_sensitive": e["case_sensitive"],
                "whole_word": e["whole_word"],
                "sticky_prompts": e["sticky_prompts"],
                "cooldown_prompts": e["cooldown_prompts"],
                "delay_prompts": e["delay_prompts"],
            }
            for e in entries
        ],
    }


def _as_int(value: object, default: int) -> int:
    """Tolerant int coercion for imported files (P-005).

    Real-world lorebook files carry explicit nulls and occasionally
    numeric strings/floats in integer fields; a null must mean the
    default, never a bare ``TypeError`` escaping ``parse_import``.
    Booleans are not integers here.
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


def _native_entry(raw: dict) -> dict:
    return {
        "name": str(raw.get("name", "")),
        "content": str(raw.get("content", "")),
        "keys": list(raw.get("keys") or []),
        "secondary_keys": list(raw.get("secondary_keys") or []),
        "selective_logic": normalise_selective_logic(raw.get("selective_logic")),
        "inclusion_group": normalise_inclusion_group(raw.get("inclusion_group")),
        "group_weight": normalise_group_weight(raw.get("group_weight")),
        "probability": normalise_probability(raw.get("probability")),
        "priority": _as_int(raw.get("priority"), 100),
        "position": str(raw.get("position", "before_char")),
        "depth": normalise_depth(raw.get("depth")),
        "role": normalise_role(raw.get("role")),
        "enabled": bool(raw.get("enabled", True)),
        "constant": bool(raw.get("constant", False)),
        "vectorised": bool(raw.get("vectorised", raw.get("vectorized", False))),
        "case_sensitive": bool(raw.get("case_sensitive", False)),
        "whole_word": bool(raw.get("whole_word", True)),
        "sticky_prompts": _as_int(raw.get("sticky_prompts"), 0),
        "cooldown_prompts": _as_int(raw.get("cooldown_prompts"), 0),
        "delay_prompts": _as_int(raw.get("delay_prompts"), 0),
    }


def _worldinfo_entry(raw: dict) -> dict:
    position = normalise_position(raw.get("position"))
    keys = raw.get("key") or []
    if isinstance(keys, str):
        keys = [keys]
    secondary = raw.get("keysecondary") or []
    if isinstance(secondary, str):
        secondary = [secondary]
    whole_word = raw.get("matchWholeWords")
    return {
        "name": str(raw.get("comment") or raw.get("name") or ""),
        "content": str(raw.get("content", "")),
        "keys": [str(k) for k in keys],
        "secondary_keys": [str(k) for k in secondary],
        "selective_logic": selective_logic_from_code(raw.get("selectiveLogic")),
        "inclusion_group": normalise_inclusion_group(raw.get("group")),
        "group_weight": normalise_group_weight(raw.get("groupWeight")),
        # P-036: probability is an integer percent; an explicit
        # useProbability=false means the gate is off, which the
        # store expresses as the effective percent 100.
        "probability": (
            DEFAULT_PROBABILITY
            if raw.get("useProbability") is not None
            and not bool(raw.get("useProbability"))
            else normalise_probability(raw.get("probability"))
        ),
        "priority": _as_int(raw.get("order"), 100),
        "position": position,
        "depth": normalise_depth(raw.get("depth")),
        "role": normalise_role(raw.get("role")),
        "enabled": not bool(raw.get("disable", False)),
        "constant": bool(raw.get("constant", False)),
        "vectorised": bool(raw.get("vectorized", False)),
        "case_sensitive": bool(raw.get("caseSensitive", False)),
        # P-005: honour the source's whole-word flag instead of
        # silently forcing it on; absent means the mirror default.
        "whole_word": True if whole_word is None else bool(whole_word),
        # P-005: the timed-effect fields exist on both sides of the
        # mapping (sticky/cooldown/delay <-> *_prompts); carry them.
        "sticky_prompts": _as_int(raw.get("sticky"), 0),
        "cooldown_prompts": _as_int(raw.get("cooldown"), 0),
        "delay_prompts": _as_int(raw.get("delay"), 0),
    }


def parse_import(data: dict) -> tuple[dict, list[dict]]:
    """Parse either import shape into (book fields, entry field dicts)."""
    if not isinstance(data, dict):
        raise ValueError("lorebook import must be a JSON object")
    try:
        validate_json_tree(data)
    except SafetyError as exc:
        raise ValueError(str(exc)) from exc
    raw_entries = data.get("entries")
    if raw_entries is None:
        raise ValueError("lorebook import has no 'entries'")
    if isinstance(raw_entries, dict):
        # world-info: uid-keyed mapping; order by numeric uid for stability
        ordered = [
            raw_entries[k]
            for k in sorted(raw_entries, key=lambda k: (len(str(k)), str(k)))
        ]
        entries = [_worldinfo_entry(e) for e in ordered]
        book = {"name": str(data.get("name") or "Imported lorebook")}
    elif isinstance(raw_entries, list):
        if raw_entries and isinstance(raw_entries[0], dict) and (
            "key" in raw_entries[0] or "keysecondary" in raw_entries[0]
        ):
            entries = [_worldinfo_entry(e) for e in raw_entries]
            book = {"name": str(data.get("name") or "Imported lorebook")}
        else:
            entries = [_native_entry(e) for e in raw_entries]
            book = {
                "name": str(data.get("name") or ""),
                "description": str(data.get("description") or ""),
                "scan_depth": _as_int(data.get("scan_depth"), 4),
                "token_budget": data.get("token_budget"),
            }
    else:
        raise ValueError("'entries' must be an object or a list")
    if not book.get("name"):
        raise ValueError("lorebook import needs a name")
    return book, entries


async def import_book(
    session: AsyncSession, user_id: str, data: dict
) -> Lorebook:
    """Create a lorebook + entries from either import shape."""
    book_fields, entry_fields = parse_import(data)
    book = await service.create_lorebook(
        session,
        user_id,
        name=book_fields["name"],
        description=book_fields.get("description", ""),
        scan_depth=book_fields.get("scan_depth", 4),
        token_budget=book_fields.get("token_budget"),
    )
    for fields in entry_fields:
        await service.create_entry(session, user_id, book.id, **fields)
    return book


def validate_parsed_book(book_fields: dict, entry_fields: list[dict]) -> list[dict]:
    """Validate a parsed book + entries without writing anything.

    Mirrors ``service.create_lorebook`` / ``service.create_entry``
    checks and returns the prepared entry rows (keys encoded, position
    and timing knobs checked). Raises ValueError on the first problem.
    Used by the transactional import (pre-validation before any
    write) and by bulk import's dry run, so a dry run's verdicts match
    a real run's.
    """
    if not book_fields.get("name"):
        raise ValueError("lorebook name must not be empty")
    scan_depth = book_fields.get("scan_depth", 4)
    token_budget = book_fields.get("token_budget")
    if isinstance(scan_depth, bool) or not isinstance(scan_depth, int) or scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and (
        isinstance(token_budget, bool)
        or not isinstance(token_budget, int)
        or token_budget < 1
    ):
        raise ValueError("token_budget must be >= 1")
    prepared: list[dict] = []
    for fields in entry_fields:
        prepared.append(
            {
                "name": fields["name"],
                "content": fields["content"],
                "keys_json": service._encode_keys(fields.get("keys")),
                "secondary_keys_json": service._encode_keys(
                    fields.get("secondary_keys")
                ),
                "selective_logic": normalise_selective_logic(fields.get("selective_logic")),
                "inclusion_group": normalise_inclusion_group(fields.get("inclusion_group")),
                "group_weight": normalise_group_weight(fields.get("group_weight")),
                "probability": normalise_probability(fields.get("probability")),
                "priority": fields["priority"],
                "position": service._check_position(
                    fields.get("position", "before_char")
                ),
                "depth": check_depth(fields.get("depth")),
                "role": check_role(normalise_role(fields.get("role"))),
                "enabled": bool(fields.get("enabled", True)),
                "constant": bool(fields.get("constant", False)),
                "vectorised": bool(fields.get("vectorised", False)),
                "case_sensitive": bool(fields.get("case_sensitive", False)),
                "whole_word": bool(fields.get("whole_word", True)),
                "sticky_prompts": service._check_prompts(
                    "sticky_prompts", fields.get("sticky_prompts", 0)
                ),
                "cooldown_prompts": service._check_prompts(
                    "cooldown_prompts", fields.get("cooldown_prompts", 0)
                ),
                "delay_prompts": service._check_prompts(
                    "delay_prompts", fields.get("delay_prompts", 0)
                ),
            }
        )
    return prepared


async def import_book_transactional(
    session: AsyncSession, user_id: str, data: dict, *, commit: bool = True
) -> Lorebook:
    """Create a lorebook + entries as ONE transaction (P-022).

    Unlike :func:`import_book` - which loops the committing service
    helpers and can leave a partial book behind - this variant
    pre-validates the whole parsed book (every entry's keys, position,
    and timing knobs, mirroring ``service.create_entry``'s checks)
    BEFORE any row is written, then writes book + entries with flush
    only inside a savepoint and commits once. Any failure rolls the
    savepoint (and, for a committing call, the transaction) back, so
    a failed book leaves nothing behind.
    """
    book_fields, entry_fields = parse_import(data)
    # Pre-validate the whole book (fields + every entry) before any write.
    prepared = validate_parsed_book(book_fields, entry_fields)
    name = book_fields["name"]
    description = book_fields.get("description", "")
    scan_depth = book_fields.get("scan_depth", 4)
    token_budget = book_fields.get("token_budget")
    try:
        async with session.begin_nested():
            book = Lorebook(
                user_id=user_id,
                name=name,
                description=description,
                scan_depth=scan_depth,
                token_budget=token_budget,
            )
            session.add(book)
            await session.flush()
            for row in prepared:
                session.add(LoreEntry(lorebook_id=book.id, user_id=user_id, **row))
            await session.flush()
    except Exception:
        if commit:
            await session.rollback()
        raise
    if commit:
        await session.commit()
    return book


# Aliases: the transactional parsed-import variant under its other
# natural names, so callers are not coupled to one spelling.
import_book_atomic = import_book_transactional
import_parsed_book = import_book_transactional
