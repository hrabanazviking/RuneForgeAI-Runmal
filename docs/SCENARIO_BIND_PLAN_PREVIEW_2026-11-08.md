# P-136 - Binding Plan Preview (Part IX, sixth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 / P-134 / P-135 precedents.
The derivation rests on Runmal's own in-tree record only
(full weighing in the team's scout record).

Base: 589065a (P-134 banking record; P-001..P-134
banked). P-135 (Binding Lifecycle Read Surface) banks
ahead of this slice from the same base; this delta is
additive against it (new service module, one additive
router road, additive __init__ exports). Migration:
NONE - head stays 0041. No storage shape changes: the
preview reads a P-131 record and stores nothing.

## The weighing

- **Binding plan preview - taken.** Binding is the one
  consequential, writing act in Part IX: it appends
  messages and seeds variables into a chat, and
  unbinding never takes that content back. Yet P-132's
  plan_materialisation - pure, exported, battery-
  pinned - was reachable only through the bind road
  itself: an owner could not see what a definition
  WOULD plant, and what it would honestly skip, without
  committing a real empty chat to it. The interpreted
  opening (the kind -> role map, cast-resolved speaker
  names, P-093 seedability verdicts) exists nowhere
  else; the stored definition reads back only its raw
  declared material. The house already honours
  inspect-before-commit (the lorebook activation
  preview / inspector, the prompt compose preview), and
  the immediately preceding slice took the same shape
  for the binding store's list verbs (P-135). Every leg
  stands on P-132's own pure function: no second
  planning law is invented.
- **Definition duplication / clone - declined.**
  Sibling domains have it (characters'
  duplicate_character; P-025 duplicate handling), and
  a true clone would preserve the P-131 report exactly
  where the composed P-133 export -> P-131 create road
  provably cannot (the naming is one-way, P-133). But
  no Part IX record names duplication as wanted, a
  clone verb must invent a naming law and organisation
  / binding carry decisions with no record guidance,
  and the composed road exists today. Named as a
  future candidate.
- **Definition history retention - declined.** P-131
  already landed the revision discipline that
  transfers; no in-tree record names a consumer, and
  retention would be a storage-shape change (fourth
  declination, evidence unchanged).
- **Organisation orphan cleanup / cross-store cascade
  - declined.** P-134 claims no cleanup road and names
  orphan rows the honest cost of independent stores;
  P-135 names binding staleness instead of deleting
  anything. No record asks for deletion semantics
  across stores.
- **Collections / folders - declined.** P-134's honest
  bound ("No collections or folders"); no named need.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** Banked P-026
  behaviour pinned by its own battery (INV-009 raw
  overlay); changing the overlay law is a P-026
  slice's call. This slice neither rewrites nor
  inherits it: the plan is computed from the stored
  definition by P-132's own pure function, exactly as
  bind computes it.
- **Portable-archive inclusion of the scenario stores
  - declined for this slice.** The archive is a
  SQL-row bundle; the scenario stores are data-dir
  JSON documents by P-131 design - a portable-
  subsystem slice, named open for that line (the
  Part VIII precedent), not a Part IX foundation.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  The preview evaluates no condition and runs nothing.

## What landed

- `src/runmal/scenarios/bindpreview.py` (new) - the
  preview service. `preview_bind_plan(record)` returns
  the envelope: definition_id, definition_name,
  definition_revision (the record's CURRENT revision),
  source_format, the plan (P-132's
  `plan_materialisation` over the stored definition,
  verbatim: bootstrap messages with kind -> chat role,
  cast-resolved speaker names and author text; seedable
  flags and variables; every skipped entry with its
  reason), counts read from the plan itself so they
  cannot drift, and the four standing honesty notes in
  fixed order. Pure: no I/O, no store access, refuses
  nothing - existence and ownership are the router's
  decision first (the storedexport.py precedent).
- `src/runmal/scenarios/router.py` (additive) - one
  road: GET /scenarios/{definition_id}/bind-plan
  answering the envelope. The record is fetched
  owner-scoped; unknown or foreign answers 404
  ("scenario definition not found") - the P-131
  no-leak discipline, identical to the P-133 export
  road. No body, no query parameters, no writes.
- `src/runmal/scenarios/__init__.py` (additive) - the
  preview_bind_plan name exported in the house style,
  plus one subsystem-map line.
- `tests/test_p136_bind_plan_preview.py` - the battery
  (11 tests; see Evidence).

## Honest bounds

- The plan is definition-side only. It is what bind
  computes from the definition alone, before any chat
  is consulted; previewing writes nothing, binds
  nothing and bumps no revision (battery-pinned: the
  definitions document is byte-untouched and no
  bindings document is created by previewing).
- Bind-time refusals are not judged here: unknown or
  foreign chat, group room, already bound and
  non-empty chat are decided by bind against a
  specific chat, and the preview names no chat at all.
- The plan names SEEDABLE keys, not landed keys: keys
  a specific chat already holds seed nothing at bind
  time (P-093 missing-keys-only), and that skip is
  knowable only at bind time. The binding record
  remains the only account of what actually landed.
- The plan is computed from the definition's CURRENT
  revision, which the envelope names; after a replace
  the preview plans the new body at the new revision
  (battery-pinned). Bind pins whatever revision is
  current when it runs.
- There is no playback in this slice, and none is
  claimed.
