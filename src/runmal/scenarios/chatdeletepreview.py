"""Chat delete-impact preview (P-149, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-149 slice doc.
What the derivation found missing, and what lands here:

- Part IX's irreversible acts each have a pre-commit
  preview except one. Definition deletion has P-139's
  delete-impact preview, definition replacement has
  P-140's (and the candidate previews P-146 / P-147),
  and binding itself has P-136 / P-138. Chat deletion -
  the chats subsystem's irreversible act - has none on
  the scenario side: chats.service.delete_chat cleans
  the chat's checkpoints, databank, undo store, vision
  links, image attachments and folder-watch
  registrations, but never the scenario binding store,
  so deleting a bound chat orphans its binding record
  with no surface naming that fact beforehand. P-148's
  binding chat-custody census names such orphans AFTER
  the fact, across the whole store; no surface names
  the one binding a named chat's deletion WOULD orphan,
  before the act.
- the cascade question is weighed and NOT taken here.
  Whether delete_chat should remove the binding record
  with the chat is a write-behaviour change inside the
  chats subsystem, and no in-tree record has taken that
  decision: P-148's scout reserved it expressly ("a
  behaviour decision no in-tree record has taken ...
  the honest next question if Volmarr wants the
  cascade"). Three further facts hold the line. The
  definition side's no-cascade law is deliberate
  (P-132 / P-139: a binding outlives its definition,
  stale and named, never silently erased), and the
  binding record is the only surviving account of what
  a binding seeded - cast, pinned revision, seeded and
  skipped lists. Chat deletion's custody blocks run
  silently and best-effort (each swallows every
  exception), so a cascade wired there would erase
  that account with no answer, no record and no undo.
  And delete_chat's custody is selective, not general,
  in the record: each addition was separately
  commissioned (P-120 attachments, P-121 folder-watch),
  and the P-093 chat variables a binding seeds are not
  cleared by delete_chat at all - there is no general
  cascade law to extend mechanically. This slice is
  therefore the honest pre-commit half: it NAMES what
  a deletion would orphan, on both custody axes, and
  leaves the write decision where the record leaves
  it - untaken, and named here as still open.

This module is the read service behind the preview
road. It is async because chat existence lives in the
SQL Chat table (the chatpreview precedent). Every fact
is read through the owning slice's own verb - P-132's
get_binding for the record, the P-144 state law for the
definition axis, the owner-scoped Chat existence law
bind and P-138 read the table by - so no second law is
invented. Pure read: writes nothing, deletes nothing,
cascades nothing.

Honesty bounds, stated in every answer:

- the preview is a read of the world as it stands;
  the chat and any binding named still stand;
- deleting a chat does not cascade into the binding
  store (today's pinned law): the record would remain
  and the per-chat binding read would still answer it
  exactly as if the chat lived; P-148's census names
  it orphaned after the fact, this preview names it
  before;
- the cascade decision is open and untaken (above);
- seeded content is asymmetric under chat deletion:
  the seeded messages are rows of the chat itself and
  die with it, while the binding record that accounts
  them survives in its own store;
- the preview judges scenario custody only - a chat's
  other deletion custodies are the chats subsystem's
  own law - and truth-as-data throughout (P-027).
"""

from __future__ import annotations

from runmal.scenarios.binding import get_binding
from runmal.scenarios.bindingcensus import (
    STATE_AHEAD,
    STATE_CURRENT,
    STATE_STALE,
    STATE_SUPERSEDED,
)

