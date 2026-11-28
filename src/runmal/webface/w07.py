"""W-07 compositions: Inspector + Tools tabs (desktop R-12 parity).

All over EXISTING engine roads (no new engine routes):

- inspector documents (P-203/P-204/P-210): GET
  /inspector/chats/{id} (overview: P-075 provenance summary
  verbatim, P-059 prompt-road pointers, P-043 bound-lorebook
  pointers, scenario-binding state), .../events (S107 census)
  and .../reasoning (P-205 census). Pure reads; the words
  renderers below are the desktop's own (inspector_logic),
  ported line for line.
- prompt trace + preview (P-059/S214/S215): POST
  /debug/prompt-inspect with include_activation_inspection
  and include_preview, exactly the desktop client's call.
  The TRACE carries no prompt content by the engine's own
  S214 contract - ids, kinds, token counts, statuses,
  reasons, triggers, provenance only. The PREVIEW is the
  separate explicit payload that carries the composed
  messages' text; the tab shows the two as what they are
  and never presents one as the other. Token counts are the
  engine's own, carried verbatim - nothing is recounted
  here. The inspect road composes a hypothetical next turn
  and sends nothing, so the FIX-STUB guard has nothing to
  guard: no generation runs and no message can land.
- per-message provenance (P-075): GET
  /chats/{id}/messages/{mid}/provenance - the recorded
  generation provenance of one landed reply.
- tools (S213/S307/P-055): the macro registry GET
  /tools/macros, expansion POST /tools/macros/expand (the
  engine's own expansion - seeded expansions are
  deterministic), the variable registry GET /tools/variables
  and resolver POST /tools/resolve, and the compose preview
  POST /tools/compose. The desktop's Compose & Macros
  explorer is exactly these roads.

Honest gaps (no engine road exists, so no control is
wired): there is NO callable-tool registry in the engine -
nothing lists, enables, disables or assigns agent tools,
and no road records tool calls - so this tab offers no
such controls and says so in words. The generation-session
driver (POST /tools/session) is an engine-internal state
machine the desktop does not surface either; it is not
wired here.
"""
from __future__ import annotations

from typing import Any

TRACE_CONTENT_NOTE = (
    "The trace itself carries no prompt text - that is the "
    "engine's own safety contract (ids, kinds, token counts, "
    "statuses and reasons only). The section texts below come "
    "from the engine's separate preview payload for the same "
    "composition, labelled as such."
)

INSPECT_NOTE = (
    "Inspecting composes a hypothetical next turn and sends "
    "nothing: no generation runs, no message lands, and no "
    "profile is needed - the stub guard governs sends, and "
    "this page never sends."
)

TOOLS_SCOPE_NOTE = (
    "The engine has no callable-tool registry: no road lists, "
    "enables, disables or assigns agent tools, and no road "
    "records tool calls - so this page offers no such "
    "controls. What the engine does expose is the prompt "
    "toolbox below: macros, variables and the compose "
    "preview, which is what the desktop's Tools explorer "
    "shows."
)

VARIABLES_NOTE = (
    "Variables are the older, smaller registry (char, user, "
    "original and the clock) that the compose preview "
    "resolves; macros above are the full documented set. "
    "Resolving runs the engine's own resolver - unknown "
    "names are flagged, never silently dropped."
)

# ------------------------------------------------- inspector words
# Ported from runmal.desktop.inspector_logic (R-12), unchanged
# in wording: the desktop's panels are the parity target.

STATUS_WORDS = {
    "included": "Included",
    "discarded": "Discarded",
    "not_triggered": "Not triggered",
    "disabled": "Disabled",
    "trimmed": "Trimmed",
}


def ledger_words(trace: dict) -> str:
    ledger = trace.get("ledger") or {}
    if not ledger:
        return "No token ledger in this trace."
    return (
        f"Context limit {ledger.get('context_limit', '?')} · "
        f"reserved for the reply {ledger.get('reserved_response', '?')} · "
        f"overhead {ledger.get('overhead', '?')} · "
        f"input budget {ledger.get('input_budget', '?')} · "
        f"input used {ledger.get('total_input_tokens', '?')} · "
        f"remaining {ledger.get('remaining_input_tokens', '?')}"
    )


