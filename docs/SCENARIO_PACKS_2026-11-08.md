# P-141 - Scenario Definition Sharing Packs (Part IX, tenth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131..P-139 precedents. The derivation rests on
Runmal's own in-tree record only (full weighing in the
team's scout/design record).

Base: ed0ed34 (P-139 banking record; P-001..P-139
banked). P-140 (definition replace-impact preview,
team-01) is in flight from an earlier base and is NOT
in this base; its assignment was read read-only in the
team-01 worktree so this slice neither duplicates nor
collides with it (its module is replacepreview.py and
its road GET /scenarios/{definition_id}/replace-impact;
this slice's module is packs.py and its roads share no
segment with it), and this delta is additive against it
(one new service module, additive router roads,
additive __init__ exports, one appended clean-room
entry). Migration: NONE - head stays 0041. No storage
shape changes and no new store: import writes through
P-131's standing store door only.

## The weighing

- **Scenario definition sharing packs - taken.** A
  proven gap beats new surface, and this gap is proven
  three ways. (1) Parity: the other two stored
  libraries can travel sealed - lorebooks as P-045
  packs and prompt artefacts as P-063 packs, each a
  JSON envelope with a manifest, a SHA-256 content
  checksum and a provenance record, inspectable before
  import and duplicate-aware on import, built ahead of
  Part XII's hub (P-187..P-202) so the hub can carry
  them unchanged; the P-003 census names scenarios as
  pack content (VX-59 the hub, VX-60 content
  packages). Scenarios could not travel sealed at
  all: the only road out of the store was P-133's
  bare file export (no checksum, no provenance, no
  inspect, no duplicate law) and the only road in was
  P-131's create, which accepts any body blindly.
  (2) The report loss: P-137 proved the record's
  P-131 import report is the one part the composed
  export -> create road cannot reproduce (P-133's
  one-way naming law) - a definition that travelled
  lost the only naming of its unmappable elements.
  A pack carries the source report as data in its
  provenance, and the import report hands it back
  verbatim: the naming travels, even though the new
  record's own report honestly remains its fresh
  parse's report (the P-045 carrier law - provenance's
  carriers are the pack and the import report, never
  a stored row). (3) Identity is already defined:
  P-133 pinned the stored definition as dict-equal to
  its native export, so a scenario payload needs no
  parse normalisation before hashing (the lorebook
  case) - the checksum is over the canonical JSON of
  the definition dict itself, exactly what an import
  would store.
- **Binding lifecycle depth beyond read/preview -
  declined.** What remains is thin and unnamed: an
  unbind-impact preview would restate the one fact
  the unbind road already answers with every unbind
  (the record goes, seeded content stays - P-132);
  rebind has no in-tree naming; binding history is
  the history-retention candidate declined in every
  Part IX weighing. No record names a missing
  aggregate surface here.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** Fourth Part IX
  declination, on the standing ground: INV-009 is
  banked P-026 behaviour pinned by its own battery,
  changing the overlay law is a P-026 slice's call
  (P-137 / P-138 / P-139), and stored definitions are
  already protected - a pack's payload is the stored
  native shape, which carries no raw at all, so this
  slice neither rewrites nor inherits the overlay.
  F1 stands as the carried candidate for a future
  P-026-hardening slice.
- **Definition replace-impact preview - not
  available.** Taken by concurrent P-140 (team-01;
  its assignment read read-only). Building it again
  here would duplicate a sibling slice mid-flight.
- **Bind-plan vs actual-bind reconciliation -
  declined.** The P-137 / P-138 / P-139 reasoning,
  unchanged: the binding record already IS the
  account of what landed; P-138's battery pins the
  prospective reconciliation directly.
- **Definition history retention - declined.**
  Eighth declination, evidence unchanged: no named
  consumer, and retention would be a storage-shape
  change.
- **Organisation orphan cleanup / cross-store
  cascade - declined.** Unchanged evidence (P-134 /
  P-135 name staleness and orphan rows, never delete
  across stores). A pack also carries NO organisation
  row: filing is library-local by P-134's design, and
  P-137's duplication - this slice's closest in-tree
  relative - carries none either.
- **Bindings in packs - declined.** A binding is a
  chat attachment (P-132), not part of a definition;
  its seeded content is the bound chat's own truth
  and cannot travel. Stated in every import report.
- **Collections / folders - declined.** P-134's
  honest bound; no named need.
