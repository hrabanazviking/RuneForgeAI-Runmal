# P-201 - Hub Reconciliation Battery (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
"XII | The Hub, Sovereign Shape | P-187 - P-202" - and no
verbatim P-201 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from
Runmal's own in-tree record only (survey:
hidden_files/P201_SCOUT.md; design:
hidden_files/P201_DESIGN.md):

- The Part XI precedent puts the reconciliation battery
  at the second-last slice of a part (P-185 ahead of the
  P-186 gate), so Part XII's battery belongs here, beside
  the P-202 gate. The scout of the banked hub estate
  (P-187..P-200) proved the surface complete as composed
  cells: one registry, one browse road, nine censuses
  and three searches plus their census - every composable
  surface already composed, every aggregate axis taken.
  What no banked slice had done is judge the whole
  estate as ONE system: that the documents agree with
  each other, not merely with their own batteries.
- The scout's live agreement probe (a synthetic six-entry
  estate, run in the scout tree, no files kept) found NO
  disagreement anywhere in the banked surface, and this
  battery is the durable form of that probe.
- F-1, the banking hazard the scout named, is closed by
  measurement at build step 1: the merged router on this
  base carries BOTH the distinct-census road (P-199) and
  the schema-census road (P-200), declaration order
  breadth -> distinct -> schema -> search, both census
  imports present, OpenAPI naming exactly 17 hub
  operations on 16 paths. The union the P-200 slice doc
  declared is the union that banked.
- F-2, the shape asymmetry, is respected, not fixed:
  P-189's census and P-190's search predate the
  entries_considered / coverage_complete document shape.
  The battery maps their own shapes (count + embedded
  list for P-189; registry metadata only, nothing
  skippable, for P-190) and never asserts the P-193
  shape against them.
- One correction to the design text, recorded plainly:
  its section A3 says "16 schema tags"; the enumerated
  truth is 15 (P-187 entry + list, then one tag per
  slice P-188..P-200), which is also the scout's count.
  The battery pins the enumerated 15.

