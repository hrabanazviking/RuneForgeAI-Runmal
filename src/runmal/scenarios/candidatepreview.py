"""Candidate replace preview (P-146, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-146 slice doc.
What the derivation found missing, and what lands here:

- P-140's replace-impact preview judges the current world
  and states in its fifth standing note that it judges NO
  candidate body, and that what a successful new body
  would plant is knowable only once it is stored. Yet a
  successful replace is permanent for the current body
  (P-140: no un-replace, no definition history), so the
  one judgement an owner most needs BEFORE committing a
  replace - would the store door accept this body, what
  would it store, and what would it plant - had no road.
- every ingredient already exists as an owning slice's
  own verb: the store door's parser (P-131: a body is
  stored only if P-026's parser accepts it, and replace
  parses before writing), P-132's pure
  plan_materialisation, P-136's plan-count law, P-131's
  summary count law, and P-140's impact envelope whole.
  No second law is invented; this module is the join.

This module is the read service behind the preview road.
The candidate body is judged through the store door's own
parser exactly as replace would store it - the same dict
check and the same P-026 parse, raising the same typed
refusals - and the would-be stored shape is P-026's
export_native of that parse, with its import report,
exactly the pair a successful replace would persist at
the next revision. Its would-be bind plan is P-132's
plan_materialisation over that shape, the current body's
plan is the same function over the stored definition, and
the comparison is read from those two answers themselves
so it cannot drift. P-140's envelope rides whole: the
candidate changes none of its facts.

Honesty bounds, stated in every answer:

- the preview is a pure read: previewing has replaced,
  written and stored nothing, the definition named still
  exists at its named revision, and the PUT road remains
  the only replacer;
- the candidate is judged exactly as replace would store
  it, and a body the parser refuses is refused here with
  the store door's own typed refusal, changing nothing -
  the parse is the store's, never a second validation;
- both plans are definition-side only (P-136): no chat
  has been consulted, bind-time refusals are not judged,
  and the plans name seedable keys, not landed keys;
- the replace-impact section is P-140's envelope for the
  world as it stands; the candidate changes none of its
  facts (bindings pin stored revisions, the organisation
  row keys on the definition's id);
- a candidate's unmappable raw values are not part of
  the native shape and would not persist (P-131); the
  candidate report in this envelope names every one;
- truth-as-data throughout (P-027): the candidate is
  parsed and planned as data - previewing evaluates no
  condition, plays nothing back and executes nothing it
  carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import plan_materialisation
from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.replacepreview import preview_replace_impact
from runmal.scenarios.store import ScenarioStoreError

_NOTE_PURE_READ = (
    "this preview is a pure read: previewing has "
    "replaced, written and stored nothing, the "
    "definition named above still exists at the "
    "revision named above, and the PUT replace road "
    "remains the only replacer"
)
_NOTE_STORE_DOOR = (
    "the candidate body was judged through the store "
    "door's own parser (P-026) exactly as a replace "
    "would store it: the native shape and import report "
    "named here are what a successful replace would "
    "persist at the next revision named above, and a "
    "body the parser refuses is refused here with the "
    "same typed refusal, changing nothing"
)
_NOTE_PLANS_DEFINITION_SIDE = (
    "both plans are definition-side only: they are what "
    "bind computes from each body alone, no chat has "
    "been consulted and bind-time refusals are not "
    "judged here; the plans name seedable keys, not "
    "landed keys - the binding record is the only "
    "account of what actually landed"
)
_NOTE_IMPACT_WHOLE = (
    "the replace-impact section is the P-140 envelope "
    "for the world as it stands, carried whole; the "
    "candidate changes none of its facts - bindings pin "
    "the revisions of the body actually stored when "
    "they bound, and the organisation row keys on this "
    "definition's id, not on its body"
)
_NOTE_UNMAPPABLE_NOT_PERSISTED = (
    "a candidate's unmappable raw values are not part "
    "of the native shape and would not persist: the "
    "candidate import report named here is the record "
    "of every element the parser could not map, "
    "recorded as data and never executed"
)
_NOTE_TRUTH_AS_DATA = (
    "the candidate was parsed and planned as data "
    "only: previewing it evaluated no condition, played "
    "nothing back and executed nothing it carries"
)


def _plan_counts(plan: dict) -> dict:
    """P-136's count law, read from the plan itself."""
    return {
        "messages": len(plan["messages"]),
        "flags": len(plan["flags"]),
        "variables": len(plan["variables"]),
        "skipped": len(plan["skipped"]),
    }


def _count_triple(current: int, candidate: int) -> dict:
    return {
        "current": current,
        "candidate": candidate,
        "delta": candidate - current,
    }


