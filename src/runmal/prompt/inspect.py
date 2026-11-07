"""Prompt inspector service (roadmap S215).

Composes a prompt from real stored data -- a character, lorebooks, and
sample messages -- through the real pipeline (lore scan/activation/
budget, then the Composer) and returns the S214 Prompt Trace for it.
The inspector is how a user answers "why was this injected / discarded?"
without reading code: every lore entry appears in the trace, included
ones with their trigger, excluded ones with their stage and reason.

Nothing here writes state: lore activation runs from a clean runtime
state, exactly like the S209 editor preview.

Activation inspector (P-043): with
``include_activation_inspection=True`` the result gains
``lorebook_inspections`` -- one P-043 explanation payload per
explicitly named lorebook, built by explain_preview over the
VERY preview dict this function already computed for the book
(never a second tick, so a gated entry's recorded roll here is
the roll that decided the trace). Scoped (chat_id) layers are
not separately explained in this slice; their rows keep the
trace treatment.

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

Lore token account (P-044): the trace now carries
``lore_account`` -- lore's exact share of this composed prompt
(tokens, share of input + budget, per-provenance), summed from
the composer's own manifest via the trace, so it reconciles
with the ledger by construction; visible before sending
because the inspector never sends.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters import service as character_service
from runmal.lorebooks import scopes as lore_scopes
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.accounting import account_from_trace
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
    chat_id: str | None = None,
    persona_character_id: str | None = None,
    include_activation_inspection: bool = False,
    context_limit: int = 4096,
    reserve_response: int = 512,
) -> dict | None:
    """Build the trace dict for a hypothetical prompt, or None when a
    referenced character/lorebook does not exist."""
    messages = list(messages or [])
    lorebook_inspections: dict = {}
    lore_scope_summary: dict | None = None
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

    # Vectorised lore (P-041): the inspector is a live path -- the
    # embedding matcher runs per book (the owner's active profile
    # backend, or the deterministic local backend) so a vectorised
    # entry can be included here, with its vector trigger shown.
    from runmal.lorebooks.vector_match import (
        match_vectorised,
        resolve_lore_embedding_backend,
    )

    lore_backend = await resolve_lore_embedding_backend(session, user_id)
    for book_id in lorebook_ids or []:
        book = await lore_service.get_lorebook(session, user_id, book_id)
        if book is None:
            return None
        entries = await lore_service.list_entries(session, user_id, book_id)
        book_settings = ScanSettings.from_book(book)
        vector_outcome = await match_vectorised(
            entries or [],
            messages,
            backend=lore_backend,
            settings=book_settings,
            external_context=[persona_text] if persona_text else [],
        )
        preview = preview_activation(
            entries,
            messages,
            book_settings.scan_depth,
            book.token_budget,
            vector_match=vector_outcome if vector_outcome.candidates else None,
            scan_mode=book_settings.scan_mode,
            scan_external_context=book_settings.scan_external_context,
            # P-037: the persona text is the external context this
            # pipeline actually holds; a book only scans it when
            # its own scan_external_context setting admits it.
            external_context=[persona_text] if persona_text else [],
        )
        if include_activation_inspection:
            from runmal.lorebooks.inspector import explain_preview
            from runmal.lorebooks.scan import (
                ScanEntry,
                scan_entries_windowed,
                scan_near_misses,
            )

            _scan_view = [ScanEntry.from_orm(e) for e in entries]
            _hits = {
                h.entry_id: h
                for h in scan_entries_windowed(
                    _scan_view, messages, book_settings,
                    [persona_text] if persona_text else [],
                )
            }
            if vector_outcome is not None:
                for _fb in vector_outcome.keyword_hits:
                    _hits.setdefault(_fb.entry_id, _fb)
            lorebook_inspections[book.id] = explain_preview(
                preview,
                entries,
                hits=list(_hits.values()),
                near_misses=scan_near_misses(
                    _scan_view, messages, book_settings,
                    [persona_text] if persona_text else [],
                ),
                lorebook_id=book.id,
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

    if chat_id is not None:
        # P-040: scoped lore layers for this chat (world ->
        # character -> persona -> chat), each with its own
        # budget, composed per scope and reported per scope.
        layered = await lore_scopes.layered_preview(
            session,
            user_id,
            chat_id=chat_id,
            persona_character_id=persona_character_id,
            messages=messages,
            external_context=[persona_text] if persona_text else [],
        )
        if layered is None:
            return None
        name_by_book = {
            book["lorebook_id"]: book["name"]
            for summary in layered["scopes"]
            for book in summary["books"]
        }
        for kind in lore_scopes.LAYER_ORDER:
            layer = layered["layers"].get(kind)
            if layer is None:
                continue
            for row in layer["entries"]:
                slot_id = f"lore/{kind}/{row['entry_id']}"
                provenance = (
                    f"lorebook:{name_by_book.get(row['lorebook_id'], '')}@{kind}"
                )
                if row["status"] == "included":
                    slots.append(_lore_slot(row, slot_id, provenance))
                else:
                    reason = (
                        f"lore:{row['discard_reason']}"
                        if row["status"] == "discarded"
                        else row["status"]
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
        lore_scope_summary = {
            "layer_order": layered["layer_order"],
            "scopes": layered["scopes"],
            "shadowed": layered["shadowed"],
            "tokens_used": layered["tokens_used"],
        }

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
    result = trace_to_dict(trace)
    if lore_scope_summary is not None:
        result["lore_scopes"] = lore_scope_summary
    if include_activation_inspection:
        result["lorebook_inspections"] = lorebook_inspections
    result["lore_account"] = account_from_trace(result)
    return result
