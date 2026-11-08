"""Library definition census (P-151, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-151 slice doc.
What the derivation found missing, and what lands here:

- every census in the part rows bindings or report rows.
  P-144 censuses bindings against the definition store,
  P-148 censuses bindings against the Chat table, P-145
  censuses the unmappable elements stored reports name.
  No census rows the definition store itself as its
  subject, and the gap is mechanical: the binding
  censuses build their per-definition groups from
  binding rows in first-binding order, so a definition
  with no bindings appears in no census at all, and no
  road answers the library question - which of an
  owner's definitions are in use at all, which stand
  sound, which are bound only through drifted pins,
  which are bound only to chats that no longer exist -
  except walking every definition by hand through the
  P-135 per-definition bindings list (the by-hand gap
  P-144's own derivation named as its justification,
  transposed to the definition axis).
- this module is that census, and nothing more: it
  composes the two owning censuses - P-144's
  census_bindings and P-148's census_binding_chats,
  both read over the same inputs - joins their verdicts
  per binding under the parents' own conjunction, and
  aggregates per definition over the caller's FULL
  definition list, so zero-binding definitions row as
  unbound and stale bindings (whose definition is gone)
  are counted in the totals while rowing under no
  definition. The consumers are standing roads: delete,
  replace, bind, duplicate and stored export all aim
  per definition, and this census is the library-wide
  answer an owner reads before aiming them.

The per-binding conjunction (no third state law is
invented; each verdict is a parent census's own):

- ``sound`` - current on the definition axis (P-144)
  and live on the chat axis (P-148);
- ``definition_drift`` - superseded or ahead on the
  definition axis, live on the chat axis;
- ``chat_orphaned`` - current on the definition axis,
  orphaned on the chat axis;
- ``doubly_broken`` - drifted on the definition axis
  and orphaned on the chat axis at once.

The definition custody law (exactly one state per
definition): ``unbound`` - no bindings at all; otherwise
the strongest standing custody fact by the precedence
``doubly_broken`` > ``chat_orphaned`` >
``definition_drift`` > ``sound`` - a doubly-broken
binding is broken on both axes; an orphaned binding's
chat is gone for good, while a drifted pin stands beside
a living chat and a living definition. The row's own
per-state binding counts name every binding's state, so
the precedence hides nothing.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, binds, unbinds, deletes and repairs
  nothing, and every definition and binding named
  still stands;
- naming is not repair: a definition remains until it
  is deleted per definition and a binding remains
  until it is unbound per chat - this census aims the
  standing roads, it is none of them;
- the subject is the definition: a definition with no
  bindings rows here as unbound and appears in no
  binding census; a stale binding rows under no
  definition, its definition being gone, and is
  counted in the census totals only;
- the join adds no third fact: each binding's two
  verdicts are the two censuses' own, joined on the
  binding itself, and this census claims nothing
  neither census claims - it carries no seeded
  content, which the binding summaries never carry;
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
    STATE_AHEAD,
    STATE_CURRENT,
    STATE_STALE,
    STATE_SUPERSEDED,
    census_bindings,
)
from runmal.scenarios.chatcensus import (
    STATE_LIVE,
    STATE_ORPHANED,
    census_binding_chats,
)

STATE_UNBOUND = "unbound"
STATE_SOUND = "sound"
STATE_DEFINITION_DRIFT = "definition_drift"
STATE_CHAT_ORPHANED = "chat_orphaned"
STATE_DOUBLY_BROKEN = "doubly_broken"
DEFINITION_CUSTODY_STATES = (
    STATE_UNBOUND,
    STATE_SOUND,
    STATE_DEFINITION_DRIFT,
    STATE_CHAT_ORPHANED,
    STATE_DOUBLY_BROKEN,
)

_PRECEDENCE = (
    STATE_DOUBLY_BROKEN,
    STATE_CHAT_ORPHANED,
    STATE_DEFINITION_DRIFT,
    STATE_SOUND,
)

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, bound, unbound, deleted "
    "and repaired nothing, and every definition and "
    "binding named here still stands"
)
_NOTE_NAMES_NEVER_REPAIRS = (
    "naming is not repair: a definition remains until "
    "it is deleted per definition and a binding remains "
    "until it is unbound per chat - this census aims "
    "the standing per-definition and per-chat roads, "
    "it is none of them, and it cleans nothing up"
)
_NOTE_SUBJECT_IS_THE_DEFINITION = (
    "the subject of this census is the definition: a "
    "definition with no bindings rows here as unbound "
    "and appears in no binding census, and a stale "
    "binding - one whose definition is gone - rows "
    "under no definition and is counted in the census "
    "totals only"
)
_NOTE_JOIN_ADDS_NO_FACT = (
    "the join adds no third fact: every binding's "
    "definition verdict is the binding census's own "
    "and its chat verdict is the chat-custody census's "
    "own, joined on the binding itself - this census "
    "claims nothing neither census claims, and it "
    "carries no seeded content, which the binding "
    "summaries never carry"
)
_NOTE_OWNER_SCOPED_TRUTH_AS_DATA = (
    "chat existence is judged for this owner at read "
    "time - another owner's chat, a never-existent id "
    "and a deleted chat answer exactly alike, so "
    "existence never leaks - and this census evaluates "
    "no condition, plays nothing back and executes "
    "nothing a definition carries: stored content is "
    "data, never code"
)


def _binding_custody(definition_state: str, chat_state: str) -> str:
    """One binding's custody state: the plain conjunction
    of P-144's definition verdict and P-148's chat
    verdict. Never called with STATE_STALE - a stale
    binding's definition is gone, so it rows under no
    definition and is counted before the join."""
    drifted = definition_state in (STATE_SUPERSEDED, STATE_AHEAD)
    if chat_state == STATE_ORPHANED:
        return STATE_DOUBLY_BROKEN if drifted else STATE_CHAT_ORPHANED
    if drifted:
        return STATE_DEFINITION_DRIFT
    return STATE_SOUND


def _definition_state(per_state: dict) -> str:
    """One definition's custody state under the
    precedence law: unbound when it holds no bindings,
    else the strongest standing custody fact among its
    bindings. The row's per-state counts name every
    binding, so the precedence hides nothing."""
    if sum(per_state.values()) == 0:
        return STATE_UNBOUND
    for state in _PRECEDENCE:
        if per_state[state] > 0:
            return state
    return STATE_SOUND  # pragma: no cover - precedence is total


async def census_definitions(session, bindings, owner_id: str, definitions) -> dict:
    """The library definition census for one owner.

    ``session`` is an async DB session; ``bindings`` is
    a ScenarioBindingStore; ``definitions`` is the
    caller's live ScenarioDefinition records for the
    same owner, in store order (the router passes the
    definition store list verb answer). The two owning
    censuses are composed over those same inputs -
    census_bindings (P-144) for the definition axis and
    census_binding_chats (P-148, the live id set built
    from ``definitions`` exactly as its road builds it)
    for the chat axis. Joined rows are matched on the
    binding's own id, consumed in row order per id, so
    a hand-damaged store holding two rows that share
    an id still joins each chat verdict to one
    definition verdict in order. Rows are the caller's
    definitions in store order, each the P-131 summary
    verbatim enriched with its bindings' custody
    counts, its distinct chat counts and its state.
    Every count is summed from the rows and the joined
    bindings themselves. Pure read: writes nothing,
    binds nothing, unbinds nothing, deletes nothing.
    """
    definition_verdicts = census_bindings(
        bindings, owner_id, definitions)["bindings"]
    live_ids = {record.id for record in definitions}
    chat_verdicts = (
        await census_binding_chats(session, bindings, owner_id, live_ids)
    )["bindings"]
    chat_by_id: dict[str, list[dict]] = {}
    for row in chat_verdicts:
        chat_by_id.setdefault(row["id"], []).append(row)
    per_definition: dict[str, dict] = {
        record.id: {
            "binding_count": 0,
            STATE_SOUND: 0,
            STATE_DEFINITION_DRIFT: 0,
            STATE_CHAT_ORPHANED: 0,
            STATE_DOUBLY_BROKEN: 0,
            "chat_ids": [],
            "live_chat_ids": [],
        }
        for record in definitions
    }
    bindings_stale = 0
    custody_totals = {
        STATE_SOUND: 0,
        STATE_DEFINITION_DRIFT: 0,
        STATE_CHAT_ORPHANED: 0,
        STATE_DOUBLY_BROKEN: 0,
    }
    for row in definition_verdicts:
        queue = chat_by_id.get(row["id"]) or []
        chat_row = queue.pop(0) if queue else None
        if row["state"] == STATE_STALE:
            bindings_stale += 1
            continue
        custody = _binding_custody(
            row["state"],
            chat_row["chat_state"] if chat_row else STATE_ORPHANED,
        )
        bucket = per_definition[row["definition_id"]]
        bucket["binding_count"] += 1
        bucket[custody] += 1
        bucket["chat_ids"].append(row["chat_id"])
        if chat_row is not None and chat_row["chat_state"] == STATE_LIVE:
            bucket["live_chat_ids"].append(row["chat_id"])
        custody_totals[custody] += 1
    rows: list[dict] = []
    for record in definitions:
        bucket = per_definition[record.id]
        per_state = {
            STATE_SOUND: bucket[STATE_SOUND],
            STATE_DEFINITION_DRIFT: bucket[STATE_DEFINITION_DRIFT],
            STATE_CHAT_ORPHANED: bucket[STATE_CHAT_ORPHANED],
            STATE_DOUBLY_BROKEN: bucket[STATE_DOUBLY_BROKEN],
        }
        rows.append({
            **record.summary(),
            "binding_count": bucket["binding_count"],
            "sound": per_state[STATE_SOUND],
            "definition_drift": per_state[STATE_DEFINITION_DRIFT],
            "chat_orphaned": per_state[STATE_CHAT_ORPHANED],
            "doubly_broken": per_state[STATE_DOUBLY_BROKEN],
            "chats_bound": len(set(bucket["chat_ids"])),
            "chats_live": len(set(bucket["live_chat_ids"])),
            "state": _definition_state(per_state),
        })
    counts = {
        "definitions_total": len(rows),
        "definitions_unbound": sum(
            1 for row in rows if row["state"] == STATE_UNBOUND),
        "definitions_sound": sum(
            1 for row in rows if row["state"] == STATE_SOUND),
        "definitions_definition_drift": sum(
            1 for row in rows if row["state"] == STATE_DEFINITION_DRIFT),
        "definitions_chat_orphaned": sum(
            1 for row in rows if row["state"] == STATE_CHAT_ORPHANED),
        "definitions_doubly_broken": sum(
            1 for row in rows if row["state"] == STATE_DOUBLY_BROKEN),
        "bindings_total": len(definition_verdicts),
        "bindings_on_live_definitions": sum(
            row["binding_count"] for row in rows),
        "bindings_stale": bindings_stale,
        "bindings_sound": custody_totals[STATE_SOUND],
        "bindings_definition_drift": custody_totals[STATE_DEFINITION_DRIFT],
        "bindings_chat_orphaned": custody_totals[STATE_CHAT_ORPHANED],
        "bindings_doubly_broken": custody_totals[STATE_DOUBLY_BROKEN],
    }
    return {
        "definitions": rows,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_NAMES_NEVER_REPAIRS,
            _NOTE_SUBJECT_IS_THE_DEFINITION,
            _NOTE_JOIN_ADDS_NO_FACT,
            _NOTE_OWNER_SCOPED_TRUTH_AS_DATA,
        ],
    }


__all__ = [
    "DEFINITION_CUSTODY_STATES",
    "STATE_CHAT_ORPHANED",
    "STATE_DEFINITION_DRIFT",
    "STATE_DOUBLY_BROKEN",
    "STATE_SOUND",
    "STATE_UNBOUND",
    "census_definitions",
]
