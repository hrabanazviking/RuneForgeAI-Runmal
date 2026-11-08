"""Message-action pure contracts (P-068, PROVISIONAL 0038).

Two pure data contracts live here; the service layer owns the rows.

Variant history -- when a message is edited, the content being
replaced is NEVER silently overwritten: it is appended to the
message's variant history first. The history is ONE JSON document
(``messages.variant_history_json``), a list of entries in edit
order, oldest first::

    {"content": <replaced text>, "edited_at": <iso8601>,
     "swipe_id": <deck index that was active>}

Composition with P-065: the swipe deck holds ALTERNATES (parallel
candidate contents); the variant history holds VERSIONS (the
lineage of the active alternate over time). Editing replaces the
ACTIVE alternate in the deck -- the deck invariant
``content == swipes[swipe_id]`` is untouched -- and the replaced
text moves here. An edit whose new content equals the active
content is a no-op (no history entry, no event). The history is
capped: beyond ``MAX_VARIANTS`` entries the oldest are dropped
(the cap is recorded implicitly by the surviving order; the most
recent edit is always retained). Defensive reads mirror the deck
law: corrupt stored data reads as an empty history, never raises.

Positions -- a chat's message order is ``messages.position`` once
materialised. Legacy rows carry ``position IS NULL`` and order by
``created_at`` (the pre-P-068 rule). The first move (or a delete in
a materialised chat) materialises the whole chat: positions are
renumbered ``0..n-1`` in current order, so positions are always
unique and contiguous inside a materialised chat. Move targets
are STRICT indexes (like ``swipes.select_index``): out-of-range
or non-int targets raise ``ValueError`` -- no clamping, no wrap.
"""

from __future__ import annotations

import json

__all__ = [
    "MAX_VARIANTS",
    "move_index",
    "parse_history",
    "record_edit",
    "validate_move_target",
]

MAX_VARIANTS = 50


def parse_history(raw: str | None) -> list[dict]:
    """Defensively decode a stored variant-history document.

    Returns the list of well-formed entries (dicts with a string
    ``content``); anything else -- None, corrupt JSON, not a list,
    malformed entries -- is dropped. Never raises.
    """
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content")
        if not isinstance(content, str) or not content:
            continue
        out.append({
            "content": content,
            "edited_at": entry.get("edited_at"),
            "swipe_id": entry.get("swipe_id"),
        })
    return out


def record_edit(history: list[dict], replaced: str, edited_at: str,
                swipe_id: int) -> list[dict]:
    """Return a NEW history with the replaced content appended.

    The replaced content must be a non-empty string (``ValueError``
    otherwise). The result is capped at ``MAX_VARIANTS`` entries,
    dropping the oldest. The input list is never mutated.
    """
    if not isinstance(replaced, str) or not replaced:
        raise ValueError("a variant must be a non-empty string")
    new = list(history)
    new.append({"content": replaced, "edited_at": edited_at,
                "swipe_id": swipe_id})
    if len(new) > MAX_VARIANTS:
        new = new[-MAX_VARIANTS:]
    return new


def validate_move_target(count: int, target: object) -> int:
    """Strict move-target validation -- NO clamping, NO wrap.

    ``target`` must be a real int (bools rejected) with
    ``0 <= target < count``; anything else raises ``ValueError``.
    Returns the target unchanged on success.
    """
    if isinstance(target, bool) or not isinstance(target, int):
        raise ValueError("move target must be an int")
    if count <= 0:
        raise ValueError("cannot move within an empty chat")
    if not 0 <= target < count:
        raise ValueError(f"move target out of range: {target}")
    return target


def move_index(order: list, from_index: int, to_index: int) -> list:
    """Return a NEW list with the element at ``from_index`` moved to
    ``to_index``; all other elements keep their relative order."""
    new = list(order)
    item = new.pop(from_index)
    new.insert(to_index, item)
    return new
