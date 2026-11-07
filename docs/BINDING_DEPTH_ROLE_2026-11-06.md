# Binding depth/role (commissioned, post-P-048 gate) — 2026-11-06

Commissioned line: *the immediate slice after the P-048 Part III
gate, closing gate finding F2 — embedded character-book entries
carry P-038 placement (position / depth / role) whole through
materialisation.*

## The defect

P-039's `lorebooks/binding.py` normalised an embedded
character-book entry's `position` but carried no `depth` and no
`role` at all: `normalise_book_entry` returned neither key, so
the raw companions on a card were silently discarded;
`materialise_character_book` therefore stored every materialised
entry at depth NULL / role `system` regardless of what the card
declared; and `serialise_bound_book` emitted neither field, so
even a correctly stored entry lost its placement when the bound
book travelled back out (export and character duplication both
ride this leg). P-047's evidence recorded the discovery and
P-048's gate commissioned this slice; the world-book legs
(service, transfer, interop) already carried placement whole —
only the character-book leg dropped it.

A second, quieter divergence rode along: binding's module-local
`_normalise_position` did not resolve numeric-string codes, so
`"4"` degraded to `before_char` where `lorebooks.placement`
(the single vocabulary owner since P-038) resolves it to
`at_depth`. Int/float codes and names agreed; only the string
form split.

## What was built

All in `src/runmal/lorebooks/binding.py`; no migration (the
`LoreEntry` depth/role columns are P-038's, migration 0030;
head stays 0032), no precedence change, no other normalise
behaviour touched.

- `normalise_book_entry` delegates placement to
  `lorebooks.placement`: `position` via `normalise_position`
  (the local re-implementation and its code tables are deleted),
  plus `"depth": normalise_depth(raw.get("depth"))` and
  `"role": normalise_role(raw.get("role"))`. The tolerant
  asymmetry is placement's own: a bad depth degrades to `None`
  (undeclared — never clamped, never an invented number) and a
  bad role degrades to `system` (role has no absence sentinel).
  Absent placement yields `before_char` / `None` / `system` —
  exactly the stored behaviour entries without placement have
  always had. Raw depth/role keys are the literal file keys
  `"depth"` / `"role"`, matching the world legs; no alias keys
  exist anywhere in the file legs.
- `materialise_character_book` passes `depth` / `role` from the
  normalised fields into the `LoreEntry` row it builds.
- `serialise_bound_book` copies `depth` / `role` from
  `entry_to_dict` (which already normalised them) into each
  serialised entry, beside `position`, under the native names.

Nothing else needed the new keys: `merge_entry_dicts` copies
entry dicts whole, `merged_preview` builds from ORM rows via
`entry_to_dict`, and character duplication rides
serialise -> materialise, so placement now flows through all of
them untouched.

## Battery

`tests/test_commissioned_binding_depth_role.py` (29 tests):
normalise carries names, world-info codes and numeric strings
whole (incl. depth 0 staying declared, and the `"4"` string
regression); bad depth -> `None` and bad role -> `system`
parametrised; absent -> defaults; the DB round-trip
(materialise -> stored `entry_to_dict` -> serialise ->
re-normalise is a fixed point, incl. a broken entry degrading
to `at_depth` / `None` / `system`); and the API round-trip
(create with embedded book -> bound lorebook read -> travelling
character-book read -> duplicate clone keeps placement).
Migration head pinned at 0032.

## Clean-room basis

Built from Rúnmál's own in-tree facts only: the P-038 placement
vocabulary and its tolerant normalisers, the P-039 binding legs,
and the P-047/P-048 recorded finding. No new external source
and no mirror reading. Full entry appended to
`docs/CLEAN_ROOM_LOG_2026-10-30.md`.