def _parse_candidate(body):
    """The store door, exactly as ScenarioStore.replace
    applies it (store.py's _parse_body law): a non-object
    body raises ScenarioStoreError; anything else is
    judged by P-026's parser alone, raising
    ScenarioParseError on refusal."""
    if not isinstance(body, dict):
        raise ScenarioStoreError(
            "scenario definition must be a JSON object")
    return parse_scenario_file(body)


def preview_candidate_replace(record, bindings, organisation,
                              live_definition_ids, body) -> dict:
    """The candidate replace-preview envelope for one
    stored record and one candidate body.

    ``record`` is a ScenarioDefinition (the router has
    already decided existence and ownership, so an unknown
    or foreign id answers 404 before any candidate verdict
    - the P-131 replace law); ``bindings`` is a
    ScenarioBindingStore and ``organisation`` a
    ScenarioOrganisationStore for the same owner;
    ``live_definition_ids`` is the caller's live definition
    id set, exactly as the P-135 roads build it; ``body``
    is the candidate definition body, judged through the
    store door's own parser - a refused body raises the
    door's own typed refusal (ScenarioParseError, or
    ScenarioStoreError for a non-object body) before any
    envelope exists, exactly as a refused replace raises
    before any write. Pure read: the candidate is stored
    nowhere and the stored record is byte-untouched.
    """
    parsed = _parse_candidate(body)
    candidate_definition = export_native(parsed)
    candidate_report = (
        parsed.report.to_dict() if parsed.report else {})
    current_plan = plan_materialisation(record.definition)
    candidate_plan = plan_materialisation(candidate_definition)
    current_counts = _plan_counts(current_plan)
    candidate_counts = _plan_counts(candidate_plan)
    summary = record.summary()
    candidate_unmappable = candidate_report.get("unmappable") or []
    candidate_roles = candidate_definition.get("roles")
    candidate_bootstrap = candidate_definition.get(
        "bootstrap_messages")
    current_flags = set(current_plan["flags"])
    candidate_flags = set(candidate_plan["flags"])
    current_variables = set(current_plan["variables"])
    candidate_variables = set(candidate_plan["variables"])
    return {
        "definition_id": record.id,
        "definition_name": record.name,
        "definition_revision": record.revision,
        "source_format": record.source_format,
        "next_revision": record.revision + 1,
        "current": {
            "summary": summary,
            "plan": current_plan,
            "counts": current_counts,
        },
        "candidate": {
            "name": parsed.name,
            "source_format": parsed.source_format,
            "definition": candidate_definition,
            "report": candidate_report,
            "counts": {
                "role_count": (
                    len(candidate_roles)
                    if isinstance(candidate_roles, list) else 0
                ),
                "bootstrap_count": (
                    len(candidate_bootstrap)
                    if isinstance(candidate_bootstrap, list) else 0
                ),
                "has_unmappable": bool(candidate_unmappable),
            },
            "plan": candidate_plan,
            "plan_counts": candidate_counts,
        },
        "comparison": {
            "name_changed": parsed.name != record.name,
            "source_format_changed": (
                parsed.source_format != record.source_format),
            "identical_body": (
                candidate_definition == record.definition),
            "roles": _count_triple(
                summary["role_count"],
                len(candidate_roles)
                if isinstance(candidate_roles, list) else 0),
            "bootstrap_messages": _count_triple(
                summary["bootstrap_count"],
                len(candidate_bootstrap)
                if isinstance(candidate_bootstrap, list) else 0),
            "plan_messages": _count_triple(
                current_counts["messages"],
                candidate_counts["messages"]),
            "plan_flags": _count_triple(
                current_counts["flags"],
                candidate_counts["flags"]),
            "plan_variables": _count_triple(
                current_counts["variables"],
                candidate_counts["variables"]),
            "plan_skipped": _count_triple(
                current_counts["skipped"],
                candidate_counts["skipped"]),
            "flag_keys_added": sorted(
                candidate_flags - current_flags),
            "flag_keys_removed": sorted(
                current_flags - candidate_flags),
            "variable_keys_added": sorted(
                candidate_variables - current_variables),
            "variable_keys_removed": sorted(
                current_variables - candidate_variables),
        },
        "replace_impact": preview_replace_impact(
            record, bindings, organisation, live_definition_ids),
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_STORE_DOOR,
            _NOTE_PLANS_DEFINITION_SIDE,
            _NOTE_IMPACT_WHOLE,
            _NOTE_UNMAPPABLE_NOT_PERSISTED,
            _NOTE_TRUTH_AS_DATA,
        ],
    }


__all__ = ["preview_candidate_replace"]
