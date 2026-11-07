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

Instruct templates (P-050): the composed messages are rendered
through the resolved instruct template (explicit name/data >
per-model default > plain); the result carries an
``instruct_template`` echo (name/source/stop strings) and
``rendered_tokens`` -- the rendered string's own token estimate,
so the cost of the template's framing is visible before sending.
The rendered TEXT never enters the result: the S214 contract
(traces carry no prompt content) outranks the convenience.

Context templates (P-051): ``context_template`` is honoured
via ``context.apply_context_template`` AFTER the P-049 layout
(the layout governs block order/toggles; the context template
governs the story-string assembly segments, their order, and
their literal framing); segments a template disables surface
in the trace as discards with reason
``context_template_disabled``; the result carries a
``context_template`` echo (metadata only). With no context
template in play the pipeline is exactly the pre-P-051
pipeline, and the default template's application is an exact
identity on the baseline assembly.

Prompt manager (P-049): ``prompt_layout`` is honoured via
``manager.apply_layout`` before compose; disabled blocks surface
in the trace as discards with reason ``prompt_manager_disabled``;
the result carries a ``prompt_layout`` echo; with no layout the
pipeline is exactly the pre-P-049 pipeline.

Author's note (P-056): when a ``chat_id`` is given, the chat's stored
author's note joins the composition: an active note becomes the
composer's depth slot (spliced into the history under the S206
contract), a note silenced by its frequency surfaces in the trace as
a discard with reason ``authors_note_frequency``, and the result
carries an ``authors_note`` echo -- metadata only (present / active /
depth / frequency / enabled / message count / source); the note text
never enters the result. With no chat the echo reports source
``none`` and the pipeline is exactly the pre-P-056 pipeline.
Post-history instructions (P-057): resolution precedence is
chat > character > none -- chat-stored instructions with content
win, else the character card's ``post_history_instructions``
field becomes the slot with source ``character``, else there is
no slot. The slot composes after history at its baseline-last
position. The result carries a ``post_history`` echo -- metadata
only (present / enabled / role / source); the instruction text
never enters the result (S214). Corrupt stored JSON reads as
empty.
Token budget governor (P-058): every result carries ``budget``
-- the whole-prompt budget, always present whether or not a
policy was declared. A declared ``budget_policy`` is resolved
via ``resolve_policy`` and applied before compose, trimming
the slot list the composer would otherwise have received;
slots the governor drops surface in the trace as discards with
the governor reasons (``governor_section_cap`` /
``governor_total_budget``), and a trimmed history slot is
composed from its trimmed parts rather than discarded. The
result also carries a ``budget_governor`` echo (applied /
source / policy / actions). No content ever enters a budget
or governor payload: ids, kinds, sections, token counts,
statuses and reasons only (S214).
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters import service as character_service
from runmal.chats import service as chat_service
from runmal.lorebooks import scopes as lore_scopes
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.accounting import account_from_trace
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.windows import ScanSettings
from runmal.prompt.authors_note import (
    FREQUENCY_REASON,
    AuthorsNote,
    is_active_for,
    note_from_data,
)
from runmal.prompt.authors_note import has_content as note_has_content
from runmal.prompt.authors_note import slot_for as note_slot_for
from runmal.prompt.composer import compose
from runmal.prompt.context import DISABLED_REASON as CONTEXT_DISABLED_REASON
from runmal.prompt.context import apply_context_template
from runmal.prompt.governor import apply_policy, budget_from_trace
from runmal.prompt.manager import DISABLED_REASON, apply_layout
from runmal.prompt.post_history import (
    PostHistoryInstructions,
    instructions_from_data,
)
from runmal.prompt.post_history import has_content as ph_has_content
from runmal.prompt.post_history import slot_for as ph_slot_for
from runmal.prompt.render import render_prompt
from runmal.prompt.service import (
    context_echo,
    layout_echo,
    policy_echo,
    resolve_context_template,
    resolve_layout,
    resolve_policy,
    resolve_template,
    template_echo,
)
from runmal.prompt.slots import Slot, baseline_order, make_slot, slot_tokens
from runmal.prompt.trace import TraceSlot, build_trace, trace_to_dict
from runmal.tokens import estimate_tokens

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