_NOTE_PREVIEW_ONLY = (
    "this preview is a read of the world as it stands; "
    "previewing has deleted, written and cascaded "
    "nothing, and the chat and any binding named here "
    "still stand"
)
_NOTE_NO_CASCADE_TODAY = (
    "deleting a chat does not cascade into the scenario "
    "binding store: a standing binding would remain as a "
    "record after its chat is gone, and the per-chat "
    "binding read would still answer it exactly as if "
    "the chat lived - the binding chat-custody census "
    "names such bindings orphaned after the fact, and "
    "this preview names the one this chat would add "
    "before it"
)
_NOTE_CASCADE_OPEN = (
    "whether chat deletion should remove the binding "
    "record with the chat is a write-behaviour decision "
    "no in-tree record has taken, and this preview does "
    "not take it: the binding record is the only "
    "surviving account of what a binding seeded, chat "
    "deletion's custody blocks run silently and "
    "best-effort, and a cascade wired there would erase "
    "that account with no answer and no undo - the "
    "record stands until its owner removes it per chat "
    "or that decision is taken expressly"
)
_NOTE_SEEDED_ASYMMETRY = (
    "content a binding seeded is not symmetric under "
    "chat deletion: the seeded messages are rows of the "
    "chat itself and die with it, while the binding "
    "record that accounts them - its cast, its pinned "
    "revision, its seeded and skipped lists - is a "
    "separate store's truth and survives; variables the "
    "binding seeded live in the chat's own variable "
    "store and are judged by that store's law, not here"
)
_NOTE_SCOPE_AND_DATA = (
    "this preview judges scenario custody only: a "
    "chat's other custodies on deletion - checkpoints, "
    "databank, undo, vision links, attachments and "
    "folder-watch registrations - are the chat "
    "subsystem's own deletion law and are not read or "
    "judged here; and truth-as-data throughout - "
    "previewing evaluates no condition, plays nothing "
    "back and executes nothing a definition carries"
)


def _definition_state(binding, live_record) -> str:
    """P-144's state law, applied to this one binding.

    stale when the definition is gone; otherwise the
    pinned revision against the live one - current,
    superseded or ahead (impossible by construction;
    a hand-damaged store, named, exactly as P-144
    names it)."""
    if live_record is None:
        return STATE_STALE
    if binding.definition_revision < live_record.revision:
        return STATE_SUPERSEDED
    if binding.definition_revision > live_record.revision:
        return STATE_AHEAD
    return STATE_CURRENT


async def preview_chat_delete_impact(
    session, bindings, definitions, owner_id: str, chat_id: str
) -> dict | None:
    """The chat delete-impact envelope, or None.

    ``bindings`` is a ScenarioBindingStore and
    ``definitions`` a ScenarioStore for the same owner.
    None means the caller holds neither an owned chat
    with this id nor a binding naming it - an unknown
    chat, another owner's chat with no binding of the
    caller's, and a foreign binding's chat all answer
    exactly alike, so existence never leaks on either
    side. A binding of the caller's naming the chat is
    the caller's own fact and answers even when the
    chat is already gone (already orphaned) or was
    never theirs: the envelope names chat_exists false
    beside the standing record. On an owned chat with
    no binding the envelope is the honest zero: no
    binding, nothing scenario-side would be orphaned.

    The binding is P-132's full record verbatim (the
    per-chat read's own shape); its definition-axis
    state is P-144's law; the impact counts are read
    from the record itself. Pure read: writes nothing,
    deletes nothing, cascades nothing.
    """
    from sqlalchemy import select

    from runmal.db.models import Chat

    binding = get_binding(bindings, owner_id, chat_id)
    result = await session.execute(
        select(Chat.id).where(
            Chat.id == chat_id, Chat.user_id == owner_id)
    )
    chat_exists = result.scalar_one_or_none() is not None
    if binding is None and not chat_exists:
        return None
    live_record = (
        definitions.get(binding.definition_id, owner_id)
        if binding is not None else None
    )
    return {
        "chat_id": chat_id,
        "chat_exists": chat_exists,
        "binding": binding.to_dict() if binding is not None else None,
        "binding_state": (
            _definition_state(binding, live_record)
            if binding is not None else None
        ),
        "definition_exists": (
            live_record is not None if binding is not None else None
        ),
        "definition_current_revision": (
            live_record.revision if live_record is not None else None
        ),
        "definition_current_name": (
            live_record.name if live_record is not None else None
        ),
        "impact": {
            "binding_would_orphan": (
                binding is not None and chat_exists
            ),
            "binding_already_orphaned": (
                binding is not None and not chat_exists
            ),
            "seeded_message_count": (
                len(binding.seeded_messages) if binding is not None else 0
            ),
            "seeded_key_count": (
                len(binding.seeded_keys) if binding is not None else 0
            ),
            "cast_count": (
                len(binding.cast) if binding is not None else 0
            ),
        },
        "notes": [
            _NOTE_PREVIEW_ONLY,
            _NOTE_NO_CASCADE_TODAY,
            _NOTE_CASCADE_OPEN,
            _NOTE_SEEDED_ASYMMETRY,
            _NOTE_SCOPE_AND_DATA,
        ],
    }


__all__ = ["preview_chat_delete_impact"]
