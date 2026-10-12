"""Prompt inspector service (roadmap S215).

Composes a prompt from real stored data -- a character, lorebooks, and
sample messages -- through the real pipeline (lore scan/activation/
budget, then the Composer) and returns the S214 Prompt Trace for it.
The inspector is how a user answers "why was this injected / discarded?"
without reading code: every lore entry appears in the trace, included
ones with their trigger, excluded ones with their stage and reason.

Nothing here writes state: lore activation runs from a clean runtime
state, exactly like the S209 editor preview.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters import service as character_service
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.preview import preview_activation
from runmal.prompt.composer import compose
from runmal.prompt.slots import Slot, make_slot
from runmal.prompt.trace import TraceSlot, build_trace, trace_to_dict

MAIN_SYSTEM_TEXT = "You are Rúnmál, a sovereign local chat companion."


def _persona_text(character) -> str:
    try:
        card = json.loads(character.card_json or "{}")
    except json.JSONDecodeError:
        card = {}
    if isinstance(card, dict) and isinstance(card.get("data"), dict):
        card = card["data"]
    parts = [f"Name: {character.name}"]
    for key in ("description", "personality", "scenario"):
        value = card.get(key) if isinstance(card, dict) else None
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _trigger_for(row: dict) -> str:
    if row["via"] == "key" and row["matched_primary"]:
        return row["matched_primary"][0]
    return row["via"] or ""


async def inspect_prompt(
    session: AsyncSession,
    user_id: str,
    *,
    character_id: str | None = None,
    lorebook_ids: list[str] | None = None,
    messages: list[str] | None = None,
    context_limit: int = 4096,
    reserve_response: int = 512,
) -> dict | None:
    """Build the trace dict for a hypothetical prompt, or None when a
    referenced character/lorebook does not exist."""
    messages = list(messages or [])
    slots: list[Slot] = [
        make_slot("main_system", "system", MAIN_SYSTEM_TEXT, required=True, id="system/main")
    ]
    extras: list[TraceSlot] = []

    if character_id is not None:
        character = await character_service.get_character(session, user_id, character_id)
        if character is None:
            return None
        slots.append(
            make_slot(
                "persona",
                "system",
                _persona_text(character),
                id=f"persona/{character.id}",
                provenance=f"character:{character.name}",
            )
        )

    for book_id in lorebook_ids or []:
        book = await lore_service.get_lorebook(session, user_id, book_id)
        if book is None:
            return None
        entries = await lore_service.list_entries(session, user_id, book_id)
        preview = preview_activation(entries, messages, book.scan_depth, book.token_budget)
        for row in preview["entries"]:
            slot_id = f"lore/{row['entry_id']}"
            provenance = f"lorebook:{book.name}"
            if row["status"] == "included":
                slots.append(
                    make_slot(
                        "lore_before",
                        "system",
                        row["content"] or "",
                        id=slot_id,
                        trigger=_trigger_for(row),
                        provenance=provenance,
                    )
                )
            else:
                reason = (
                    f"lore:{row['discard_reason']}"
                    if row["status"] == "discarded"
                    else row["status"]  # "not_triggered" | "disabled"
                )
                extras.append(
                    TraceSlot(
                        slot_id=slot_id,
                        kind="lore_before",
                        role="system",
                        status="discarded",
                        tokens=row["tokens"] or 0,
                        reason=reason,
                        trigger=(_trigger_for(row) if row["via"] else None),
                        provenance=provenance,
                    )
                )

    if messages:
        slots.append(
            make_slot(
                "history",
                "user",
                "",
                id="history",
                splittable=True,
                parts=tuple(messages),
            )
        )

    composed = compose(slots, context_limit=context_limit, reserve_response=reserve_response)
    trace = build_trace(composed, slots, extra_discards=tuple(extras))
    return trace_to_dict(trace)
