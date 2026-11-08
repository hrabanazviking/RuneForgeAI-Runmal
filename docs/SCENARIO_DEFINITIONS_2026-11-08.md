# P-131 - Scenario Definitions: the Scenario Truth Layer (Part IX opener)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 opener precedents.
The derivation rests on Runmal's own in-tree record only:
P-026's scenario file interop, whose router said in its own
docstring that "scenarios are not stored until Part IX";
the P-117 versioned-JSON house store pattern; and the
P-027 law that content is data, never code.

Base: be86774 (P-130 banking record; Part VIII COMPLETE).
Migration: NONE - head stays 0041. NOTE on provenance:
hidden_files/P131_DESIGN.md names a scout at
hidden_files/P131_SCOUT.md; that file does not exist in
this worktree (verified by the keeper and again by the
finisher lead). The DESIGN governs; no scout content is
claimed anywhere in this slice's record.

## The weighing

- **Stored scenario definitions - taken.** The one
  foundation Part IX honestly needs first. P-026 made
  scenario FILES parse, report and re-export -
  statelessly. Nothing could be kept, listed, owned or
  revised. This slice makes scenarios stored citizens.
- **Instantiation / seeding - declined, named seam.**
  Creating a definition starts nothing: no chat is
  seeded, no bootstrap message is posted, no variable is
  written. The P-093 seed_variables contract is the named
  next slice's seam.
- **Playback / scene graph / branching runtime -
  declined.** Contexts and conditions are carried as
  data, never evaluated. No runtime exists in this slice.
- **Library organisation over definitions - declined.**
  No tags, favourites or search yet; the list road is the
  whole read surface beyond single-read.
- **A second validation law - declined.** The store door
  IS P-026's parser. Nothing is stored that P-026 would
  refuse, and no parallel rules are invented.

## What landed

- `src/runmal/scenarios/store.py` (new) - the truth
  layer. `ScenarioDefinition` (frozen dataclass: id,
  owner_id, name, definition, source_format, report,
  revision, created_at, updated_at); `to_dict()` is the
  full record and `summary()` the list shape, its counts
  read from the definition itself so they cannot drift.
  `ScenarioStore` is the versioned JSON document
  `scenarios.json` (house pattern, `definitions_path()`
  under RUNMAL_DATA_DIR): tolerant load, owner-scoped
  verbs create / get / list_for_owner / replace / remove.
  Create parses the body through P-026 and persists the
  NATIVE export; the parser's import report rides with
  the record as data on both the Voxta and native roads.
  Replace checks existence BEFORE parsing (a foreign id
  with a malformed body still answers None), parses
  before writing (a refused body leaves the stored row
  byte-untouched), and bumps revision with a fresh
  updated_at. Duplicate names are allowed as distinct
  citizens - no silent merge, no refusal.
- `src/runmal/scenarios/router.py` - five CRUD roads
  appended on the existing /scenarios prefix (POST 201 /
  GET list / GET one / PUT / DELETE), owner-scoped via
  get_owner_id; unknown and foreign alike answer 404;
  parse and store refusals answer 422. The P-026
  import/export roads are byte-untouched; the module
  docstring gains the P-131 paragraph and drops the
  now-false "not stored" claim.
- `src/runmal/scenarios/__init__.py` - exports for the
  new symbols plus one subsystem-map line.
- `tests/test_p131_scenario_definitions.py` - the
  battery (29 tests; see Evidence).

## Honest limitations

- Stored definitions are the NATIVE truth. A Voxta
  file's unmappable raw values (carried in
  `unmappable_values` on the parse) are not part of the
  native shape and do not persist; the record's report
  names every one of them, and the stateless P-026
  import/export roads remain the lossless hand-back road
  for raw files. Nothing is silently dropped - the loss
  is named here and in the record's own report.
- No instantiation, no playback, no library
  organisation (see The weighing).

## Finisher finding (fixed in-slice)

The landed `_load` converted each stored row through
`from_dict`, whose `int()` parse of `revision` raised on
a hand-damaged row (revision "abc" or null), bricking
every store verb - against the design's tolerant-load
law ("the road never bricks"). `_load` now skips a
malformed row (it reads as absent) and keeps the rows
beside it. Two battery tests pin it: a malformed row
never bricks the store, and a good row survives a bad
neighbour.