def _post_history_from_json(raw) -> PostHistoryInstructions:
    """Parse stored post-history JSON defensively (P-057).

    Corrupt JSON, None, and invalid documents all read as the
    default (empty) instructions rather than failing.
    """
    try:
        parsed = json.loads(raw) if raw else None
        return instructions_from_data(parsed)
    except (json.JSONDecodeError, ValueError, TypeError):
        return PostHistoryInstructions()


def _character_post_history_text(character) -> str:
    """The character card's post_history_instructions text (P-057).

    Parses ``card_json`` exactly like :func:`_persona_text` (dict
    with a ``data`` envelope unwrap); returns "" when the field
    is absent or not a string.
    """
    try:
        card = json.loads(character.card_json or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return ""
    if isinstance(card, dict) and isinstance(card.get("data"), dict):
        card = card["data"]
    if not isinstance(card, dict):
        return ""
    value = card.get("post_history_instructions")
    return value if isinstance(value, str) else ""


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
    prompt_layout: object | None = None,
    model_id: str | None = None,
    instruct_template: object | None = None,
    context_template: object | None = None,
    context_preset: object | None = None,
    budget_policy: object | None = None,
) -> dict | None:
    """Build the trace dict for a hypothetical prompt, or None when a
    referenced character/lorebook does not exist."""
    layout, layout_source = resolve_layout(prompt_layout)
    template, template_source = resolve_template(instruct_template, model_id)
    ctx_template, ctx_source = resolve_context_template(
        context_template, preset=context_preset
    )
    policy, policy_source = resolve_policy(budget_policy)
    governor_actions: tuple = ()
    messages = list(messages or [])
    note = AuthorsNote()
    authors_note_active = False
    lorebook_inspections: dict = {}
    lore_scope_summary: dict | None = None
    slots: list[Slot] = [
        make_slot("main_system", "system", MAIN_SYSTEM_TEXT, required=True, id="system/main")
    ]
    extras: list[TraceSlot] = []

    persona_text = ""
    character = None
    chat_ph: PostHistoryInstructions | None = None
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
        chat = await chat_service.get_chat(session, user_id, chat_id)
        if chat is None:
            return None
        try:
            note = note_from_data(json.loads(chat.authors_note_json or "{}"))
        except (json.JSONDecodeError, ValueError, TypeError):
            note = AuthorsNote()
        chat_ph = _post_history_from_json(
            getattr(chat, "post_history_json", None)
        )
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

    message_count = len(messages)
    if note_has_content(note):
        if is_active_for(note, message_count):
            an_slot = note_slot_for(note, message_count)
            if an_slot is not None:
                slots.append(an_slot)
                authors_note_active = True
        else:
            _an_probe = make_slot(
                "authors_note",
                note.role,
                note.text,
                id="authors_note/chat",
                depth=note.depth,
                provenance="chat:authors_note",
            )
            extras.append(
                TraceSlot(
                    slot_id="authors_note/chat",
                    kind="authors_note",
                    role=note.role,
                    status="discarded",
                    tokens=slot_tokens(_an_probe),
                    reason=FREQUENCY_REASON,
                    provenance="chat:authors_note",
                )
            )
    authors_note_echo = {
        "present": note_has_content(note),
        "active": authors_note_active,
        "depth": note.depth,
        "frequency": note.frequency,
        "enabled": note.enabled,
        "message_count": message_count,
        "source": "chat" if chat_id else "none",
    }
    # P-057: post-history resolution -- chat with content wins;
    # a disabled/blank chat falls through to the character card;
    # otherwise none. Appended after history (baseline-last order
    # does the positioning) and before layout/context stages so
    # the slot flows through them like every other slot.
    winning_ph: PostHistoryInstructions | None = None
    ph_source = "none"
    if chat_ph is not None and ph_has_content(chat_ph):
        winning_ph = chat_ph
        ph_source = "chat"
    elif character is not None:
        card_text = _character_post_history_text(character)
        if card_text.strip():
            winning_ph = PostHistoryInstructions(text=card_text)
            ph_source = "character"
    if winning_ph is not None:
        ph_slot = ph_slot_for(winning_ph, ph_source)
        if ph_slot is not None:
            slots.append(ph_slot)
    if winning_ph is None and chat_ph is not None:
        # No content winner, but a chat was loaded: the echo
        # reports the chat candidate itself (P057_DESIGN S5 rule
        # (3)) -- present False with the chat's enabled/role. A
        # corrupt stored document already read as the default
        # chat candidate above, so it lands here too. No slot
        # behaviour changes: nothing is appended for this case.
        winning_ph = chat_ph
        ph_source = "chat"
    if ph_source == "none":
        post_history_echo = {
            "present": False,
            "enabled": True,
            "role": "system",
            "source": "none",
        }
    else:
        post_history_echo = {
            "present": ph_has_content(winning_ph),
            "enabled": winning_ph.enabled,
            "role": winning_ph.role,
            "source": ph_source,
        }

    slots_for_compose = slots
    if layout is not None:
        kept, dropped = apply_layout(slots, layout)
        for slot in dropped:
            extras.append(
                TraceSlot(
                    slot_id=slot.id,
                    kind=slot.kind,
                    role=slot.role,
                    status="discarded",
                    tokens=slot_tokens(slot),
                    reason=DISABLED_REASON,
                    trigger=slot.trigger or None,
                    provenance=slot.provenance,
                )
            )
        slots_for_compose = kept
    if ctx_template is not None:
        kept, dropped = apply_context_template(slots_for_compose, ctx_template)
        for slot in dropped:
            extras.append(
                TraceSlot(
                    slot_id=slot.id,
                    kind=slot.kind,
                    role=slot.role,
                    status="discarded",
                    tokens=slot_tokens(slot),
                    reason=CONTEXT_DISABLED_REASON,
                    trigger=slot.trigger or None,
                    provenance=slot.provenance,
                )
            )
        slots_for_compose = kept
    if policy is not None:
        governed = apply_policy(
            slots_for_compose,
            policy,
            input_budget=context_limit - reserve_response,
        )
        governor_actions = governed.actions
        _pre_governor_by_id = {slot.id: slot for slot in slots_for_compose}
        for action in governor_actions:
            if action.action == "dropped":
                slot = _pre_governor_by_id.get(action.slot_id)
                if slot is not None:
                    extras.append(
                        TraceSlot(
                            slot_id=slot.id,
                            kind=slot.kind,
                            role=slot.role,
                            status="discarded",
                            tokens=action.tokens_before,
                            reason=action.reason,
                            trigger=slot.trigger or None,
                            provenance=slot.provenance,
                        )
                    )
        slots_for_compose = list(governed.kept)
    composed = compose(
        slots_for_compose, context_limit=context_limit, reserve_response=reserve_response
    )
    trace = build_trace(composed, slots, extra_discards=tuple(extras))
    result = trace_to_dict(trace)
    result["prompt_layout"] = layout_echo(layout, layout_source)
    rendered = render_prompt(composed.messages, template)
    result["instruct_template"] = template_echo(template, template_source)
    result["context_template"] = context_echo(ctx_template, ctx_source)
    result["rendered_tokens"] = estimate_tokens(rendered.text)
    result["authors_note"] = authors_note_echo
    result["post_history"] = post_history_echo
    if lore_scope_summary is not None:
        result["lore_scopes"] = lore_scope_summary
    if include_activation_inspection:
        result["lorebook_inspections"] = lorebook_inspections
    result["lore_account"] = account_from_trace(result)
    result["budget"] = budget_from_trace(result)
    result["budget_governor"] = {
        "applied": policy is not None,
        **policy_echo(policy, policy_source),
        "actions": [a.to_dict() for a in governor_actions],
    }
    return result
