# P-135 - Binding Lifecycle Read Surface (Part IX, fifth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 / P-134 precedents. The
derivation rests on Runmal's own in-tree record only.

Base: 589065a (P-134 banking record; P-001..P-134
banked). Migration: NONE - head stays 0041. No storage
shape changes: the slice reads the P-132 binding store
and stores nothing.

## The weighing

- **Binding lifecycle read surface - taken.** P-132's
  binding store landed owner-scoped list verbs
  (list_for_owner / list_for_definition), battery-pinned
  from the first day, yet no HTTP road ever exposed
  them: bindings could be read only one chat at a time.
  An owner could not enumerate their own bindings, nor
  ask which chats a definition has seeded. P-134 weighed
  exactly this item ("Binding lifecycle depth (HTTP list
  roads over the binding store's existing list verbs)")
  and named it a future candidate, while honestly
  recording the counterweight that no record names a
  missing consumer. The gap is nevertheless real and
  measurable - every other Part IX store pairs its verbs
  with HTTP reads - and the surface is pure read over
  pinned verbs, so it is taken, bounded by that
  counterweight: summaries only, no invented filters,
  sorts or paging. One scout finding sharpens the
  slice: deleting a definition does not cascade into
  the binding store (P-132 has no cascade; the DELETE
  road removes only the definition), so a binding can
  outlive its definition - a list that could not say so
  would mislead, so every summary names it.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** P-133 records F1
  as banked P-026 behaviour pinned by its own battery:
  "changing the overlay law is a P-026 slice's call".
  It is a Part II interop-hardening slice, not a Part
  IX foundation; this slice neither rewrites nor
  inherits it.
- **Definition history retention - declined.** P-131
  already landed the revision discipline that
  transfers; no in-tree record names a consumer, and
  retention would be a storage-shape change.
- **Organisation orphan cleanup / cross-store cascade
  - declined.** P-134 states orphan rows are the honest
  cost of independent stores and claims no cleanup
  road; no record asks for deletion semantics across
  stores. This slice names binding staleness in its
  summaries instead of deleting anything.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  Nothing in this slice evaluates or runs anything.

## What landed

- `src/runmal/scenarios/binding.py` - `ScenarioBinding.
  summary()`: the list shape (id, chat_id, definition
  id / name / pinned revision, bound_at, and cast /
  seeded-message / seeded-key / skipped counts read
  from the record itself so they cannot drift - the
  P-131 summary precedent). Two pure services,
  `list_bindings` and `list_bindings_for_definition`,
  wrap the store's pinned list verbs in store (bind)
  order and enrich each summary with `definition_exists`
  judged against the caller's live definition ids.
- `src/runmal/scenarios/router.py` (additive) - two
  roads. GET /scenarios/bindings answers
  {"bindings", "total"} and is declared BEFORE the
  {definition_id} roads so the literal "bindings" is
  never read as a definition id (the P-134 library/tags
  precedent; battery-pinned). GET /scenarios/
  {definition_id}/bindings answers {"definition_id",
  "bindings", "total"}; existence is decided first
  (unknown or foreign answers 404 - the P-131 no-leak
  discipline) and an owned definition with no bindings
  answers 200 with an empty list. The P-026, P-131,
  P-132, P-133 and P-134 roads are untouched beside them.
- `src/runmal/scenarios/__init__.py` (additive) - the
  two service names exported in the house style, plus
  one subsystem-map line.
- `tests/test_p135_binding_read_surface.py` - the
  battery (16 tests; see Evidence).

## Honest bounds

- Summaries are counts, not content: seeded message
  texts, cast bodies and skipped reasons stay on the
  P-132 single-read road, which answers the full record
  exactly as before (battery-pinned).
- A binding whose definition was deleted remains
  listed until it is unbound - the record is the chat's
  truth - with definition_exists: false. No cascade and
  no cleanup road is claimed.
- No filters, sorts or paging: no record names a
  consumer needing them, and none is invented.
- The reads write nothing: the binding document is
  byte-untouched by listing (battery-pinned).
- There is no playback in this slice, and none is
  claimed.