Base: 6d69720b59d666bdf90ec5e19226850e0aadf6b6 (P-200
banking record; banked P-001..P-200). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `tests/test_p201_hub_reconciliation.py` (new,
  fresh-authored, P-005 discipline) - 26 tests in four
  sections, the battery ONLY. No new src module, no new
  road, no migration:
  * Section A (presence / shape, static): the 14 slice
    docs HUB_REGISTRY..HUB_SCHEMA_CENSUS exist; all 15
    hub modules (14 truth + router) import and every
    document function the router calls exists; the 15
    schema tags are pairwise distinct and all -v1;
    OpenAPI names exactly the 17 hub operations on 16
    paths (the F-1 pin: distinct AND schema both
    present); the router declares the estate censuses
    in slice order before the searches, per-entry reads
    after, list then delete last; the migration head
    stays 0041; and the one-law objects hold - P-196 /
    P-197 / P-198 / P-199 / P-200's OUTCOMES IS P-193's
    object, every parse module's MAX_BROWSE_BYTES IS
    P-188's 16 MiB int, MAX_MATCHES is 100 in P-190 /
    P-191 / P-192 alike, and P-191's own OUTCOMES
    ({searched, unavailable, invalid}) is pinned as a
    different object from P-193's, not conflated.
  * Section B (cross-surface agreement, live estates
    EMPTY / FULL / MIXED): B1 the P-187 list document
    equals the list embedded in P-189 and in every
    parse census, count = estate size; B2 per-entry
    P-188 browse states tally to P-189's
    by_browse_state verbatim and the inspected set is
    the parse censuses' parsed set; B3 all six parse
    censuses (P-193 / P-196 / P-197 / P-198 / P-199 /
    P-200) agree identically on entries_considered,
    by_outcome, parsed_count and coverage_complete,
    each census_state the matching member of its own
    closed law for the estate class; B4 string volume
    agrees three ways (P-193 total = P-196 total =
    P-199 total, per estate and per row); B5 structure
    agrees (P-198 total_containers = P-196 objects +
    arrays; P-200 total_objects = P-196 total_objects;
    per-row object_count equal); B6 the duplicate
    census reconciles (embedded content census
    dict-equals a direct P-193 call; duplicate +
    unique + unidentified = count; groups match an
    independent grouping by verified checksum; the
    bare bundle is unidentified; one pack registered
    twice forms exactly one group of 2); B7 P-197
    per-row file bytes equal os.stat of the fixture
    files and total_verified_bytes is their sum over
    parsed rows, with P-198 row widths bounded by the
    estate widest; B8 the unified search is the union
    (probe estate splitting both / content-only /
    metadata-only: ids, matched_by sides, verbatim
    embedded documents, totals adding without double
    counting); B9 the P-194 census reconciles with
    P-192 (aggregator over a direct document equals
    the wrapper; totals, occurrence count,
    by_skip_outcome and the coverage / truncated
    verdicts equal an independent recomputation;
    SKIP_OUTCOMES never contains searched); B10 search
    refusals agree (empty / blank query and unknown
    kind refused with each module's own error type at
    unit level and 422 over HTTP on all four search
    roads; unknown kind on the list road also 422);
    B11 kind narrowing agrees (the kind filter narrows
    all three searches to the same subset; the
    censuses take no kind parameter - TypeError - and
    always cover the estate); B12 truncation agrees
    (on the 101-entry metadata-side TRUNCATION estate
    P-190 and P-192 cap at 100 carrying the true total
    101 and naming matches_truncated; the content
    side's true answer there is 101 named unavailable
    skips; P-194 inherits the capped verdict).
  * Section C (fences): C1 every hub read is a pure
    read - registry file and pack bytes hash-identical
    before / after every document function and every
    GET road; C2 no census or search retains content -
    no fixture payload string value, payload key name
    or digest of a value in any census document, and
    excerpts appear ONLY inside P-191 / P-192 match
    rows; C3 owner scoping holds on every surface -
    no document for owner A names an id of owner B,
    per-entry GET / browse / DELETE of B's id by A is
    404 over HTTP (and removes nothing), and every GET
    road without a bearer is 401; C4 the mutating
    roads are exactly the banked writes (POST entries,
    DELETE entry) and every census / search road is
    GET; C5 one TestClient session walks all 17
    operations on one estate and every HTTP document
    dict-equals the unit document.
  * Section D (carried items / gate readiness): D1
    the carried items are pinned absent - no hub
    history road, no retention / bulk-clear road, no
    binding-label surface in OpenAPI, the hub modules
    or their public names, and no clear-all verb on
    the store; D2 the no-orphan closure holds in both
    directions - every hub truth module is imported
    by the router and used by its banked road(s), and
    every one of the 17 handlers calls a banked truth
    function (registry store verbs included).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - exactly +1 entry.

## Defects found

None in the banked estate: every reconciliation claim
B1..B12 held on the merged tree exactly as the scout's
probe predicted. The battery's first run failed one of
its own expectations - D2's known-calls list omitted
the registry store verbs (get_entry / remove_entry)
that the DELETE handler lawfully calls instead of a
document function - a defect in this slice's test
arithmetic, corrected in the battery. Nothing in
P-187..P-200 was changed by this slice.

## Honest limitations

1. A reconciliation battery proves the banked surfaces
   agree with each other through their public
   contracts; it adds no capability, and Part XII still
   ends at the P-202 gate, which is not this slice.
2. The estates are the fixture pattern's shapes (four
   verified kinds, one bare bundle, one missing, one
   broken, one wrong-kind, one foreign owner, one
   metadata-side truncation); cap arithmetic inside
   each surface stays pinned by the slices' own
   batteries, which this battery runs beside as
   neighbours.
3. All judgements are point-in-time live reads (the
   estate's standing law); the pure-read pin covers
   the reads the battery runs, not concurrent writers.

## Carried forward, named open

- A binding label update stays named open (the
  registry's own law is remove-then-register, never a
  silent in-place update).
- History retention / bulk clear awaits Volmarr's
  ruling; none is invented here.
- A unified-search history surface stays named open:
  it presupposes a recording write and a store that no
  banked slice has taken - it is not a pure-read
  composition.
- Part XII gate is P-202; it follows in roadmap order
  after this slice banks.
