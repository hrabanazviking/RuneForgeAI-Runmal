# P-139 - Definition Delete-Impact Preview (Part IX, eighth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 / P-134 / P-135 / P-136 /
P-137 / P-138 precedents. The derivation rests on
Runmal's own in-tree record only (full weighing in the
team's scout record).

Base: 3f66b48 (P-137 banking record; P-001..P-137
banked). P-138 (Chat-Scoped Bind Preview, team-02) is
being finished concurrently from base d93521f and is
NOT in this base; its scout / design were read
read-only in the team-02 worktree so this slice neither
duplicates nor contradicts it, and this delta is
additive against it (one new service module, one
additive router road, additive __init__ exports, one
appended clean-room entry). Migration: NONE - head
stays 0041. No storage shape changes: the preview
reads the three standing stores and stores nothing.

## The weighing

- **Definition delete-impact preview - taken.**
  Deletion is Part IX's other irreversible act beside
  binding: DELETE removes the record permanently (no
  undelete road exists, and definition history
  retention has been declined in every Part IX
  weighing, so there is no recovery), and by design
  it cascades NOWHERE. Its consequences land in two
  other independent stores and in the bound chats,
  and every one of them is named only at the surface
  that suffers it, after the fact: the bindings stay
  in scenario_bindings.json and turn stale, with
  P-135's definition_exists flag naming the staleness
  only on a read taken after the definition is gone -
  and the per-definition bindings road itself answers
  404 once the definition is deleted (P-135
  battery-pinned), so after deletion the orphaned
  bindings cannot even be enumerated per definition;
  the organisation row stays in
  scenario_organisation.json as an orphan, filtered
  at every read (P-134), invisible and never named at
  delete time; and the record's P-131 import report -
  the only naming of the definition's unmappable
  elements under P-133's one-way law - goes with the
  record. Measured against the router on this base,
  no road joined these facts to the definition while
  it still exists: the bindings road enumerates, the
  organisation road shows the filing, DELETE answers
  {"id", "deleted": true} - but nothing answers the
  question the irreversible act poses: what will
  deleting THIS definition orphan, and what will it
  not touch? P-138's scout weighed this exact
  candidate and declined it FOR P-138 on one stated
  ground - "no record names a missing aggregate
  surface; (a) is named twice in-tree and (c) is not.
  Named as a future candidate." That ground has
  lapsed the same way P-137's grounds lapsed for
  P-138: the chat-scoped candidate is taken (by P-138
  itself), and this candidate IS now named in-tree -
  by P-138's own scout, as the named future
  candidate. The house inspect-before-commit
  precedent (P-136 for bind, P-138 for
  bind-against-a-chat, the lorebook activation
  preview) covers the writing act; the deleting act
  had no equivalent. Every fact is read through the
  owning slice's own verb, so no second law is
  invented, and no deletion semantics change: cascade
  itself stays declined (below); this slice previews
  the impact, it does not perform or soften the
  deletion.
- **Chat-scoped bind preview - not available.**
  Taken by concurrent P-138 (its scout / design read
  read-only in the team-02 worktree; its road is
  GET /scenarios/{definition_id}/bind-plan/{chat_id},
  its module chatpreview.py). Building it again here
  would duplicate a sibling slice mid-flight. This
  slice's road (/delete-impact) and module
  (deletepreview.py) share no segment or file with
  it.
- **Bind-plan vs actual-bind reconciliation -
  declined, evidence weakened further.** P-137 and
  P-138 both declined it: the binding record already
  IS the account of what landed, and a plan
  comparison is exact only while the definition's
  current revision still equals the pinned revision -
  after a replace it is gone (history retention,
  declined). P-138's battery additionally pins the
  preview-vs-bind reconciliation directly
  (seeded_keys == would_seed, already-present
  pairings), so the prospective half is covered; the
  retrospective road remains exact sometimes and
  misleading the rest.
- **Definition history retention - declined.**
  P-131 already landed the revision discipline that
  transfers; no in-tree record names a consumer, and
  retention would be a storage-shape change (seventh
  declination, evidence unchanged).