def slot_lines(trace: dict) -> list[str]:
    """One line per slot: kind - status - tokens - why."""
    lines: list[str] = []
    for slot in trace.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        kind = str(slot.get("kind") or slot.get("slot_id") or "slot")
        status = STATUS_WORDS.get(
            str(slot.get("status") or ""), str(slot.get("status") or ""))
        tokens = slot.get("tokens")
        line = f"{kind} — {status}"
        if isinstance(tokens, int):
            line += f" · {tokens} tokens"
        reason = str(slot.get("reason") or "").strip()
        if reason:
            line += f" · {reason}"
        trigger = slot.get("trigger")
        if isinstance(trigger, str) and trigger.strip():
            line += f" · triggered by \"{trigger.strip()}\""
        elif isinstance(trigger, dict) and trigger:
            via = trigger.get("via") or trigger.get("kind") or ""
            key = trigger.get("key") or trigger.get("matched") or ""
            detail = " ".join(str(p) for p in (via, key) if p)
            if detail:
                line += f" · triggered {detail}"
        provenance = str(slot.get("provenance") or "").strip()
        if provenance:
            line += f" · from {provenance}"
        lines.append(line)
    return lines


def lore_account_words(trace: dict) -> list[str]:
    account = trace.get("lore_account")
    lines: list[str] = []
    if isinstance(account, dict) and account:
        entries = account.get("entries")
        entry_count = len(entries) if isinstance(entries, list) else 0
        lines.append(
            "Lore: "
            f"{account.get('tokens_used', 0)} tokens used · "
            f"{account.get('discarded_tokens', 0)} discarded · "
            f"{entry_count} entr(ies) in the prompt")
        by_provenance = account.get("by_provenance")
        if isinstance(by_provenance, dict):
            for provenance, tally in by_provenance.items():
                if isinstance(tally, dict):
                    lines.append(
                        f"- {provenance}: "
                        f"{tally.get('tokens_used', 0)} tokens · "
                        f"{tally.get('entries', 0)} entr(ies)")
    return lines


def _scalar(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, dict)):
        return "[]" if not value else "{}"
    return str(value)


def document_words(document, *, indent: int = 0) -> list[str]:
    """Render a sectioned engine document as plain words
    (the desktop's generic renderer, depth-capped)."""
    pad = "  " * indent
    lines: list[str] = []
    if indent > 4:
        return [pad + "…"]
    if isinstance(document, dict):
        for key, value in document.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{key}:")
                lines.extend(document_words(value, indent=indent + 1))
            else:
                lines.append(f"{pad}{key}: {_scalar(value)}")
    elif isinstance(document, list):
        for item in document:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(document_words(item, indent=indent + 1))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    else:
        lines.append(pad + _scalar(document))
    return lines


def preview_sections(preview) -> list[dict]:
    """The preview payload's composed messages, in order:
    the section texts of the composition, each with the
    slot it came from and its role - exactly as the engine's
    preview reports them."""
    preview = preview if isinstance(preview, dict) else {}
    out: list[dict] = []
    for message in preview.get("messages") or []:
        if not isinstance(message, dict):
            continue
        out.append({
            "slot_id": str(message.get("slot_id") or ""),
            "role": str(message.get("role") or ""),
            "content": str(message.get("content") or ""),
        })
    return out


def preview_words(preview) -> str:
    preview = preview if isinstance(preview, dict) else {}
    if not preview:
        return "No preview in this result."
    bits = []
    if preview.get("template_name"):
        bits.append(f"instruct rendering: {preview['template_name']}")
    if isinstance(preview.get("rendered_tokens"), int):
        bits.append(f"rendered text: {preview['rendered_tokens']} tokens "
                    "(the engine's own estimate for the rendered string)")
    note = str(preview.get("note") or "").strip()
    head = " · ".join(bits)
    return "\n".join(p for p in (head, note) if p) or "Preview present."

# ------------------------------------------------------- inspector


def _chat_row(engine, chat_id: str) -> dict:
    payload = engine.request("GET", f"/api/v1/chats/{chat_id}")
    return payload if isinstance(payload, dict) else {}


def sample_messages(engine, chat_id: str, limit: int = 20) -> list[str]:
    """The chat's stored message texts, oldest first, capped
    at the last ``limit`` - the sample the desktop hands the
    trace (lore scanning reads message text)."""
    rows = engine.list_messages(chat_id)
    texts = [str(r.get("content") or "") for r in rows
             if isinstance(r, dict)]
    return texts[-limit:]


