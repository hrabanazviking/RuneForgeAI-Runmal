"""Expression/sprite plugin surface (P-092).

Roadmap line: "Expression/sprite plugin surface (Part X
builds on it)."

A first-class P-081 citizen carrying the DECLARATION,
SELECTION and INSPECTION surface for a character's
expressions — the surface Part X (avatars) will consume.
The line this slice draws, from the code (P092_SCOUT.md):
P-023 (:mod:`runmal.assets`) already stores expression
SPRITES as character assets of kind ``expression``; this
citizen stores no bytes and copies none. What did not exist
— and what lives here — is the declared SET of named
expressions per character, the CURRENT expression selected
per chat with its provenance receipt, and the binding view
joining each declared name to its P-023 asset (or honestly
reporting it unbound, missing, wrong-kind or not stored).

Sets and selections are durable owner data in the P-089
file idiom — one JSON document at
``data_dir()/expressions/<user_id>.json``, written
atomically (tmp sibling, chmod 0o600, replace). A corrupt
store raises :class:`ExpressionError` and is never silently
reset. No migration: head stays 0041.

Selection semantics (plain): a selection is always an
explicit act. The owner picks a declared name (source
``manual``), a declared default is applied only through
the explicit :func:`apply_default` road (source
``default``), or a caller names its source in the closed
vocabulary (``plugin`` / ``message`` — ``message`` means
the caller asserts a message motivated the choice; this
citizen never scans message text to guess an expression).
Choosing an undeclared name refuses loudly. Every
selection records its provenance receipt — source, actor,
reason, message id, the expression it replaced and when —
and appends to a kept history, so the current state Part X
reads is inspectable end to end, never a bare name.

Honest boundaries: no renderer is invented here (Part X
owns rendering and reads sprite bytes through the P-023
roads itself), no image is generated, no network is
touched, no model is called. Sandbox stance (P-082): only
v1 surface permissions are declared (``chat.read``,
``ui.contribute``; ``chat.write`` is RESERVED and NOT
declared), so the derived resource grant set is EMPTY.
Selections are owner data in the citizen's own store, not
chat writes through the plugin API. Wiring:
:func:`register_plugin` only; ``build_registry`` /
``create_app`` are unchanged. See
docs/EXPRESSION_SPRITE_2026-11-07.md.
"""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.expressions"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "expressions-panel"
STORE_SCHEMA = "runmal-p092-expressions-v1"
STORE_DIR_NAME = "expressions"
MAX_SETS_PER_USER = 200
MAX_ENTRIES_PER_SET = 64
MAX_HISTORY_KEPT = 100
MAX_LABEL_CHARS = 120
MAX_NOTES_CHARS = 500
MAX_REASON_CHARS = 500
SELECTION_SOURCES = frozenset({"manual", "default", "plugin", "message"})
DECLARED_EVENTS = ("chat.created", "chat.deleted")
_ENTRY_FIELDS = frozenset({"name", "label", "asset_id", "notes"})
_SET_FIELDS = frozenset({"character_id", "entries", "default",
                         "created_at", "updated_at"})
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_ID_RE = re.compile(r"[0-9a-fA-F-]{1,64}")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ExpressionError(ValueError):
    """A declaration, store, binding or selection refusal (house 422)."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ExpressionError(f"invalid {what}: {value!r}")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ExpressionError(f"invalid {what}: {value!r}") from None
    return value


def _check_name(value, what: str = "expression name") -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ExpressionError(
            f"{what} must be a slug of 1..64 chars "
            f"([a-z0-9][a-z0-9_-]*): {value!r}")
    return value


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", str(text or "").lower()).strip("-")
    slug = slug.replace("-", "_")[:64].strip("_")
    return slug or "expression"


# -- Entry / set documents (strict *_from_data) ---------------------------


def entry_from_data(data, index: int = 0) -> dict:
    """One validated expression entry (strict keys, house style).

    ``label`` defaults to the name; ``asset_id`` is a UUID
    string or None (declared-but-unbound); ``notes`` is free
    text capped at MAX_NOTES_CHARS.
    """
    if not isinstance(data, dict):
        raise ExpressionError(f"entry {index} must be an object")
    extra = set(data) - _ENTRY_FIELDS
    if extra:
        raise ExpressionError(
            f"entry {index} has unknown keys: {sorted(extra)}")
    name = _check_name(data.get("name"), f"entry {index} name")
    label = data.get("label", name)
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= MAX_LABEL_CHARS:
        raise ExpressionError(
            f"entry {index} label must be 1..{MAX_LABEL_CHARS} chars")
    asset_id = data.get("asset_id")
    if asset_id is not None:
        asset_id = _check_id(asset_id, f"entry {index} asset_id")
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > MAX_NOTES_CHARS:
        raise ExpressionError(
            f"entry {index} notes must be a string of at most "
            f"{MAX_NOTES_CHARS} chars")
    return {"name": name, "label": label.strip(),
            "asset_id": asset_id, "notes": notes}


def entry_to_data(entry: dict) -> dict:
    return {"name": entry["name"], "label": entry["label"],
            "asset_id": entry["asset_id"], "notes": entry["notes"]}


def set_body_from_data(data) -> dict:
    """A validated set body (character_id + entries + default),
    minus timestamps. Duplicate entry names reject; a default
    naming an undeclared entry rejects."""
    if not isinstance(data, dict):
        raise ExpressionError("expression set must be an object")
    extra = set(data) - _SET_FIELDS
    if extra:
        raise ExpressionError(f"expression set has unknown keys: {sorted(extra)}")
    character_id = _check_id(data.get("character_id"), "character_id")
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ExpressionError("set entries must be a list")
    if len(raw_entries) > MAX_ENTRIES_PER_SET:
        raise ExpressionError(
            f"set has too many entries (max {MAX_ENTRIES_PER_SET})")
    entries = [entry_from_data(row, i) for i, row in enumerate(raw_entries)]
    seen: set[str] = set()
    for entry in entries:
        if entry["name"] in seen:
            raise ExpressionError(
                f"duplicate expression name in set: {entry['name']!r}")
        seen.add(entry["name"])
    default = data.get("default")
    if default is not None:
        _check_name(default, "set default")
        if default not in seen:
            raise ExpressionError(
                f"set default {default!r} is not a declared entry")
    return {"character_id": character_id, "entries": entries,
            "default": default}


def set_to_data(expr_set: dict) -> dict:
    return {
        "character_id": expr_set["character_id"],
        "entries": [entry_to_data(e) for e in expr_set["entries"]],
        "default": expr_set["default"],
        "created_at": expr_set["created_at"],
        "updated_at": expr_set["updated_at"],
    }


# -- Durable per-user store (file idiom, no migration) ---------------------


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    """The owner's store file under the data dir. The user id
    is validated as a UUID before it ever becomes a path."""
    _check_id(user_id, "user_id")
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{user_id}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "sets": [], "selections": [],
            "history": []}


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExpressionError(
            f"expression store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("sets"), list) \
            or not isinstance(doc.get("selections"), list) \
            or not isinstance(doc.get("history"), list):
        raise ExpressionError("expression store has an unknown shape")
    return doc


def _save_doc(user_id: str, doc: dict, base_dir: Path | None = None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _stored_set(row) -> dict:
    """A stored set row re-validated on read: corrupt rows
    raise, never silently vanish from the owner's library."""
    if not isinstance(row, dict):
        raise ExpressionError("stored expression set is not an object")
    body = set_body_from_data(row)
    return {**body,
            "created_at": row.get("created_at") or _now_iso(),
            "updated_at": row.get("updated_at") or _now_iso()}


