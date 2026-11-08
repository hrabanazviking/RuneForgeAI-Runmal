"""Chat-scoped candidate bind preview (P-147, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-147 slice doc.
What the derivation found missing, and what lands here:

- the Part IX preview matrix had exactly one empty cell.
  P-136 judges the STORED body definition-side; P-138
  judges the STORED body against one chat; P-146 judges
  a CANDIDATE body definition-side, and its own third
  standing note bounds those plans exactly as P-136's
  notes bounded its plan: no chat has been consulted,
  bind-time refusals are not judged, and the plans name
  seedable keys, not landed keys. P-146's scout declined
  this composition for its slice on the ground that the
  definition-side plan plus P-138 after a real replace
  covers the need in two steps - but a successful
  replace is permanent for the current body (P-140:
  no un-replace, no definition history), so that cover
  requires committing the irreversible act first. The
  pre-commit candidate x chat verdict had no road.

This module is the read service behind the chat-scoped
candidate road. The candidate is judged through the
store door exactly as P-146 applies it (the store.py
_parse_body law: a non-object body raises
ScenarioStoreError, anything else is judged by P-026's
parser alone) - P-146 is not in this base, so the door
is stated here in full and no second validation law is
invented. The chat side is P-138's judgement, called
never re-implemented: the Chat row and its group flag,
the binding store's get_for_chat, the chat service's
history, and P-093's resolve_key + get_entry pair,
applied to the CANDIDATE plan. The stored plan's split
is computed by the same law beside it, so the owner
sees exactly what the candidate changes for this chat.
The preview refuses nothing, replaces nothing, binds
nothing and writes nothing: PUT remains the only
replacer, bind the only binder, and the binding record
the only account of what actually landed.

Honesty bounds, stated in every answer:

- would_bind and the splits judge the candidate AS IF
  it were stored at the next revision and then bound;
  binding today would bind the current revision, whose
  own chat verdict stays on P-138's road.
- the chat is judged as it stands; bind re-decides
  every fact when it runs, and a replace landing first
  changes the stored body bind would pin.
- already-present verdicts are judged under the
  scenario writer by the P-093 store's own presence
  law; the splits name seedable keys, not landed keys.
- truth-as-data throughout (P-027): the candidate is
  parsed and planned as data; nothing it carries is
  evaluated, played back or executed, and its
  unmappable raw values would not persist (P-131) -
  the candidate report in this envelope names them.
"""

from __future__ import annotations

from pathlib import Path

from runmal.scenarios.binding import (
    ScenarioBindingStore,
    bindings_path,
    plan_materialisation,
)
from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.store import ScenarioStoreError

