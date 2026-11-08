# P-146 — Candidate Replace Preview (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md)
gives Part IX only its part-table line — "IX | Scenarios — the Visual
Novel Engine | P-131 – P-154" — and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated plainly as
derived everywhere, following the P-101 / P-117 / P-131..P-145
precedents. The derivation rests on Runmal's own in-tree record only
(full weighing in the team's scout record).

Base: 1499ca85 (P-144 banking record; P-001..P-144 banked). P-145
(library unmappable-content census, team-03) banks concurrently ahead
of this slice and is NOT in this base; this delta is disjoint from it by
design (new service module candidatepreview.py, new road POST
/scenarios/{definition_id}/replace-preview; the router.py,
scenarios/__init__.py and clean-room log edits are additive in disjoint
blocks), and the keeper reconciles the pure additive union at banking
(P-145 banks before P-146). Migration: NONE — head stays 0041. No
storage-shape changes: the preview parses a candidate body in memory
and reads the definition, binding and organisation stores; it stores
nothing.

## The weighing

- **Candidate replace preview — taken.** P-140's replace-impact preview
  judges the current world and states in its fifth standing note that it
  judges no candidate body, and that what a successful new body would
  plant is knowable only once it is stored, through bind-plan previews
  that compute from whatever revision is current when they run. That
  named half is this slice. A successful replace is permanent for the
  current body (P-140: the stored definition and its import report are
  overwritten, there is no un-replace and no definition history), so
  before the act an owner could not learn whether the store door would
  accept a given body at all, what native shape and import report it
  would persist, what it would plant, or how it differs from the body it
  would supersede — except by committing the replace. Every ingredient
  already exists as an owning slice's own verb: the store door's parser
  (P-131 parses before writing; the stored shape is export_native of the
  parse and the report rides with the record), P-132's pure
  plan_materialisation, P-136's plan-count law, P-131's summary count
  law, and P-140's impact envelope. This slice is the join, as a pure
  read, changing no replace semantics: the PUT road remains the only
  replacer.
- **A third census — declined, deliberately.** P-144 landed the global
  binding census and concurrent P-145 lands the library
  unmappable-content census (definition import reports). This slice is
  not a census and duplicates neither: P-145 judges stored records'
  reports library-wide; P-146 judges one unstored candidate body for
  one definition.
- **Chat-scoped candidate preview (a P-138 analogue) — declined for
  this slice.** P-138 judges a stored definition against one named
  chat. Composing candidate x chat would judge an unstored body against
  chat state with no in-tree record naming a consumer; the
  definition-side candidate plan landed here, plus P-138 against the
  new body after a real replace, covers the honest need in two named
  steps.
- **A store-level dry-run replace verb — declined.** It would duplicate
  the parse this preview already performs through the same parser, and
  previews live at the read surface (P-136 / P-138 / P-139 / P-140 /
  P-143 precedent), not as verbs on the store. The PUT road remains the
  only replacer and the store gains no new verb.
- **Definition history retention — declined.** Standing declination,
  evidence unchanged: P-131 already landed the revision discipline that
  transfers; no in-tree record names a consumer, and retention would be
  a storage-shape change. The candidate preview meets the underlying
  need honestly — judge before committing — while retaining nothing.
- **Organisation orphan cleanup / cross-store cascade — declined.**
  Evidence unchanged (P-139 / P-140 weighings): independent stores name
  drift instead of deleting across stores. This slice performs no
  cleanup and adds no cascade.
- **Bind-plan vs actual-bind reconciliation — declined.** Standing
  evidence (P-140 weighing): the binding record already IS the account
  of what landed, and P-138's battery pins the prospective half.
- **P-026 stateless raw-overlay leak (P-133 finding F1) — declined,
  carried unchanged.** Banked P-026 behaviour pinned by its own battery;
  this slice judges candidates through the same parser and inherits its
  law exactly, as replace itself does — changing the overlay law is a
  P-026 slice's call.
- **Playback / runtime / condition evaluation — declined. Executing
  stored scripting — declined ABSOLUTELY.** P-027 law: content is data,
  never code. The candidate is parsed and planned as data; nothing it
  carries is evaluated or run.

## What landed

- `src/runmal/scenarios/candidatepreview.py` (new) — the candidate
  replace-preview service. `preview_candidate_replace(record, bindings,
  organisation, live_definition_ids, body)` judges the body through the
  store door exactly as `ScenarioStore.replace` applies it (a non-object
  body raises ScenarioStoreError; otherwise P-026's parse_scenario_file
  alone, raising ScenarioParseError on refusal — before any envelope
  exists, exactly as a refused replace raises before any write) and
  returns the envelope: the P-136 identity four (id, name, CURRENT
  revision, source format), `next_revision` (current + 1, P-131's replace
  law), `current` (the record's P-131 summary() verbatim, P-132's plan
  over the stored definition, and P-136 plan counts read from that plan),
  `candidate` (the parsed name and source format, the would-be stored
  native shape — export_native of the parse — and its import report,
  exactly the pair a successful replace would persist; counts by the
  P-131 summary law read from the shape and report; P-132's plan over
  the would-be shape with its plan counts), `comparison` (name /
  source-format change flags, identical_body — the would-be shape
  deep-equals the stored definition — role and bootstrap count triples,
  plan count triples for messages / flags / variables / skipped, and the
  seedable-key deltas between the two plans: flag and variable keys
  added and removed, sorted, all read from the two plans themselves),
  `replace_impact` (P-140's `preview_replace_impact` envelope whole,
  verbatim — the candidate changes none of its facts), and six standing
  honesty notes in fixed order.
- `src/runmal/scenarios/router.py` (additive) — one road: POST
  /scenarios/{definition_id}/replace-preview answering the envelope,
  declared in its own section after the P-140 replace-impact section.
  The definition is fetched owner-scoped first (unknown or foreign
  answers 404 "scenario definition not found" — existence decided before
  the body is judged, the P-131 replace law, so no parse verdict ever
  leaks about someone else's definition); a refused candidate answers
  422 with the store door's own refusal, the create/replace roads'
  mapping. No query parameters, no writes. The third segment
  "replace-preview" is a new literal shared with no existing road
  (P-140's is "replace-impact").
- `src/runmal/scenarios/__init__.py` (additive) — the
  preview_candidate_replace name exported in the house style, plus one
  subsystem-map line.
- `tests/test_p146_candidate_replace_preview.py` — the battery
  (see Evidence).

## Honest bounds

- The preview is a statement about the candidate and the world as they
  stand when read: a replace committed with a different body, or after
  the world changes, is judged by the PUT road when it runs, which
  re-parses and re-reads everything. The preview is never a promise
  about replace time, and the candidate is stored nowhere — if it is
  not then PUT, it exists only in this answer.
- Judged exactly as stored cuts both ways: the would-be shape named
  here is the native shape only. A Voxta candidate's unmappable raw
  values are not part of it and would not persist (P-131); the candidate
  report carried in the envelope names every one of them, and the
  stateless P-026 roads remain the lossless hand-back road for raw
  files.
- Both plans are definition-side (P-136's bounds): no chat is consulted,
  bind-time refusals are not judged, and seedable keys are not landed
  keys — a chat that already holds a key seeds nothing for it at bind
  time, knowable only against that chat (P-138 judges the stored body
  that way; it does not judge candidates).
- identical_body is a statement about the would-be native shape only:
  replacing with an identical body still moves the revision by one and
  overwrites the record's import report with the candidate's (P-131
  replace law) — the preview names next_revision either way and claims
  no no-op.
- The candidate changes none of P-140's facts: bindings pin the revision
  of the body actually stored when they bound, and the organisation row
  keys on the definition's id. The impact section is therefore P-140's
  envelope verbatim, not a candidate-adjusted variant.
- There is no playback in this slice, and none is claimed.