- **Organisation orphan cleanup / cross-store
  cascade (incl. orphan-binding cleanup) -
  declined.** P-134 claims no cleanup road and names
  orphan rows the honest cost of independent stores;
  P-135 names binding staleness instead of deleting
  anything, and a stale binding already has a removal
  road (P-132 unbind, per chat). No record asks for
  deletion semantics across stores. This slice is a
  preview only: it performs no cleanup and adds no
  cascade.
- **Collections / folders - declined.** P-134's
  honest bound ("No collections or folders"); no
  named need.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** Banked P-026
  behaviour pinned by its own battery (INV-009 raw
  overlay); changing the overlay law is a P-026
  slice's call. This slice reads stored records and
  store rows only; it neither rewrites nor inherits
  the overlay.
- **Portable-archive inclusion of the scenario
  stores - declined for this slice.** The archive is
  a SQL-row bundle; the scenario stores are data-dir
  JSON documents by P-131 design - a portable-
  subsystem slice, named open for that line, not a
  Part IX foundation.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never
  code. The preview evaluates no condition and runs
  nothing; it reports facts about stored records, as
  data.

## What landed

- `src/runmal/scenarios/deletepreview.py` (new) -
  the preview service. `preview_delete_impact(record,
  bindings, organisation, live_definition_ids)`
  returns the envelope: definition_id,
  definition_name, definition_revision (the record's
  current revision), source_format (the P-136 four);
  bindings - P-135's `list_bindings_for_definition`
  output verbatim, each summary naming
  definition_exists against the caller's live ids
  (true while the definition exists); organisation -
  P-134's `organisation_view` verbatim, plus
  `organisation_row_exists`, the one fact the view
  alone cannot state (an unorganised definition's
  view is a computed default identical in shape to a
  persisted empty filing), read through the
  organisation store's own `get`; impact -
  bindings_orphaned / organisation_row_orphaned /
  chats_affected, read from those answers themselves
  (one binding is one chat, P-132's law) so they
  cannot drift; and the five standing honesty notes
  in fixed order (see Honest bounds). Pure read: no
  store is written, no row created or removed.
- `src/runmal/scenarios/router.py` (additive) - one
  road: GET /scenarios/{definition_id}/delete-impact
  answering the envelope. The record is fetched
  owner-scoped; unknown or foreign answers 404
  ("scenario definition not found") - the P-131
  no-leak discipline, identical to the P-133 / P-136
  roads. No body, no query parameters, no writes.
- `src/runmal/scenarios/__init__.py` (additive) -
  the preview_delete_impact name exported in the
  house style, plus one subsystem-map bullet.
- `tests/test_p139_delete_impact_preview.py` - the
  battery (11 tests; see Evidence).

## Honest bounds

- The preview is a read of the world as it stands:
  previewing deletes, writes and cascades nothing,
  and the definition named still exists afterwards
  (battery-pinned at service and HTTP level: no
  document created or changed, the definition still
  readable, still deletable, seeded chat content
  untouched).
- Deleting does not cascade into the binding store:
  every binding named would remain as a record and
  would afterwards read definition_exists false on
  the P-135 surface - stale, named, never hidden -
  and each chat's binding can still be removed per
  chat by unbinding (P-132). The battery pins the
  contrast: the same binding reads true in the
  preview and false, through P-135's own list verb,
  after a real deletion.
- Deleting does not cascade into the organisation
  store: an organisation row, if one exists, would
  remain as an orphan, filtered at every read and
  never surfaced (P-134); no road cleans organisation
  rows up, and this slice adds none.
- Content a binding already seeded into a chat -
  messages and variables - is the chat's own truth
  and is untouched by deleting the definition,
  exactly as it is untouched by unbinding.
- Deletion is permanent in this design: there is no
  undelete and no definition history, and the
  record's import report goes with the record. The
  stored-export road (P-133) is the way to keep a
  file copy first, under its own stated limits (its
  not_restored naming applies).
- The DELETE road remains the only deleter and
  re-reads the world when it runs: a binding created
  between preview and delete is deleted-around
  exactly as the standing no-cascade law already
  provides. The preview is a statement about the
  world as it stood, never a promise about delete
  time.
- There is no playback in this slice, and none is
  claimed.