def _find_set_row(doc: dict, character_id: str) -> int | None:
    for index, row in enumerate(doc["sets"]):
        if isinstance(row, dict) and row.get("character_id") == character_id:
            return index
    return None


# -- Set CRUD (owner-scoped service API) -----------------------------------


def create_set(user_id: str, data, *, base_dir: Path | None = None) -> dict:
    """Declare a character's expression set. Refuses when a
    set for that character already exists (PUT replaces)."""
    body = set_body_from_data(data)
    doc = _load_doc(user_id, base_dir)
    if _find_set_row(doc, body["character_id"]) is not None:
        raise ExpressionError(
            f"an expression set already exists for character "
            f"{body['character_id']}")
    if len(doc["sets"]) >= MAX_SETS_PER_USER:
        raise ExpressionError(f"expression set limit reached ({MAX_SETS_PER_USER})")
    now = _now_iso()
    expr_set = {**body, "created_at": now, "updated_at": now}
    doc["sets"].append(set_to_data(expr_set))
    _save_doc(user_id, doc, base_dir)
    return set_to_data(expr_set)


def get_set(user_id: str, character_id: str,
            *, base_dir: Path | None = None) -> dict | None:
    _check_id(character_id, "character_id")
    doc = _load_doc(user_id, base_dir)
    index = _find_set_row(doc, character_id)
    if index is None:
        return None
    return set_to_data(_stored_set(doc["sets"][index]))


