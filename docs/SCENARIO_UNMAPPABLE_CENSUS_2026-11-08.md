# P-145 - Library Unmappable-Content Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131..P-144
precedents. The derivation rests on Rúnmál's own in-tree
record only (full weighing below; scout and design in the
team hidden record).

Base: 336b204 (P-143 banking record; P-001..P-143 banked).
P-144 (global binding census, team-02) banks ahead of this
slice and is NOT in this base; its doc and design were read
read-only in the team-02 worktree so this slice neither
duplicates nor collides with it: P-144 joins BINDINGS to
definitions and reads no import report, while this slice
reads DEFINITION REPORTS and touches no binding; both add
one literal library/bindings road and additive router +
__init__ lines in disjoint blocks, flagged for the keeper's
banking reconciliation. Migration: NONE - head stays 0041.
No storage shape changes: the census reads the P-131
definition store and stores nothing.

## The weighing

- **Library unmappable-content census - taken.** The gap is
  mechanical, verified in code on this base. Every P-131
  record carries its P-026 import report as data, and the
  report's unmappable list is the ONE naming of the
  machinery a file carried that Rúnmál cannot map -
  recorded, never executed (P-027). P-139 calls that report
  "the only naming" of a definition's unmappable elements
  and warns that deleting the record loses it. Yet the
  naming is reachable only one record at a time: the P-131
  single read, P-133's per-definition not_restored inside
  an export envelope, P-141's per-definition provenance
  inside a pack. The library list shape (P-131 summary)
  reduces the whole list to one bool, has_unmappable -
  kinds, counts, paths and reasons appear in NO list or
  aggregate surface. An owner who imported many Voxta
  files could not answer "how much unmappable machinery
  does my library carry, of what kinds, and in which
  definitions?" except by fetching every record in full,
  one by one. This slice is that answer: one pure read
  joining every stored report across the caller's library
  - the same shape of gap P-144 closed for bindings
  (per-row flags, no joined judgement), transposed to the
  definition reports P-144 never reads.
- **Global binding census - not available.** Taken by
  concurrent P-144 (team-02); not duplicated. This slice
  touches no binding store and no binding road.
- **Unbind-impact preview - declined.** P-141 / P-142 /
  P-144 weighing stands, evidence unchanged: the unbind
  road already answers its one fact with every unbind
  (the record goes, seeded content stays - P-132).
- **Duplication preview - declined.** P-144 stands:
  duplication (P-137) is non-destructive, orphans and
  supersedes nothing, and no record names a risk needing
  inspection before it.
- **Organisation orphan census / cleanup - declined.**
  P-144 stands: orphan rows are filtered at every read
  (P-134) and P-139 names the row per definition before
  the deletion that orphans it; cross-store cleanup is
  declined standing law (censuses name, never repair).
- **Export / pack-export previews - declined.** Stored
  export and pack export are pure reads whose own
  envelopes already carry their honest reports (P-133
  not_restored, P-141 manifest + provenance); a preview
  of a read adds no knowledge. Pack import has its
  preview (P-143), and create has its dry read (the
  stateless P-026 import road IS parse-and-report).
- **Within-library duplicate-content census - weighed,
  not taken.** Identity-by-checksum is P-141 / P-143's
  pack law, judged there against packs; no in-tree record
  names within-library duplicate groups as a missing
  fact, and P-137 clones are honest citizens by design,
  not drift. Weaker naming than the unmappable gap, whose
  per-definition naming the record itself calls
  load-bearing (P-139).
- **General library status aggregate - declined.**
  P-142 stands: counts by format / revision / filing /
  bound-ness would restate banked envelopes. The
  unmappable census is not that: it surfaces report
  content no envelope aggregates.
- **Bind-plan vs actual-bind reconciliation - declined.**
  Standing evidence: the binding record already IS the
  account of what landed; P-138 pins prospectively.
- **Definition history retention - declined.** Evidence
  unchanged: no named consumer; a storage-shape change.
- **Portable-archive inclusion of the scenario stores -
  declined for this slice.** A portable-subsystem slice,
  named open for that line.
- **Playback / runtime / condition evaluation - declined.
  Executing stored scripting - declined ABSOLUTELY.**
  P-027 law: content is data, never code. This census
  serves that law: it names the machinery precisely so
  it stays named data, never a running thing.

## What landed

- `src/runmal/scenarios/reportcensus.py` (new) - the
  census service. `census_unmappable(definitions)` takes
  the caller's own records (the store's list_for_owner
  answer) and answers rows in store order for ONLY the
  definitions whose stored report names at least one
  unmappable element. Each row names its definition by
  P-131's summary() verbatim and carries the report's
  elements verbatim, in report order, with the kinds
  listed per element so they sum to the row's count.
  Elements are read through P-133's exact reading law
  (missing/malformed report = no elements; non-dict rows
  skipped; fields str-coerced) - no second report law.
  `by_kind` rolls the same elements up per kind in
  first-appearance order across the rows, and every
  count (definitions_total, definitions_with_unmappable,
  definitions_clean, unmappable_total,
  kinds_represented) is summed from the rows themselves,
  so the census cannot drift from its own evidence
  (the P-144 construction). Five standing notes state
  the bounds in every answer.
- `src/runmal/scenarios/router.py` (additive) - one road:
  GET /scenarios/library/unmappable, declared in the
  library block after GET /scenarios/library/tags and
  before the bindings block, so the literal "library"
  is never read as a definition id (the P-134
  declaration-order precedent; battery-pinned by contrast
  with the per-definition read and the tags road). It has
  no 404 case: an owner with no definitions - or none
  with unmappable elements - answers the honest zero
  census.
- `src/runmal/scenarios/__init__.py` (additive) - one
  subsystem-map bullet plus the `census_unmappable`
  export.
- `tests/test_p145_unmappable_census.py` - the battery
  (15 tests; see Evidence).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one appended
  entry.

No new store, no write of any kind: the census is a read
of the P-131 records' own reports and stores nothing.

## Honest bounds

- A census, not a cleanup: nothing is removed, converted
  or repaired. Unmappable elements stay recorded on
  their definitions until those records themselves are
  replaced or deleted under their own roads.
- The report is the record: the census claims only what
  the stored reports name, as they stand now. A record
  whose report is missing or malformed reads as clean
  here, exactly as P-133's export reads it; a replace
  re-parses and replaces the report (P-131), so the
  census judges the current report of the current
  revision and keeps no history.
- Kinds are whatever the reports name, counted as named
  (the parser's kind strings - scripting, action,
  hud_widget, and kin - are data here, never a closed
  enum the census enforces).
- The census carries the reports' unmappable rows
  themselves - that is its purpose - but no definition
  content: no scenario text, roles or bootstrap bodies.
  The full record stays on the P-131 single-read road.
- It judges reports only: nothing about bindings, filing,
  chats or liveness. The binding drift surface is
  P-144's; the tag census is P-134's; neither is restated.
- No filters, sorts or paging: store order, the whole
  owner set - the P-135 / P-144 bounded-surface precedent;
  no record names a consumer needing more.
