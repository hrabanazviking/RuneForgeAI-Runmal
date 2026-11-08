"""Global binding census (P-144, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice scope is
derived from the in-tree record - see the P-144 slice doc.
What the derivation found missing, and what lands here:

- P-142 named this exact candidate: "a global
  stale/superseded binding census - named as a future
  candidate, not built here." The gap is mechanical.
  A binding outlives two things: its definition (delete
  never cascades into the binding store, P-132 / P-135)
  and its pinned revision (replace never re-materialises
  a binding, P-140). Both drifts accumulate in the one
  store, yet no surface judges them together: P-135 list
  summaries carry the pinned revision and
  definition_exists, but no live revision to judge the
  pin against, so supersession is unjudgeable from the
  only global binding surface; P-140 pinned split is
  per-definition, inside a replace preview, before a
  replace - after replaces have landed, an owner could
  learn which bindings pin a superseded revision only
  by walking every definition by hand.

This module is the read service behind the census road.
Every row is read through the owning slice own verb -
P-135 list_bindings - so summaries are verbatim P-135
shape and cannot drift; the census only joins each row
to the live definition record (its current revision and
name) and classifies it. Every count is summed from the
rows and groups themselves.

The state law (exactly one state per binding):

- ``stale`` - the definition is gone (definition_exists
  false on the P-135 surface);
- ``current`` - the pinned revision is the live one;
- ``superseded`` - the pinned revision is older than
  the live one (a replace landed after the bind);
- ``ahead`` - the pinned revision is newer than the
  live one. Impossible by construction (bind pins the
  then-current revision and replace only moves it up),
  counted anyway so a hand-damaged store is named,
  never hidden - the P-140 pinned_newer precedent.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, unbinds and cascades nothing, cleans
  nothing up, and every binding named still stands;
- stale bindings remain until unbound per chat
  (P-132); superseded bindings keep their pinned
  revision and their seeded content, which is the
  chat's own truth (P-140);
- the census judges revisions and existence only,
  against the definition store only: it carries no
  seeded content (summaries never do, P-135) and it
  judges no chat liveness - the binding store carries
  no such fact and none is fabricated here;
- truth-as-data throughout (P-027): censusing evaluates
  no condition, plays nothing back and executes
  nothing a definition carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import list_bindings

STATE_CURRENT = "current"
STATE_SUPERSEDED = "superseded"
STATE_AHEAD = "ahead"
STATE_STALE = "stale"
BINDING_STATES = (
    STATE_CURRENT,
    STATE_SUPERSEDED,
    STATE_AHEAD,
    STATE_STALE,
)

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, unbound and cascaded "
    "nothing, and every binding named here still stands"
)
_NOTE_STALE_REMAINS = (
    "a stale binding remains until it is unbound per "
    "chat: deleting a definition does not cascade into "
    "the binding store, and this census cleans nothing "
    "up - it names drift, it does not repair it"
)
_NOTE_SUPERSEDED_KEEPS_PIN = (
    "a superseded binding keeps the revision it pinned "
    "when it bound and the content it seeded - messages "
    "and variables are the chat's own truth, and "
    "replacing a definition never re-materialises a "
    "binding; a chat that wants the new body unbinds "
    "and binds again as its own act"
)
_NOTE_AHEAD_NAMED = (
    "an ahead binding pins a revision newer than the "
    "definition current one: impossible by construction "
    "(a bind pins the then-current revision and a "
    "replace only moves it up), so an ahead row names "
    "a hand-damaged store - it is counted and shown, "
    "never hidden and never repaired here"
)
_NOTE_JUDGES_REVISIONS_ONLY = (
    "this census judges bindings against the definition "
    "store only - pinned revision against live revision, "
    "and existence; it carries no seeded content (the "
    "binding summaries never do) and judges no chat "
    "liveness, a fact the binding store does not carry"
)


def _state_for(row: dict, live: dict | None) -> str:
    if live is None:
        return STATE_STALE
    pinned = row["definition_revision"]
    if pinned < live["revision"]:
        return STATE_SUPERSEDED
    if pinned > live["revision"]:
        return STATE_AHEAD
    return STATE_CURRENT


def census_bindings(bindings, owner_id: str, definitions) -> dict:
    """The global binding census for one owner.

    ``bindings`` is a ScenarioBindingStore;
    ``definitions`` is the caller live ScenarioDefinition
    records for the same owner (the router passes the
    definition store list verb answer). Rows are P-135
    list_bindings summaries verbatim, enriched with
    ``current_revision`` and ``current_name`` (the live
    record facts, None when the definition is gone) and
    ``state`` under the state law above. Groups roll the
    same rows up per definition in first-binding order.
    Every count is summed from the rows and groups
    themselves. Pure read: writes nothing, unbinds
    nothing, cascades nothing.
    """
    live_by_id = {
        record.id: {"revision": record.revision, "name": record.name}
        for record in definitions
    }
    live_ids = set(live_by_id)
    rows: list[dict] = []
    for summary in list_bindings(bindings, owner_id, live_ids):
        live = live_by_id.get(summary["definition_id"])
        rows.append({
            **summary,
            "current_revision": live["revision"] if live else None,
            "current_name": live["name"] if live else None,
            "state": _state_for(summary, live),
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
                "current": 0,
                "superseded": 0,
                "ahead": 0,
                "stale": 0,
                "chat_ids": [],
            }
            by_id[row["definition_id"]] = group
            groups.append(group)
        group["bindings_total"] += 1
        group[row["state"]] += 1
        group["chat_ids"].append(row["chat_id"])
    counts = {
        "bindings_total": len(rows),
        "current": sum(1 for row in rows if row["state"] == STATE_CURRENT),
        "superseded": sum(
            1 for row in rows if row["state"] == STATE_SUPERSEDED),
        "ahead": sum(1 for row in rows if row["state"] == STATE_AHEAD),
        "stale": sum(1 for row in rows if row["state"] == STATE_STALE),
        "chats_affected": len(rows),
        "definitions_referenced": len(groups),
        "definitions_with_current": sum(
            1 for group in groups if group["current"] > 0),
        "definitions_with_superseded": sum(
            1 for group in groups if group["superseded"] > 0),
        "definitions_with_stale": sum(
            1 for group in groups if group["stale"] > 0),
    }
    return {
        "bindings": rows,
        "by_definition": groups,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_STALE_REMAINS,
            _NOTE_SUPERSEDED_KEEPS_PIN,
            _NOTE_AHEAD_NAMED,
            _NOTE_JUDGES_REVISIONS_ONLY,
        ],
    }


__all__ = [
    "BINDING_STATES",
    "STATE_AHEAD",
    "STATE_CURRENT",
    "STATE_STALE",
    "STATE_SUPERSEDED",
    "census_bindings",
]