def list_sets(user_id: str, *, base_dir: Path | None = None) -> list[dict]:
    """The owner's declared sets, sorted by character id for
    a stable surface."""
    doc = _load_doc(user_id, base_dir)
    out = [set_to_data(_stored_set(row)) for row in doc["sets"]]
    out.sort(key=lambda s: s["character_id"])
    return out


def update_set(user_id: str, character_id: str, data,
               *, base_dir: Path | None = None) -> dict | None:
    """Full replace of a set's entries + default; the path
    character is the truth (a body naming another character
    rejects). created_at is preserved. None when no set."""
    _check_id(character_id, "character_id")
    body = set_body_from_data(data)
    if body["character_id"] != character_id:
        raise ExpressionError(
            "set body character_id does not match the addressed character")
    doc = _load_doc(user_id, base_dir)
    index = _find_set_row(doc, character_id)
    if index is None:
        return None
    existing = _stored_set(doc["sets"][index])
    updated = {**body, "created_at": existing["created_at"],
               "updated_at": _now_iso()}
    doc["sets"][index] = set_to_data(updated)
    _save_doc(user_id, doc, base_dir)
    return set_to_data(updated)


def delete_set(user_id: str, character_id: str,
               *, base_dir: Path | None = None) -> bool:
    """Remove a set declaration. Selections naming it are NOT
    silently rewritten: they stay in history as the record of
    what was shown; current selections for its chats are
    dropped by the explicit clear road, and re-selection
    refuses until a new set is declared."""
    _check_id(character_id, "character_id")
    doc = _load_doc(user_id, base_dir)
    kept = [row for row in doc["sets"]
            if not (isinstance(row, dict)
                    and row.get("character_id") == character_id)]
    if len(kept) == len(doc["sets"]):
        return False
    doc["sets"] = kept
    _save_doc(user_id, doc, base_dir)
    return True


# -- Selections (current expression per chat, with provenance) -------------


def _check_source(value) -> str:
    source = value if value is not None else "manual"
    if source not in SELECTION_SOURCES:
        raise ExpressionError(f"unknown selection source: {source!r}")
    return source


def _check_reason(value) -> str:
    reason = value if value is not None else ""
    if not isinstance(reason, str) or len(reason) > MAX_REASON_CHARS:
        raise ExpressionError(
            f"selection reason must be a string of at most "
            f"{MAX_REASON_CHARS} chars")
    return reason


def _selection_doc(*, chat_id: str, character_id: str, name: str,
                   source: str, actor_user_id: str, reason: str,
                   message_id, previous) -> dict:
    return {
        "chat_id": chat_id,
        "character_id": character_id,
        "expression": name,
        "selected_at": _now_iso(),
        "provenance": {
            "via": "expression_plugin",
            "source": source,
            "actor_user_id": actor_user_id,
            "reason": reason,
            "message_id": message_id,
            "previous_expression": previous,
        },
    }


