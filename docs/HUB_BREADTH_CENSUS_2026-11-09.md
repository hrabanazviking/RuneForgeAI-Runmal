# P-198 - Hub Breadth Census (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
XII | The Hub, Sovereign Shape | P-187 - P-202 - and no
verbatim P-198 entry exists anywhere in it. This slice
scope is therefore DERIVED, not roadmap-verbatim, from
Runmal's own in-tree record only (survey:
hidden_files/P198_SCOUT.md; design:
hidden_files/P198_DESIGN.md):

- P-196's content-shape census measures the DEPTH axis
  of verified payloads - node counts by type, key
  totals and max_depth - and discards how WIDE any
  single container spreads. No banked hub document
  carries a single container-size field: a payload
  holding one array of five hundred items and a
  payload holding five hundred arrays of one item sit
  in the same P-196 totals class, yet their breadth
  is opposite. The width of the widest container, the
  per-container size distribution and the summed
  breadth of an estate exist in no banked document.
- The scout verified this against the banked estate
  (P-187 kinds/locators, P-189 verdicts/claims, P-193
  string volume, P-194 one query's answer, P-195
  verified-identity groups, P-196 node shape/depth,
  P-197 file bytes) and weighed and declined WITH
  REASONS: locator-sharing census (derivable from the
  P-187 list; shadows P-195 at an unverified layer),
  registration-age census (derivable from list
  created_at values, and needs a moving now),
  claim-coverage decomposition (a recount of P-189),
  metadata completeness (derivable from P-187 list),
  envelope / manifest census (no closed cross-kind
  law banked), reconciliation battery / part gate
  (premature mid-part - Part XII ends at P-202),
  signing (no key machinery banked), friend-instance
  exchange (no banked transport), and the VX-59
  ruled-out forms (central store, catalogue, creator
  profiles).

Base: 1c18009d5bb3500cb91425afe7d22f8f8ce0e946 (P-197
banking record; banked P-001..P-197). Migration: NONE
- head stays 0041, no 0042, battery-pinned.

## The breadth law (stated up front)

1. Every CONTAINER in a verified payload (every dict
   and every list) has a WIDTH - its immediate child
   count. A dict's width is its counted keys: a member
   under a content_sha256 key is excluded WHOLE,
   exactly as P-196 excludes it - it adds nothing to
   the width and its value subtree is never walked
   (the pack's identity is not its breadth). A list's
   width is its length. Scalars are not containers.
   The payload root counts as a container when it is
   a dict or a list.
2. Breadth is measured over PARSED rows only: only a
   payload its owning layer's own verified parse road
   verified is walked. Per payload: container count,
   summed breadth, widest container width, widest
   object width, widest array width (each widest 0
   when no container of that kind exists).
3. The bucket law is closed (BREADTH_BUCKETS) over the
   containers of parsed rows: empty (width 0), narrow
   (1 to 2), medium (3 to 5), wide (6 to 10), vast
   (11 and over); a width exactly on an edge belongs
   to the higher bucket, judged by container_bucket.
4. No silent omission: every entry ends parsed, or is
   named by its row outcome under P-193's imported
   OUTCOMES law (unavailable - locator not ready;
   invalid - unreadable, over the bound with this
   module's own error text, not valid JSON on the
   bundle road, or the owning road's refusal carried
   verbatim), and coverage_complete is false whenever
   any entry was not parsed; count always equals
   parsed plus unavailable plus invalid.
5. No content is retained or returned: counts, entry
   data and verified checksums only - never a key
   name, never a value, never an excerpt, never a
   payload field (the P-183 law).

## What landed

- src/runmal/hub/breadth_census.py (new) - the truth
  layer: breadth_census_document(entries) composes
  P-187's list_document verbatim (embedded whole as
  list), then parses each ready entry through its
  owning layer's own verified parse road, dispatched
  exactly as P-193 dispatches, and walks its verified
  payload under the breadth law. Schema
  runmal-p198-hub-breadth-census-v1. Rows carry the
  entry verbatim plus locator_state, outcome,
  verified_content_sha256, error and the breadth
  fields breadth_container_count, breadth_total,
  widest_container_width, widest_object_width and
  widest_array_width (zero for non-parsed rows).
  Axes: count / entries_considered / parsed_count /
  coverage_complete; by_outcome zero-filled;
  by_kind_breadth zero-filled under HUB_KINDS
  (entries, parsed, containers, breadth and
  widest_container_width as a max per kind);
  by_breadth_bucket zero-filled under the closed
  BREADTH_BUCKETS law over the containers of parsed
  rows; total_containers; total_breadth;
  widest_container_width (the estate max); widest_entry
  over parsed rows (first in store order on a tie;
  null when nothing parsed); max_browse_bytes;
  kind_formats; NOTES. census_state under the closed
  BREADTH_CENSUS_STATES law, judged on the parsed
  axis: no_entries / no_breadth / some_breadth /
  all_breadth.
- src/runmal/hub/router.py - ONE new road:
  GET /hub/breadth-census, declared directly after
  the size-census road, bearer-gated and owner-scoped
  exactly like the content-census road. Every census
  state answers 200 as data.
- tests/test_p198_hub_breadth_census.py - the battery
  (20 tests): empty and full estates with axes summed
  exactly against an independent walk, hand-pinned
  breadth statistics on literal payloads (including
  the content_sha256 whole-exclusion), the bucket law
  pinned at every edge, the mixed estate, all-missing,
  bare bundle, wrong-kind and oversize rows, the
  widest entry with the tie law, the distinctness
  fence, no content text, pure read, owner scoping,
  HTTP 200 / 401, migration head 0041 and the
  imported-laws identity pins.
- This doc and one clean-room log entry.

## Distinctness, stated plainly

P-189 counts verdicts and claims; P-193 counts payload
string volume; P-194 counts one query's answer; P-195
groups by verified identity; P-196 counts payload node
shape and depth; P-197 measures the file as stored.
This census measures how wide each verified payload's
containers spread - an axis none of them carries, and
carries none of theirs (the battery fence pins the
absences). Its container count necessarily equals
P-196's object plus array counts on the same estate -
the same containers, counted there and measured here -
and that agreement is expected, not the new fact.

## Honest boundaries

A breadth census parses every ready entry, so it reads
pack files, each verified under the 16 MiB bound; an
oversize, corrupt or wrong-kind pack is an invalid row,
never a census failure. The census writes nothing,
registers nothing, records nothing and grants nothing.
An entry's registered checksum stays the caller's claim.
Signing and friend-instance exchange stay declined.
There is no central store, no catalogue and no creator
profile here (VX-59). Carried items untouched: binding
label update (unbind-then-bind law), history retention
/ bulk clear (awaits the ruling of Volmarr), and
unified-search history. Named open after this slice:
the reconciliation / gate battery beside P-202.