_NOTE_PURE_READ = (
    "this preview is a pure read: previewing has "
    "replaced, bound, written and seeded nothing; the "
    "PUT replace road remains the only replacer and "
    "the POST bind road remains the only binder"
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
_NOTE_AS_IF_STORED = (
    "would_bind and the key splits judge the candidate "
    "as if it were stored at the next revision and then "
    "bound to this chat; binding today would bind the "
    "current revision named above, whose own chat "
    "verdict stays on the P-138 bind-plan road"
)
_NOTE_CHAT_AS_IT_STANDS = (
    "the blockers are bind's refusal facts read from "
    "the chat as it stands; bind re-decides every one "
    "of them when it runs, and a replace landing first "
    "changes the stored body bind would pin"
)
_NOTE_PRESENCE_LAW = (
    "already-present keys are judged by the P-093 "
    "store's own presence law under the scenario "
    "writer; the splits name seedable keys, not landed "
    "keys - the binding record is the only account of "
    "what actually landed"
)
_NOTE_TRUTH_AS_DATA = (
    "the candidate was parsed and planned as data "
    "only: previewing it evaluated no condition, played "
    "nothing back and executed nothing it carries; a "
    "candidate's unmappable raw values are not part of "
    "the native shape and would not persist - the "
    "candidate import report named here records every "
    "one of them"
)

_REASON_ALREADY_PRESENT = (
    "already present; seeding never overwrites live state"
)


def _plan_counts(plan: dict) -> dict:
    """P-136's count law, read from the plan itself."""
    return {
        "messages": len(plan["messages"]),
        "flags": len(plan["flags"]),
        "variables": len(plan["variables"]),
        "skipped": len(plan["skipped"]),
    }


def _parse_candidate(body):
    """The store door, exactly as ScenarioStore.replace
    applies it (store.py's _parse_body law, as P-146
    states it): a non-object body raises
    ScenarioStoreError; anything else is judged by
    P-026's parser alone, raising ScenarioParseError on
    refusal."""
    if not isinstance(body, dict):
        raise ScenarioStoreError(
            "scenario definition must be a JSON object")
    return parse_scenario_file(body)


def _split_keys(plan: dict, user_id: str, chat_id: str,
                variables_base_dir) -> dict:
    """One plan's seedable keys split by P-093's own
    presence law - chatpreview's exact calls, in plan
    order (flags, then variables)."""
    from runmal.plugins.variables import get_entry, resolve_key

    would_seed: list[str] = []
    already_present: list[dict] = []
    for where, mapping in (
        ("initial_flags", plan["flags"]),
        ("initial_variables", plan["variables"]),
    ):
        for key in mapping:
            full_key, _, _ = resolve_key(
                key, "scenario", "runmal.scenario")
            entry = get_entry(
                user_id, chat_id, full_key,
                writer_kind="scenario",
                writer_id="runmal.scenario",
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
        "would_seed": would_seed,
        "already_present": already_present,
    }


async def preview_candidate_for_chat(
    session,
    record,
    user_id: str,
    chat_id: str,
    body,
    *,
    bindings: ScenarioBindingStore | None = None,
    variables_base_dir: Path | None = None,
) -> dict | None:
    """The chat-scoped candidate envelope, or None.

    ``record`` is a ScenarioDefinition (the router has
    already decided the definition's existence and
    ownership). None means the chat is unknown or
    foreign - the two answer exactly alike, so existence
    never leaks - and is decided BEFORE the candidate
    body is judged, so a foreign chat with a malformed
    candidate still answers None (the P-131 existence-
    before-body law, on both sides). On an owned chat a
    refused candidate raises the store door's own typed
    refusal (ScenarioParseError, or ScenarioStoreError
    for a non-object body) before any envelope exists.
    Pure read: nothing is written anywhere.
    """
    from sqlalchemy import select

    from runmal.chats import service as chat_service
    from runmal.db.models import Chat

    bindings = bindings or ScenarioBindingStore(bindings_path())

    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        return None

    parsed = _parse_candidate(body)
    candidate_definition = export_native(parsed)
    candidate_report = (
        parsed.report.to_dict() if parsed.report else {})
    candidate_plan = plan_materialisation(candidate_definition)
    current_plan = plan_materialisation(record.definition)
    candidate_counts = _plan_counts(candidate_plan)

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

    keys = _split_keys(
        candidate_plan, user_id, chat_id, variables_base_dir)
    current_keys = _split_keys(
        current_plan, user_id, chat_id, variables_base_dir)
    cand_seed = set(keys["would_seed"])
    cur_seed = set(current_keys["would_seed"])
    cand_present = {row["full_key"] for row in keys["already_present"]}
    cur_present = {
        row["full_key"] for row in current_keys["already_present"]}

    candidate_roles = candidate_definition.get("roles")
    candidate_bootstrap = candidate_definition.get(
        "bootstrap_messages")
    candidate_unmappable = candidate_report.get("unmappable") or []

    return {
        "definition_id": record.id,
        "definition_name": record.name,
        "definition_revision": record.revision,
        "source_format": record.source_format,
        "next_revision": record.revision + 1,
        "chat_id": chat_id,
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
        "current": {
            "plan_counts": _plan_counts(current_plan),
        },
        "counts": candidate_counts,
        "blockers": blockers,
        "would_bind": not blockers,
        "keys": keys,
        "current_keys": current_keys,
        "key_deltas": {
            "would_seed_added": sorted(cand_seed - cur_seed),
            "would_seed_removed": sorted(cur_seed - cand_seed),
            "already_present_added": sorted(
                cand_present - cur_present),
            "already_present_removed": sorted(
                cur_present - cand_present),
        },
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_STORE_DOOR,
            _NOTE_AS_IF_STORED,
            _NOTE_CHAT_AS_IT_STANDS,
            _NOTE_PRESENCE_LAW,
            _NOTE_TRUTH_AS_DATA,
        ],
    }


__all__ = ["preview_candidate_for_chat"]