def _current_row(doc: dict, chat_id: str) -> dict | None:
    for row in doc["selections"]:
        if isinstance(row, dict) and row.get("chat_id") == chat_id:
            return row
    return None


def _record_selection(doc: dict, selection: dict) -> None:
    kept = [row for row in doc["selections"]
            if not (isinstance(row, dict)
                    and row.get("chat_id") == selection["chat_id"])]
    kept.append(copy.deepcopy(selection))
    doc["selections"] = kept
    doc["history"].append(copy.deepcopy(selection))
    doc["history"] = doc["history"][-MAX_HISTORY_KEPT:]


def select_expression(user_id: str, chat_id: str, character_id: str,
                      name: str, *, source: str | None = None,
                      reason: str | None = None, message_id=None,
                      base_dir: Path | None = None) -> dict:
    """Select the current expression for one chat (sync core).

    The character's set must exist and must declare ``name``;
    anything else raises :class:`ExpressionError` before any
    write. The selection replaces the chat's current one and
    is appended to the kept history with its provenance.
    """
    _check_id(chat_id, "chat_id")
    _check_id(character_id, "character_id")
    _check_name(name)
    source = _check_source(source)
    reason = _check_reason(reason)
    if message_id is not None:
        _check_id(message_id, "message_id")
    doc = _load_doc(user_id, base_dir)
    index = _find_set_row(doc, character_id)
    if index is None:
        raise ExpressionError(
            f"no expression set declared for character {character_id}")
    expr_set = _stored_set(doc["sets"][index])
    if name not in {e["name"] for e in expr_set["entries"]}:
        raise ExpressionError(
            f"expression {name!r} is not declared for this character")
    current = _current_row(doc, chat_id)
    previous = current.get("expression") if current else None
    if current is not None and current.get("character_id") != character_id:
        previous = None
    selection = _selection_doc(
        chat_id=chat_id, character_id=character_id, name=name,
        source=source, actor_user_id=user_id, reason=reason,
        message_id=message_id, previous=previous)
    _record_selection(doc, selection)
    _save_doc(user_id, doc, base_dir)
    return copy.deepcopy(selection)


def current_expression(user_id: str, chat_id: str,
                       *, base_dir: Path | None = None) -> dict | None:
    """The chat's current selection, or None when none was
    ever selected (or it was cleared)."""
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    row = _current_row(doc, chat_id)
    return copy.deepcopy(row) if row is not None else None


def clear_selection(user_id: str, chat_id: str, *,
                    reason: str | None = None,
                    base_dir: Path | None = None) -> bool:
    """Drop the chat's current selection, recording the
    clearing in history with its provenance. False when
    there was nothing to clear."""
    _check_id(chat_id, "chat_id")
    reason = _check_reason(reason)
    doc = _load_doc(user_id, base_dir)
    row = _current_row(doc, chat_id)
    if row is None:
        return False
    doc["selections"] = [
        r for r in doc["selections"]
        if not (isinstance(r, dict) and r.get("chat_id") == chat_id)]
    doc["history"].append({
        "chat_id": chat_id,
        "character_id": row.get("character_id"),
        "expression": None,
        "cleared": True,
        "selected_at": _now_iso(),
        "provenance": {
            "via": "expression_plugin",
            "source": "manual",
            "actor_user_id": user_id,
            "reason": reason,
            "message_id": None,
            "previous_expression": row.get("expression"),
        },
    })
    doc["history"] = doc["history"][-MAX_HISTORY_KEPT:]
    _save_doc(user_id, doc, base_dir)
    return True


