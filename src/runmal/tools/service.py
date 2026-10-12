"""Prompt tools service (S213): UI-facing drivers over S205/S206/S209.

- ``compose_preview`` runs the prompt composer with an Author's Note depth
  injection and returns messages + manifest. Impossible prompt states
  raise :class:`runmal.prompt.ImpossiblePromptError` (surfaced as a
  visible 422 by the router, never a silent truncation).
- ``drive_session`` advances the S209 generation-session state machine by
  one action. The session travels as its serialized dict, so the tools UI
  is stateless on the server and candidate state persists client-side.
"""

from __future__ import annotations

import dataclasses

from runmal.generation.modes import GenerationSession, Mode
from runmal.prompt import baseline_order, compose, make_slot
from runmal.prompt.slots import Slot


def compose_preview(
    system: str = "",
    persona: str = "",
    history: list[str] | None = None,
    authors_note: str = "",
    note_depth: int = 0,
    context_limit: int = 4096,
    reserve_response: int = 512,
) -> dict:
    slots = []
    if system:
        slots.append(
            make_slot("main_system", "system", system, id="system", required=True)
        )
    if persona:
        slots.append(make_slot("persona", "system", persona, id="persona"))
    if history:
        slots.append(
            Slot(
                id="history",
                kind="history",
                role="user",
                order=baseline_order("history"),
                splittable=True,
                parts=tuple(history),
            )
        )
    if authors_note:
        slots.append(
            make_slot(
                "authors_note", "system", authors_note, id="note", depth=note_depth
            )
        )
    result = compose(
        slots, context_limit=context_limit, reserve_response=reserve_response
    )
    return dataclasses.asdict(result)


def drive_session(
    action: str,
    session_data: dict | None = None,
    mode: str = "normal",
    messages: list[dict] | None = None,
    content: str = "",
    delta: int = 0,
) -> dict:
    """Apply one action; returns {"session": ..., "result": ...}."""
    if action == "create":
        session = GenerationSession(mode=Mode(mode))
        return {"session": session.to_dict(), "result": {"state": "idle"}}
    if session_data is None:
        raise ValueError("session is required for this action")
    session = GenerationSession.from_dict(session_data)
    result: dict = {}
    if action == "compose":
        result["fingerprint"] = session.compose(messages or [])
    elif action == "begin":
        session.begin()
    elif action == "complete":
        cand = session.complete(content)
        result["candidate"] = cand.to_dict()
    elif action == "swipe":
        result["moved"] = session.swipe(delta)
        result["active"] = session.active().to_dict()
    elif action == "regenerate":
        session.regenerate(messages or [])
    elif action == "commit":
        role, text = session.commit()
        result["role"] = role
        result["content"] = text
    elif action == "abort":
        session.abort()
    else:
        raise ValueError(f"unknown action: {action!r}")
    result["state"] = session.state.value
    return {"session": session.to_dict(), "result": result}
