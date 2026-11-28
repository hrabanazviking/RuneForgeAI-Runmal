"""W-06 compositions: Memory + Scenarios tabs (desktop R-12 parity).

All over EXISTING engine roads (no new engine routes):

- memory (S410): GET /memories (q/state/kind filters, in the
  engine's own order) and GET /memories/{id} (sources +
  provenance graph). The engine offers NO memory create, edit
  or delete road and no embedding controls - the desktop says
  exactly this (R-12 memory_logic) and so does this tab:
  memories are read here, in words, with their scope, kind,
  state, provenance and extractor/embedding facts as stored.
  Cross-links name the owning chat/character when the record
  carries one.
- scenarios (P-131..P-153): definition CRUD + duplicate over
  /scenarios, organisation (tags / favourite), the stored
  export + pack roads, the stateless import/export parse
  roads, and binding: POST /scenarios/{id}/bind seeds an
  owned EMPTY one-to-one chat - its bootstrap lines become
  the chat's opening messages and its initial flags/variables
  seed through the engine's variable store. APPLY here is:
  make a fresh chat with the chosen character, then bind.
  The seeded chat is a normal chat afterwards.

Saves compose over the stored definition document (the
lossless-overlay discipline of W-02/W-05 and desktop R-12):
the editor owns the authored text fields; structured sections
(roles, bootstrap messages, contexts, memory-book refs,
initial flags/variables) are carried verbatim unless the
editor's JSON for that section is replaced wholesale; every
unknown key of the stored document survives a save verbatim.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .engine import EngineError

# ------------------------------------------------------------- memory

MEMORY_KINDS = ("nucleus", "episodic", "semantic", "summary")
MEMORY_STATES = ("active", "superseded", "disputed", "historical",
                "invalidated", "pinned")
MEMORY_SCOPES = ("user", "global", "character", "chat", "witnesses")

SCOPE_WORDS = {
    "user": "about you",
    "global": "everywhere (global)",
    "character": "tied to a character",
    "chat": "tied to a chat",
    "witnesses": "witnessed",
}

MEMORY_READ_ONLY_NOTE = (
    "Memories are read here. The engine offers no road to "
    "create, edit or delete a memory by hand - memories are "
    "written by the engine's own extraction as chats happen, "
    "so this page offers no such controls."
)

EMBEDDING_NOTE = (
    "Which embedding model a connection uses - and whether "
    "memory recall is active - is set per backend profile in "
    "Connections; the engine offers no separate embedding or "
    "re-embedding controls."
)


def scope_words(scope) -> str:
    text = str(scope or "")
    return SCOPE_WORDS.get(text, text or "no scope recorded")


def memory_line(memory: dict) -> str:
    memory = memory if isinstance(memory, dict) else {}
    content = str(memory.get("content") or "").strip()
    bits = [content.split("\n")[0][:80] or "(empty)"]
    if memory.get("kind"):
        bits.append(str(memory["kind"]))
    if memory.get("state"):
        bits.append(str(memory["state"]))
    if memory.get("scope"):
        bits.append(scope_words(memory["scope"]))
    if memory.get("pinned"):
        bits.append("pinned")
    return " · ".join(bits)


def detail_words(detail: dict) -> str:
    """The memory detail pane: fields, sources, provenance."""
    if not detail:
        return "No memory selected."
    lines: list[str] = [str(detail.get("content", "")).strip()]
    meta: list[str] = []
    for key, label in (("kind", "Kind"), ("state", "State"),
                       ("subject", "Subject"),
                       ("predicate", "Predicate")):
        value = detail.get(key)
        if value:
            meta.append(f"{label}: {value}")
    if detail.get("scope"):
        meta.append(f"Scope: {scope_words(detail['scope'])} "
                    f"({detail['scope']})")
    for key, label in (("salience", "Salience"),
                       ("stability", "Stability"),
                       ("confidence", "Confidence")):
        value = detail.get(key)
        if isinstance(value, (int, float)):
            meta.append(f"{label}: {value:.2f}")
    if detail.get("pinned"):
        meta.append("Pinned: yes")
    recalls = detail.get("recall_count")
    if isinstance(recalls, int) and recalls:
        meta.append(f"Recalled: {recalls} time(s)")
    if detail.get("last_recalled_at"):
        meta.append(f"Last recalled: {detail['last_recalled_at']}")
    witnesses = detail.get("witnesses") or []
    if witnesses:
        meta.append("Witnesses: " + ", ".join(str(w) for w in witnesses))
    if detail.get("character_id"):
        meta.append(f"Character: {detail['character_id']}")
    if detail.get("chat_id"):
        meta.append(f"Chat: {detail['chat_id']}")
    if detail.get("supersedes_id"):
        meta.append(f"Supersedes: {detail['supersedes_id']}")
    if detail.get("created_at"):
        meta.append(f"Created: {detail['created_at']}")
    if detail.get("valid_from"):
        meta.append(f"Valid from: {detail['valid_from']}")
    if detail.get("valid_until"):
        meta.append(f"Valid until: {detail['valid_until']}")
    extractor = detail.get("extractor")
    if isinstance(extractor, dict) and extractor:
        meta.append("Extractor: " + json.dumps(extractor, sort_keys=True))
    embedding = detail.get("embedding")
    if isinstance(embedding, dict) and embedding:
        meta.append("Embedding: " + json.dumps(embedding, sort_keys=True))
    else:
        meta.append("Embedding: none recorded on this memory")
    if meta:
        lines.append("")
        lines.extend(meta)
    sources = detail.get("sources") or []
    if sources:
        lines.append("")
        lines.append("Sources:")
        for source in sources:
            if not isinstance(source, dict):
                continue
            kind = source.get("source_kind") or source.get("kind") or "source"
            ref = source.get("source_id") or source.get("ref") or ""
            line = f"- {kind}"
            if ref:
                line += f" · {ref}"
            if source.get("chat_id"):
                line += f" · chat {source['chat_id']}"
            lines.append(line)
    graph = detail.get("graph")
    if isinstance(graph, dict) and graph:
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        lines.append("")
        lines.append(
            f"Provenance graph: {len(nodes)} node(s), {len(edges)} edge(s).")
    return "\n".join(lines)


def list_memories(engine, *, q: str = "", state=None, kind=None) -> dict:
    params: dict[str, Any] = {}
    if q:
        params["q"] = q
    if state:
        params["state"] = state
    if kind:
        params["kind"] = kind
    payload = engine.request("GET", "/api/v1/memories", params=params)
    rows = payload.get("memories") if isinstance(payload, dict) else []
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    return {"memories": rows,
            "lines": [memory_line(r) for r in rows],
            "total": len(rows),
            "kinds": list(MEMORY_KINDS), "states": list(MEMORY_STATES),
            "scopes": list(MEMORY_SCOPES),
            "note": MEMORY_READ_ONLY_NOTE,
            "embedding_note": EMBEDDING_NOTE}


def memory_detail(engine, memory_id: str) -> dict:
    payload = engine.request("GET", f"/api/v1/memories/{memory_id}")
    payload = payload if isinstance(payload, dict) else {}
    return {"memory": payload, "words": detail_words(payload),
            "line": memory_line(payload)}

# ---------------------------------------------------------- scenarios

#: The authored text fields, in form order (desktop R-12 parity):
#: (key, label, long?).
AUTHORED_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("name", "Name", False),
    ("description", "Description", True),
    ("scenario_text", "Scenario", True),
    ("flow", "Flow", False),
    ("style", "Style", False),
    ("template_text", "Template", True),
    ("system_prompt_text", "System prompt", True),
    ("system_prompt_mode", "System prompt mode", False),
    ("impersonation_name", "Impersonation name", False),
    ("impersonation_description", "Impersonation description", True),
    ("narrator_name", "Narrator name", False),
    ("narrator_voice", "Narrator voice", False),
)

#: Structured sections: (key, label, JSON kind). Carried verbatim
#: unless the editor replaces that section's JSON wholesale.
STRUCTURED_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("roles", "Roles", "list"),
    ("bootstrap_messages", "Bootstrap messages", "list"),
    ("contexts", "Contexts", "list"),
    ("memory_book_refs", "Memory-book refs", "list"),
    ("initial_flags", "Initial flags", "object"),
    ("initial_variables", "Initial variables", "object"),
)

SECTION_KEYS = tuple(k for k, _l, _k in STRUCTURED_SECTIONS)


def scenario_line(row: dict) -> str:
    row = row if isinstance(row, dict) else {}
    bits = [str(row.get("name") or "(unnamed scenario)")]
    roles = row.get("role_count")
    if isinstance(roles, int) and roles:
        bits.append(f"{roles} role(s)")
    boot = row.get("bootstrap_count")
    if isinstance(boot, int) and boot:
        bits.append(f"{boot} opening line(s)")
    if row.get("is_favourite"):
        bits.append("★ favourite")
    tags = row.get("tags") or []
    if tags:
        bits.append("tags: " + ", ".join(str(t) for t in tags))
    if row.get("has_unmappable"):
        bits.append("carries unmappable elements (recorded, never run)")
    return " · ".join(bits)


def carried_words(definition: dict) -> str:
    parts: list[str] = []
    for key, label, _kind in STRUCTURED_SECTIONS:
        value = definition.get(key) if isinstance(definition, dict) else None
        if isinstance(value, list) and value:
            parts.append(f"{label.lower()}: {len(value)}")
        elif isinstance(value, dict) and value:
            parts.append(f"{label.lower()}: {len(value)}")
    if not parts:
        return "No structured sections (roles, bootstrap, contexts) yet."
    return "Carried unchanged on save unless replaced below - " + " · ".join(parts)


def parse_section(key: str, kind: str, raw):
    """Parse one editor JSON section; EngineError on bad shape."""
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        value = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise EngineError(f"{key}: not valid JSON ({exc})", status=422) from exc
    if kind == "list" and not isinstance(value, list):
        raise EngineError(f"{key}: must be a JSON list", status=422)
    if kind == "object" and not isinstance(value, dict):
        raise EngineError(f"{key}: must be a JSON object", status=422)
    return value


def compose_definition(stored: dict, values: dict,
                       sections: dict | None = None) -> dict:
    """Lay the form's authored fields over the stored definition.

    Every key the form does not own survives verbatim (deep
    copy); a structured section is replaced only when the
    caller parsed a replacement for it.
    """
    document = copy.deepcopy(stored) if isinstance(stored, dict) else {}
    values = values if isinstance(values, dict) else {}
    for key, _label, _long in AUTHORED_FIELDS:
        if key in values:
            document[key] = str(values.get(key) or "")
    for key, value in (sections or {}).items():
        if key in SECTION_KEYS and value is not None:
            document[key] = copy.deepcopy(value)
    return document


def binding_words(binding: dict) -> str:
    if not binding:
        return "This chat has no scenario bound."
    name = binding.get("definition_name") or binding.get("name") or ""
    bits = ["Bound scenario: " + (name or str(binding.get("definition_id", "")))]
    seeded = binding.get("seeded_messages")
    if isinstance(seeded, list):
        bits.append(f"{len(seeded)} opening line(s) seeded")
    elif isinstance(binding.get("seeded_message_count"), int):
        bits.append(f"{binding['seeded_message_count']} opening line(s) seeded")
    keys = binding.get("seeded_keys")
    if isinstance(keys, list) and keys:
        bits.append("seeded: " + ", ".join(str(k) for k in keys))
    skipped = binding.get("skipped")
    if isinstance(skipped, list) and skipped:
        bits.append(f"{len(skipped)} skipped (named in the binding record)")
    if binding.get("definition_exists") is False:
        bits.append("the definition itself is gone (stale binding)")
    return " · ".join(bits)


def bindings_lines(bindings: list) -> list[str]:
    lines: list[str] = []
    for binding in bindings or []:
        if not isinstance(binding, dict):
            continue
        name = (binding.get("definition_name") or binding.get("name")
                or binding.get("definition_id", ""))
        chat = binding.get("chat_id", "")
        line = f"{name} → chat {str(chat)[:8]}…"
        if binding.get("definition_exists") is False:
            line += " · stale (definition gone)"
        count = binding.get("seeded_message_count")
        if isinstance(count, int):
            line += f" · {count} opening line(s)"
        lines.append(line)
    return lines


def list_scenarios(engine, *, q: str = "", favourites_only: bool = False) -> dict:
    params: dict[str, Any] = {}
    if q:
        params["q"] = q
    if favourites_only:
        params["favourites_only"] = "true"
    payload = engine.request("GET", "/api/v1/scenarios", params=params)
    rows = payload.get("scenarios") if isinstance(payload, dict) else []
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    return {"scenarios": rows, "lines": [scenario_line(r) for r in rows],
            "total": payload.get("total", len(rows)) if isinstance(payload, dict) else len(rows)}


def scenario_detail(engine, definition_id: str) -> dict:
    record = engine.request("GET", f"/api/v1/scenarios/{definition_id}")
    record = record if isinstance(record, dict) else {}
    definition = record.get("definition")
    definition = definition if isinstance(definition, dict) else {}
    org = {}
    try:
        org = engine.request(
            "GET", f"/api/v1/scenarios/{definition_id}/organisation")
        org = org if isinstance(org, dict) else {}
    except EngineError:
        org = {}
    binds = []
    try:
        payload = engine.request(
            "GET", f"/api/v1/scenarios/{definition_id}/bindings")
        rows = payload.get("bindings") if isinstance(payload, dict) else payload
        binds = [b for b in (rows or []) if isinstance(b, dict)]
    except EngineError:
        binds = []
    return {"record": record, "definition": definition,
            "organisation": org, "bindings": binds,
            "binding_lines": bindings_lines(binds),
            "carried": carried_words(definition),
            "fields": [{"name": k, "label": label, "long": long}
                       for k, label, long in AUTHORED_FIELDS],
            "sections": [{"name": k, "label": label, "kind": kind,
                          "json": _section_json(definition, k, kind)}
                         for k, label, kind in STRUCTURED_SECTIONS]}


def save_scenario(engine, definition_id, body: dict) -> dict:
    body = body if isinstance(body, dict) else {}
    values = body.get("values") if isinstance(body.get("values"), dict) else {}
    raw_sections = body.get("sections") if isinstance(body.get("sections"), dict) else {}
    sections = {}
    for key, _label, kind in STRUCTURED_SECTIONS:
        if key in raw_sections:
            parsed = parse_section(key, kind, raw_sections.get(key))
            if parsed is not None:
                sections[key] = parsed
    if definition_id:
        stored = engine.request("GET", f"/api/v1/scenarios/{definition_id}")
        stored_def = stored.get("definition") if isinstance(stored, dict) else {}
        document = compose_definition(
            stored_def if isinstance(stored_def, dict) else {}, values, sections)
        record = engine.request(
            "PUT", f"/api/v1/scenarios/{definition_id}", json_body=document)
    else:
        base = body.get("document")
        document = compose_definition(
            base if isinstance(base, dict) else {}, values, sections)
        record = engine.request("POST", "/api/v1/scenarios", json_body=document)
    record = record if isinstance(record, dict) else {}
    return {"record": record, "id": record.get("id", ""),
            "words": f"Saved scenario: {record.get('name') or document.get('name') or ''}"}


def delete_scenario(engine, definition_id: str) -> dict:
    payload = engine.request("DELETE", f"/api/v1/scenarios/{definition_id}")
    return {"deleted": True, "id": definition_id,
            "words": "Scenario deleted. Chats it seeded keep their "
                     "opening lines and variables - those are the "
                     "chats' own truth now; any binding left behind "
                     "is named stale, never hidden.",
            "engine": payload if isinstance(payload, dict) else {}}


def duplicate_scenario(engine, definition_id: str) -> dict:
    record = engine.request(
        "POST", f"/api/v1/scenarios/{definition_id}/duplicate")
    record = record if isinstance(record, dict) else {}
    return {"record": record, "id": record.get("id", ""),
            "words": f"Duplicated as: {record.get('name') or ''}"}


def set_favourite(engine, definition_id: str, value: bool) -> dict:
    org = engine.request("PUT", f"/api/v1/scenarios/{definition_id}/favourite",
                         json_body={"is_favourite": bool(value)})
    return {"organisation": org if isinstance(org, dict) else {},
            "words": "Favourite set." if value else "Favourite cleared."}


def set_tags(engine, definition_id: str, tags) -> dict:
    if isinstance(tags, str):
        tags = tags.replace(",", chr(10)).splitlines()
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()]
    org = engine.request("PUT", f"/api/v1/scenarios/{definition_id}/tags",
                         json_body={"tags": cleaned})
    return {"organisation": org if isinstance(org, dict) else {},
            "tags": cleaned,
            "words": "Tags saved: " + (", ".join(cleaned) or "(none)")}


def list_bindings(engine) -> dict:
    payload = engine.request("GET", "/api/v1/scenarios/bindings")
    rows = payload.get("bindings") if isinstance(payload, dict) else []
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    return {"bindings": rows, "lines": bindings_lines(rows),
            "total": len(rows)}


def chat_binding(engine, chat_id: str) -> dict:
    try:
        binding = engine.request(
            "GET", f"/api/v1/scenarios/bindings/{chat_id}")
    except EngineError as exc:
        if exc.status == 404:
            return {"binding": None, "words": binding_words({})}
        raise
    binding = binding if isinstance(binding, dict) else None
    return {"binding": binding, "words": binding_words(binding or {})}


def apply_scenario(engine, definition_id: str, character_id: str) -> dict:
    """Start a chat from a scenario: fresh chat, then bind.

    The bind is the engine's own seeding act (bootstrap lines
    become opening messages; initial flags/variables seed
    missing keys only). If the bind refuses, the fresh chat
    still exists - the answer says so plainly and names it.
    """
    if not character_id:
        raise EngineError("pick a character to start the chat with",
                          status=422)
    # The scenario's bootstrap lines are the opening act, so the
    # chat is made with the engine's quiet greeting mode - the
    # card greeting would land first and the bind would then
    # honestly refuse a non-empty chat (P-079/P-132).
    chat = engine.request("POST", "/api/v1/chats", json_body={
        "character_id": character_id, "greeting_mode": "quiet"})
    chat = chat if isinstance(chat, dict) else {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        raise EngineError("the engine made no chat to bind", status=502)
    binding = engine.request(
        "POST", f"/api/v1/scenarios/{definition_id}/bind",
        json_body={"chat_id": chat_id})
    binding = binding if isinstance(binding, dict) else {}
    return {"chat": chat, "chat_id": chat_id, "binding": binding,
            "words": binding_words(binding),
            "note": "The chat is a normal chat now: pin a mind in "
                    "Connections before sending, like any chat."}


def unbind_scenario(engine, chat_id: str) -> dict:
    payload = engine.request(
        "DELETE", f"/api/v1/scenarios/bindings/{chat_id}")
    return {"unbound": True, "chat_id": chat_id,
            "words": "Binding removed. The seeded opening lines and "
                     "variables stay - they are the chat's own truth.",
            "engine": payload if isinstance(payload, dict) else {}}


def check_import(engine, document) -> dict:
    """Parse a scenario file WITHOUT storing it (the import road)."""
    if not isinstance(document, dict):
        raise EngineError("a scenario file must be a JSON object", status=422)
    payload = engine.request("POST", "/api/v1/scenarios/import",
                             json_body=document)
    payload = payload if isinstance(payload, dict) else {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    unmappable = report.get("unmappable") or []
    return {"source_format": payload.get("source_format", ""),
            "scenario": payload.get("scenario") or {},
            "report": report,
            "words": "Parsed as " + str(payload.get("source_format") or "?")
                     + f"; {len(unmappable)} unmappable element(s) "
                     "recorded, never run. Nothing was stored - "
                     "use 'Store this scenario' to keep it."}


def export_document(engine, definition: dict, fmt: str = "native") -> dict:
    fmt = fmt if fmt in ("native", "voxta") else "native"
    payload = engine.request("POST", "/api/v1/scenarios/export",
                             params={"format": fmt}, json_body=definition)
    return payload if isinstance(payload, dict) else {}


def _section_json(definition: dict, key: str, kind: str) -> str:
    value = definition.get(key)
    if value is None:
        value = [] if kind == "list" else {}
    return json.dumps(value, indent=2)


def editor_model() -> dict:
    """The editor's fixed field model (the engine's scenario shape)."""
    empty: dict = {}
    return {"fields": [{"name": k, "label": label, "long": long}
                       for k, label, long in AUTHORED_FIELDS],
            "sections": [{"name": k, "label": label, "kind": kind,
                          "json": json.dumps([] if kind == "list" else {})}
                         for k, label, kind in STRUCTURED_SECTIONS],
            "carried": carried_words(empty)}
