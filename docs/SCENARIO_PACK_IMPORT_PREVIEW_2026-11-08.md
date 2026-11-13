# P-143 — Library-Scoped Pack Import Preview (Part IX, thirteenth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line — "IX | Scenarios — the Visual Novel Engine |
P-131 – P-154" — and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-131..P-142
precedents. The derivation rests on Rúnmál's own in-tree
record only (full weighing in the team's scout/design
record, hidden_files/P143_DESIGN.md).

Base: cefe709 (P-141 banking record; P-001..P-141
banked, migration head 0041). P-142 (team-03, closing
the carried P-133 finding F1 in scenarios/fileexport.py)
is in flight and is NOT in this base; its assignment,
its modified fileexport.py and its battery were read
read-only in the team-03 worktree so this slice neither
duplicates nor collides with it: P-142 adds no module
and no road and repairs one exporter, while this slice
touches NO line of fileexport.py, adds one new module
(scenarios/packpreview.py) and one new road
(POST /scenarios/pack/import-preview). The keeper
reconciles the disjoint delta at banking. Migration:
NONE — head stays 0041. No storage shape changes and no
new store: the preview reads only, through P-141's own
verbs and the P-131 store's standing list door.

## The weighing

- **Library-scoped pack import preview — taken.** Pack
  import is the one consequential Part IX act left with
  no inspect-before-commit surface, and its two existing
  surfaces prove the gap from both sides. (1) P-141's
  inspect_pack is pack-side only: its own module states
  it touches no store and writes nothing — it validates
  the envelope, the manifest and the checksum and
  reports provenance, but it cannot say what importing
  THIS pack would do in THIS caller's library.
  (2) P-141's import_pack computes exactly those
  verdicts — duplicate_exact (an owned record with the
  same content checksum, imports unwritten),
  name_collision (an owned record with the manifest's
  name and different contents), and the
  on_conflict=reject refusal — but only INSIDE the
  importing act: under the default create_new mode,
  learning that a pack collides means a fresh record
  has already been created, and the duplicate verdict
  likewise arrives only as the import's own answer.
  So an owner holding a pack cannot read, before
  importing, the three facts import itself will decide
  by. This is P-136 → P-138's progression exactly (a
  definition-side preview whose standing notes named
  the facts it could not judge, answered by a scoped
  preview that judges them as data), transposed to the
  pack surface P-141 landed after both.
- **P-133 finding F1 (stateless raw-overlay leak) —
  not available.** Taken by concurrent P-142
  (team-03), read read-only in its worktree; building
  it again would duplicate a sibling slice mid-flight,
  and this slice touches no line of fileexport.py.
- **Unbind-impact preview — declined (P-141's ground,
  unchanged).** It would restate the one fact the
  unbind road already answers with every unbind (the
  record goes, seeded content stays — P-132).
- **Bind-plan vs actual-bind reconciliation —
  declined.** The P-137/P-138/P-139/P-141 reasoning,
  unchanged: the binding record already IS the account
  of what landed.
- **Definition history retention — declined.** No
  named consumer; a storage-shape change.
- **Organisation orphan cleanup / cross-store cascade
  — declined.** P-134/P-135 name staleness and orphan
  rows, never delete across stores.
- **Pack-carried organisation / bindings in packs —
  declined.** P-141 settled both: filing is
  library-local (P-134) and a binding is a chat
  attachment (P-132); the preview inherits the
  settlement — it reports that nothing else travels,
  it does not change it.
- **Collections / folders — declined.** P-134's honest
  bound; no named need.
- **Portable-archive inclusion of the scenario stores
  — declined for this slice.** A portable-subsystem
  slice, named open for that line.
- **Multi-definition / library packs — declined.**
  P-141 packs are deliberately one definition; a
  collection pack is new surface with no in-tree
  naming, and Part XII's hub questions belong to
  Part XII.
- **Playback / runtime / condition evaluation —
  declined. Executing stored scripting — declined
  ABSOLUTELY.** P-027 law: content is data, never code.

## What landed

- `src/runmal/scenarios/packpreview.py` (new) — the
  library-scoped pack import preview service. One verb,
  `preview_pack_import(store, owner_id, data, *,
  on_conflict="create_new")`. Validation is P-141's
  own, called never re-implemented: the mode is judged
  first with import's own PackError (import validates
  the mode before parsing; the preview mirrors that
  order), then the pack is judged through inspect_pack
  verbatim — its report rides in the envelope whole, so
  a malformed pack raises PackError before any library
  fact is read, one typed refusal at the boundary,
  exactly as import. The library scan is import's own
  law, read not run: the owner's records only
  (store.list_for_owner — another owner's identical
  definition never counts, the P-141 owner-scoping
  law), identity by packs.content_checksum over each
  record's stored definition (the payload-only identity
  P-141 defined), collision by record name against the
  manifest's definition_name. The envelope is the
  inspect report's fields verbatim at the top level
  plus `on_conflict` (the mode judged under), `library`
  ({definitions_total, duplicate_exact, duplicate_of —
  the matching record's summary via P-131's summary()
  verbatim, or None — name_collision, name_collisions
  — summaries of every same-name record that is not
  the exact duplicate, in store order}), `outcome`
  (exactly one of "duplicate_exact", "would_refuse",
  "would_create_with_name_collision", "would_create" —
  the verdict import would reach first, in import's own
  decision order: duplicate scan first, then collision
  plus the reject refusal, then create), the
  `would_create` / `would_refuse` bools read from the
  outcome, `refusal_reason` (import's own refusal
  sentence when the outcome is would_refuse, else
  None), and four standing honesty notes in fixed
  order (pure read; the library as it stands;
  payload-only identity; nothing else travels). Pure
  read: the store document is byte-untouched,
  battery-pinned at service level and over HTTP.
- `src/runmal/scenarios/router.py` (additive) — one
  road: POST /scenarios/pack/import-preview
  (?on_conflict=create_new|reject, default create_new)
  answering 200 with the envelope and 422 on a
  malformed pack or an unknown mode (PackError → 422,
  the router's ValueError mapping). Declared with the
  literal pack roads BEFORE the {definition_id} roads
  (the P-134/P-135/P-141 precedent), so "pack" is
  never read as a definition id. A reject-mode
  would_refuse is DATA at 200, never the road's own
  answer.
- `src/runmal/scenarios/__init__.py` (additive) — the
  preview_pack_import name exported in the house style,
  plus one subsystem-map bullet.
- `tests/test_p143_pack_import_preview.py` — the
  battery (13 tests; see Evidence).

## Honest bounds

- The preview is a statement about the library as it
  stands when read: import re-decides every fact when
  it runs, and P-141's check-then-create is not
  transactional, so a library that changes first
  changes the outcome. The import road remains the
  only importer; the preview is never a promise about
  import time.
- Identity is the definition payload only (P-141): a
  duplicate verdict is about what an import would
  store, never about ids, revisions or filing — two
  records holding the same payload under different
  ids are one duplicate, named by the first in store
  order, exactly as import's own scan returns it.
- The preview performs no import, no cleanup and no
  cascade, and no P-141 answer changes: packs.py is
  untouched, and inspect / import keep their exact
  standing shapes beside the new road.
- No organisation row and no binding travels in a pack
  or would be created by importing one (P-141); the
  preview inherits that settlement and reports it as a
  standing note.
- There is no playback in this slice, and none is
  claimed.
