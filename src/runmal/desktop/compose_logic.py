"""Compose & macros logic for the desktop shell (R-12) — Qt-free.

The explorer over the engine's tools surface (S307/P-055): the
macro registry as readable lines, macro expansion of a sample
text, and the compose preview (system / persona / history /
author's note under a token budget) rendered as the messages
it would send plus its token account, in words.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import RunmalClient


def macro_line(macro: dict[str, Any]) -> str:
    name = str(macro.get("name") or "")
    syntax = str(macro.get("syntax") or "")
    description = str(macro.get("description") or "")
    head = syntax or ("{{" + name + "}}")
    return f"{head} — {description}" if description else head


def expansion_words(result: dict[str, Any]) -> str:
    if not result:
        return "Nothing came back."
    text = result.get("text") or result.get("expanded") or ""
    if text:
        return str(text)
    return str(result)


def compose_words(result: dict[str, Any]) -> str:
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
        for key in (
            "context_limit",
            "input_budget",
            "total_input_tokens",
            "remaining_input_tokens",
        ):
            if key in ledger:
                bits.append(f"{key.replace('_', ' ')} {ledger[key]}")
        if bits:
            lines.append("")
            lines.append(" · ".join(bits))
    dropped = result.get("dropped") or result.get("discards") or []
    if dropped:
        lines.append(f"Dropped to fit: {len(dropped)} part(s).")
    return "\n".join(lines)


class ComposeFlow:
    """The Compose dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def macros(self) -> list[dict[str, Any]]:
        return self._client.list_macros()

    def expand(
        self, text: str, *, char: str = "", user: str = "User"
    ) -> dict[str, Any]:
        return self._client.expand_macros(text, char=char, user=user)

    def compose(
        self,
        *,
        system: str = "",
        persona: str = "",
        history: list[str] | None = None,
        authors_note: str = "",
        note_depth: int = 0,
        context_limit: int = 4096,
        reserve_response: int = 512,
    ) -> dict[str, Any]:
        return self._client.compose_preview(
            system=system,
            persona=persona,
            history=history,
            authors_note=authors_note,
            note_depth=note_depth,
            context_limit=context_limit,
            reserve_response=reserve_response,
        )
