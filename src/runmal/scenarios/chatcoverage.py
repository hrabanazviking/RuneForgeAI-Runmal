"""Chat coverage census (P-152, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-152 slice doc.
What the derivation found missing, and what lands here:

- every census in the part rows bindings, definitions or
  report rows. P-144 censuses bindings against the
  definition store, P-148 censuses bindings against the
  Chat table, P-150 joins the two per binding, P-151 rows
  definitions over the caller's full list, and P-145 rows
  the unmappable elements stored reports name. No census
  rows the Chat table itself as its subject, and the gap
  is mechanical: the binding censuses build their rows
  from list_bindings, so a chat with NO binding appears
  in no census at all - the most common chat state in
  any real library, carrying no scenario, is invisible
  to every custody surface in the part - and no road
  answers the chat-side library question - which of my
  chats carry a binding at all, which stand sound, which
  carry a drifted pin, which carry a binding whose
  definition is gone - except walking every chat by hand
  through the P-132 per-chat binding read, judging the
  definition-axis verdict by eye against the definition
  list. That is exactly the by-hand gap P-144's own
  derivation named as its justification, transposed to
  the chat axis, and the exact mirror of the gap P-151
  closed for definitions.
- this module is that census, and nothing more: it
  composes the one owning verdict service - P-144's
  census_bindings over the caller's own inputs - and
  joins its rows per chat over the caller's FULL chat
  list, read owner-scoped from the Chat table in the
  chats service's own list order, so unbound chats row
  as unbound and orphaned bindings (their chat gone -
  P-148's rows) are counted in the totals while rowing
  under no chat: P-151's stale-in-totals law, transposed.
  The consumers are standing roads, not invented ones:
  bind aims at one chat (an owner choosing a chat to
  bind needs a FREE chat - bind refuses an already-bound
  one, P-132), unbind aims per chat, the P-149
  delete-impact preview aims per chat, and chat deletion
  itself is per chat. Every one of those acts is aimed
  from the chat side, and this census is the roster they
  aim from.

The coverage law (exactly one state per chat) - no
third state law is invented; each bound row carries
P-144's row verbatim, and the coverage state is its
plain reading on the chat axis (the chat axis itself
needs no verdict: a rowed chat exists for this owner
by construction):

- ``unbound`` - no binding row names this chat;
- ``sound`` - the carried binding's P-144 state is
  current;
- ``definition_drift`` - the carried binding's P-144
  state is superseded or ahead;
- ``definition_gone`` - the carried binding's P-144
  state is stale: the definition is gone. Split out
  from drift because on a standing chat the distinction
  is the actionable one - a drifted pin can be
  refreshed by unbind + bind against a living
  definition, a gone definition leaves nothing to
  rebind to - and P-151's own law likewise counts stale
  apart from drift.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, binds, unbinds and deletes nothing, and
  every chat and binding named still stands;
- naming is not repair: a bound chat stays bound until
  it is unbound per chat and an unbound chat stays
  unbound until it is bound - this census aims the
  standing bind / unbind roads, it is neither of them;
- the subject is the chat: a chat with no binding rows
  here as unbound and appears in no binding census; an
  orphaned binding rows under no chat and is counted
  in the census totals only;
- the join adds no third fact: every rowed binding is
  the binding census's own row verbatim, and this
  census carries no seeded content (the binding
  summaries never do, P-135);
- chat facts here are identity facts only - id, title,
  group flag and creation stamp; no message, character
  or seeded content is read or carried - and the chat
  list is this owner's own, so another owner's chats
  never row and existence never leaks;
- truth-as-data throughout (P-027): censusing evaluates
  no condition, plays nothing back and executes
  nothing a definition carries.
"""

from __future__ import annotations

from runmal.scenarios.bindingcensus import (
    STATE_AHEAD,
    STATE_CURRENT,
    STATE_STALE,
    STATE_SUPERSEDED,
    census_bindings,
)

STATE_UNBOUND = "unbound"
STATE_SOUND = "sound"
STATE_DEFINITION_DRIFT = "definition_drift"
STATE_DEFINITION_GONE = "definition_gone"
CHAT_COVERAGE_STATES = (
    STATE_UNBOUND,
    STATE_SOUND,
    STATE_DEFINITION_DRIFT,
    STATE_DEFINITION_GONE,
)

