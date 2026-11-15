"""Prompt-inspector logic for the desktop shell (R-12) — Qt-free.

The inspector answers one question in words: for the open
chat's next turn, what would the prompt contain, and why? The
engine's trace (``POST /debug/prompt-inspect``) carries a
ledger (the token account) and slots, each with a status and a
reason. This module renders both, plus a generic
document-to-words renderer for the P-203 overview, P-204
events census and P-210 reasoning census documents, whose
shapes are sectioned dicts.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import RunmalClient

STATUS_WORDS = {
    "included": "Included",
    "discarded": "Discarded",
    "not_triggered": "Not triggered",
    "disabled": "Disabled",
    "trimmed": "Trimmed",
}


def ledger_words(trace: dict[str, Any]) -> str:
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


def slot_lines(trace: dict[str, Any]) -> list[str]:
    """One line per slot: kind — status — tokens — why."""
    lines: list[str] = []
    for slot in trace.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        kind = str(slot.get("kind") or slot.get("slot_id") or "slot")
        status = STATUS_WORDS.get(
            str(slot.get("status") or ""), str(slot.get("status") or "")
        )
        tokens = slot.get("tokens")
        line = f"{kind} — {status}"
        if isinstance(tokens, int):
            line += f" · {tokens} tokens"
        reason = str(slot.get("reason") or "").strip()
        if reason:
            line += f" · {reason}"
        trigger = slot.get("trigger")
        if isinstance(trigger, str) and trigger.strip():
            # The engine names the matched key itself ("ember").
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


def lore_account_words(trace: dict[str, Any]) -> list[str]:
    """The lore account, when the trace carries one.

    The engine's account (``account_from_trace``) counts tokens:
    ``tokens_used`` / ``discarded_tokens`` overall, an
    ``entries`` list, and a ``by_provenance`` breakdown keyed by
    ``lorebook:<name>@<scope>``.
    """
    account = trace.get("lore_account")
    lines: list[str] = []
    if isinstance(account, dict) and account:
        entries = account.get("entries")
        entry_count = len(entries) if isinstance(entries, list) else 0
        lines.append(
            "Lore: "
            f"{account.get('tokens_used', 0)} tokens used · "
            f"{account.get('discarded_tokens', 0)} discarded · "
            f"{entry_count} entr(ies) in the prompt"
        )
        by_provenance = account.get("by_provenance")
        if isinstance(by_provenance, dict):
            for provenance, tally in by_provenance.items():
                if isinstance(tally, dict):
                    lines.append(
                        f"- {provenance}: "
                        f"{tally.get('tokens_used', 0)} tokens · "
                        f"{tally.get('entries', 0)} entr(ies)"
                    )
    return lines


def document_words(document: Any, *, indent: int = 0) -> list[str]:
    """Render a sectioned engine document as plain words.

    Dicts become headed sections; scalars become ``key: value``
    lines; lists of scalars join with commas, lists of dicts
    recurse with a dash. Depth-capped so a pathological
    document stays readable.
    """
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


def _scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, dict)):
        return "[]" if not value else "{}"
    return str(value)


class InspectorFlow:
    """The Inspector dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def overview(self, chat_id: str) -> dict[str, Any]:
        return self._client.inspector_overview(chat_id)

    def events(self, chat_id: str) -> dict[str, Any]:
        return self._client.inspector_events(chat_id)

    def reasoning(self, chat_id: str) -> dict[str, Any]:
        return self._client.inspector_reasoning(chat_id)

    def trace(
        self,
        chat_id: str,
        *,
        character_id: str | None = None,
        messages: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._client.prompt_inspect(
            chat_id=chat_id,
            character_id=character_id,
            messages=messages,
        )