def apply_default(user_id: str, chat_id: str, character_id: str,
                  *, base_dir: Path | None = None) -> dict | None:
    """Apply the set's declared default when the chat has no
    current selection (explicit road, source ``default``).
    Returns the existing selection untouched when one is
    already current, and None when there is no set or the
    set declares no default."""
    _check_id(chat_id, "chat_id")
    _check_id(character_id, "character_id")
    existing = current_expression(user_id, chat_id, base_dir=base_dir)
    if existing is not None:
        return existing
    expr_set = get_set(user_id, character_id, base_dir=base_dir)
    if expr_set is None or expr_set["default"] is None:
        return None
    return select_expression(
        user_id, chat_id, character_id, expr_set["default"],
        source="default", reason="declared default applied",
        base_dir=base_dir)


def list_history(user_id: str, *, chat_id: str | None = None,
                 base_dir: Path | None = None) -> list[dict]:
    """Selection history, newest first; one chat's when a
    chat_id is named."""
    if chat_id is not None:
        _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    rows = [copy.deepcopy(row) for row in reversed(doc["history"])]
    if chat_id is not None:
        rows = [row for row in rows if row.get("chat_id") == chat_id]
    return rows


# -- Asset binding + chat roads (async, ride the founding services) --------


async def binding_report(session, user_id: str, character_id: str,
                         *, base_dir: Path | None = None) -> dict | None:
    """Join a declared set to its P-023 sprite assets.

    None when the character is missing/foreign. Otherwise
    {character_id, set (or None), entries: [{entry, bound,
    problem, asset}]} — an honestly unbound entry is a
    report, never an error. Bytes are never read here."""
    from runmal.assets.models import asset_to_dict
    from runmal.assets.service import get_asset
    from runmal.characters.service import get_character

    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    expr_set = get_set(user_id, character_id, base_dir=base_dir)
    entries = []
    for entry in (expr_set["entries"] if expr_set else []):
        asset_id = entry["asset_id"]
        if asset_id is None:
            entries.append({"entry": entry_to_data(entry), "bound": False,
                            "problem": "no_asset", "asset": None})
            continue
        asset = await get_asset(session, user_id, character_id, asset_id)
        if asset is None:
            entries.append({"entry": entry_to_data(entry), "bound": False,
                            "problem": "asset_missing", "asset": None})
        elif str(asset.kind) != "expression":
            entries.append({"entry": entry_to_data(entry), "bound": False,
                            "problem": "wrong_kind",
                            "asset": asset_to_dict(asset)})
        elif str(asset.status) != "stored":
            entries.append({"entry": entry_to_data(entry), "bound": False,
                            "problem": "not_stored",
                            "asset": asset_to_dict(asset)})
        else:
            entries.append({"entry": entry_to_data(entry), "bound": True,
                            "problem": None,
                            "asset": asset_to_dict(asset)})
    return {"character_id": character_id, "set": expr_set,
            "entries": entries,
            "bound_count": sum(1 for e in entries if e["bound"]),
            "entry_count": len(entries)}


async def derive_set_from_assets(session, user_id: str, character_id: str,
                                 ) -> dict | None:
    """A DRAFT set built from the character's stored P-023
    expression assets — returned, never saved. Declaration
    stays an explicit owner act. Names slugify from asset
    names; collisions suffix -2, -3 deterministically in
    asset order. None when the character is missing."""
    from runmal.assets.service import list_assets
    from runmal.characters.service import get_character

    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    assets = await list_assets(session, user_id, character_id) or []
    entries = []
    used: set[str] = set()
    for asset in assets:
        if str(asset.kind) != "expression" or str(asset.status) != "stored":
            continue
        base = _slugify(asset.name or "expression")
        name = base
        suffix = 2
        while name in used:
            name = f"{base[:60]}-{suffix}"
            suffix += 1
        used.add(name)
        entries.append({"name": name, "label": asset.name or name,
                        "asset_id": asset.id, "notes": ""})
    return {"character_id": character_id, "entries": entries,
            "default": entries[0]["name"] if entries else None}