_COVERAGE_BY_BINDING_STATE = {
    STATE_CURRENT: STATE_SOUND,
    STATE_SUPERSEDED: STATE_DEFINITION_DRIFT,
    STATE_AHEAD: STATE_DEFINITION_DRIFT,
    STATE_STALE: STATE_DEFINITION_GONE,
}

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, bound, unbound and deleted "
    "nothing, and every chat and binding named here "
    "still stands"
)
_NOTE_NAMES_NEVER_REPAIRS = (
    "naming is not repair: a bound chat stays bound "
    "until it is unbound per chat and an unbound chat "
    "stays unbound until it is bound - this census aims "
    "the standing bind and unbind roads, it is neither "
    "of them, and it cleans nothing up"
)
_NOTE_SUBJECT_IS_THE_CHAT = (
    "the subject of this census is the chat: a chat "
    "with no binding rows here as unbound and appears "
    "in no binding census, and an orphaned binding - "
    "one whose chat is gone - rows under no chat and "
    "is counted in the census totals only"
)
_NOTE_JOIN_ADDS_NO_FACT = (
    "the join adds no third fact: every rowed binding "
    "is the binding census's own row verbatim and the "
    "coverage state is its plain reading on the chat "
    "axis - current reads sound, superseded or ahead "
    "reads definition_drift, stale reads "
    "definition_gone, split out because a drifted pin "
    "can be refreshed by unbind and bind against a "
    "living definition while a gone definition leaves "
    "nothing to rebind to - and this census carries no "
    "seeded content, which the binding summaries never "
    "carry"
)
_NOTE_IDENTITY_FACTS_OWNER_SCOPED = (
    "chat facts here are identity facts only - id, "
    "title, group flag and creation stamp; no message, "
    "character or seeded content is read or carried - "
    "the chat list is this owner's own, another owner's "
    "chats never row, and this census evaluates no "
    "condition, plays nothing back and executes "
    "nothing a definition carries: stored content is "
    "data, never code"
)


async def census_chat_coverage(
    session, bindings, owner_id: str, definitions
) -> dict:
    """The chat coverage census for one owner.

    ``session`` is an async DB session (the subject
    lives in the SQL Chat table); ``bindings`` is a
    ScenarioBindingStore; ``definitions`` is the
    caller's live ScenarioDefinition records for the
    same owner (the router passes the definition
    store's list_for_owner answer, exactly as the
    P-144 road does). The definition verdicts are
    P-144's census_bindings rows over those same
    inputs, queued per chat_id in row order (the
    P-150 / P-151 duplicate-id law: a hand-damaged
    store holding two rows for one chat joins the
    first to the chat; the surplus is counted, never
    hidden). Chats are the caller's own, read
    owner-scoped from the Chat table in the chats
    service's own list order (Chat.created_at, then
    Chat.id for determinism). Rows carry identity
    facts only - chat_id, title, is_group (the group
    flag P-138 reads), created_at - plus the carried
    P-144 row verbatim (or None) and the coverage
    state. Every count is summed from the rows and
    verdict rows themselves; bindings are counted per
    row and chats per chat, stated separately exactly
    as P-148 states its distinct law. Pure read:
    writes nothing, binds nothing, unbinds nothing,
    deletes nothing.
    """
    from sqlalchemy import select

    from runmal.db.models import Chat

    verdicts = census_bindings(
        bindings, owner_id, definitions)["bindings"]
    result = await session.execute(
        select(Chat)
        .where(Chat.user_id == owner_id)
        .order_by(Chat.created_at, Chat.id)
    )
    chats = list(result.scalars().all())
    queues: dict[str, list[dict]] = {}
    for verdict in verdicts:
        queues.setdefault(verdict["chat_id"], []).append(verdict)
    standing_ids = {chat.id for chat in chats}
    rows: list[dict] = []
    surplus = 0
    rowed_definition_ids: set = set()
    for chat in chats:
        queue = queues.get(chat.id) or []
        binding = queue[0] if queue else None
        surplus += max(0, len(queue) - 1)
        if binding is not None:
            rowed_definition_ids.add(binding["definition_id"])
        rows.append({
            "chat_id": chat.id,
            "title": chat.title,
            "is_group": chat.group_id is not None,
            "created_at": chat.created_at.isoformat(),
            "binding": binding,
            "coverage_state": (
                _COVERAGE_BY_BINDING_STATE[binding["state"]]
                if binding is not None
                else STATE_UNBOUND
            ),
        })
    bindings_rowed = sum(
        1 for row in rows if row["binding"] is not None)
    bindings_orphaned = sum(
        1 for verdict in verdicts
        if verdict["chat_id"] not in standing_ids
    )
    counts = {
        "chats_total": len(rows),
        "chats_unbound": sum(
            1 for row in rows
            if row["coverage_state"] == STATE_UNBOUND),
        "chats_sound": sum(
            1 for row in rows
            if row["coverage_state"] == STATE_SOUND),
        "chats_definition_drift": sum(
            1 for row in rows
            if row["coverage_state"] == STATE_DEFINITION_DRIFT),
        "chats_definition_gone": sum(
            1 for row in rows
            if row["coverage_state"] == STATE_DEFINITION_GONE),
        "bindings_total": len(verdicts),
        "bindings_rowed": bindings_rowed,
        "bindings_orphaned_chat": bindings_orphaned,
        "bindings_surplus_rows": surplus,
        "definitions_referenced": len(rowed_definition_ids),
    }
    return {
        "chats": rows,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_NAMES_NEVER_REPAIRS,
            _NOTE_SUBJECT_IS_THE_CHAT,
            _NOTE_JOIN_ADDS_NO_FACT,
            _NOTE_IDENTITY_FACTS_OWNER_SCOPED,
        ],
    }


__all__ = [
    "CHAT_COVERAGE_STATES",
    "STATE_DEFINITION_DRIFT",
    "STATE_DEFINITION_GONE",
    "STATE_SOUND",
    "STATE_UNBOUND",
    "census_chat_coverage",
]
