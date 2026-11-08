# P-137 - Scenario Definition Duplication (Part IX, seventh slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 / P-134 / P-135 / P-136
precedents. The derivation rests on Runmal's own in-tree
record only (full weighing in the team's scout record).

Base: 5a210f6 (P-135 banking record; P-001..P-135
banked). P-136 (Binding Plan Preview) banks ahead of
this slice from the older base 589065a; this delta is
additive against it (one additive store verb, one
additive router road, additive __init__ map line).
Migration: NONE - head stays 0041. No storage shape
changes: the clone is an ordinary row in the existing
versioned scenarios.json document.

## The weighing

- **Definition duplication / clone - taken.** P-136
  weighed this candidate and declined it on one stated
  ground: "a clone verb must invent a naming law and
  organisation / binding carry decisions with no record
  guidance". Re-weighed against the whole tree, the
  naming ground does not hold: the characters domain
  carries the verb (duplicate_character, S303) with an
  in-tree naming law — the clone is named the source's
  name + " (copy)" — and P-131's own law already
  allows duplicate names as distinct citizens, so no
  naming law needs inventing either way; the S303 law
  is taken. The measured gap is real: the store had
  no copy verb and the router no duplicate road, and
  the composed road that exists — P-133 export
  (native) -> P-131 create — reproduces the definition
  exactly but provably NOT the record. Create
  re-parses, so the copy's report is a fresh native
  report: for a Voxta-origin definition the original
  report names every unmappable element and the
  copy's names none (P-133's one-way naming law,
  battery-pinned there and re-pinned here as a
  contrast). A faithful copy of definition + report +
  source_format was impossible with the roads that
  existed. The carry decisions are judged in the
  open, not invented silently (see Honest bounds):
  bindings belong to chats (P-132) and are not
  carried; organisation is the owner's filing of the
  source entry in its own independent store (P-134)
  and is not carried.
- **Chat-scoped bind preview - declined for this
  slice.** P-136's four standing notes bound its
  definition-side plan (bind-time refusals unjudged,
  already-held keys unknowable). Those are bounds,
  not a named seam: P-136 states refusals are decided
  by bind against a specific chat — bind's own code
  is the one judge. A second judge would re-implement
  the refusal law (against the house rule that a
  domain's law is called, never re-implemented) or
  refactor the writing service while P-136 banks
  ahead of this slice. Named as a future candidate
  if a record ever names it.
- **Definition history retention - declined.** P-131
  already landed the revision discipline that
  transfers; no in-tree record names a consumer, and
  retention would be a storage-shape change (fifth
  declination, evidence unchanged).
- **Organisation orphan cleanup / cross-store cascade
  (incl. orphan-binding cleanup) - declined.** P-134
  claims no cleanup road and names orphan rows the
  honest cost of independent stores; P-135 names
  binding staleness instead of deleting anything, and
  a stale binding already has a removal road (P-132
  unbind, per chat). No record asks for deletion
  semantics across stores.
- **Collections / folders - declined.** P-134's honest
  bound ("No collections or folders"); no named need.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** Banked P-026
  behaviour pinned by its own battery (INV-009 raw
  overlay); changing the overlay law is a P-026
  slice's call. This slice neither rewrites nor
  inherits it: duplication copies the STORED record,
  which holds no raw overlay at all.
- **Portable-archive inclusion of the scenario stores
  - declined for this slice.** The archive is a
  SQL-row bundle; the scenario stores are data-dir
  JSON documents by P-131 design - a portable-
  subsystem slice, named open for that line (the
  Part VIII precedent), not a Part IX foundation.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  Duplication copies data; it runs nothing.

## What landed

- `src/runmal/scenarios/store.py` (additive) -
  `ScenarioStore.duplicate(definition_id, owner_id)`:
  one new verb beside create / replace / remove.
  Unknown or foreign answers None before anything is
  copied or written (the P-131 no-leak discipline).
  The clone is a new citizen: fresh uuid, the source's
  owner, revision 1 with one birth stamp (created_at
  == updated_at), its name under the characters S303
  law — the source's name + " (copy)", written on the
  record and on the definition's own name field alike
  so the P-131 invariant (record name == the stored
  definition's name) holds for clones too. The
  definition and the P-131 import report are
  deep-copied exactly — the report holds no name
  value, so the rename falsifies nothing in it — and
  source_format is preserved. Duplicating a copy
  appends " (copy)" again (the S303 law applied to
  the source's own name; battery-pinned, never
  trimmed by an invented rule). The clone is appended
  in store order through the store's own save; the
  source row is untouched.
- `src/runmal/scenarios/router.py` (additive) - one
  road: POST /scenarios/{definition_id}/duplicate
  answering 201 with the clone's full record (the
  create road's shape); unknown or foreign answers
  404 ("scenario definition not found"), decided by
  the store verb before any copy. No body, no query
  parameters. The P-026, P-131, P-132, P-133, P-134
  and P-135 roads are untouched beside it.
- `src/runmal/scenarios/__init__.py` (additive) - one
  subsystem-map line on the store bullet.
- `tests/test_p137_definition_duplication.py` - the
  battery (12 tests; see Evidence).

## Honest bounds

- The clone carries NO organisation: it has no row
  in the P-134 document and reads with the computed
  unorganised default (no tags, not favourite); the
  organisation document is byte-untouched by
  duplicating (battery-pinned). Tags and favourite
  are the owner's filing of the source entry; the
  owner files the copy as they choose.
- The clone carries NO bindings and binds nothing:
  a binding belongs to a chat (P-132), and the
  source's chats stay bound to the source, pinned to
  the source's revision. No bindings document is
  created by duplicating (battery-pinned).
- The clone is independent from birth: a later
  replace on either record leaves the other
  byte-untouched (battery-pinned both ways).
- Revision 1 is deliberate: the source's replace
  history belongs to the source record; the clone's
  own history starts fresh, exactly as a created
  definition's does.
- There is no playback in this slice, and none is
  claimed.
