# P-140 — Definition Replace-Impact Preview (Part IX, tenth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md)
gives Part IX only its part-table line — "IX | Scenarios — the Visual
Novel Engine | P-131 – P-154" — and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated plainly as
derived everywhere, following the P-101 / P-117 / P-131..P-139
precedents. The derivation rests on Runmal's own in-tree record only
(full weighing in the team's scout record).

Base: 74a0c17 (P-138 banking record; P-001..P-138 banked). P-139
(Definition Delete-Impact Preview) is being banked concurrently from
a base that includes P-137 but not P-138 and is NOT in this base; this
delta is additive against it (new service module, one additive router
road, additive __init__ exports, one appended clean-room entry), and
its facts are replace's facts, not delete's (see The weighing).
Migration: NONE — head stays 0041. No storage-shape changes: the
preview reads a P-131 record, the binding store and the organisation
store, and stores nothing.

## The weighing

- **Definition replace-impact preview — taken.** Replace is Part
  IX's remaining consequential definition act with no
  inspect-before-commit surface: binding has two previews (P-136
  definition-side, P-138 chat-scoped) and deletion has P-139's
  delete-impact preview, while PUT replace answers only the new
  record, after the act. A successful replace is permanent for the
  current body, on exactly P-139's ground: the old definition body
  is overwritten and its P-131 import report — the only naming of
  what the original file carried, including every unmappable
  element (P-133's one-way law) — is replaced by the new body's
  report, and definition history retention has been declined in
  every Part IX weighing, so there is no recovery and no
  un-replace. Its cross-store consequences differ from delete's,
  which is why P-139's surface cannot answer for it: bindings pin
  their revision at bind time (P-132's contract) and are not
  re-materialised, so after a replace every binding pinned at the
  superseded revision diverges from the definition it names while
  `definition_exists` stays true — and the organisation row stays
  LIVE against the same id (replace writes only the definitions
  document), the opposite of delete's orphan. Before the act, no
  single surface joins the per-definition pinned revisions
  (P-135's list) to the definition's current revision (the P-131
  read) against the replace decision; an owner compares two roads
  by hand. The preview joins each store's own verbs, invents no
  second law, and changes no replace semantics: the PUT road
  remains the only replacer.
- **Definition delete-impact preview — not available.** Taken by
  concurrent P-139; building it again here would duplicate a
  sibling slice mid-flight, and its facts are delete's facts, not
  replace's.
- **Bind-plan vs actual-bind reconciliation — declined.** Third
  declination, evidence weakened further: P-137 and P-138 declined
  it (the binding record already IS the account of what landed,
  exposed in full by P-132's single-read road and in summary by
  P-135; a plan comparison is exact only while the pinned revision
  still equals the current one — after a replace it is gone,
  history retention, declined). P-138's battery additionally pins
  the preview-vs-bind reconciliation directly (the record's landed
  keys are the preview's would-seed set), so the prospective half
  is covered by a banked battery; the retrospective road remains
  a road exact sometimes and misleading the rest.
- **Binding-summary freshness enrichment — declined as a shape
  change.** Adding current-revision keys to P-135's list answers
  would mutate a banked surface whose summary shape is pinned by
  exact dict equality; every Part IX slice has added roads rather
  than changing banked answers. The freshness fact is carried by
  this slice's new road as split counts read from P-135's own
  summaries.
- **Unbind-impact preview — declined.** Unbind destroys nothing
  beyond the record it names, that record is already readable in
  full before the act on P-132's single-read road, and the DELETE
  road's own answer already states that seeded content is kept;
  the aggregate gap that justified P-139 has no analogue here.
- **Definition history retention — declined.** Eighth declination,
  evidence unchanged: P-131 already landed the revision discipline
  that transfers; no in-tree record names a consumer, and
  retention would be a storage-shape change.
- **Organisation orphan cleanup / cross-store cascade — declined.**
  Evidence unchanged: P-134 claims no cleanup road and names
  orphan rows the honest cost of independent stores; P-135 names
  binding staleness instead of deleting anything, and a stale
  binding already has a removal road (P-132 unbind, per chat). No
  record asks for deletion semantics across stores. This slice is
  a preview only: it performs no cleanup and adds no cascade.
- **Collections / folders — declined.** P-134's honest bound ("No
  collections or folders"); no named need.
- **P-026 stateless raw-overlay leak (P-133 finding F1) —
  declined, carried unchanged.** Banked P-026 behaviour pinned by
  its own battery (INV-009 raw overlay); changing the overlay law
  is a P-026 slice's call. This slice reads stored records and
  store rows only; it neither rewrites nor inherits the overlay.
- **Portable-archive inclusion of the scenario stores — declined
  for this slice.** The archive is a SQL-row bundle; the scenario
  stores are data-dir JSON documents by P-131 design — a
  portable-subsystem slice, named open for that line, not a Part
  IX foundation.
- **Playback / runtime / condition evaluation — declined.
  Executing stored scripting — declined ABSOLUTELY.** P-027 law:
  content is data, never code. The preview evaluates no condition
  and runs nothing.

## What landed

- `src/runmal/scenarios/replacepreview.py` (new) — the
  replace-impact preview service. `preview_replace_impact(record,
  bindings, organisation, live_definition_ids)` returns the
  envelope: the P-136 definition four (id, name, CURRENT revision,
  source format), `next_revision` (current + 1 — P-131's replace
  law: a successful replace pins exactly current + 1), the
  bindings (P-135's `list_bindings_for_definition` verbatim — the
  same summaries the per-definition bindings road answers, each
  naming `definition_exists`), the organisation (P-134's
  `organisation_view` verbatim) plus `organisation_row_exists`
  (whether a persisted row exists at all — the one fact the view
  alone cannot state, since an unorganised definition's view is a
  computed default identical in shape to a persisted empty filing,
  the P-139 precedent), impact counts read from those answers
  themselves so they cannot drift (bindings total; the pinned
  split — pinned at the current revision, already pinned older,
  and pinned newer, impossible by construction since bind pins
  the revision current when it runs and revisions only grow, yet
  counted so the three always reconcile with the total and a
  hand-damaged store is named, never hidden; chats affected —
  one binding is one chat under P-132's law; and whether the
  organisation row survives, which is whether one exists), and
  five standing honesty notes in fixed order.
- `src/runmal/scenarios/router.py` (additive) — one road:
  GET /scenarios/{definition_id}/replace-impact answering the
  envelope, declared in its own section after the P-138
  chat-scoped bind-preview section. The definition is fetched
  owner-scoped first (unknown or foreign answers 404 "scenario
  definition not found" — the P-131 no-leak discipline); live ids
  are the caller's own definition ids (the P-135 router
  precedent). No body, no query parameters, no writes. The third
  segment "replace-impact" is a new literal shared with no
  existing road; concurrent P-139's "delete-impact" is a
  different literal, so neither captures the other.
- `src/runmal/scenarios/__init__.py` (additive) — the
  preview_replace_impact name exported in the house style, plus
  one subsystem-map line.
- `tests/test_p140_replace_impact_preview.py` — the battery
  (12 tests; see Evidence).

## Honest bounds

- The preview is a statement about the world as it stands when
  read: a binding created between preview and replace pins the
  then-current revision exactly as the standing pin law already
  provides. The PUT road remains the only replacer and re-reads
  the world when it runs; the preview is never a promise about
  replace time.
- No candidate body is judged here: a replace body P-026 refuses
  answers 422 at the replace road and changes nothing (P-131
  parses before writing — battery-pinned there), and what a
  successful new body would plant is knowable only once it is
  stored, through the bind-plan previews (P-136 / P-138), which
  compute from whatever revision is current when they run.
- Superseded is not stale: after a replace, a binding's
  `definition_exists` stays true and its pinned revision simply
  names an older body than the definition's current one. Nothing
  is re-materialised, and no rebind road is claimed — a chat that
  wants the new body unbinds and binds again as its own act
  (P-132's roads, unchanged).
- The preview performs no cleanup and no cascade, and P-135's
  summary shape is untouched: the pinned split is computed FROM
  the summaries, never added to them.
- There is no playback in this slice, and none is claimed.
