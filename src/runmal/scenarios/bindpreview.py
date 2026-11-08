"""Binding plan preview (P-136, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-136 slice doc.
What the derivation found missing, and what lands here:

- the one consequential act in Part IX — binding — could
  not be inspected before it was done. P-132's
  plan_materialisation is pure, exported and battery-
  pinned, but the only road that reached it was the bind
  road itself, which executes the plan (messages
  appended, variables seeded, record written — and
  unbinding never takes seeded content back). An owner
  who wanted to know what a definition would plant, and
  what it would honestly skip, had to bind a real empty
  chat to find out. The interpreted opening (the kind ->
  role map, cast-resolved speaker names, P-093
  seedability verdicts) exists nowhere else.

This module is the read service behind the preview road.
It runs P-132's OWN plan function over the stored
definition — no second planning law is invented — and
wraps the plan in an envelope naming the definition it
was computed from (id, name, its CURRENT revision, its
source format), counts read from the plan itself so they
cannot drift (the P-131 summary precedent), and the
standing honesty notes.

Honesty bounds, stated in every answer:

- the plan is DEFINITION-side only: it is what bind
  computes from the definition alone, before any chat
  is consulted. Nothing has been written, and no chat
  outcome is promised.
- bind-time refusals are NOT judged here: unknown or
  foreign chat, group room, already bound, non-empty
  chat are decided by bind against a specific chat.
- keys a specific chat already holds seed nothing at
  bind time (P-093 missing-keys-only); that skip is
  knowable only at bind time, so the plan names
  SEEDABLE keys, not landed keys — the binding record
  remains the only account of what actually landed.
- the plan is computed from the definition's current
  revision; bind pins whatever revision is current
  when it runs.
- truth-as-data throughout (P-027): previewing a
  definition evaluates no condition, plays nothing
  back and executes nothing it carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import plan_materialisation

_NOTE_DEFINITION_SIDE = (
    "this is the definition-side plan that P-132's bind "
    "computes from the definition alone; no chat has been "
    "consulted and nothing has been written"
)
_NOTE_REFUSALS_NOT_JUDGED = (
    "bind-time refusals are not judged here: an unknown or "
    "foreign chat, a group room, an already-bound chat and "
    "a non-empty chat are decided by bind against a "
    "specific chat"
)
_NOTE_MISSING_KEYS_ONLY = (
    "keys a specific chat already holds seed nothing at "
    "bind time (P-093 missing-keys-only); those skips are "
    "knowable only at bind time, so this plan names "
    "seedable keys, not landed keys — the binding record "
    "is the only account of what actually landed"
)
_NOTE_CURRENT_REVISION = (
    "this plan is computed from the definition's current "
    "revision, named above; bind pins whatever revision "
    "is current when it runs"
)


def preview_bind_plan(record) -> dict:
    """The bind-plan preview envelope for one stored record.

    ``record`` is a ScenarioDefinition (the router has
    already decided existence and ownership). The plan is
    P-132's plan_materialisation over the record's stored
    definition, verbatim; the counts are read from the
    plan itself; the notes are the standing bounds, in
    fixed order. Pure: reads the record, writes nothing.
    """
    plan = plan_materialisation(record.definition)
    return {
        "definition_id": record.id,
        "definition_name": record.name,
        "definition_revision": record.revision,
        "source_format": record.source_format,
        "plan": plan,
        "counts": {
            "messages": len(plan["messages"]),
            "flags": len(plan["flags"]),
            "variables": len(plan["variables"]),
            "skipped": len(plan["skipped"]),
        },
        "notes": [
            _NOTE_DEFINITION_SIDE,
            _NOTE_REFUSALS_NOT_JUDGED,
            _NOTE_MISSING_KEYS_ONLY,
            _NOTE_CURRENT_REVISION,
        ],
    }


__all__ = ["preview_bind_plan"]
