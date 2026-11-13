"""Binding custody census - both axes (P-150, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-150 slice doc.
What the derivation found missing, and what lands here:

- a binding answers to two parents, and by P-148 both of
  its axes had a judge - separately. P-144 censuses the
  definition axis (current, superseded, ahead, stale)
  against the definition store; P-148 censuses the chat
  axis (live, orphaned) against the Chat table. P-148's
  own standing notes state the joint fact plainly - the
  two axes are independent, and a binding can be orphaned
  and stale at once - yet no surface joined the two
  verdicts on one row. An owner asking which of their
  bindings are sound, which drift on one axis, and which
  are broken on both, had to fetch two censuses and merge
  them by hand, row by row, with no road accountable for
  the merge.
- this module is that merge, and nothing more: it composes
  the two owning services - P-144's census_bindings and
  P-148's census_binding_chats, both read over the same
  P-135 list_bindings rows - and classifies each joined
  row under a four-state custody law. No third state law
  is invented: the definition verdict is P-144's own
  ``state``, the chat verdict is P-148's own
  ``chat_state``, and the custody state is their plain
  conjunction. Every count is summed from the joined
  rows themselves.

The custody law (exactly one state per binding):

- ``sound`` - current on the definition axis and live on
  the chat axis: the binding stands as it bound;
- ``definition_drift`` - the chat stands but the
  definition axis is broken: superseded, ahead or stale;
- ``chat_orphaned`` - the definition axis is current but
  the chat is gone;
- ``doubly_broken`` - both axes broken at once: a drifted
  or stale definition pinned to a deleted chat.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, unbinds, deletes and repairs nothing, and
  every binding named still stands;
- naming is not repair on either axis: a stale or
  drifted binding and an orphaned binding alike remain
  until unbound per chat - the unbind road works on the
  binding store alone, so any binding named here can
  still be removed by it;
- the join adds no third fact: each row's two verdicts
  are the two censuses' own, joined on the binding's
  identity, and this census claims nothing neither
  census claims - it carries no seeded content (the
  binding summaries never do, P-135);
- chat existence is judged for this owner at read time
  only (P-148's law, inherited verbatim): another
  owner's chat, a never-existent id and a deleted chat
  answer exactly alike, so existence never leaks;
- truth-as-data throughout (P-027): censusing evaluates
  no condition, plays nothing back and executes nothing
  a definition carries.
"""

from __future__ import annotations

from runmal.scenarios.bindingcensus import (
    STATE_CURRENT,
    census_bindings,
)
from runmal.scenarios.chatcensus import (
    STATE_LIVE,
    census_binding_chats,
)

STATE_SOUND = "sound"
STATE_DEFINITION_DRIFT = "definition_drift"
STATE_CHAT_ORPHANED = "chat_orphaned"
STATE_DOUBLY_BROKEN = "doubly_broken"
CUSTODY_STATES = (
    STATE_SOUND,
    STATE_DEFINITION_DRIFT,
    STATE_CHAT_ORPHANED,
    STATE_DOUBLY_BROKEN,
)

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, unbound, deleted and "
    "repaired nothing, and every binding named here "
    "still stands"
)
_NOTE_NAMES_NEVER_REPAIRS = (
    "naming is not repair on either axis: a stale, "
    "drifted or orphaned binding remains until it is "
    "unbound per chat, deleting a definition or a chat "
    "never touches the binding store, and the unbind "
    "road works on the binding store alone, so any "
    "binding named here can still be removed by it - "
    "this census cleans nothing up, it names custody, "
    "it does not repair it"
)
_NOTE_JOIN_ADDS_NO_FACT = (
    "the join adds no third fact: every row's "
    "definition verdict is the binding census's own "
    "and its chat verdict is the chat-custody census's "
    "own, joined on the binding itself - this census "
    "claims nothing neither census claims, and it "
    "carries no seeded content, which the binding "
    "summaries never carry"
)
_NOTE_OWNER_SCOPED_EXISTENCE = (
    "chat existence is judged for this owner at read "
    "time: a chat id that names another owner's chat, "
    "or no chat at all, reads as gone exactly as a "
    "deleted chat does - existence never leaks, and no "
    "chat fact beyond existence is read or carried here"
)
_NOTE_TRUTH_AS_DATA = (
    "this census evaluates no condition, plays nothing "
    "back and executes nothing a definition carries: "
    "stored content is data, never code"
)


def _custody_state(definition_state: str, chat_state: str) -> str:
    definition_sound = definition_state == STATE_CURRENT
    chat_sound = chat_state == STATE_LIVE
    if definition_sound and chat_sound:
        return STATE_SOUND
    if chat_sound:
        return STATE_DEFINITION_DRIFT
    if definition_sound:
        return STATE_CHAT_ORPHANED
    return STATE_DOUBLY_BROKEN