def inspector_documents(engine, chat_id: str) -> dict:
    overview = engine.request(
        "GET", f"/api/v1/inspector/chats/{chat_id}")
    events = engine.request(
        "GET", f"/api/v1/inspector/chats/{chat_id}/events")
    reasoning = engine.request(
        "GET", f"/api/v1/inspector/chats/{chat_id}/reasoning")
    overview = overview if isinstance(overview, dict) else {}
    events = events if isinstance(events, dict) else {}
    reasoning = reasoning if isinstance(reasoning, dict) else {}
    return {
        "chat_id": chat_id,
        "overview": overview,
        "overview_words": "\n".join(document_words(overview)),
        "events": events,
        "events_words": "\n".join(document_words(events)),
        "reasoning": reasoning,
        "reasoning_words": "\n".join(document_words(reasoning)),
        "note": INSPECT_NOTE,
    }


def inspector_trace(engine, chat_id: str) -> dict:
    """The desktop's trace call, verbatim in shape: the chat,
    its character, the stored message texts as the sample,
    activation inspection on, preview on. Pure composition -
    nothing is generated and nothing lands."""
    chat = _chat_row(engine, chat_id)
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "include_activation_inspection": True,
        "include_preview": True,
        "messages": sample_messages(engine, chat_id),
    }
    character_id = chat.get("character_id")
    if character_id:
        body["character_id"] = str(character_id)
    result = engine.request(
        "POST", "/api/v1/debug/prompt-inspect", json_body=body)
    result = result if isinstance(result, dict) else {}
    preview = result.get("prompt_preview")
    preview = preview if isinstance(preview, dict) else {}
    return {
        "chat_id": chat_id,
        "trace": result,
        "ledger_words": ledger_words(result),
        "slot_lines": slot_lines(result),
        "lore_lines": lore_account_words(result),
        "preview": preview,
        "sections": preview_sections(preview),
        "preview_words": preview_words(preview),
        "content_note": TRACE_CONTENT_NOTE,
    }


def message_provenance(engine, chat_id: str, message_id: str) -> dict:
    payload = engine.request(
        "GET", f"/api/v1/chats/{chat_id}/messages/{message_id}/provenance")
    payload = payload if isinstance(payload, dict) else {}
    return {"provenance": payload,
            "words": "\n".join(document_words(payload))}

# ------------------------------------------------------------ tools
# Words ported from runmal.desktop.compose_logic (R-12).


def macro_line(macro: dict) -> str:
    macro = macro if isinstance(macro, dict) else {}
    name = str(macro.get("name") or "")
    syntax = str(macro.get("syntax") or "")
    description = str(macro.get("description") or "")
    head = syntax or ("{{" + name + "}}")
    return f"{head} — {description}" if description else head


def expansion_words(result: dict) -> str:
    if not result:
        return "Nothing came back."
    text = result.get("text") or result.get("expanded") or ""
    if text:
        return str(text)
    return str(result)


def expansion_report_words(result: dict) -> list[str]:
    """The expansion report in words: what expanded, what
    rolled, what stayed unknown - from the engine's report."""
    report = (result or {}).get("report")
    report = report if isinstance(report, dict) else {}
    lines: list[str] = []
    for row in report.get("expansions") or []:
        if isinstance(row, dict):
            lines.append(f"{row.get('raw', '')} → {row.get('value', '')}")
    for row in report.get("rolls") or []:
        if isinstance(row, dict):
            seeded = "seeded" if row.get("seeded") else "unseeded (not reproducible)"
            lines.append(f"roll for {row.get('raw', '')}: {seeded}, "
                         f"outcome {row.get('outcome', '')}")
    unknown = report.get("unknown") or []
    if unknown:
        lines.append("Left as written (unknown): " + ", ".join(
            str(u) for u in unknown))
    errors = report.get("errors") or []
    if errors:
        lines.append("Errors: " + ", ".join(str(e) for e in errors))
    return lines


