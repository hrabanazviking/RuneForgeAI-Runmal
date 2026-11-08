# P-142 - Stateless Native-to-Voxta Export: the F1 Leak Closed (Part IX, eleventh slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131..P-141
precedents. The derivation rests on Runmal's own in-tree
record only (full weighing in the team's design record).

Base: f9b52ac (P-140 banking record; P-001..P-140 banked).
P-141 (Scenario Definition Sharing Packs, team-02) is in
flight, banks ahead of this slice, and is NOT in this base;
its chosen scope was read read-only in the team-02 worktree
so this slice neither duplicates nor collides with it (its
module is packs.py, its roads are the pack roads; this slice
adds no module and no road and touches no file of P-141's).
Migration: NONE - head stays 0041. No storage shape changes:
the fix changes one pure export function and stores nothing.

## The weighing

- **The carried P-133 finding F1 - taken.** A proven gap
  beats new surface, and this gap is a proven DEFECT.
  P-133 recorded it and every Part IX slice since carried
  it, declined, as banked P-026 behaviour whose repair was
  "a P-026 slice's call" - a slice no queue ever
  commissioned. Re-probed on this base, the defect is worse
  than its record: export_voxta is a raw overlay (INV-009)
  and a native parse keeps raw = the whole native dict, so
  the stateless native->Voxta export carried every native
  key verbatim beside its Voxta spelling (scenario_text
  beside scenario, initial_variables beside variables,
  bootstrap_messages beside bootstrapMessages, and inside
  the role objects character_name beside characterName,
  enabled_on_start beside enabledOnStart, can_speak beside
  canSpeak) - and the hybrid RE-PARSED AS NATIVE, because
  it carries strong native keys, so the stateless road
  never produced a Voxta file from a native one at all.
  For the same content, P-133's stored export produces the
  clean typed-fields conversion: the two export roads
  DISAGREED, which is also the record's one open definition
  interop parity gap. A discovered bug is never left
  unfixed; this slice fixes it at the exporter, the
  P-133 precedent's own construction.
- **Binding lifecycle depth beyond read/preview -
  declined.** P-141's weighing stands: an unbind-impact
  preview would restate the one fact the unbind road
  already answers with every unbind (the record goes,
  seeded content stays - P-132); rebind has no in-tree
  naming; binding history is the history-retention
  candidate declined in every Part IX weighing. The
  strongest remainder, a global stale/superseded binding
  census, is still weaker than a proven defect: P-140
  already joins the pinned split per definition and
  P-135 names definition_exists per row, and no record
  names a consumer for the aggregate. Named as a future
  candidate.
- **Definition interop parity gaps beyond F1 - declined.**
  With P-141's packs in flight the remaining legs are
  closed or owned: import-to-store IS P-131's create,
  stored->file is P-133, sealed travel is P-141. The one
  open parity gap in the record was the stateless-vs-
  stored Voxta disagreement - F1 itself, taken above.
- **Organisation/binding interplay - declined.** The
  surfaces already compose on the definition id (P-135
  per-definition bindings, P-134 organisation view), and
  P-139/P-140 join bindings + organisation per definition
  for the two consequential acts. No record names a
  joined consumer beyond those; a general status
  aggregate would restate banked envelopes.
- **Scenario packs - not available.** Taken by concurrent
  P-141; not duplicated here.
- **Bind-plan vs actual-bind reconciliation - declined.**
  Standing evidence: the binding record already IS the
  account of what landed, and P-138's battery pins the
  prospective reconciliation.
- **Definition history retention - declined.** Ninth
  declination, evidence unchanged: no named consumer,
  and retention would be a storage-shape change.
- **Organisation orphan cleanup / cross-store cascade -
  declined.** Standing evidence (P-134 / P-135): orphan
  rows are the honest cost of independent stores, named
  rather than deleted across stores.
- **Collections / folders - declined.** P-134's honest
  bound ("No collections or folders"); no named need.
- **Portable-archive inclusion of the scenario stores -
  declined for this slice.** The archive is a SQL-row
  bundle; the scenario stores are data-dir JSON documents
  by P-131 design - a portable-subsystem slice, named
  open for that line, not a Part IX foundation.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  This slice evaluates nothing and runs nothing.

## What landed

- `src/runmal/scenarios/fileexport.py` (fix) - the
  overlay law amended for one origin. A parse whose
  source_format is native has no Voxta raw to overlay:
  export_voxta now starts from an empty object for such
  a parse and passes every element (roles, bootstrap
  messages, contexts) through a new `_rawless` shallow
  copy with `raw` cleared, so the overlay steps write
  only the Voxta spellings from the typed fields - the
  identical construction P-133's
  scenario_file_from_stored performs externally before
  calling the same exporters. The module docstring and
  the export_voxta docstring state the amended law. The
  parser is untouched (filemodels' law stands: raw
  always holds the complete original mapping), the
  original parse is never mutated (battery-pinned), and
  the Voxta-origin overlay is unchanged byte for byte:
  raw carriage, the alias spelling the source file used,
  unmappable hand-back and the fixed point all stand,
  guarded by the battery and by the untouched P-026 /
  P-030 neighbours. export_native and both bytes
  variants are untouched in code (the Voxta bytes
  variant inherits the fix through export_voxta).
- `tests/test_p142_native_voxta_export.py` - the battery
  (16 tests; see Evidence).
- `docs/SCENARIO_NATIVE_VOXTA_EXPORT_2026-11-08.md` -
  this doc.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one appended
  entry.

No new module, no new road, no __init__ change: there is
no new surface to export. The router's stateless export
road and P-133's stored-export road now answer the same
file for the same content, which is the slice's whole
point.

## Honest bounds

- The fix is origin-scoped: only a parse the importer
  classified as native takes the clean path, judged by
  the parse's own source_format - the same fact P-133's
  reconstruction relies on. A file the importer
  classifies as Voxta keeps the full INV-009 overlay,
  including any native-spelled keys its raw happens to
  carry as unknowns: those are that file's own carriage,
  under the standing raw law, not this slice's to strip.
- Inside elements, a native file's unknown keys do not
  survive a Voxta export: the native parser never typed
  them, and the stored truth (P-131) drops them the same
  way, so stateless and stored agree. Top-level unknowns
  are different: they ride as `extra` on both roads and
  still ride here, verbatim (battery-pinned).
- A carried `extra` key spelled like a Voxta typed field
  still loses to the typed value under the exporter's
  standing setdefault law on this road, exactly as
  before; P-133's report names that shadowing on the
  stored road, and the stateless road's import report
  names the key as carried. No behaviour changes here.
- Nothing is stored, seeded, played or executed: export
  remains a pure function of the parse (P-027).