async def select_for_chat(session, user_id: str, chat_id: str, name: str,
                          *, source: str | None = None,
                          reason: str | None = None, message_id=None,
                          base_dir: Path | None = None) -> dict | None:
    """Select a declared expression for a chat's bound
    character. None when the chat is missing/foreign; a chat
    with no bound character raises (no set to select from)."""
    from runmal.chats import service as chats_svc

    chat = await chats_svc.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if not getattr(chat, "character_id", None):
        raise ExpressionError(
            "chat has no bound character: no expression set to select from")
    return select_expression(
        user_id, chat_id, chat.character_id, name, source=source,
        reason=reason, message_id=message_id, base_dir=base_dir)


async def apply_default_for_chat(session, user_id: str, chat_id: str,
                                 *, base_dir: Path | None = None,
                                 ) -> dict | None:
    """apply_default for a chat's bound character. None when
    the chat is missing/foreign, unbound, or nothing applies."""
    from runmal.chats import service as chats_svc

    chat = await chats_svc.get_chat(session, user_id, chat_id)
    if chat is None or not getattr(chat, "character_id", None):
        return None
    return apply_default(user_id, chat_id, chat.character_id,
                         base_dir=base_dir)


async def inspect_state(session, user_id: str, chat_id: str,
                        *, base_dir: Path | None = None) -> dict | None:
    """The inspectable surface Part X reads: chat, character,
    declared set, per-entry bindings and the current
    selection with its provenance, in one document. None
    when the chat is missing/foreign."""
    from runmal.chats import service as chats_svc

    chat = await chats_svc.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    character_id = getattr(chat, "character_id", None)
    current = current_expression(user_id, chat_id, base_dir=base_dir)
    bindings = None
    if character_id:
        bindings = await binding_report(
            session, user_id, character_id, base_dir=base_dir)
    current_binding = None
    if current is not None and bindings is not None:
        for row in bindings["entries"]:
            if row["entry"]["name"] == current["expression"]:
                current_binding = row
                break
    return {
        "chat_id": chat_id,
        "character_id": character_id,
        "set": bindings["set"] if bindings else None,
        "bindings": bindings["entries"] if bindings else [],
        "bound_count": bindings["bound_count"] if bindings else 0,
        "entry_count": bindings["entry_count"] if bindings else 0,
        "current": current,
        "current_binding": current_binding,
    }


# -- The P-081 citizen -------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Expressions",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Expression/sprite plugin surface: "
                       "declared expression sets per character, "
                       "current-expression selection per chat "
                       "with provenance, bound to P-023 assets.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.sidebar",
                "label": "Expressions",
                "order": 110,
                "payload": {"kind": "panel", "route": "expressions"},
            }
        ],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class ExpressionsPlugin:
    """The citizen: a UI contribution plus declared chat
    events whose handler abstains — chat deletion must never
    silently delete a character's declared set, and
    selections are explicit owner acts, never event-driven."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    @property
    def manifest(self):
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    async def on_event(self, event) -> None:
        return None


def register_plugin(registry: PluginRegistry, *,
                    base_dir: Path | None = None,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, ExpressionsPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = ExpressionsPlugin(base_dir)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS", "MAX_ENTRIES_PER_SET", "MAX_HISTORY_KEPT",
    "MAX_LABEL_CHARS", "MAX_NOTES_CHARS", "MAX_REASON_CHARS",
    "MAX_SETS_PER_USER", "PLUGIN_ID", "PLUGIN_VERSION",
    "SELECTION_SOURCES", "STORE_SCHEMA", "UI_LOCAL_ID", "VERSION",
    "ExpressionError", "ExpressionsPlugin", "apply_default",
    "apply_default_for_chat", "binding_report", "build_manifest",
    "clear_selection", "create_set", "current_expression",
    "delete_set", "derive_set_from_assets", "entry_from_data",
    "entry_to_data", "get_set", "inspect_state", "list_history",
    "list_sets", "manifest_data", "register_plugin", "sandbox_grants",
    "select_expression", "select_for_chat", "set_body_from_data",
    "set_to_data", "store_path", "update_set",
]
