"""Prompt inspector service (roadmap S215).

Composes a prompt from real stored data -- a character, lorebooks, and
sample messages -- through the real pipeline (lore scan/activation/
budget, then the Composer) and returns the S214 Prompt Trace for it.
The inspector is how a user answers "why was this injected / discarded?"
without reading code: every lore entry appears in the trace, included
ones with their trigger, excluded ones with their stage and reason.

Nothing here writes state: lore activation runs from a clean runtime
state, exactly like the S209 editor preview.

Position & depth control (P-038): lore slots honour each entry's
declared placement via the preview row's placement fields --
before_char entries become lore_before slots, after_char entries
lore_after slots, and at_depth entries lore_before slots carrying
the S206 depth splice count (Slot.depth) and the entry's role,
which the composer splices into the history. Before P-038 every
lore slot was built as lore_before/system regardless of the
declared position.

One ordering subtlety is load-bearing: the composer splices a
depth slot into the history only when it reaches the slot AFTER
the history slot has been emitted (the S206 contract -- the
depth-note kinds sit after history in the baseline order). A
lore_before-ordered depth slot would be reached first, find no
history, and fall through to plain emission before the history
-- its depth silently unhonoured. At-depth lore slots therefore
keep kind lore_before (the trace still groups them as lore) but
take the baseline order of the depth-injection position
(authors_note) as explicit slot data. Ordering stays data,
never a hidden branch (PROMPT_COMPOSER.md section 2).
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters import service as character_service
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.windows import ScanSettings
from runmal.prompt.composer import compose
from runmal.prompt.slots import Slot, baseline_order, make_slot
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


def _lore_slot(row: dict, slot_id: str, provenance: str) -> Slot:
    """The composer slot for one included lore row (P-038).

    Placement comes from the preview row's placement fields:
    at_depth rows become lore_before slots carrying the S206
    depth + the entry's role, ordered at the depth-injection
    position (see the module docstring for why the order is
    load-bearing); after_char rows become lore_after slots;
    everything else is a plain lore_before slot.
    """
    if row.get("injection_depth") is not None:
        return make_slot(
            "lore_before",
            row.get("role") or "system",
            row["content"] or "",
            id=slot_id,
            trigger=_trigger_for(row),
            provenance=provenance,
            depth=row["injection_depth"],
            order=baseline_order("authors_note"),
        )
    if row.get("position") == "after_char":
        return make_slot(
            "lore_after",
            "system",
            row["content"] or "",
            id=slot_id,
            trigger=_trigger_for(row),
            provenance=provenance,
        )
    return make_slot(
        "lore_before",
        "system",
        row["content"] or "",
        id=slot_id,
        trigger=_trigger_for(row),
        provenance=provenance,
    )


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

    persona_text = ""
    if character_id is not None:
        character = await character_service.get_character(session, user_id, character_id)
        if character is None:
            return None
        persona_text = _persona_text(character)
        slots.append(
            make_slot(
                "persona",
                "system",
                persona_text,
                id=f"persona/{character.id}",
                provenance=f"character:{character.name}",
            )
        )

    for book_id in lorebook_ids or []:
        book = await lore_service.get_lorebook(session, user_id, book_id)
        if book is None:
            return None
        entries = await lore_service.list_entries(session, user_id, book_id)
        book_settings = ScanSettings.from_book(book)
        preview = preview_activation(
            entries,
            messages,
            book_settings.scan_depth,
            book.token_budget,
            scan_mode=book_settings.scan_mode,
            scan_external_context=book_settings.scan_external_context,
            # P-037: the persona text is the external context this
            # pipeline actually holds; a book only scans it when
            # its own scan_external_context setting admits it.
            external_context=[persona_text] if persona_text else [],
        )
        for row in preview["entries"]:
            slot_id = f"lore/{row['entry_id']}"
            provenance = f"lorebook:{book.name}"
            if row["status"] == "included":
                slots.append(_lore_slot(row, slot_id, provenance))
            else:
                reason = (
                    f"lore:{row['discard_reason']}"
                    if row["status"] == "discarded"
                    else row["status"]  # "not_triggered" | "disabled"
                )
                extras.append(
                    TraceSlot(
                        slot_id=slot_id,
                        kind=(
                            "lore_after"
                            if row.get("position") == "after_char"
                            else "lore_before"
                        ),
                        role=row.get("role") or "system",
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
