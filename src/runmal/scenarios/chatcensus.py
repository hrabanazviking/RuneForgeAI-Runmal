"""Binding chat-custody census (P-148, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-148 slice doc.
What the derivation found missing, and what lands here:

- a binding has two parents, and only one axis was ever
  judged. The definition axis is complete: delete never
  cascades into the binding store (P-132 / P-135),
  P-139 previews the orphaning before a delete, and
  P-144 censuses the drift after it (current, superseded,
  ahead, stale). The chat axis was judged nowhere:
  chats.service.delete_chat cleans the chat's
  checkpoints, databank, undo store, vision links, image
  attachments and folder-watch registrations, but never
  the scenario binding store, so a deleted chat's binding
  record stands forever - and the per-chat binding read
  (P-132) reads only the binding store, so it still
  answers that record exactly as if the chat lived.
  P-144's own fifth note states the bound: its census
  "judges no chat liveness, a fact the binding store
  does not carry". Chat existence is a fact the Chat
  table carries, and P-138 already reads that table
  through the same owner-scoped law.
- the one removal road, unbind per chat, works on the
  binding store alone and could remove an orphan - but
  no surface named which bindings are orphaned, so the
  owner could not aim it. Custody without a census is
  undiscoverable. This module is the census.

This module is the read service behind the census road.
It is async because chat existence lives in the SQL Chat
table (the chatpreview precedent: a scenario read
service that consults chats takes the session). Every
row is read through the owning slice's own verb -
P-135's list_bindings - so summaries are verbatim P-135
shape and cannot drift; the census only joins each row
to the caller's live chats and classifies it. Every
count is summed from the rows and groups themselves.

The state law (exactly one state per binding):

- ``live`` - the binding's chat row still exists for
  this owner in the Chat table;
- ``orphaned`` - it does not: the chat was deleted, the
  id never existed, or the chat belongs to another
  owner. The three answer exactly alike - existence is
  judged owner-scoped, so nothing leaks.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, unbinds and deletes nothing, cleans
  nothing up, and every binding named still stands;
- deleting a chat does not touch the binding store, and
  an orphaned binding remains until it is unbound per
  chat - the unbind road works on the binding store
  alone, so an orphan named here can still be removed;
- existence is judged for this owner at read time only;
  the census names no chat content and no chat facts
  beyond existence - a group room that exists is live
  here, because custody judges existence, not
  bindability (bind's refusal law is bind's);
- the two axes are independent: definition-side drift
  is P-144's census, a binding can be orphaned and
  stale at once, and this census carries no seeded
  content (the binding summaries never do, P-135);
- truth-as-data throughout (P-027): censusing evaluates
  no condition, plays nothing back and executes
  nothing a definition carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import list_bindings

STATE_LIVE = "live"
STATE_ORPHANED = "orphaned"
CHAT_CUSTODY_STATES = (
    STATE_LIVE,
    STATE_ORPHANED,
)

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, unbound and deleted "
    "nothing, and every binding named here still stands"
)
_NOTE_ORPHAN_REMAINS = (
    "deleting a chat does not touch the binding store: "
    "an orphaned binding remains until it is unbound "
    "per chat, and the unbind road works on the binding "
    "store alone, so an orphan named here can still be "
    "removed by it - this census cleans nothing up, it "
    "names custody, it does not repair it"
)
_NOTE_OWNER_SCOPED_EXISTENCE = (
    "chat existence is judged for this owner at read "
    "time: a chat id that names another owner's chat, "
    "or no chat at all, reads as gone exactly as a "
    "deleted chat does - existence never leaks, and no "
    "chat fact beyond existence is read or carried here"
)
_NOTE_TWO_AXES = (
    "the chat axis judged here is independent of the "
    "definition axis: definition-side drift - current, "
    "superseded, ahead, stale - is the P-144 census, a "
    "binding can be orphaned and stale at once, and "
    "this census carries no seeded content, which the "
    "binding summaries never carry"
)
_NOTE_TRUTH_AS_DATA = (
    "this census evaluates no condition, plays nothing "
    "back and executes nothing a definition carries: "
    "stored content is data, never code"
)


async def census_binding_chats(
    session, bindings, owner_id: str, live_definition_ids
) -> dict:
    """The binding chat-custody census for one owner.

    ``session`` is an async DB session; ``bindings`` is
    a ScenarioBindingStore; ``live_definition_ids`` is
    the caller's live definition id set, exactly as the
    P-135 roads build it. Rows are P-135 list_bindings
    summaries verbatim, enriched with ``chat_exists``
    and ``chat_state`` under the state law above.
    Existence is judged once for the whole set: the
    rows' distinct chat ids are selected from the Chat
    table under this owner's id alone (the owner-scoped
    existence law bind and P-138 read the table by);
    no query is issued when there are no bindings.
    Groups roll the same rows up per definition in
    first-binding order. Every count is summed from the
    rows and groups themselves; chat counts are
    DISTINCT chat ids, stated separately from the row
    counts because a hand-damaged store could hold two
    rows for one chat (bind forbids it) and the census
    counts rows and chats honestly, separately. Pure
    read: writes nothing, unbinds nothing, deletes
    nothing.
    """
    from sqlalchemy import select

    from runmal.db.models import Chat

    summaries = list_bindings(bindings, owner_id, live_definition_ids)
    live_chat_ids: set = set()
    chat_ids = {row["chat_id"] for row in summaries}
    if chat_ids:
        result = await session.execute(
            select(Chat.id).where(
                Chat.user_id == owner_id, Chat.id.in_(chat_ids))
        )
        live_chat_ids = set(result.scalars().all())
    rows: list[dict] = []
    for summary in summaries:
        exists = summary["chat_id"] in live_chat_ids
        rows.append({
            **summary,
            "chat_exists": exists,
            "chat_state": STATE_LIVE if exists else STATE_ORPHANED,
        })
    groups: list[dict] = []
    by_id: dict[str, dict] = {}
    for row in rows:
        group = by_id.get(row["definition_id"])
        if group is None:
            group = {
                "definition_id": row["definition_id"],
                "definition_name": row["definition_name"],
                "definition_exists": row["definition_exists"],
                "bindings_total": 0,
                "live": 0,
                "orphaned": 0,
                "chat_ids": [],
            }
            by_id[row["definition_id"]] = group
            groups.append(group)
        group["bindings_total"] += 1
        group[row["chat_state"]] += 1
        group["chat_ids"].append(row["chat_id"])
    counts = {
        "bindings_total": len(rows),
        "live": sum(1 for row in rows if row["chat_state"] == STATE_LIVE),
        "orphaned": sum(
            1 for row in rows if row["chat_state"] == STATE_ORPHANED),
        "chats_live": len({
            row["chat_id"] for row in rows
            if row["chat_state"] == STATE_LIVE
        }),
        "chats_orphaned": len({
            row["chat_id"] for row in rows
            if row["chat_state"] == STATE_ORPHANED
        }),
        "definitions_referenced": len(groups),
        "definitions_with_live": sum(
            1 for group in groups if group["live"] > 0),
        "definitions_with_orphaned": sum(
            1 for group in groups if group["orphaned"] > 0),
    }
    return {
        "bindings": rows,
        "by_definition": groups,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_ORPHAN_REMAINS,
            _NOTE_OWNER_SCOPED_EXISTENCE,
            _NOTE_TWO_AXES,
            _NOTE_TRUTH_AS_DATA,
        ],
    }


__all__ = [
    "CHAT_CUSTODY_STATES",
    "STATE_LIVE",
    "STATE_ORPHANED",
    "census_binding_chats",
]
