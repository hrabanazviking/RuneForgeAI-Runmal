"""Library bind-plan census (P-153, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-153 slice doc.
What the derivation found missing, and what lands here:

- every judgement Part IX computes has been joined across
  its library exactly once, except the bind plan. P-144
  censuses bindings against definitions, P-148 against
  chats, P-150 joins the two per binding, P-151 rows
  definitions by the custody of their bindings, P-152
  rows chats by their coverage, and P-145 joins the
  stored import reports. The plan - P-132's
  plan_materialisation as P-136's preview judges it for
  ONE stored definition - is reachable only one
  definition at a time, through the P-136 road alone.
- the plan is a distinct computed judgement, not a
  restatement of any list shape: the P-131 summary
  counts every bootstrap entry (including the blank and
  non-object entries the plan honestly skips) and counts
  no seedable flag or variable at all. What a definition
  would actually plant - its messages after the
  kind-to-role map, its seedable flags and variables
  under the P-093 seedability law, and every entry that
  law or the bootstrap law skips, with its reason -
  exists only inside per-definition P-136 envelopes.
  An owner choosing which definition to bind, or
  auditing a library for openings that would plant
  less than they declare, could learn each plan only
  by walking every definition by hand through the
  P-136 road - the by-hand gap P-144's own derivation
  named as its justification, transposed to the plan
  axis, and the exact shape P-145 closed for reports.
- this module is that census, and nothing more: it
  calls the owning service - P-136's preview_bind_plan -
  verbatim per record over the caller's FULL definition
  list, and rows each definition with that envelope's
  own counts and the plan's skipped rows verbatim,
  classified under the plan law below. No second
  planning law is invented. The consumers are standing
  roads: bind aims at one definition and one chat, and
  P-138 / P-147 judge a named pair - choosing the
  definition half of that pair is aimed from the
  library, and this census is the library's plan
  surface to choose from.

The plan law (exactly one state per definition), read
from P-136's own counts (planned = messages + flags +
variables):

- ``clean`` - planned > 0 and skipped == 0: the opening
  plants everything it declares;
- ``partial`` - planned > 0 and skipped > 0: the
  opening plants, and honestly skips some of what it
  declares;
- ``skips_only`` - planned == 0 and skipped > 0: every
  declared opening entry is skipped (blank bootstrap,
  unseedable flag or variable), so a bind would plant
  nothing but the binding record itself;
- ``empty`` - planned == 0 and skipped == 0: the
  definition declares no opening material at all.

Honesty bounds, stated in every answer:

- the census is a pure read of the world as it stands:
  it writes, binds, seeds and repairs nothing, and
  every definition named still stands;
- every plan is definition-side only (P-136's bound,
  inherited): no chat has been consulted, bind-time
  refusals are not judged, and no chat outcome is
  promised;
- the plans name seedable keys, not landed keys: keys
  a specific chat already holds seed nothing at bind
  time (P-093 missing-keys-only), that skip is
  knowable only at bind time, and the binding record
  remains the only account of what actually landed;
- the census carries counts and the plans' skipped
  rows only: no message text, no flag or variable
  value, and no seedable key is named - a skipped row
  names only where it stood, its key or index and its
  reason - and the full plan stays on the P-136
  per-definition bind-plan road;
- each plan is computed from its definition's current
  revision, and truth-as-data throughout (P-027):
  censusing evaluates no condition, plays nothing
  back and executes nothing a definition carries.

No new store, no migration (the head stays 0041), no
storage-shape change, and no change to any banked answer.
"""

from __future__ import annotations

from runmal.scenarios.bindpreview import preview_bind_plan

STATE_CLEAN = "clean"
STATE_PARTIAL = "partial"
STATE_SKIPS_ONLY = "skips_only"
STATE_EMPTY = "empty"
BIND_PLAN_STATES = (
    STATE_CLEAN,
    STATE_PARTIAL,
    STATE_SKIPS_ONLY,
    STATE_EMPTY,
)

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, bound, seeded and repaired "
    "nothing, and every definition named here still "
    "stands as it stood"
)
_NOTE_DEFINITION_SIDE = (
    "every plan here is definition-side only: it is what "
    "bind computes from the definition alone - no chat "
    "has been consulted, bind-time refusals are not "
    "judged, and no chat outcome is promised"
)
_NOTE_SEEDABLE_NOT_LANDED = (
    "the plans name seedable keys, not landed keys: keys "
    "a specific chat already holds seed nothing at bind "
    "time (missing-keys-only), that skip is knowable "
    "only at bind time, and the binding record remains "
    "the only account of what actually landed"
)
_NOTE_NO_CONTENT = (
    "this census carries counts and the plans' skipped "
    "rows only - no message text, no flag or variable "
    "value, and no seedable key is named; a skipped row "
    "names only where it stood, its key or index and "
    "its reason, and the full plan stays on the "
    "per-definition bind-plan road"
)
_NOTE_CURRENT_REVISION_TRUTH_AS_DATA = (
    "each plan is computed from its definition's "
    "current revision, named in its row; bind pins "
    "whatever revision is current when it runs - and "
    "censusing evaluates no condition, plays nothing "
    "back and executes nothing a definition carries: "
    "stored content is data, never code"
)


