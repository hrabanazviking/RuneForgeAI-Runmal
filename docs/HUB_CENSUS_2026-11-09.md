# Hub census over the registry estate (P-189) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's and
P-188's were - see `hidden_files/P189_SCOUT.md` and
`P189_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-187's list document is a per-list
primitive (counts for any list it is handed, no
classification, no browse or checksum axis), P-188's
browse is per-entry only, and the house order -
foundation, per-item surface, estate census (the
P-169 / P-170 / P-171 workspaces sequence, the
scenario census family) - names the census as the
next honest Part XII cell. Nothing here is roadmap
verbatim.

## What was built

- `src/runmal/hub/census.py` - the census truth layer:
  `census_document(entries)` (schema
  `runmal-p189-hub-census-v1`) returns:
  - `list` - P-187's `list_document` composed VERBATIM
    and embedded whole: its count, `by_kind` and
    `by_locator_state` arithmetic is the registry's
    own, never recomputed under a second law;
  - `entries` - one row per entry in store order: the
    P-187 entry row verbatim plus that entry's P-188
    browse verdict carried verbatim (`locator_state`,
    `browse_state`, `verified_content_sha256`,
    `checksum_match`, `error`). The inspection
    document itself is not embedded - it stays on
    P-188's per-entry browse road;
  - `by_browse_state` - every state in P-188's closed
    `BROWSE_STATES` law, zero-filled, summed from the
    rows' own values;
  - `by_checksum_match` - closed keys `match` /
    `mismatch` / `undetermined`, zero-filled, summed
    from the rows' `checksum_match` verbatim (null is
    undetermined: no claim, no verified checksum, or
    a browse that never reached inspection - never
    separated by guessing why);
  - `census_state` under the closed `CENSUS_STATES`
    law, judged on the browse axis: `no_entries` /
    `none_inspected` / `some_inspected` /
    `all_inspected`.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/census`, bearer-gated and owner-scoped
  exactly like the list road. The subject is the
  caller's own estate, so no foreign entry can appear
  and no foreign existence can leak.

## The laws this slice keeps

- Pure read: the census writes nothing - the registry
  file and every pack file are byte-unchanged by a
  census (pinned in the battery) - and it imports,
  installs, copies and grants nothing.
- The cost, stated plainly: a census browses every
  ready entry through P-188's own law, so it reads
  pack files, each under the 16 MiB browse bound. An
  oversize, corrupt or wrong-kind pack is an
  `invalid` row, never a census failure.
- The checksum law: an entry's checksum stays the
  caller's CLAIM. The census counts the browse
  documents' verdicts; counting a claim never
  upgrades it to verified.
- Named open, on this record: hub search over entries
  (the list road filters by kind only) for a later
  Part XII slice. Signing / attestation stays
  declined (no key machinery is banked) and
  friend-instance exchange stays declined (no banked
  pack transport exists) - census precedes exchange
  as index and browse did. Entry lifecycle depth
  stays as P-187 left it: remove-then-register, never
  a silent overwrite; no edit road is invented here.
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

- `tests/test_p189_hub_census.py` - see
  `hidden_files/P189_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.
