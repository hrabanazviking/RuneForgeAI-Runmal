# Hub content-shape census - payload structure (P-196) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in
the repo; this slice's scope is DERIVED, as P-187's
through P-195's were - see `hidden_files/P196_SCOUT.md`
and `P196_DESIGN.md` in the team worktree. The
derivation, stated plainly: every banked hub surface
that opens a pack measures its payload as TEXT only -
P-191 searches string values and P-193 counts string
values and their characters, both under a walk law
that excludes dict keys and non-string values by name -
and no banked document measures the verified payloads'
STRUCTURE: node types, keys, containers or depth.
Nothing here is roadmap verbatim.

## What was built

- `src/runmal/hub/content_shape_census.py` - the census
  truth layer: `content_shape_census_document(entries)`
  (schema `runmal-p196-hub-content-shape-census-v1`)
  returns:
  - `list` - P-187's `list_document` composed VERBATIM
    and embedded whole: its count, `by_kind` and
    `by_locator_state` arithmetic is the registry's
    own, never recomputed under a second law;
  - `entries` - one row per entry in store order: the
    P-187 entry row verbatim plus `locator_state`
    (judged live), `outcome` under P-193's imported
    `OUTCOMES` law (`parsed` / `unavailable` /
    `invalid`), `verified_content_sha256` (the owning
    parse road's own; empty for a bare preset bundle
    and for any non-parsed row), the shape counts
    (`object_count`, `array_count`, `string_count`,
    `number_count`, `boolean_count`, `null_count`,
    `node_count`, `key_count`, `max_depth`; all zero
    for a non-parsed row), and `error` (the owning
    road's refusal verbatim for an invalid row). No
    key name, no value and no payload appear anywhere
    in the document;
  - `by_outcome` - every outcome in the imported law,
    zero-filled, summed from the rows' own values;
  - `by_kind_shape` - for every kind in `HUB_KINDS`,
    zero-filled: `entries`, `parsed`, `objects`,
    `arrays`, `strings`, `numbers`, `booleans`,
    `nulls`, `nodes`, `keys` and `max_depth`, summed
    from the parsed rows, so the kind axis always sums
    to the totals;
  - `by_node_type` (the six node totals under the
    closed `NODE_TYPES` law) and the totals
    themselves, the estate `max_depth`, and
    `deepest_entry` (the parsed entry with the
    greatest depth, first in store order on a tie;
    null when nothing parsed);
  - coverage in P-193's form: `count` =
    `entries_considered`, `parsed_count`, and
    `coverage_complete` false whenever any entry was
    not parsed - `count` always equals parsed plus
    unavailable plus invalid;
  - `census_state` under the closed
    `SHAPE_CENSUS_STATES` law, judged on the parsed
    axis: `no_entries` / `no_shape` / `some_shape` /
    `all_shape`;
  - composition: each entry is judged under P-188's
    locator law and its imported 16 MiB bound, then
    parsed through the owning layer's OWN verified
    parse road, dispatched exactly as P-193 dispatches
    (`parse_pack` for the three pack kinds, payload
    members `lorebook` / `items` / `scenario`;
    `parse_share` for the preset bundle). This module
    contains no pack parser of its own.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/content-shape-census`, bearer-gated and
  owner-scoped exactly like the content-census road.
  The subject is the caller's own estate, so no
  foreign entry can appear and no foreign existence
  can leak.

## The laws this slice keeps

- The walk law: every NODE in the verified payload
  counts exactly once under the closed `NODE_TYPES`
  law (`object` / `array` / `string` / `number` /
  `boolean` / `null`) - a boolean is never counted as
  a number; every dict KEY counts once toward the key
  count (keys are structure - counted as counts only,
  key names never returned); `max_depth` is the
  deepest nesting with the payload root at depth 1;
  a member under a `content_sha256` key is excluded
  WHOLE, neither the key nor its subtree counted
  (P-191's identity exclusion carried to the pair);
  the pack envelope lives outside the payload member
  and is never walked.
- The distinctness law, stated in the document itself:
  P-189 counts browse verdicts and checksum claims,
  P-193 counts string VOLUME, P-194 counts one query's
  answer and P-195 groups entries by verified
  identity; this census measures STRUCTURE. Its
  string count is a NODE count, never a length: it
  necessarily equals P-193's string-value count on the
  same estate (the same nodes, counted not measured) -
  that agreement is expected, stated on every
  document, and is not the new fact; the other five
  node types, the keys, the node totals and the depth
  axes are. No character is ever counted here, no
  entry is ever grouped, and the per-row verified
  checksum is never compared across rows.
- Pure read: the census writes nothing - the registry
  file and every pack file are byte-unchanged by a
  census (pinned in the battery) - and it imports,
  installs, copies and grants nothing. No content is
  retained or returned: counts, entry data and
  verified checksums only (the P-183 law).
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
- Named open for later Part XII: a storage / byte-size
  census over the locator files (declined here as the
  weaker cell - file bytes measure the file, not the
  verified payload) and the reconciliation / gate
  battery beside P-202 (premature mid-part). Signing /
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
- Banking note: P-195 (hub duplicate census) banks
  ahead of this slice; both slices add one module, one
  router import and one router road to the hub, and
  the keeper reconciles the additive router delta.

## Tests

- `tests/test_p196_hub_content_shape_census.py` - see
  `hidden_files/P196_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.
