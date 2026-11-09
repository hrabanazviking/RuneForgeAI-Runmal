# Hub content census - content coverage (P-193) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's through
P-192's were - see `hidden_files/P193_SCOUT.md` and
`P193_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-191's record names a hub content
census open for a later Part XII slice, and the P-192
scout's warning fixes its honest shape - a query-free
census over parse outcomes alone would merely recount
P-189's browse axis (every layer's inspect road stands
on its parse road), so this census measures what P-189
has no field for: the verified payloads' CONTENT
VOLUME. Nothing here is roadmap verbatim.

## What was built

- `src/runmal/hub/content_census.py` - the census truth
  layer: `content_census_document(entries)` (schema
  `runmal-p193-hub-content-census-v1`) returns:
  - `list` - P-187's `list_document` composed VERBATIM
    and embedded whole: its count, `by_kind` and
    `by_locator_state` arithmetic is the registry's
    own, never recomputed under a second law;
  - `entries` - one row per entry in store order: the
    P-187 entry row verbatim plus `locator_state`
    (judged live), `outcome` under the closed
    `OUTCOMES` law (`parsed` / `unavailable` /
    `invalid`), `verified_content_sha256` (the owning
    parse road's own; empty for a bare preset bundle
    and for any non-parsed row), `string_value_count`
    and `string_char_count` (the verified payload's
    string values and their total length under P-191's
    walk law; zero for a non-parsed row), and `error`
    (the owning road's refusal verbatim for an invalid
    row). No content text and no payload appear
    anywhere in the document;
  - `by_outcome` - every outcome in the closed law,
    zero-filled, summed from the rows' own values;
  - `by_kind_content` - for every kind in `HUB_KINDS`,
    zero-filled: `entries`, `parsed`, `string_values`
    and `string_chars`, summed from the rows, so the
    kind axis always sums to the totals;
  - `total_string_values` / `total_string_chars` over
    parsed rows, and `largest_content_entry` (the
    parsed entry with the most string characters,
    first in store order on a tie; null when nothing
    parsed);
  - coverage in P-191's form: `count` =
    `entries_considered`, `parsed_count`, and
    `coverage_complete` false whenever any entry was
    not parsed - `count` always equals parsed plus
    unavailable plus invalid;
  - `census_state` under the closed
    `CONTENT_CENSUS_STATES` law, judged on the content
    axis: `no_entries` / `no_content` / `some_content`
    / `all_content`;
  - composition: each entry is judged under P-188's
    locator law and its imported 16 MiB bound, then
    parsed through the owning layer's OWN verified
    parse road, dispatched exactly as P-191 dispatches
    (`parse_pack` for the three pack kinds, payload
    members `lorebook` / `items` / `scenario`;
    `parse_share` for the preset bundle). This module
    contains no pack parser of its own.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/content-census`, bearer-gated and
  owner-scoped exactly like the census road. The
  subject is the caller's own estate, so no foreign
  entry can appear and no foreign existence can leak.

## The laws this slice keeps

- The distinctness law, stated in the document itself:
  P-189 counts inspect verdicts and checksum claims
  and measures no content; this census measures
  content volume. Parsed counts will usually agree
  with P-189's inspected counts because inspect stands
  on parse - that agreement is expected, stated on
  every document, and is not the new fact; the volume
  axes are.
- The walk law (P-191's, carried in): string VALUES
  only - dict keys are structure, non-string values
  are not text, the pack envelope lives outside the
  payload member, registry metadata is never counted,
  and any value under a `content_sha256` key is the
  pack's identity, not its content, its subtree never
  counted.
- Pure read: the census writes nothing - the registry
  file and every pack file are byte-unchanged by a
  census (pinned in the battery) - and it imports,
  installs, copies and grants nothing. No content is
  retained or returned: counts, entry data and
  verified checksums only, never an excerpt (the
  P-183 law).
- The cost, stated plainly on the document: a census
  parses every ready entry through its own layer's
  verified parse road, so it reads pack files, each
  under the 16 MiB browse bound. An oversize, corrupt
  or wrong-kind pack is an `invalid` row, never a
  census failure.
- The checksum law: an entry's checksum stays the
  caller's CLAIM. The census carries the parse road's
  verified checksum beside it; counting a claim never
  upgrades it to verified.
- Named open for later Part XII: a unified-search
  census (the P-184 shape) once P-192's unified search
  is banked in the merged tree - it was not taken here
  because P-192 is not in this slice's base and its
  module is never copied unbanked. Signing /
  attestation stays declined (no key machinery is
  banked) and friend-instance exchange stays declined
  (no banked pack transport exists). Entry lifecycle
  depth stays as P-187 left it: remove-then-register,
  never a silent overwrite.
- VX-59's shape stands: no central store, no
  catalogue, no creator profiles.
- The P-186 carried items are untouched, exactly as
  recorded: the binding label update stays named
  open, automatic retention / bulk clear of history
  still awaits Volmarr's ruling (none invented), and
  unified-search history stays named open.
- No migration (head stays 0041); no existing module
  changed except the hub router; no README touched.

## Tests

- `tests/test_p193_hub_content_census.py` - see
  `hidden_files/P193_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.
