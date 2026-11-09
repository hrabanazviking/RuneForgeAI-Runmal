"""Face presentation resolution (P-155, Part X opener - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/FACE_PRESENTATION_2026-11-08.md
and hidden_files/P155_SCOUT.md / P155_DESIGN.md.

What the derivation found: P-092 (plugins/expressions.py)
declares expression sets per character, binds each entry by
reference to a P-023 sprite asset, and selects the current
expression per chat with provenance - and states plainly
that no renderer is invented there because Part X owns
rendering, naming inspect_state as "the inspectable surface
Part X reads". P-023 stores the sprites and serves their
bytes through its content / thumbnail roads. What did not
exist - and what lives here - is the RESOLUTION of that
record into the one presentation document a client renders:

- every declared entry resolved to a renderable descriptor
  (the P-092 binding row verbatim in substance - entry,
  bound, problem, asset facts - plus the P-023 content and
  thumbnail roads as URL data, present only when bound);
- the chat's current face classified under a closed state
  law (PRESENTATION_STATES) with the current entry's
  descriptor named as ``face`` only when it is bound;
- the declared default and the character's avatar named as
  fallback DATA - never silently substituted for a face
  that is not ready.

Honest boundaries: Runmal renders NOTHING here. This module
draws, composites, animates and generates nothing, reads
no sprite bytes, selects nothing, applies no default and
scans no message text (P-092's standing laws). It is a pure
read over the owning surfaces: P-092 inspect_state is
composed verbatim, the avatar facts are get_character's own,
and no second binding, selection or asset law is invented.
No store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

PRESENTATION_SCHEMA = "runmal-p155-face-presentation-v1"

STATE_READY = "ready"
STATE_CURRENT_UNBOUND = "current_unbound"
STATE_NO_SELECTION = "no_selection"
STATE_NO_SET = "no_set"
STATE_NO_CHARACTER = "no_character"
PRESENTATION_STATES = frozenset({
    STATE_READY, STATE_CURRENT_UNBOUND, STATE_NO_SELECTION,
    STATE_NO_SET, STATE_NO_CHARACTER,
})
PROBLEM_NOT_DECLARED = "not_declared"

NOTES = (
    "Runmal renders nothing: this document is presentation "
    "data a client renders; it carries no image bytes - the "
    "content and thumbnail URLs are the P-023 roads a client "
    "fetches.",
    "Selection stays P-092's explicit act: this read selects "
    "nothing, applies no declared default, and scans no "
    "message text to guess an expression.",
    "face is the current selection only when it is bound; "
    "when face is None the fallbacks are named as data and "
    "are never silently substituted.",
    "A bound entry's thumbnail road answers honestly: it "
    "serves a thumbnail only when the asset's P-023 "
    "thumbnail_status is ready, and 404s otherwise - the "
    "original bytes are never served dressed as a thumbnail.",
    "Pure read: this surface stores, generates and animates "
    "nothing; sets, selections and sprite bytes stay with "
    "P-092 and P-023.",
)


def _asset_urls(character_id: str, asset: dict | None) -> tuple[str | None, str | None]:
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


async def resolve_presentation(session, user_id: str, chat_id: str,
                               *, base_dir: Path | None = None) -> dict | None:
    """The face presentation document for one chat.

    None when the chat is missing or foreign (P-092's
    inspect law - existence never leaks). Otherwise the
    envelope described in the module docstring: P-092's
    inspect document composed verbatim in substance, every
    entry resolved to a presentation descriptor, the
    current face classified under PRESENTATION_STATES, and
    the fallbacks named as data.
    """
    from runmal.characters.service import get_character
    from runmal.plugins import expressions as ex

    inspected = await ex.inspect_state(
        session, user_id, chat_id, base_dir=base_dir)
    if inspected is None:
        return None
    character_id = inspected["character_id"]
    entries = [
        _descriptor(character_id, row)
        for row in inspected["bindings"]
    ] if character_id else []
    by_name = {row["name"]: row for row in entries}
    current = inspected["current"]
    current_binding = inspected["current_binding"]
    face = None
    current_problem = None
    if character_id is None:
        state = STATE_NO_CHARACTER
    elif (current is not None and current_binding is not None
          and current_binding["bound"]):
        state = STATE_READY
        face = by_name.get(current["expression"])
    elif current is not None:
        # A selection outliving its set (set deleted or
        # replaced after selection) names no entry in the
        # current set: not_declared, never a vanished face.
        state = STATE_CURRENT_UNBOUND
        current_problem = (current_binding["problem"]
                           if current_binding is not None
                           else PROBLEM_NOT_DECLARED)
    elif inspected["set"] is None:
        state = STATE_NO_SET
    else:
        state = STATE_NO_SELECTION
    default_entry = None
    expr_set = inspected["set"]
    if expr_set is not None and expr_set.get("default") is not None:
        default_entry = by_name.get(expr_set["default"])
    avatar = {"has_avatar": False, "avatar_asset": None,
              "avatar_url": None}
    if character_id is not None:
        character = await get_character(session, user_id, character_id)
        if character is not None and getattr(character, "avatar_asset", None):
            avatar = {
                "has_avatar": True,
                "avatar_asset": character.avatar_asset,
                "avatar_url": f"/api/v1/characters/{character_id}/avatar",
            }
    return {
        "schema": PRESENTATION_SCHEMA,
        "chat_id": inspected["chat_id"],
        "character_id": character_id,
        "state": state,
        "set": expr_set,
        "entries": entries,
        "entry_count": inspected["entry_count"],
        "bound_count": inspected["bound_count"],
        "renderable_count": sum(1 for row in entries if row["renderable"]),
        "current": current,
        "current_problem": current_problem,
        "face": face,
        "fallbacks": {
            "default_entry": default_entry,
            "avatar": avatar,
        },
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "PRESENTATION_SCHEMA", "PRESENTATION_STATES",
    "PROBLEM_NOT_DECLARED", "STATE_CURRENT_UNBOUND",
    "STATE_NO_CHARACTER", "STATE_NO_SELECTION", "STATE_NO_SET",
    "STATE_READY", "resolve_presentation",
]