- **Portable-archive inclusion of the scenario
  stores - declined for this slice.** The archive is
  a SQL-row bundle; the scenario stores are data-dir
  JSON documents by P-131 design - a portable-
  subsystem slice, named open for that line.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never
  code. A pack moves a definition as data; nothing
  is played, evaluated or executed.

## What landed

- `src/runmal/scenarios/packs.py` (new) - the pack
  service, synchronous (the scenario stores are JSON
  documents, not SQL rows - the one structural
  divergence from P-045, forced by the store shape
  and stated in the module). `build_pack(record)`
  seals one stored definition: envelope {format
  "runmal-scenario-pack", pack_version 1, kind
  "scenario", schema "runmal-p141-scenario-pack-v1",
  manifest, provenance, scenario} where the payload
  is the stored definition verbatim, validated
  through P-026's own parser before sealing (a pack
  is never minted around contents the store door
  would refuse) and required to be the native shape.
  The manifest carries the definition name, role and
  bootstrap counts read from the payload itself, the
  content checksum, the canonical payload byte
  length, the export stamp, the app version and the
  payload format. Provenance carries the source
  record's id, name, pinned revision and ORIGINAL
  source format, the stamp, the app version, the
  checksum, and `source_report` - the source record's
  P-131 import report verbatim when one exists -
  plus a caller note only when one was supplied;
  unknown facts are omitted, never fabricated.
  `parse_pack(data)` validates a pack whole (safety
  tree check; envelope, manifest-against-payload and
  provenance checksum agreement; payload through
  P-026's parser as PackError throughout) before any
  write exists; bytes/str input decodes under a
  local 16 MiB cap (named local, the P-063
  precedent). `inspect_pack(data)` returns the
  pre-flight report and touches no store.
  `import_pack(store, owner_id, data, on_conflict)`
  applies the collision discipline and writes only
  through `ScenarioStore.create`.
- `src/runmal/scenarios/router.py` (additive) -
  three roads: POST /scenarios/import-pack (201
  created / 200 duplicate, the P-045 JSONResponse
  shape; the record in full plus `pack_import`),
  POST /scenarios/pack/inspect (200 report / 422
  malformed; writes nothing) - both declared with
  the literal roads before the {definition_id} roads,
  the P-134/P-135 precedent - and
  GET /scenarios/{definition_id}/pack (the pack for
  one owned definition; unknown or foreign 404,
  decided before anything is built).
- `src/runmal/scenarios/__init__.py` (additive) -
  the packs names exported in the house style, plus
  one subsystem-map bullet.
- `tests/test_p141_scenario_packs.py` - the battery
  (see Evidence).

## Honest bounds

- Identity is the definition payload only: two
  records whose definitions are dict-identical are
  exact duplicates for pack purposes even if their
  records' own reports differ (a Voxta-born record
  and its native-born twin) - the checksum verdict
  is about what an import would store, and the
  pack's carried source_report still reaches the
  receiver in the import report on the duplicate
  path too, so the naming is not lost by the verdict.
- The new record's own import report is its fresh
  native parse's report: re-imported natively, it
  cannot name unmappable elements the native shape
  never carried (P-133's one-way law, battery-pinned
  here rather than papered over). The pack's
  source_report is data in the pack and the import
  report; it is never installed as the record's
  report, and no road claims otherwise.
- Import never overwrites and never merges. An
  exact duplicate writes nothing (the store document
  is byte-untouched, battery-pinned). A name
  collision under create_new mints a fresh record
  under the same name - definitions are told apart
  by id, as they have been since P-131 (duplicate
  names are distinct citizens there too).
- The duplicate scan is over the importing owner's
  records only and is O(owned definitions) canonical
  checksums: pack import is a deliberate act, not a
  hot path. The check-then-create is not
  transactional across concurrent imports of the
  same pack - the JSON store has no unique
  constraint to lean on without a migration - so two
  racing imports can both create; accepted for a
  single-owner local app and stated plainly (the
  P-045 honesty precedent).
- A pack is a file, not a signature: the checksum
  proves the contents match the manifest a pack
  carries, not who made the pack. Provenance is the
  pack's own statement of origin, carried verbatim,
  never verified against any authority - the hub's
  signing questions belong to Part XII.
- Nothing else travels: no organisation row, no
  binding, no chat content. Importing a pack into a
  library files the new definition unorganised and
  unbound, exactly as a plain create does.
- There is no playback in this slice, and none is
  claimed.
