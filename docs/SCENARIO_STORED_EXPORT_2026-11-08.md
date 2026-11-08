# P-133 - Stored-Definition File Export (Part IX, third slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131 / P-132
precedents. The derivation rests on Runmal's own in-tree
record only: P-132's slice doc names this exact candidate -
"store-to-file export by id ... it is the natural next
candidate" - and its clean-room entry repeats the naming
("the one missing leg of import/export parity"); P-131's
recorded limitation defines what the export can and cannot
restore.

Base: d11ee6b (P-132 banking record; P-001..P-132 banked).
Migration: NONE - head stays 0041. No storage shape changes:
the export reads the P-131 record and stores nothing.

## The weighing

- **Store-to-file export parity - taken.** The one missing
  leg of import/export parity. P-131 made files storable,
  P-132 gave the stored truth a consumer (binding); nothing
  led back from a stored definition to a file - the only
  export road (P-026) parses a caller-supplied body. Every
  leg of this slice stands on P-026's own exporters; no
  second export law is invented.
- **Definition versioning / revision discipline per P-025 -
  declined.** P-131 already landed the discipline that
  transfers (revision 1 at create, +1 on replace, pinned
  created_at); P-132 pinned revision-at-bind as the
  consumption contract. No in-tree record names a missing
  revision behaviour for the JSON store, and history
  retention would be a storage-shape change with no named
  consumer.
- **Library organisation over definitions - declined.**
  P-132's declined (c), on its own reasoning, unchanged:
  organisation follows consumption, and the record's own
  order queued export parity first.
- **Playback / runtime / condition evaluation - declined.**
  No runtime machinery exists in tree; contexts stay data.
- **Executing stored scripting - declined absolutely.**
  P-027 law: unmappable scripting is recorded, never
  executed. A stored definition does not even carry
  scripting values; its P-131 report names them, and this
  slice's export report names them again.

## What landed

- `src/runmal/scenarios/storedexport.py` (new) - the
  export service. `scenario_file_from_stored(definition)`
  rebuilds a ScenarioFile through P-026's own parser, then
  clears `raw`, `unmappable_values` and every element's
  `raw` (see Finding F1): the stored truth holds typed
  fields + `extra` only, and no raw is fabricated for it.
  `export_stored_definition(record, format)` returns
  `(file_dict, report_dict)`: the file is built by P-026's
  `export_native` / `export_voxta` over the reconstruction;
  an unknown format raises `StoredExportError` before any
  work. The report is plain data: definition id, name, the
  record's current revision and its own source_format, the
  requested format, the exported top-level keys, every
  `not_restored` element (path + kind + name + reason, read
  from the record's own P-026 import report; a missing or
  malformed report reads as an empty list), every
  `carried_shadowed` key (see the honest account below),
  and the standing honesty notes in fixed order.
- `src/runmal/scenarios/router.py` (additive) - one road:
  GET /scenarios/{definition_id}/export answering the
  envelope {"format", "file", "report"}. The default
  format is native, the stored truth's own shape.
  Existence is decided BEFORE the format is judged (an
  unknown or foreign id answers 404 even with a bad
  format - the P-131/P-132 no-leak discipline); an unknown
  format on an owned definition answers 422 — including
  an explicitly empty `?format=`, which is a value outside
  FORMATS, not the default (finisher fix; the default
  applies only when the parameter is absent). The P-026,
  P-131 and P-132 roads are untouched beside it.
- `src/runmal/scenarios/__init__.py` (additive) - the
  storedexport names exported in the house style, plus one
  subsystem-map line.
- `tests/test_p133_stored_export.py` - the battery
  (24 tests; see Evidence).

## What export does and does not restore (the honest account)

- **Native export restores the definition exactly.** The
  native file IS the stored definition (dict equality,
  battery-pinned for native- and Voxta-origin records).
  File->store->file and store->file->store round-trips are
  exact at the definition level.
- **Voxta export restores a typed-fields conversion.**
  Built by P-026's own exporter from typed fields +
  carried `extra` only: Voxta spellings throughout, no
  native key rides along, carried unknowns (extra) ride
  back, and store->Voxta-file->store reproduces the stored
  definition exactly (the re-imported record's
  source_format honestly reads "voxta" - its road).
  It is NOT the original Voxta file: no raw overlay
  exists for stored truth, because no raw persisted.
- **Unmappable values are never restored - and are always
  named.** A Voxta file's scripts / hudWidgets / etc.
  values were never persisted (P-131); both export shapes
  omit them, and the report's `not_restored` names each
  one with the reason P-026 recorded at import.
- **A carried key shadowed by the format's own spelling
  is named (finisher finding F2).** A stored definition can
  carry an `extra` key spelled like a Voxta field a typed
  field also writes (a native file carrying `variables`
  beside `initial_variables`, or `flags` beside
  `initial_flags`). The Voxta file has one such key: the
  typed value wins it, the carried value cannot also ride,
  and the report's `carried_shadowed` names every such key
  with its reason — never a silent drop. A carried key
  whose value equals the typed value loses nothing and is
  not named; one the typed fields do not write rides
  verbatim. The native file shadows nothing: it IS the
  stored definition, carried keys included.
- **The naming itself is one-way.** Re-importing an
  exported native file creates a record whose native
  report cannot name unmappable elements the native shape
  never carried; the second record's `not_restored` is
  honestly empty. The battery pins this rather than
  papering over it.

## Finding F1 (carried, not fixed and not inherited)

P-026's stateless native->Voxta road leaks: export_voxta
is a raw overlay (its INV-009 law), a native parse keeps
raw = the native dict, so a stateless native->Voxta export
carries the native keys verbatim beside their Voxta
spellings (probe on this base: scenario_text beside
scenario; role objects gain character_name beside
characterName). That is banked P-026 behaviour, pinned by
its own battery; changing the overlay law is a P-026
slice's call, so this slice does NOT rewrite it. It also
does not inherit it: the stored export reconstructs with
no fabricated raw, so its Voxta file is clean. F1 stands
recorded here, in the scout and in the evidence as a
carried candidate for a future P-026-hardening slice.

## Honest bounds

- Export is read-only: it stores nothing, bumps no
  revision, and touches no binding. A definition bound to
  a chat exports exactly as an unbound one does.
- The export report reflects the record it is read from:
  after a replace, the export names the NEW record's
  revision and the NEW body's report (battery-pinned).
- There is no playback in this slice, and none is claimed.
