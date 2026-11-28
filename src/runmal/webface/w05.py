"""W-05 compositions: Personas + Lorebooks tabs (R-10 parity).

All over EXISTING engine roads (no new engine routes):
- persona (R-03): GET/PUT /user-name, GET/POST
  /chats/{id}/persona. Persona in this engine is exactly two
  mechanisms: the persisted {{user}} name and a chat's persona
  character (future turns only). Persona-FILE interop exists in
  the engine library (runmal.persona.interop) but NO route
  serves it; the panel says exactly that and offers no decoy
  import/export controls (the R-10 honesty rule).
- lorebooks (S201/P-040/P-042/P-045/P-047): books/entries CRUD,
  the P-042 editor census (forms generated from it;
  activation_kind is derived, read-only, never sent), scope
  assignments (global/character/persona/chat + budget +
  position; the engine's PUT scope road upserts), import /
  import-pack / upgrade, the book activation preview and the
  layered per-chat lore preview with every verdict in words.

Saves compose over the stored document (the lossless-overlay
discipline of W-02/W-03 and desktop R-10): a save starts from
the stored book/entry dict, overlays only the census fields the
form carries, and PATCHes only what changed - so fields the
form does not know survive an edit verbatim.

Scope assignments are NOT the W-02 card binding (the P-039
character lorebook-binding edited in the Characters tab): a
scope dresses a layer of every applicable chat; a binding is
one character's own book travelling with its card. Where both
exist for a book, the Lorebooks tab shows both, plainly
labelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import EngineError

DEFAULT_USER_NAME = "User"

PERSONA_FILE_NOTE = (
    "Persona files: the engine library defines a persona-file "
    "format, but no engine route serves it, so this page offers "
    "no persona import or export - there is nothing honest to "
    "wire a button to."
)

FUTURE_TURNS_NOTE = (
    "Switching a chat's persona shapes FUTURE turns only; "
    "messages already stored keep the speaker they were written "
    "with."
)

# ------------------------------------------------------------ user name


def user_name_state(engine) -> dict:
    payload = engine.request("GET", "/api/v1/user-name")
    payload = payload if isinstance(payload, dict) else {}
    name = str(payload.get("user_name") or DEFAULT_USER_NAME)
    is_set = bool(payload.get("is_set", False))
    words = (
        f"Your name in chats: {name}"
        if is_set
        else f"Your name in chats: {name} "
        "(the built-in default - no name saved yet)"
    )
    return {"user_name": name, "is_set": is_set, "words": words}


def set_user_name(engine, name: str, *, clear: bool = False) -> dict:
    """Save the {{user}} name.

    Webface semantics (R-03/R-05, as in W-04's first-run road):
    an empty field NEVER clears - it keeps the current name and
    says so. Clearing is its own explicit act (``clear=True``),
    which uses the engine road's own semantics: an empty name
    on PUT /user-name clears the setting back to the default.
    """
    cleaned = str(name or "").strip()
    if clear:
        saved = engine.request(
            "PUT", "/api/v1/user-name", json_body={"user_name": ""})
        saved = saved if isinstance(saved, dict) else {}
        return {
            "user_name": str(saved.get("user_name") or DEFAULT_USER_NAME),
            "is_set": bool(saved.get("is_set", False)),
            "cleared": True, "kept": False,
            "words": "Name cleared - chats will call you "
                     f"{saved.get('user_name') or DEFAULT_USER_NAME} "
                     "(the built-in default) again.",
        }
    if not cleaned:
        state = user_name_state(engine)
        return {**state, "cleared": False, "kept": True,
                "words": state["words"] + " (an empty field never "
                         "clears the name - it was kept)"}
    saved = engine.request(
        "PUT", "/api/v1/user-name", json_body={"user_name": cleaned})
    saved = saved if isinstance(saved, dict) else {}
    return {
        "user_name": str(saved.get("user_name") or cleaned),
        "is_set": bool(saved.get("is_set", True)),
        "cleared": False, "kept": False,
        "words": f"Your name in chats: {saved.get('user_name') or cleaned}",
    }


# --------------------------------------------------------- chat persona


def _persona_words(persona) -> str:
    if not isinstance(persona, dict) or not persona.get("character_id"):
        return "This chat has no persona character."
    return f"Persona: {persona.get('name') or persona['character_id']}"


def persona_view(engine, chat_id: str) -> dict:
    payload = engine.request("GET", f"/api/v1/chats/{chat_id}/persona")
    payload = payload if isinstance(payload, dict) else {}
    persona = payload.get("persona")
    persona = persona if isinstance(persona, dict) else None
    return {
        "chat_id": str(payload.get("chat_id") or chat_id),
        "persona": persona,
        "words": _persona_words(persona),
        "note": FUTURE_TURNS_NOTE,
    }


def set_persona(engine, chat_id: str, character_id) -> dict:
    if not chat_id:
        raise EngineError("open a chat before changing its persona",
                          status=422)
    cid = str(character_id).strip() if character_id else None
    payload = engine.request(
        "POST", f"/api/v1/chats/{chat_id}/persona",
        json_body={"character_id": cid or None})
    payload = payload if isinstance(payload, dict) else {}
    persona = payload.get("persona")
    persona = persona if isinstance(persona, dict) else None
    return {
        "chat_id": str(payload.get("chat_id") or chat_id),
        "persona": persona,
        "previous_character_id": payload.get("previous_character_id"),
        "words": _persona_words(persona),
        "note": FUTURE_TURNS_NOTE,
    }

# ------------------------------------------------------- census forms

KIND_TEXT = "text"
KIND_LONGTEXT = "longtext"
KIND_INT = "int"
KIND_INT_OR_NULL = "int_or_null"
KIND_KEYS = "keys"
KIND_BOOL = "bool"
KIND_SELECT = "select"
KIND_LINES = "lines"

DERIVED_FIELDS = frozenset({"activation_kind"})
IDENTITY_FIELDS = frozenset(
    {"id", "lorebook_id", "created_at", "updated_at", "entry_count"})

FIELD_LABELS: dict[str, str] = {
    "name": "Name",
    "description": "Description",
    "scan_depth": "Scan depth (recent messages examined)",
    "token_budget": "Token budget (blank = no limit)",
    "scan_mode": "Scan window",
    "scan_external_context": "Also scan external context",
    "content": "Content (injected text)",
    "keys": "Keywords (one per line)",
    "secondary_keys": "Secondary keywords (one per line)",
    "selective_logic": "Secondary-key logic",
    "inclusion_group": "Inclusion group",
    "group_weight": "Group weight",
    "probability": "Probability (%)",
    "priority": "Priority (higher wins budget)",
    "position": "Injection position",
    "depth": "Depth (for at-depth position)",
    "role": "Injection role",
    "enabled": "Enabled",
    "constant": "Always on (constant)",
    "vectorised": "Vectorised (similarity match)",
    "activation_kind": "Activation kind",
    "case_sensitive": "Case-sensitive keywords",
    "whole_word": "Whole-word keywords",
    "sticky_prompts": "Sticky (prompts it stays active)",
    "cooldown_prompts": "Cooldown (prompts before it can refire)",
    "delay_prompts": "Delay (prompts before it can first fire)",
    "scope_kind": "Scope kind",
    "owner_id": "Owner",
}

FIELD_HELP: dict[str, str] = {
    "scan_depth": "How many recent messages are scanned for keywords.",
    "scan_mode": "Depth = the last few messages; whole chat = everything.",
    "keys": "The entry fires when a message mentions one of these.",
    "secondary_keys": "Extra keywords combined by the secondary-key logic.",
    "selective_logic": "How secondary keywords gate the entry.",
    "constant": "Constant entries are always injected, keyword or not.",
    "vectorised": "Vectorised entries match by meaning, not exact words.",
    "activation_kind": "Derived from Always-on / Vectorised - shown, not edited.",
    "position": "Where the entry lands relative to the character's text.",
    "sticky_prompts": "Once fired, stays active for this many further prompts.",
    "cooldown_prompts": "After firing, cannot fire again for this many prompts.",
    "delay_prompts": "Cannot fire until this many prompts have passed.",
}


@dataclass(frozen=True)
class SchemaField:
    name: str
    kind: str
    options: list[str] = field(default_factory=list)
    derived: bool = False

    @property
    def label(self) -> str:
        return FIELD_LABELS.get(
            self.name, self.name.replace("_", " ").title())

    @property
    def help(self) -> str:
        return FIELD_HELP.get(self.name, "")

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind,
                "options": list(self.options), "derived": self.derived,
                "label": self.label, "help": self.help}


def schema_fields(schema, surface: str) -> list[SchemaField]:
    """The census fields for one surface, in census order."""
    surfaces = schema.get("surfaces") if isinstance(schema, dict) else None
    rows = surfaces.get(surface) if isinstance(surfaces, dict) else None
    out: list[SchemaField] = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        name = str(row["name"])
        kind = str(row.get("kind", KIND_TEXT) or KIND_TEXT)
        out.append(SchemaField(
            name=name, kind=kind,
            options=[str(o) for o in (row.get("options") or [])],
            derived=name in DERIVED_FIELDS or kind == "derived"))
    return out


def census(engine) -> dict:
    """The P-042 editor census, with the form model per surface."""
    schema = engine.request("GET", "/api/v1/lorebooks/editor-schema")
    schema = schema if isinstance(schema, dict) else {}
    return {
        "schema": schema,
        "forms": {
            surface: [f.as_dict() for f in schema_fields(schema, surface)]
            for surface in ("book", "entry", "scope", "preview")
        },
    }


def activation_kind_words(values) -> str:
    if isinstance(values, dict) and values.get("constant"):
        return "constant (always on)"
    if isinstance(values, dict) and values.get("vectorised"):
        return "vectorised (similarity)"
    return "keyword"


def parse_form_values(fields: list[SchemaField], values) -> dict:
    """Type the page script's raw values by census kind.

    Raw contract: keys arrive as lists (or newline text), bools
    as bools, everything else as text ('' = blank). Derived
    fields are never read here and never sent onward."""
    values = values if isinstance(values, dict) else {}
    out: dict[str, Any] = {}
    for f in fields:
        if f.derived or f.name not in values:
            continue
        raw = values[f.name]
        if f.kind == KIND_KEYS:
            if isinstance(raw, list):
                out[f.name] = [str(k).strip() for k in raw if str(k).strip()]
            else:
                out[f.name] = [line.strip() for line in
                               str(raw or "").splitlines() if line.strip()]
        elif f.kind == KIND_BOOL:
            out[f.name] = bool(raw)
        elif f.kind in (KIND_INT, KIND_INT_OR_NULL):
            if isinstance(raw, bool):
                raise EngineError(f"{f.label} must be a whole number",
                                  status=422)
            if isinstance(raw, int):
                out[f.name] = raw
                continue
            text = str(raw if raw is not None else "").strip()
            if not text:
                if f.kind == KIND_INT_OR_NULL:
                    out[f.name] = None
                    continue
                raise EngineError(f"{f.label} needs a whole number",
                                  status=422)
            try:
                out[f.name] = int(text)
            except ValueError:
                raise EngineError(
                    f"{f.label} must be a whole number",
                    status=422) from None
        else:
            out[f.name] = "" if raw is None else str(raw)
    return out


def collect_fields(fields: list[SchemaField], values, base) -> dict:
    """Compose a save payload over the stored document: unknown
    fields survive verbatim, derived fields are never overlaid."""
    out: dict[str, Any] = dict(base or {})
    for f in fields:
        if f.derived:
            continue
        if f.name in (values or {}):
            out[f.name] = values[f.name]
    return out


def validate_book(values) -> None:
    if not str((values or {}).get("name", "") or "").strip():
        raise EngineError("the lorebook needs a name", status=422)
    depth = (values or {}).get("scan_depth")
    if depth is not None and (not isinstance(depth, int)
                              or isinstance(depth, bool) or depth < 1):
        raise EngineError("scan depth must be at least 1", status=422)
    budget = (values or {}).get("token_budget")
    if budget is not None and (not isinstance(budget, int)
                               or isinstance(budget, bool) or budget < 1):
        raise EngineError(
            "token budget must be at least 1, or blank", status=422)


def validate_entry(values) -> None:
    probability = (values or {}).get("probability")
    if probability is not None and (
            not isinstance(probability, int)
            or isinstance(probability, bool)
            or not 0 <= probability <= 100):
        raise EngineError(
            "probability must be between 0 and 100", status=422)
    for key in ("group_weight", "depth", "sticky_prompts",
                "cooldown_prompts", "delay_prompts"):
        value = (values or {}).get(key)
        if value is not None and (not isinstance(value, int)
                                  or isinstance(value, bool) or value < 0):
            label = FIELD_LABELS.get(key, key)
            raise EngineError(f"{label} cannot be negative", status=422)

# ------------------------------------------------------------ books

_BOOK_ROAD = "/api/v1/lorebooks"


def _stored_book(engine, book_id: str) -> dict:
    payload = engine.request("GET", f"{_BOOK_ROAD}/{book_id}")
    return payload if isinstance(payload, dict) else {}


def _stored_entry(engine, book_id: str, entry_id: str) -> dict:
    payload = engine.request(
        "GET", f"{_BOOK_ROAD}/{book_id}/entries/{entry_id}")
    return payload if isinstance(payload, dict) else {}


def save_book(engine, book_id, body) -> dict:
    """Create or edit a book through the census form shape."""
    body = body if isinstance(body, dict) else {}
    schema = engine.request("GET", "/api/v1/lorebooks/editor-schema")
    fields = schema_fields(schema, "book")
    values = parse_form_values(fields, body.get("values") or {})
    if book_id is None:
        validate_book(values)
        payload = collect_fields(fields, values, None)
        created = engine.request("POST", _BOOK_ROAD, json_body=payload)
        return created if isinstance(created, dict) else {}
    stored = _stored_book(engine, book_id)
    base = {k: stored.get(k) for k in
            ("name", "description", "scan_depth", "token_budget",
             "scan_mode", "scan_external_context")}
    composed = collect_fields(fields, values, {**stored, **base})
    validate_book(composed)
    changed = {f.name: composed[f.name] for f in fields
               if not f.derived and f.name in composed
               and stored.get(f.name) != composed[f.name]}
    if not changed:
        return stored
    saved = engine.request(
        "PATCH", f"{_BOOK_ROAD}/{book_id}", json_body=changed)
    return saved if isinstance(saved, dict) else {}


def save_entry(engine, book_id: str, entry_id, body) -> dict:
    """Create or edit an entry through the census form shape.

    The composed document starts from the stored entry, so any
    field the form does not carry survives; only changed census
    fields are PATCHed, and identity/derived keys never travel."""
    body = body if isinstance(body, dict) else {}
    schema = engine.request("GET", "/api/v1/lorebooks/editor-schema")
    fields = schema_fields(schema, "entry")
    values = parse_form_values(fields, body.get("values") or {})
    validate_entry(values)
    if entry_id is None:
        payload = collect_fields(fields, values, None)
        for key in IDENTITY_FIELDS | DERIVED_FIELDS:
            payload.pop(key, None)
        created = engine.request(
            "POST", f"{_BOOK_ROAD}/{book_id}/entries", json_body=payload)
        return created if isinstance(created, dict) else {}
    stored = _stored_entry(engine, book_id, entry_id)
    composed = collect_fields(fields, values, stored)
    for key in IDENTITY_FIELDS | DERIVED_FIELDS:
        composed.pop(key, None)
    changed = {key: value for key, value in composed.items()
               if stored.get(key) != value}
    if not changed:
        return stored
    saved = engine.request(
        "PATCH", f"{_BOOK_ROAD}/{book_id}/entries/{entry_id}",
        json_body=changed)
    return saved if isinstance(saved, dict) else {}


def delete_book(engine, book_id: str) -> dict:
    payload = engine.request("DELETE", f"{_BOOK_ROAD}/{book_id}")
    return payload if isinstance(payload, dict) else {"deleted": True}


def delete_entry(engine, book_id: str, entry_id: str) -> dict:
    payload = engine.request(
        "DELETE", f"{_BOOK_ROAD}/{book_id}/entries/{entry_id}")
    return payload if isinstance(payload, dict) else {"deleted": True}


# ------------------------------------------------------------ scopes

SCOPE_KINDS = ["global", "character", "persona", "chat"]

SCOPE_LABELS = {
    "global": "Global (every chat)",
    "character": "Character (chats with this character)",
    "persona": "Persona (chats where you speak as this character)",
    "chat": "Chat (one chat only)",
}

SCOPE_NOTE = (
    "Scopes assign this book to a layer of a chat's world. They "
    "are a different mechanism from the card binding in the "
    "Characters tab (one character's own book travelling with "
    "its card, with a precedence); where both exist for a book, "
    "both are shown below, plainly labelled."
)


def scope_words(scope, owner_name: str = "") -> str:
    scope = scope if isinstance(scope, dict) else {}
    kind = str(scope.get("scope_kind") or "")
    label = SCOPE_LABELS.get(kind, kind or "scope")
    words = label
    owner = scope.get("owner_id")
    if owner:
        words += f" - {owner_name or owner}"
    if scope.get("token_budget") is not None:
        words += f" - budget {scope['token_budget']} tokens"
    else:
        words += " - no budget limit"
    words += f" - position {scope.get('position', 0)}"
    return words


def list_scopes(engine, book_id: str) -> list[dict]:
    payload = engine.request("GET", f"{_BOOK_ROAD}/{book_id}/scopes")
    rows = payload.get("scopes") if isinstance(payload, dict) else None
    out = []
    for row in rows or []:
        if isinstance(row, dict):
            out.append({**row, "words": scope_words(row)})
    return out


def assign_scope(engine, book_id: str, body) -> dict:
    """Assign (or re-assign: the engine road upserts on the
    (book, kind, owner) triple, so this is also the budget /
    position edit road)."""
    body = body if isinstance(body, dict) else {}
    kind = str(body.get("scope_kind") or "").strip()
    if kind not in SCOPE_KINDS:
        raise EngineError(f"unknown scope kind: {kind or '(blank)'}",
                          status=422)
    owner = body.get("owner_id")
    owner = str(owner).strip() if owner else None
    if kind == "global":
        owner = None
    elif not owner:
        raise EngineError("that scope kind needs an owner", status=422)
    budget = body.get("token_budget")
    if budget is not None and budget != "":
        try:
            budget = int(budget)
        except (TypeError, ValueError):
            raise EngineError(
                "scope budget must be a whole number", status=422) from None
        if budget < 0:
            raise EngineError("scope budget cannot be negative",
                              status=422)
    else:
        budget = None
    position = body.get("position", 0)
    try:
        position = int(position if position not in (None, "") else 0)
    except (TypeError, ValueError):
        raise EngineError(
            "scope position must be a whole number", status=422) from None
    payload: dict[str, Any] = {"scope_kind": kind, "owner_id": owner,
                               "position": position}
    if budget is not None:
        payload["token_budget"] = budget
    saved = engine.request(
        "PUT", f"{_BOOK_ROAD}/{book_id}/scope", json_body=payload)
    saved = saved if isinstance(saved, dict) else {}
    return {**saved, "words": scope_words(saved)}


def unassign_scope(engine, book_id: str, kind: str, owner_id) -> dict:
    params: dict[str, Any] = {"scope_kind": kind}
    if owner_id:
        params["owner_id"] = owner_id
    payload = engine.request(
        "DELETE", f"{_BOOK_ROAD}/{book_id}/scope", params=params)
    return payload if isinstance(payload, dict) else {"deleted": True}


def bindings_for_book(engine, book_id: str) -> list[dict]:
    """The W-02 card bindings (P-039) that name this book, so a
    book carried by BOTH mechanisms shows both, plainly."""
    out = []
    for character in engine.list_characters():
        cid = character.get("id") if isinstance(character, dict) else None
        if not cid:
            continue
        try:
            binding = engine.request(
                "GET", f"/api/v1/characters/{cid}/lorebook-binding")
        except EngineError:
            continue
        binding = binding if isinstance(binding, dict) else {}
        nested = binding.get("lorebook")
        bound_id = binding.get("lorebook_id") or (
            nested.get("id") if isinstance(nested, dict) else None)
        if bound_id == book_id:
            out.append({
                "character_id": cid,
                "character_name": str(character.get("name") or cid),
                "precedence": str(binding.get("precedence") or ""),
                "binding": binding,
                "words": "Card binding: this book is "
                         f"{character.get('name') or cid}'s own book "
                         "(Characters tab)"
                         + (f" - precedence {binding['precedence']}"
                            if binding.get("precedence") else ""),
            })
    return out


def book_detail(engine, book_id: str) -> dict:
    stored = _stored_book(engine, book_id)
    entries = stored.get("entries")
    if not isinstance(entries, list):
        rows = engine.request("GET", f"{_BOOK_ROAD}/{book_id}/entries")
        entries = rows if isinstance(rows, list) else []
    book = {k: v for k, v in stored.items() if k != "entries"}
    return {
        "book": book,
        "entries": [e for e in entries if isinstance(e, dict)],
        "scopes": list_scopes(engine, book_id),
        "bindings": bindings_for_book(engine, book_id),
        "scope_note": SCOPE_NOTE,
    }

# ----------------------------------------------------------- previews

_STATUS_WORDS = {
    "included": "Included",
    "not_triggered": "Not triggered",
    "discarded": "Discarded",
    "disabled": "Disabled",
    "group_excluded": "Excluded by its inclusion group",
}


def verdict_words(row) -> str:
    """One preview row as a plain sentence (never raw JSON)."""
    row = row if isinstance(row, dict) else {}
    status = str(row.get("status") or "")
    head = _STATUS_WORDS.get(status, status or "Unknown")
    name = str(row.get("name") or row.get("entry_id") or "entry")
    parts = [f"{name}: {head}"]
    matched = row.get("matched_primary") or []
    if matched:
        parts.append("matched key " + ", ".join(str(k) for k in matched))
    secondary = row.get("matched_secondary") or []
    if secondary:
        parts.append("secondary " + ", ".join(str(k) for k in secondary))
    if row.get("scope"):
        parts.append(f"scope: {row['scope']}")
    if row.get("via"):
        parts.append(f"via {row['via']}")
    if row.get("tokens") is not None and status in ("included", "discarded"):
        parts.append(f"{row['tokens']} tokens")
    if status == "discarded" and row.get("discard_reason"):
        parts.append(f"reason: {row['discard_reason']}")
    return " - ".join(parts) if len(parts) > 1 else parts[0]


def _rows_with_words(rows) -> list[dict]:
    return [{**r, "words": verdict_words(r)}
            for r in (rows or []) if isinstance(r, dict)]


def preview_book(engine, book_id: str, messages) -> dict:
    msgs = [str(m) for m in (messages or []) if str(m).strip()]
    payload = engine.request(
        "POST", f"{_BOOK_ROAD}/{book_id}/preview",
        json_body={"messages": msgs})
    payload = payload if isinstance(payload, dict) else {}
    rows = _rows_with_words(payload.get("entries"))
    return {"book_id": book_id, "rows": rows,
            "tokens_used": payload.get("tokens_used"),
            "words": [r["words"] for r in rows]}


def layer_words(summary) -> str:
    summary = summary if isinstance(summary, dict) else {}
    scope = str(summary.get("scope") or "")
    label = SCOPE_LABELS.get(scope, scope or "layer")
    books = summary.get("books") or []
    names = []
    for b in books:
        if isinstance(b, dict):
            names.append(str(b.get("name") or b.get("lorebook_id") or ""))
        elif b:
            names.append(str(b))
    parts = [f"{label}: {', '.join(n for n in names if n) or 'no books'}"]
    if summary.get("budget") is not None:
        parts.append(f"budget {summary['budget']}")
    parts.append(f"{summary.get('tokens_used', 0)} tokens used")
    parts.append(f"{summary.get('included', 0)} included")
    parts.append(f"{summary.get('discarded', 0)} discarded")
    return " - ".join(parts)


def preview_chat(engine, chat_id: str, messages) -> dict:
    """The layered per-chat lore preview, every verdict in words."""
    if not chat_id:
        raise EngineError("open a chat before previewing its lore",
                          status=422)
    msgs = [str(m) for m in (messages or []) if str(m).strip()]
    payload = engine.request(
        "POST", f"/api/v1/chats/{chat_id}/lore-preview",
        json_body={"messages": msgs})
    payload = payload if isinstance(payload, dict) else {}
    rows: list[dict] = []
    layers = payload.get("layers")
    if isinstance(layers, dict):
        for layer in layers.values():
            if isinstance(layer, dict):
                rows.extend(_rows_with_words(layer.get("entries")))
    summaries = payload.get("scopes") or []
    shadowed = []
    for item in payload.get("shadowed") or []:
        if isinstance(item, dict):
            shadowed.append(str(item.get("name")
                                or item.get("lorebook_id") or item))
        elif item:
            shadowed.append(str(item))
    return {
        "chat_id": chat_id, "rows": rows,
        "layers": [{**s, "words": layer_words(s)}
                   for s in summaries if isinstance(s, dict)],
        "shadowed": shadowed,
        "tokens_used": payload.get("tokens_used"),
        "words": [r["words"] for r in rows],
    }


# ------------------------------------------- import / pack / upgrade


def import_words(book) -> str:
    book = book if isinstance(book, dict) else {}
    name = str(book.get("name") or "the lorebook")
    count = book.get("entry_count")
    tail = f" with {count} entr{'y' if count == 1 else 'ies'}" if count is not None else ""
    return f"Imported '{name}'{tail}."


def import_book(engine, document) -> dict:
    if not isinstance(document, dict) or not document:
        raise EngineError("that file is not a lorebook document",
                          status=422)
    book = engine.request("POST", f"{_BOOK_ROAD}/import",
                          json_body=document)
    book = book if isinstance(book, dict) else {}
    return {"book": book, "words": import_words(book)}


def import_pack(engine, pack, on_conflict: str = "create_new") -> dict:
    if not isinstance(pack, dict) or not pack:
        raise EngineError("that file is not a lorebook pack", status=422)
    conflict = on_conflict if on_conflict in ("create_new", "reject") \
        else "create_new"
    book = engine.request(
        "POST", f"{_BOOK_ROAD}/import-pack",
        json_body=pack, params={"on_conflict": conflict})
    book = book if isinstance(book, dict) else {}
    report = book.get("pack_import") if isinstance(
        book.get("pack_import"), dict) else {}
    words = import_words(book)
    if report.get("duplicate_exact"):
        words += " It was an exact duplicate, so the existing book was kept."
    return {"book": book, "report": report, "words": words}


def inspect_pack(engine, pack) -> dict:
    if not isinstance(pack, dict) or not pack:
        raise EngineError("that file is not a lorebook pack", status=422)
    report = engine.request("POST", f"{_BOOK_ROAD}/pack/inspect",
                            json_body=pack)
    report = report if isinstance(report, dict) else {}
    manifest = report.get("manifest") if isinstance(
        report.get("manifest"), dict) else {}
    name = manifest.get("name") or report.get("name") or "a lorebook pack"
    entries = manifest.get("entry_count", report.get("entry_count"))
    words = f"Pack check: '{name}' looks valid and intact"
    if entries is not None:
        words += f" - {entries} entries"
    words += ". Nothing was imported."
    return {"report": report, "words": words}


def upgrade_words(report, *, upgraded: bool) -> str:
    report = report if isinstance(report, dict) else {}
    bits = []
    fmt = report.get("source_format") or report.get("format") or ""
    if fmt:
        bits.append(f"source format: {fmt}")
    if report.get("already_current"):
        bits.append("already current - nothing to change")
    elif report.get("would_change"):
        bits.append("an upgrade would change the file")
    materialised = report.get("fields_materialised")
    if materialised is not None:
        bits.append(f"{materialised} field(s) filled in")
    head = "Upgraded lorebook file" if upgraded else "Upgrade check"
    return head + (": " + "; ".join(bits) if bits else " done.")


def inspect_upgrade(engine, document) -> dict:
    if not isinstance(document, dict) or not document:
        raise EngineError("that file is not a lorebook document",
                          status=422)
    report = engine.request("POST", f"{_BOOK_ROAD}/upgrade/inspect",
                            json_body=document)
    report = report if isinstance(report, dict) else {}
    return {"report": report, "words": upgrade_words(report, upgraded=False)}


def upgrade_book(engine, document) -> dict:
    """Upgrade one lorebook FILE (the engine road writes nothing
    to the library; the upgraded document comes back for the
    page to download or import)."""
    if not isinstance(document, dict) or not document:
        raise EngineError("that file is not a lorebook document",
                          status=422)
    payload = engine.request("POST", f"{_BOOK_ROAD}/upgrade",
                             json_body=document)
    payload = payload if isinstance(payload, dict) else {}
    report = payload.get("upgrade") if isinstance(
        payload.get("upgrade"), dict) else {}
    return {"lorebook": payload.get("lorebook") or {},
            "report": report,
            "words": upgrade_words(report, upgraded=True)}
