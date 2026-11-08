"""Library-scoped pack import preview (P-143, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-143 slice doc.
What the derivation found missing, and what lands here:

- P-141's inspect_pack judges a scenario pack ALONE: it
  validates the envelope, the manifest and the checksum
  and reports provenance, but its own module states it
  "touches no store and writes nothing" — it cannot say
  what importing THIS pack would do in THIS caller's
  library.
- P-141's import_pack computes exactly the verdicts a
  holder needs first — duplicate_exact (an owned record
  with the same content checksum, imports unwritten),
  name_collision (an owned record with the manifest's
  name and different contents), and the
  on_conflict=reject refusal — but only INSIDE the
  importing act itself: under the default create_new
  mode, learning that a pack collides means a fresh
  record has already been created, and the duplicate
  verdict likewise arrives only as the import's own
  answer.

This module is the read service behind the preview road:
the read-only judgement of one pack against the caller's
own library BEFORE any import — would it create, is it
an exact duplicate (and of which record), would it
collide by name (and with which records), and would the
named on_conflict mode refuse it. It is the
P-136 -> P-138 progression transposed to the pack
surface P-141 landed after both: a pack-side preview
whose standing facts could not judge the library,
answered by a scoped preview that judges them AS DATA.

Every fact is read through the owning slice's own verbs,
never re-implemented: validation is P-141's inspect_pack
verbatim (its report rides in the envelope whole, so a
malformed pack raises PackError before any library fact
is read — one typed refusal at the boundary, exactly as
import), the library scan is import's own law read not
run (the owner's records only, identity by
packs.content_checksum over each record's stored
definition, collision by record name against the
manifest's definition name), and the duplicate /
collision summaries are P-131's summary() verbatim. The
outcome is the verdict import would reach FIRST, in
import's own decision order: duplicate scan first, then
collision plus the reject refusal, then create.

Honesty bounds, stated in every answer:

- the preview is a pure read: previewing has imported,
  written and created nothing, and import remains the
  only importer;
- the verdict judges the library as it stands: import
  re-decides every fact when it runs, and P-141's
  check-then-create is not transactional, so a library
  that changes first changes the outcome;
- identity is the definition payload only (P-141): a
  duplicate verdict is about what an import would
  store, never about ids, revisions or filing;
- no organisation row and no binding travels in a pack
  or would be created by importing one (P-141).

Truth-as-data throughout (P-027): previewing a pack
against a library plays nothing back and executes
nothing it carries. No migration (the head stays
0041), no storage-shape change, no new store, and no
change to packs.py or any P-141 answer.
"""

from __future__ import annotations

from runmal.scenarios.packs import (
    CONFLICT_MODES,
    CONFLICT_REJECT,
    PackError,
    content_checksum,
    inspect_pack,
)

_NOTE_PURE_READ = (
    "previewing has imported, written and created "
    "nothing: this is a read of the pack against the "
    "library as it stands, and import remains the "
    "only importer"
)
_NOTE_LIBRARY_AS_IT_STANDS = (
    "the verdict judges the library as it stands: "
    "import re-decides every fact when it runs, and "
    "the check-then-create is not transactional, so "
    "a library that changes first changes the outcome"
)
_NOTE_IDENTITY_PAYLOAD_ONLY = (
    "identity is the definition payload only: a "
    "duplicate verdict is about what an import would "
    "store, never about ids, revisions or filing"
)
_NOTE_NOTHING_ELSE_TRAVELS = (
    "no organisation row and no binding travels in a "
    "pack or would be created by importing one: filing "
    "is library-local and a binding is a chat attachment"
)

OUTCOME_DUPLICATE_EXACT = "duplicate_exact"
OUTCOME_WOULD_REFUSE = "would_refuse"
OUTCOME_WOULD_CREATE_WITH_NAME_COLLISION = (
    "would_create_with_name_collision"
)
OUTCOME_WOULD_CREATE = "would_create"


def preview_pack_import(store, owner_id: str, data, *,
                        on_conflict: str = "create_new") -> dict:
    """Judge one pack against the caller's own library.

    ``store`` is a ScenarioStore; ``data`` is a pack as
    bytes, str or dict, exactly as P-141's roads accept.
    The mode is validated first, with import's own
    refusal (import validates the mode before parsing;
    the preview mirrors that order), then the pack is
    judged through inspect_pack verbatim — a malformed
    pack raises PackError before any library fact is
    read. The library scan reads the owner's records
    only (another owner's identical definition never
    counts — the P-141 owner-scoping law). Pure read:
    the store document is byte-untouched.
    """
    if on_conflict not in CONFLICT_MODES:
        raise PackError(
            f"unknown on_conflict mode: {on_conflict!r} "
            f"(valid: {sorted(CONFLICT_MODES)})"
        )
    report = inspect_pack(data)
    checksum = report["content_sha256"]
    definition_name = report["definition_name"]
    owned = store.list_for_owner(owner_id)
    duplicate_of = None
    for record in owned:
        if content_checksum(record.definition) == checksum:
            duplicate_of = record
            break
    name_collisions = [
        record.summary()
        for record in owned
        if record.name == definition_name
        and (duplicate_of is None or record.id != duplicate_of.id)
    ]
    name_collision = bool(name_collisions)
    refusal_reason = None
    if duplicate_of is not None:
        outcome = OUTCOME_DUPLICATE_EXACT
    elif name_collision and on_conflict == CONFLICT_REJECT:
        outcome = OUTCOME_WOULD_REFUSE
        refusal_reason = (
            f"a scenario definition named "
            f"{definition_name!r} already exists "
            f"with different contents and on_conflict='reject'"
        )
    elif name_collision:
        outcome = OUTCOME_WOULD_CREATE_WITH_NAME_COLLISION
    else:
        outcome = OUTCOME_WOULD_CREATE
    envelope = dict(report)
    envelope.update(
        {
            "on_conflict": on_conflict,
            "library": {
                "definitions_total": len(owned),
                "duplicate_exact": duplicate_of is not None,
                "duplicate_of": (
                    duplicate_of.summary()
                    if duplicate_of is not None else None
                ),
                "name_collision": name_collision,
                "name_collisions": name_collisions,
            },
            "outcome": outcome,
            "would_create": outcome in (
                OUTCOME_WOULD_CREATE,
                OUTCOME_WOULD_CREATE_WITH_NAME_COLLISION,
            ),
            "would_refuse": outcome == OUTCOME_WOULD_REFUSE,
            "refusal_reason": refusal_reason,
            "notes": [
                _NOTE_PURE_READ,
                _NOTE_LIBRARY_AS_IT_STANDS,
                _NOTE_IDENTITY_PAYLOAD_ONLY,
                _NOTE_NOTHING_ELSE_TRAVELS,
            ],
        }
    )
    return envelope


__all__ = ["preview_pack_import"]
