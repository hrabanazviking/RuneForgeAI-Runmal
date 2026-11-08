"""Chat-scoped binding plan preview (P-138, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-138 slice doc.
What the derivation found missing, and what lands here:

- P-136's bind-plan preview is definition-side only, and
  its own standing notes say so in every answer: bind-time
  refusals "are decided by bind against a specific chat",
  and already-present skips are "knowable only at bind
  time". The preview named no chat, so neither fact could
  be read anywhere before attempting the bind itself —
  and bind reveals them only by refusing (409) or by
  writing (201; unbinding never takes seeded content
  back). P-137's scout named this exact slice ("chat-
  scoped bind preview") as a future candidate; its two
  decline grounds have lapsed or been answered in-tree
  (P-136 is banked; the presence verdict is P-093's own
  law, called — never re-implemented).

This module is the read service behind the chat-scoped
road. The definition side is P-136's preview_bind_plan,
called verbatim — no second planning law is invented.
The chat side reports, as data, the facts bind judges
by, each read through the same law bind reads it
through: the Chat row and its group flag, the binding
store's get_for_chat, the chat service's history, and
P-093's resolve_key + get_entry pair (the exact calls
seed_variables makes to decide missing-keys-only). The
preview refuses nothing and writes nothing: bind
remains the only road that refuses or writes, and the
binding record remains the only account of what
actually landed.

Honesty bounds, stated in every answer:

- the preview judges the named chat's CURRENT state;
  a chat that changes before bind runs changes the
  outcome, and bind re-decides every fact when it runs.
- blockers are reported, never acted on: every
  applicable one is listed in bind's decision order.
- already-present verdicts are judged under the
  scenario writer by the P-093 store's own presence
  law; would_bind is a statement about the chat as it
  stands, never a promise about bind time.
- truth-as-data throughout (P-027): previewing a
  definition against a chat evaluates no condition,
  plays nothing back and executes nothing it carries.
"""

from __future__ import annotations

from pathlib import Path

from runmal.scenarios.binding import ScenarioBindingStore, bindings_path
from runmal.scenarios.bindpreview import preview_bind_plan

_NOTE_CURRENT_STATE = (
    "this preview judges the named chat's current state; "
    "previewing has written, bound and seeded nothing"
)
_NOTE_BIND_REDECIDES = (
    "the blockers are bind's refusal facts read from the "
    "chat as it stands; bind re-decides every one of them "
    "when it runs"
)
_NOTE_PRESENCE_LAW = (
    "already-present keys are judged by the P-093 store's "
    "own presence law under the scenario writer; a key the "
    "chat gains or loses before bind runs changes the "
    "outcome — the binding record remains the only account "
    "of what actually landed"
)
_NOTE_CURRENT_REVISION = (
    "this plan is computed from the definition's current "
    "revision, named above; bind pins whatever revision "
    "is current when it runs"
)

_REASON_ALREADY_PRESENT = (
    "already present; seeding never overwrites live state"
)


async def preview_bind_for_chat(
    session,
    record,
    user_id: str,
    chat_id: str,
    *,
    bindings: ScenarioBindingStore | None = None,
    variables_base_dir: Path | None = None,
) -> dict | None:
    """The chat-scoped bind-plan envelope, or None.

    ``record`` is a ScenarioDefinition (the router has
    already decided the definition's existence and
    ownership, the bindpreview precedent). None means
    the chat is unknown or foreign — the two answer
    exactly alike, so existence never leaks. On an
    owned chat the envelope is P-136's (definition
    identity, the plan, counts read from the plan)
    plus chat_id, the blocker facts in bind's decision
    order, would_bind, the seedable keys split by
    P-093's own presence law, and the four standing
    notes. Pure read: nothing is written anywhere.
    """
    from sqlalchemy import select

    from runmal.chats import service as chat_service
    from runmal.db.models import Chat
    from runmal.plugins.variables import get_entry, resolve_key

    bindings = bindings or ScenarioBindingStore(bindings_path())

    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        return None

    base = preview_bind_plan(record)
    plan = base["plan"]

    blockers: list[dict] = []
    if chat.group_id is not None:
        blockers.append({
            "kind": "group_room",
            "detail": "group rooms take no scenario binding in this slice",
        })
    standing = bindings.get_for_chat(chat_id, user_id)
    if standing is not None:
        blockers.append({
            "kind": "already_bound",
            "detail": "chat already has a scenario binding",
            "binding_id": standing.id,
            "definition_id": standing.definition_id,
        })
    history = await chat_service.get_history(session, user_id, chat_id)
    if history:
        blockers.append({
            "kind": "chat_not_empty",
            "detail": (
                "chat already has messages; a scenario binding "
                "is an opening act"
            ),
            "message_count": len(history),
        })

    would_seed: list[str] = []
    already_present: list[dict] = []
    for where, mapping in (
        ("initial_flags", plan["flags"]),
        ("initial_variables", plan["variables"]),
    ):
        for key in mapping:
            full_key, _, _ = resolve_key(key, "scenario", "runmal.scenario")
            entry = get_entry(
                user_id, chat_id, full_key,
                writer_kind="scenario", writer_id="runmal.scenario",
                base_dir=variables_base_dir,
            )
            if entry is None:
                would_seed.append(full_key)
            else:
                already_present.append({
                    "where": where,
                    "key_or_index": str(key),
                    "full_key": full_key,
                    "reason": _REASON_ALREADY_PRESENT,
                })

    return {
        "definition_id": base["definition_id"],
        "definition_name": base["definition_name"],
        "definition_revision": base["definition_revision"],
        "source_format": base["source_format"],
        "chat_id": chat_id,
        "plan": plan,
        "counts": base["counts"],
        "blockers": blockers,
        "would_bind": not blockers,
        "keys": {
            "would_seed": would_seed,
            "already_present": already_present,
        },
        "notes": [
            _NOTE_CURRENT_STATE,
            _NOTE_BIND_REDECIDES,
            _NOTE_PRESENCE_LAW,
            _NOTE_CURRENT_REVISION,
        ],
    }


__all__ = ["preview_bind_for_chat"]
