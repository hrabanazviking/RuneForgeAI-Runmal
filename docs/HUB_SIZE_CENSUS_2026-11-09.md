# P-197 - Hub Byte-Size Census (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
XII | The Hub, Sovereign Shape | P-187 - P-202 - and no
verbatim P-197 entry exists anywhere in it. This slice
scope is therefore DERIVED, not roadmap-verbatim, from
Runmal own in-tree record only (survey:
hidden_files/P197_SCOUT.md; design:
hidden_files/P197_DESIGN.md):

- No banked hub document carries a single field for how
  much storage an owner estate occupies. Every hub
  surface stats each ready pack file to enforce the
  16 MiB browse bound and discards the size: P-187
  counts kinds and locator states, P-189 counts browse
  verdicts and checksum claims, P-193 counts payload
  string values and characters, P-194 aggregates one
  query answer, P-195 groups entries by verified
  identity, P-196 counts payload node shapes. A locator
  is not a size, so the estate byte footprint is not
  derivable from any banked document - it exists only
  on the filesystem at read time.
- The P-196 scout declined this cell as the weaker one
  beside content shape and named it a lawful later
  cell. P-196 banks ahead of this slice; shape first,
  size now is the order that scout stated.
- This slice takes that cell in the P-193/P-196 shape:
  a query-free estate aggregate composing the banked
  verified parse roads directly (as P-193 and P-196
  do), under P-193 imported OUTCOMES law and P-188
  imported bound, measuring the FILE each entry came
  from.
- Weighed and declined WITH REASONS in the scout:
  locator-sharing census (derivable from P-187 list,
  which carries every locator whole; shadows P-195 at
  an unverified layer), registration-age census
  (derivable from P-187 list created_at values, and
  needs a moving now), claim-coverage decomposition
  (a recount of P-189), metadata completeness
  (derivable from P-187 list), envelope / manifest
  census (no closed cross-kind law banked),
  reconciliation battery / part gate (premature
  mid-part - Part XII ends at P-202), signing (no key
  machinery banked), friend-instance exchange (no
  banked transport), and the VX-59 ruled-out forms
  (central store, catalogue, creator profiles).

Base: ff191c1aaafa3b2c7c0e07ab4f75469b80254cc1 (P-195
banking record; banked P-001..P-195, PART XII OPEN).
P-196 (team-01, hub content-shape census) banks ahead
of this slice and is NOT in this base; the only file
both slices touch is src/runmal/hub/router.py (one
additive import + one additive road each), reconciled
by the keeper at banking. Migration: NONE - head stays
0041, no 0042, battery-pinned.

## The byte law (stated up front)

1. file_bytes is a FILESYSTEM fact: the stat size of
   the file at a ready locator, carried for every ready
   row whether or not its pack verifies - an oversize
   or corrupt file still occupies its bytes, and hiding
   them would understate the estate. It is null for any
   row whose locator is not ready or whose stat fails:
   no file, no number, never faked.
2. The VERIFIED axes sum parsed rows only:
   total_verified_bytes, per-kind verified bytes, the
   size buckets, and largest / smallest never present a
   byte as verified content bytes unless its pack
   verified through its own layer road, so
   total_verified_bytes is always at most
   total_file_bytes. The two halves never mix
   (battery-pinned on a mixed estate).
3. Bytes are per FILE and never deduplicated: two
   registrations of byte-equal copies count their bytes
   twice, because two files occupy them twice. Whether
   two entries hold the same verified content is P-195
   ground and is never stated here.
4. No silent omission: every entry ends parsed, or is
   named by its row outcome under P-193 imported
   OUTCOMES law (unavailable - locator not ready,
   file_bytes null; invalid - stat failed, over the
   bound with this module own error text and file_bytes
   still carried, not valid JSON on the bundle road, or
   the owning road refusal carried verbatim), and
   coverage_complete is false whenever any entry was
   not parsed; count always equals parsed plus
   unavailable plus invalid.
5. No content is retained or returned: sizes, counts,
   entry data and verified checksums only - never a
   byte of file content, never an excerpt, never a
   payload field (the P-183 law).

## What landed

- src/runmal/hub/size_census.py (new) - the truth
  layer: size_census_document(entries) composes P-187
  list_document verbatim (embedded whole as list),
  then stats and parses each ready entry through its
  owning layer own verified parse road, dispatched
  exactly as P-193 dispatches. Schema
  runmal-p197-hub-size-census-v1. Rows carry the entry
  verbatim plus locator_state, outcome, 
  verified_content_sha256, file_bytes (int or null)
  and error. Axes: count / entries_considered /
  parsed_count / measured_count / coverage_complete;
  by_outcome zero-filled; by_kind_size zero-filled
  under HUB_KINDS (entries, parsed, measured, bytes,
  verified_bytes per kind); by_size_bucket zero-filled
  under the closed SIZE_BUCKETS law over parsed rows
  (tiny under 1024, small 1024 to under 16384, medium
  16384 to under 262144, large 262144 to under
  1048576, huge 1048576 and over; an edge size belongs
  to the higher bucket, judged by size_bucket);
  total_file_bytes (measured rows); total_verified_
  bytes (parsed rows); largest_file_entry and
  smallest_file_entry over parsed rows (first in store
  order on a tie; null when nothing parsed);
  max_browse_bytes; kind_formats; NOTES. census_state
  under the closed SIZE_CENSUS_STATES law, judged on
  the parsed axis: no_entries / no_sizes / some_sizes
  / all_sizes.
- src/runmal/hub/router.py - ONE new road:
  GET /hub/size-census, bearer-gated and owner-scoped
  exactly like the content-census road. Every census
  state answers 200 as data.
- tests/test_p197_hub_size_census.py - the battery
  (20 tests): empty and full estates, the bucket law
  hand-pinned at every edge, the mixed estate pinning
  both byte laws, all-missing, bare bundle, wrong-kind
  and oversize rows carrying their bytes, duplicate
  copies counted twice, largest / smallest with the
  tie law, the distinctness fence, no content text,
  pure read, owner scoping, HTTP 200 / 401, migration
  head 0041 and the imported-laws identity pins.
- This doc and one clean-room log entry.

## Distinctness, stated plainly

P-189 counts verdicts and claims; P-193 counts payload
string volume; P-194 counts one query answer; P-195
groups by verified identity; P-196 counts payload node
shape. This census measures the file as stored -
envelope, manifest, formatting and payload together -
an axis none of them carries, and carries none of
theirs (the battery fence pins the absences).

## Honest boundaries

A size census parses every ready entry, so it reads
pack files, each verified under the 16 MiB bound; an
oversize, corrupt or wrong-kind pack is an invalid row,
never a census failure. The census writes nothing,
registers nothing, records nothing and grants nothing.
An entry registered checksum stays the caller claim.
Signing and friend-instance exchange stay declined.
There is no central store, no catalogue and no creator
profile here (VX-59). Carried items untouched: binding
label update (unbind-then-bind law), history retention
/ bulk clear (awaits the ruling of Volmarr), and
unified-search history. Named open after this slice:
the reconciliation / gate battery beside P-202.
