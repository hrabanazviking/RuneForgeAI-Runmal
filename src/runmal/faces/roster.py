"""Character face roster resolution (P-156, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/CHARACTER_FACE_ROSTER_2026-11-08.md
and hidden_files/P156_SCOUT.md / P156_DESIGN.md.

What the derivation found: P-092 (plugins/expressions.py)
declares expression sets per character and joins each entry
by reference to a P-023 sprite asset through
``binding_report`` - a CHARACTER-keyed read. P-155 (Part X
opener, in flight on the same base) resolves the face
presentation of one CHAT from P-092's chat-keyed
inspect_state, and its design names the per-character
(chat-less) presentation as the open candidate it declined
as the opener: a character roster for clients that hold a
character before - or without - any chat (a character
page, a roster, a picker). What did not exist - and what
lives here - is that resolution:

- every declared entry resolved to a renderable descriptor
  in the same shape P-155's presentation descriptors use
  (the P-092 binding row verbatim in substance - entry,
  bound, problem, asset facts - plus the P-023 content and
  thumbnail roads as URL data, present only when bound);
- the roster classified under a closed state law
  (ROSTER_STATES) that says honestly whether the character
  has anything renderable at all;
- the declared default and the character's avatar named as
  fallback DATA - never applied, never substituted.

Honest boundaries: Runmal renders NOTHING here, and this
document names NO current face. Selection is per chat and
always an explicit act (P-092's standing law); a roster
names what a character CAN show, never what some chat is
showing - that is P-155's chat presentation document. This
module draws, composites, animates and generates nothing,
reads no sprite bytes, selects nothing, applies no default
and scans no message text. It is a pure read over the
owning surfaces: P-092 binding_report is composed
verbatim, the character facts are the character service's
own, and no second binding, selection or asset law is
invented. No store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

ROSTER_SCHEMA = "runmal-p156-character-face-roster-v1"

STATE_READY = "ready"
STATE_NO_RENDERABLE = "no_renderable"
STATE_EMPTY_SET = "empty_set"
STATE_NO_SET = "no_set"
ROSTER_STATES = frozenset({
    STATE_READY, STATE_NO_RENDERABLE, STATE_EMPTY_SET,
    STATE_NO_SET,
})

SELECTION_SCOPE = "per_chat"

NOTES = (
    "Runmal renders nothing: this roster is presentation "
    "data a client renders; it carries no image bytes - "
    "the content and thumbnail URLs are the P-023 roads "
    "a client fetches.",
    "This roster names no current face: expression "
    "selection is per chat and stays P-092's explicit "
    "act - this read selects nothing, applies no "
    "declared default, and scans no message text to "
    "guess an expression. A chat's current face is the "
    "P-155 presentation document's to name.",
    "The declared default rides as fallback data only; "
    "it is never applied or silently substituted by "
    "this read.",
    "A bound entry's thumbnail road answers honestly: "
    "it serves a thumbnail only when the asset's P-023 "
    "thumbnail_status is ready, and 404s otherwise - "
    "the original bytes are never served dressed as "
    "a thumbnail.",
    "Pure read: this surface stores, generates and "
    "animates nothing; sets, selections and sprite "
    "bytes stay with P-092 and P-023.",
)


def _asset_urls(character_id: str,
                asset: dict | None) -> tuple[str | None, str | None]:
    if not asset:
        return None, None
    asset_id = asset.get("id")
    if not asset_id:
        return None, None
    base = f"/api/v1/characters/{character_id}/assets/{asset_id}"
    return f"{base}/content", f"{base}/thumbnail"


def _descriptor(character_id: str, row: dict) -> dict:
    entry = row["entry"]
    bound = bool(row["bound"])
    asset = row["asset"]
    content_url, thumbnail_url = (
        _asset_urls(character_id, asset) if bound else (None, None))
    return {
        "name": entry["name"],
        "label": entry["label"],
        "notes": entry["notes"],
        "bound": bound,
        "problem": row["problem"],
        "asset": asset,
        "renderable": bound,
        "content_url": content_url,
        "thumbnail_url": thumbnail_url,
    }


async def resolve_character_roster(session, user_id: str,
                                   character_id: str,
                                   *, base_dir: Path | None = None,
                                   ) -> dict | None:
    """The face roster document for one character.

    None when the character is missing or foreign (P-092's
    binding law - existence never leaks). Otherwise the
    envelope described in the module docstring: P-092's
    binding report composed verbatim in substance, every
    entry resolved to a roster descriptor, the roster
    classified under ROSTER_STATES, and the fallbacks
    named as data. The document carries no current face:
    selection is per chat.
    """
    from runmal.characters.service import (
        character_to_dict, get_character)
    from runmal.plugins import expressions as ex

    report = await ex.binding_report(
        session, user_id, character_id, base_dir=base_dir)
    if report is None:
        return None
    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    entries = [_descriptor(character_id, row)
               for row in report["entries"]]
    by_name = {row["name"]: row for row in entries}
    renderable_count = sum(1 for row in entries if row["renderable"])
    expr_set = report["set"]
    if expr_set is None:
        state = STATE_NO_SET
    elif not entries:
        state = STATE_EMPTY_SET
    elif renderable_count:
        state = STATE_READY
    else:
        state = STATE_NO_RENDERABLE
    default_entry = None
    if expr_set is not None and expr_set.get("default") is not None:
        default_entry = by_name.get(expr_set["default"])
    character_data = character_to_dict(character)
    avatar = {"has_avatar": False, "avatar_asset": None,
              "avatar_url": None}
    if character_data["has_avatar"]:
        avatar = {
            "has_avatar": True,
            "avatar_asset": character_data["avatar_asset"],
            "avatar_url": f"/api/v1/characters/{character_id}/avatar",
        }
    return {
        "schema": ROSTER_SCHEMA,
        "character_id": character_id,
        "character": character_data,
        "state": state,
        "set": expr_set,
        "entries": entries,
        "entry_count": report["entry_count"],
        "bound_count": report["bound_count"],
        "renderable_count": renderable_count,
        "unbound_count": len(entries) - renderable_count,
        "selection_scope": SELECTION_SCOPE,
        "default_entry": default_entry,
        "avatar": avatar,
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "ROSTER_SCHEMA", "ROSTER_STATES",
    "SELECTION_SCOPE", "STATE_EMPTY_SET", "STATE_NO_RENDERABLE",
    "STATE_NO_SET", "STATE_READY", "resolve_character_roster",
]
