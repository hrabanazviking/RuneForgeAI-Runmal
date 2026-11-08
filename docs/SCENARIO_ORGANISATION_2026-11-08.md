# P-134 - Scenario Library Organisation (Part IX, fourth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 precedents. The derivation
rests on Runmal's own in-tree record only.

Base: d11ee6b (P-132 banking record; P-001..P-132
banked). P-133 (store-to-file export parity) banks ahead
of this slice; this delta is additive against it (new
module, additive router roads, additive __init__
exports). Migration: NONE - head stays 0041.

## The weighing

- **Scenario library organisation - taken.** Named and
  deferred three times in the record's own order:
  P-131 declined it ("No tags, favourites or search
  yet; the list road is the whole read surface"),
  P-132 declined it behind consumption ("organisation
  follows consumption"), and P-133's scout declined it
  behind export parity alone. Consumption (P-132) and
  export parity (P-133) have landed or bank ahead of
  this slice, so the deferral grounds are spent. The
  measured gap: beyond single-read, the P-131 list road
  was the whole read surface - no way to tag, favourite,
  search or sort a growing library of definitions.
- **Import-from-file parity (the reverse leg) -
  declined.** Already landed: import-to-store IS the
  POST /scenarios road (P-131, named in P-132's doc).
  The only values without a home - a Voxta file's
  unmappable raw values - are excluded by P-131's
  recorded storage bound, not by a missing road.
- **Binding lifecycle depth (HTTP list roads over the
  binding store's existing list verbs) - declined for
  this slice.** The store verbs exist and are pinned by
  P-132's battery; no in-tree record names the missing
  HTTP surface. Named as a future candidate.
- **Definition history retention - declined.** P-131
  already landed revision discipline (P-133 scout's
  reasoning, unchanged); no named consumer.
- **Playback / runtime / scripting execution -
  declined ABSOLUTELY.** P-027 law: content is data,
  never code. Nothing in this slice evaluates or runs
  anything a definition carries.

## What landed

- `src/runmal/scenarios/organisation.py` (new) - the
  organisation truth layer. `ScenarioOrganisation`
  (frozen dataclass: definition_id, owner_id, tags as
  display forms, is_favourite, updated_at) and
  `ScenarioOrganisationStore`: the versioned JSON
  document `scenario_organisation.json` beside P-131's
  `scenarios.json` (house pattern, tolerant load - a
  corrupt document reads empty, a malformed row reads
  as absent). Verbs set_tags / add_tags / remove_tag /
  set_favourite, all owner-scoped. The tag law is
  P-024's own, IMPORTED from runmal.library.organise
  (normalise_tag / normalise_tags: display form +
  casefold key, first display wins, 64-char / 50-tag
  bounds) - no second normalisation law. Pure services:
  `organisation_view` (the unorganised default is
  computed, never persisted), `enrich_summary` (a P-131
  summary plus tags + is_favourite), `query_definitions`
  (q search over name + description + scenario_text,
  tag any/all, favourites_only, sorts oldest / newest /
  name / name_desc / favourites_first, limit/offset
  applied after filtering with the filtered total
  reported before paging; every invalid parameter
  raises before any filtering) and `list_tags` (the
  owner's census over existing definitions only).
- `src/runmal/scenarios/router.py` (additive) -
  GET /scenarios/library/tags (declared before the
  {definition_id} roads so "library" is never read as
  an id); GET /scenarios gains the query surface (q,
  repeatable tag, tag_mode, favourites_only, sort,
  limit, offset) with the no-parameter answer exactly
  the P-131 answer; per-definition roads GET
  .../organisation, PUT + POST .../tags, DELETE
  .../tags/{tag}, PUT .../favourite. Existence is
  decided before any body verdict (a foreign id with
  invalid tags answers 404, never 422); invalid tags,
  sort, tag_mode, limit or offset on an owned id
  answer 422.
- `src/runmal/scenarios/__init__.py` (additive) - the
  organisation names exported in the house style.
- `tests/test_p134_scenario_organisation.py` - the
  battery (12 tests; see Evidence).

## Honest bounds

- Organisation lives in its OWN document: the P-131
  definitions document is byte-untouched by organising
  (a battery test pins it), and the stored definition
  stays exactly the P-026 native shape, so P-133's
  native-identity law is preserved.
- Deleting a definition does not cascade into the
  organisation document. Orphan rows are filtered at
  every read - they never surface in lists, queries or
  the tag census - and are the honest cost of keeping
  the two stores independent; no cleanup road is
  claimed in this slice.
- Search covers name, description and scenario_text
  only - not roles, contexts or bootstrap text. No
  collections or folders. No UI.

## In-slice finding (fixed, pinned)

The first battery run caught the repeatable `tag`
query parameter silently unbound: declared as a plain
`list[str] | None = None` parameter, FastAPI did not
bind it as a query list, so tag filtering answered the
unfiltered library. It is now declared with
`Query(default=None)`, the P-024 router's own pattern,
and the HTTP list test pins the filtered answer.