def _plan_state(planned: int, skipped: int) -> str:
    """One definition's plan state under the plan law:
    exactly one of clean / partial / skips_only / empty,
    read from P-136's own counts alone."""
    if planned > 0:
        return STATE_PARTIAL if skipped > 0 else STATE_CLEAN
    return STATE_SKIPS_ONLY if skipped > 0 else STATE_EMPTY


def census_bind_plans(definitions) -> dict:
    """The library bind-plan census for one owner.

    ``definitions`` is the caller's own ScenarioDefinition
    records (the router passes the store's list_for_owner
    answer; owner scoping is the store's own). Each record
    is judged by the owning service - P-136's
    preview_bind_plan, called verbatim - and rows in the
    caller's list order. Every definition rows, clean and
    empty ones included: the subject is the definition.
    Each row names its definition by P-131's summary()
    verbatim and carries the envelope's own counts and
    the plan's skipped rows verbatim. ``by_where`` rolls
    the skipped rows up per where in first-appearance
    order across the rows, and every count is summed from
    the rows themselves, so the census cannot drift from
    its own evidence (the P-144 construction). Pure read:
    writes nothing, binds nothing, seeds nothing.
    """
    rows: list[dict] = []
    for record in definitions:
        envelope = preview_bind_plan(record)
        counts = envelope["counts"]
        planned = (
            counts["messages"] + counts["flags"]
            + counts["variables"]
        )
        skipped_rows = envelope["plan"]["skipped"]
        rows.append({
            "definition": record.summary(),
            "source_format": envelope["source_format"],
            "definition_revision": envelope["definition_revision"],
            "planned_messages": counts["messages"],
            "planned_flags": counts["flags"],
            "planned_variables": counts["variables"],
            "planned_total": planned,
            "skipped_total": counts["skipped"],
            "skipped": skipped_rows,
            "plan_state": _plan_state(planned, counts["skipped"]),
        })
    by_where: list[dict] = []
    where_index: dict[str, dict] = {}
    for row in rows:
        for skipped in row["skipped"]:
            entry = where_index.get(skipped["where"])
            if entry is None:
                entry = {"where": skipped["where"], "count": 0}
                where_index[skipped["where"]] = entry
                by_where.append(entry)
            entry["count"] += 1
    counts = {
        "definitions_total": len(rows),
        "definitions_clean": sum(
            1 for row in rows if row["plan_state"] == STATE_CLEAN),
        "definitions_partial": sum(
            1 for row in rows if row["plan_state"] == STATE_PARTIAL),
        "definitions_skips_only": sum(
            1 for row in rows
            if row["plan_state"] == STATE_SKIPS_ONLY),
        "definitions_empty": sum(
            1 for row in rows if row["plan_state"] == STATE_EMPTY),
        "planned_messages_total": sum(
            row["planned_messages"] for row in rows),
        "planned_flags_total": sum(
            row["planned_flags"] for row in rows),
        "planned_variables_total": sum(
            row["planned_variables"] for row in rows),
        "planned_total": sum(row["planned_total"] for row in rows),
        "skipped_total": sum(row["skipped_total"] for row in rows),
    }
    return {
        "definitions": rows,
        "by_where": by_where,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_DEFINITION_SIDE,
            _NOTE_SEEDABLE_NOT_LANDED,
            _NOTE_NO_CONTENT,
            _NOTE_CURRENT_REVISION_TRUTH_AS_DATA,
        ],
    }


__all__ = [
    "BIND_PLAN_STATES",
    "STATE_CLEAN",
    "STATE_EMPTY",
    "STATE_PARTIAL",
    "STATE_SKIPS_ONLY",
    "census_bind_plans",
]