def compose_words(result: dict) -> str:
    """The compose preview as words: messages, then the account."""
    if not result:
        return "Nothing came back."
    lines: list[str] = []
    messages = result.get("messages") or []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role") or "")
            content = str(message.get("content") or "")
            lines.append(f"[{role}] {content}")
        else:
            lines.append(str(message))
    if not messages:
        lines.append("(no messages — every field was empty)")
    ledger = result.get("ledger") or result.get("budget") or {}
    if isinstance(ledger, dict) and ledger:
        bits = []
        for key in ("context_limit", "input_budget",
                    "total_input_tokens", "remaining_input_tokens"):
            if key in ledger:
                bits.append(f"{key.replace('_', ' ')} {ledger[key]}")
        if bits:
            lines.append("")
            lines.append(" · ".join(bits))
    dropped = result.get("dropped") or result.get("discards") or []
    if dropped:
        lines.append(f"Dropped to fit: {len(dropped)} part(s).")
    return "\n".join(lines)


def compose_manifest_words(result: dict) -> str:
    """The compose result's own manifest account, when the
    result carries one (the composer's token account)."""
    manifest = (result or {}).get("manifest")
    if not isinstance(manifest, dict) or not manifest:
        return ""
    return "\n".join(document_words(manifest))


def variable_line(variable: dict) -> str:
    variable = variable if isinstance(variable, dict) else {}
    name = str(variable.get("name") or "")
    description = str(variable.get("description") or "")
    example = str(variable.get("example") or "")
    head = "{{" + name + "}}"
    line = f"{head} — {description}" if description else head
    if example:
        line += f" (e.g. {example})"
    return line


def resolve_words(result: dict) -> str:
    if not result:
        return "Nothing came back."
    lines = [str(result.get("text") or "")]
    unknown = result.get("unknown") or []
    if unknown:
        lines.append("Unknown, left as written: " + ", ".join(
            str(u) for u in unknown))
    resolved = result.get("resolved") or []
    if resolved:
        lines.append("Resolved: " + ", ".join(str(r) for r in resolved))
    return "\n".join(lines)


def list_macros(engine) -> dict:
    payload = engine.request("GET", "/api/v1/tools/macros")
    rows = [r for r in (payload or []) if isinstance(r, dict)] \
        if isinstance(payload, list) else []
    return {"macros": rows, "lines": [macro_line(r) for r in rows],
            "total": len(rows), "note": TOOLS_SCOPE_NOTE}


def expand_macros(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    text = str(payload.get("text") or "")
    body: dict[str, Any] = {
        "text": text,
        "char": str(payload.get("char") or ""),
        "user": str(payload.get("user") or "User"),
    }
    seed = payload.get("seed")
    if isinstance(seed, int) and not isinstance(seed, bool):
        body["seed"] = seed
    result = engine.request(
        "POST", "/api/v1/tools/macros/expand", json_body=body)
    result = result if isinstance(result, dict) else {}
    return {"result": result, "words": expansion_words(result),
            "report_lines": expansion_report_words(result)}


def list_variables(engine) -> dict:
    payload = engine.request("GET", "/api/v1/tools/variables")
    rows = [r for r in (payload or []) if isinstance(r, dict)] \
        if isinstance(payload, list) else []
    return {"variables": rows,
            "lines": [variable_line(r) for r in rows],
            "total": len(rows), "note": VARIABLES_NOTE}


def resolve_variables(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {
        "text": str(payload.get("text") or ""),
        "char": str(payload.get("char") or ""),
        "user": str(payload.get("user") or "User"),
    }
    if payload.get("chat_id"):
        body["chat_id"] = str(payload["chat_id"])
    result = engine.request(
        "POST", "/api/v1/tools/resolve", json_body=body)
    result = result if isinstance(result, dict) else {}
    return {"result": result, "words": resolve_words(result)}


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compose_preview(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    history = payload.get("history") or []
    if isinstance(history, str):
        history = [ln for ln in history.split("\n") if ln.strip()]
    body: dict[str, Any] = {
        "system": str(payload.get("system") or ""),
        "persona": str(payload.get("persona") or ""),
        "history": [str(h) for h in history if isinstance(history, list)],
        "authors_note": str(payload.get("authors_note") or ""),
        "note_depth": _as_int(payload.get("note_depth"), 0),
        "context_limit": _as_int(payload.get("context_limit"), 4096),
        "reserve_response": _as_int(payload.get("reserve_response"), 512),
    }
    result = engine.request(
        "POST", "/api/v1/tools/compose", json_body=body)
    result = result if isinstance(result, dict) else {}
    return {"result": result, "words": compose_words(result),
            "manifest_words": compose_manifest_words(result)}