async def census_binding_custody(
    session, bindings, owner_id: str, definitions
) -> dict:
    """The two-axis binding custody census for one owner.

    ``session`` is an async DB session (the chat axis
    lives in the SQL Chat table); ``bindings`` is a
    ScenarioBindingStore; ``definitions`` is the caller's
    live ScenarioDefinition records for the same owner
    (the router passes the definition store's
    list_for_owner answer, exactly as the P-144 road
    does). The census composes the two owning services
    over those same inputs - census_bindings for the
    definition axis, census_binding_chats for the chat
    axis, the live id set built from ``definitions``
    exactly as the P-148 road builds it - so both parents
    read the identical P-135 row set. Joined rows are
    matched on the binding's own id, consumed in row
    order per id, so a hand-damaged store holding two
    rows that share an id still joins each chat verdict
    to one definition verdict in order. Each joined row
    is the P-144 row verbatim, enriched with exactly
    ``chat_exists`` and ``chat_state`` (P-148 verbatim)
    and ``custody_state`` under the law above. Groups
    roll the same rows up per definition in
    first-binding order (P-144's group shape plus the
    four custody counts). Every count is summed from
    the joined rows and groups themselves; chat counts
    are DISTINCT chat ids (P-148's law), stated
    separately from the row counts. Pure read: writes
    nothing, unbinds nothing, deletes nothing.
    """
    definition_side = census_bindings(bindings, owner_id, definitions)
    live_definition_ids = {record.id for record in definitions}
    chat_side = await census_binding_chats(
        session, bindings, owner_id, live_definition_ids)
    chat_by_id: dict[str, list[dict]] = {}
    for chat_row in chat_side["bindings"]:
        chat_by_id.setdefault(chat_row["id"], []).append(chat_row)
    rows: list[dict] = []
    for row in definition_side["bindings"]:
        queue = chat_by_id.get(row["id"]) or []
        chat_row = queue.pop(0) if queue else None
        chat_exists = bool(chat_row["chat_exists"]) if chat_row else False
        chat_state = chat_row["chat_state"] if chat_row else "orphaned"
        rows.append({
            **row,
            "chat_exists": chat_exists,
            "chat_state": chat_state,
            "custody_state": _custody_state(row["state"], chat_state),
        })
    groups: list[dict] = []
    by_id: dict[str, dict] = {}
    for row in rows:
        group = by_id.get(row["definition_id"])
        if group is None:
            group = {
                "definition_id": row["definition_id"],
                "definition_name": (
                    row["current_name"]
                    if row["current_name"] is not None
                    else row["definition_name"]
                ),
                "definition_exists": row["definition_exists"],
                "current_revision": row["current_revision"],
                "bindings_total": 0,
                "sound": 0,
                "definition_drift": 0,
                "chat_orphaned": 0,
                "doubly_broken": 0,
                "chat_ids": [],
            }
            by_id[row["definition_id"]] = group
            groups.append(group)
        group["bindings_total"] += 1
        group[row["custody_state"]] += 1
        group["chat_ids"].append(row["chat_id"])
    counts = {
        "bindings_total": len(rows),
        "current": sum(
            1 for row in rows if row["state"] == "current"),
        "superseded": sum(
            1 for row in rows if row["state"] == "superseded"),
        "ahead": sum(
            1 for row in rows if row["state"] == "ahead"),
        "stale": sum(
            1 for row in rows if row["state"] == "stale"),
        "live": sum(
            1 for row in rows if row["chat_state"] == "live"),
        "orphaned": sum(
            1 for row in rows if row["chat_state"] == "orphaned"),
        "sound": sum(
            1 for row in rows if row["custody_state"] == STATE_SOUND),
        "definition_drift": sum(
            1 for row in rows
            if row["custody_state"] == STATE_DEFINITION_DRIFT),
        "chat_orphaned": sum(
            1 for row in rows
            if row["custody_state"] == STATE_CHAT_ORPHANED),
        "doubly_broken": sum(
            1 for row in rows
            if row["custody_state"] == STATE_DOUBLY_BROKEN),
        "chats_live": len({
            row["chat_id"] for row in rows
            if row["chat_state"] == "live"
        }),
        "chats_orphaned": len({
            row["chat_id"] for row in rows
            if row["chat_state"] == "orphaned"
        }),
        "definitions_referenced": len(groups),
        "definitions_with_sound": sum(
            1 for group in groups if group["sound"] > 0),
        "definitions_with_definition_drift": sum(
            1 for group in groups if group["definition_drift"] > 0),
        "definitions_with_chat_orphaned": sum(
            1 for group in groups if group["chat_orphaned"] > 0),
        "definitions_with_doubly_broken": sum(
            1 for group in groups if group["doubly_broken"] > 0),
    }
    return {
        "bindings": rows,
        "by_definition": groups,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_NAMES_NEVER_REPAIRS,
            _NOTE_JOIN_ADDS_NO_FACT,
            _NOTE_OWNER_SCOPED_EXISTENCE,
            _NOTE_TRUTH_AS_DATA,
        ],
    }


__all__ = [
    "CUSTODY_STATES",
    "STATE_CHAT_ORPHANED",
    "STATE_DEFINITION_DRIFT",
    "STATE_DOUBLY_BROKEN",
    "STATE_SOUND",
    "census_binding_custody",
]
