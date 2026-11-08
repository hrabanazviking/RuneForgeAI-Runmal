# P-132 - Scenario-to-Chat Binding (Part IX, second slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 opener precedents. The derivation rests on
Runmal's own in-tree record only (full weighing in the
team's scout record): P-131's slice doc names this exact
seam - "Instantiation / seeding - declined, named seam.
The P-093 seed_variables contract is the named next
slice's seam" - and P-093's module was written for it:
"Part IX scenarios consume the same store", with a
``seed_variables`` whose writer kind is ``scenario`` and
whose docstring reads "Seed MISSING keys only (the Part
IX contract): a scenario's initial_variables land in the
shared store without ever overwriting live state."

Base: be86774 (P-130 banking record; Part VIII COMPLETE).
P-131 banks first; this slice's worktree carries P-131's
store.py byte-identical and its router / __init__ as the
ground the binding roads append to, so the slice stands
on its real base (the keeper reconciles at banking).
Migration: NONE - head stays 0041. No chats.scenario_id
column is taken; the binding lives in the house JSON
pattern, as P-131's definitions do.

## The weighing

- **Scenario-to-chat binding - taken.** The first
  consumption of P-131's stored truth, and the seam
  P-131 + P-093 both name. Every leg stands on existing
  machinery: bootstrap placement on the P-079 greeting
  precedent (placed author text, P-075 provenance),
  state seeding on the P-093 contract written for
  Part IX, binding storage on the house JSON pattern.
- **Versioning / import-export parity for stored
  definitions - declined for this slice.** Half already
  landed inside P-131 (revision discipline; import-to-
  store IS the POST /scenarios road). The missing leg -
  store-to-file export by id - polishes the truth
  layer's edge while the layer still does nothing; it
  is the natural next candidate.
- **Scenario library organisation - declined for this
  slice.** The P-073 SQL pattern does not transfer to a
  JSON-document store, and organisation follows
  consumption in every prior part's order.
- **Playback / runtime / condition evaluation -
  declined.** No runtime machinery exists in tree;
  contexts stay data.
- **Executing stored scripting - declined absolutely.**
  P-027 law: unmappable scripting is recorded, never
  executed. A stored definition does not even carry
  scripting values; its P-131 report names them.

## What landed

- `src/runmal/scenarios/binding.py` (new) - the binding
  truth layer + service. `ScenarioBinding` (frozen
  dataclass: id, owner_id, chat_id, definition_id,
  definition_name, definition_revision PINNED at bind
  time, bound_at, cast as data, seeded_messages,
  seeded_keys, skipped - every list read back from what
  actually landed). `ScenarioBindingStore`: the
  versioned JSON document `scenario_bindings.json`
  (house pattern, tolerant load), owner-scoped verbs
  add / get_for_chat / list_for_owner /
  list_for_definition / remove_for_chat.
  `plan_materialisation(definition)` (pure): bootstrap
  entries map kind -> chat role (user -> user,
  instructions -> system, the other natively-mapped
  kinds -> assistant); speaker names resolve against
  the declared cast (a role name speaks under its
  character_name when declared; an unmatched author
  label rides verbatim; no label -> narrator_name for
  placed lines, impersonation_name for user lines);
  speaker_id is ALWAYS None - a scenario role is not a
  character row and no id is fabricated. Blank or
  non-string bootstrap text seeds nothing and is
  recorded skipped; initial flags / variables are
  judged seedable by the P-093 store's OWN law (its
  resolve_key and value rules are called, never
  re-implemented): flags hold bool only, variables hold
  typed scalars, anything else is skipped with a reason,
  never coerced.
  `bind_scenario(session, ...)`: every refusal is
  decided before any write - unknown / foreign
  definition or chat -> BindingNotFoundError (existence
  never leaks); group room, already-bound chat,
  non-empty chat -> BindingConflictError (the P-079
  law: an opening setup cannot honestly land
  mid-conversation). On success: flags then variables
  seed through P-093 `seed_variables` with the scenario
  writer (keys the store reports as not landed are
  recorded "already present" - seeding never overwrites
  live state); bootstrap lines land in order through
  the chat service's append road, each with event data
  carrying metadata only and a P-075 provenance record
  (origin manual, origin facts naming source
  scenario_bootstrap + definition id + pinned revision
  + bootstrap index + kind; model and lore sections
  not_applicable; the preset section is the chat's
  applied-preset snapshot, the greeting record's
  precedent); the binding record is written last, from
  what landed. `unbind` removes only the record.
- `src/runmal/scenarios/router.py` (additive, on the
  P-131 router) - POST /scenarios/{definition_id}/bind
  (201 record; 404 unknown/foreign definition or chat;
  409 group / bound / non-empty; 422 a body without a
  string chat_id), GET /scenarios/bindings/{chat_id},
  DELETE /scenarios/bindings/{chat_id} (answers
  seeded_content_kept: true - unbinding never reaches
  back into the chat's history or state).
- `src/runmal/scenarios/__init__.py` (additive) - the
  binding names exported in the P-131 style.
- `pyproject.toml` - one per-file-ignores line
  (scenarios/router.py joins every other router's B008
  ignore; the bind road is the first in this router to
  take a session dependency).
- `tests/test_p132_scenario_binding.py` - the battery
  (18 tests): plan pins, store pins, service pins
  (exact author texts in order, role map, speakers,
  provenance per message, P-093 seeding with the
  scenario writer + already-present honesty, revision
  pinning across a later replace, refusals and
  conflicts writing nothing, unbind keeping seeded
  content), HTTP pins, migration head pinned at 0041.

## Honest bounds

- Seeded messages ride the append road's own position
  law: a chat built purely from appends is legacy-
  ordered (positions NULL, display order by created_at)
  exactly like any appended chat; no second ordering
  law is invented over it.
- Seeded key ORDER within one mapping is the stored
  definition's own key order; P-131's store writes
  sort_keys, so a reloaded definition seeds in sorted
  order. The record reports what landed, in land order.
- Cast flags (enabled_on_start, can_speak) are recorded
  as data, not treated as a casting engine: a role
  speaks in the opening only where the author wrote it
  a bootstrap line.
- template_text / system_prompt_text are NOT installed
  as chat configuration by binding; the definition
  stays the truth for those fields. Contexts and
  conditions are not evaluated. There is no playback
  in this slice, and none is claimed.
