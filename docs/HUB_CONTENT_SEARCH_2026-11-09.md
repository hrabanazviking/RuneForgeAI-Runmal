# Hub pack-content search (P-191) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's through
P-190's were - see `hidden_files/P191_SCOUT.md` and
`P191_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-190's slice doc names pack-content
search open for its own slice with its own cost law -
the registry holds metadata only, so content search
must compose the pack layers' own roads and state its
coverage honestly. Inspection documents alone cannot
carry it: they hold names and manifests, never payload
bodies (scout, verified against a minted pack). Nothing
here is roadmap verbatim.

## What was built

- `src/runmal/hub/content_search.py` - the truth layer:
  `content_search_document(entries, query, kind=None)`
  (schema `runmal-p191-hub-content-search-v1`) returns
  the query verbatim (stripped), the optional kind
  filter, `matches`, `match_count`, `total_matches`,
  `truncated`, `entries_considered`, `entries_searched`,
  `skipped_entries`, `coverage_complete`,
  `max_browse_bytes`, the embedded `list`,
  `kind_formats` and `notes`, with `search_state` under
  the closed `SEARCH_STATES` law: `no_matches` /
  `matches` / `matches_truncated`.
  - Composition, verbatim roads only: bytes are read
    once per ready entry, under P-188's locator law
    and P-188's size bound (imported - one bound law),
    then dispatched by kind to the owning layer's OWN
    verified parse road - `parse_pack` for the three
    pack kinds (the road each `inspect_pack` itself
    stands on; payload members `lorebook` / `items` /
    `scenario`) and `parse_share` for the preset
    bundle (the road P-188's browse composes; the
    bundle it returns is the payload). Each parse road
    verifies format, manifest, checksum and payload
    before any text is searched. This module contains
    no pack parser of its own.
  - A match is LITERAL only: the query casefolded as a
    substring of a searched string value's casefolded
    form (the P-178 match law). Searched text is every
    string value in the verified payload. A match row
    carries `occurrences` (total casefolded substring
    occurrences across all searched values), `excerpt`
    (40 characters either side of the first occurrence
    in the first matching value - the P-180 context
    law) and `verified_content_sha256` (the checksum
    the owning road itself verified; empty for a bare
    preset bundle, whose road verifies none).
  - No silent omission (the P-180 law): every
    considered entry ends as searched or as a named
    skip in `skipped_entries` under the closed
    `OUTCOMES` law - `unavailable` (locator not ready;
    no read attempted) or `invalid` (unreadable, over
    the size bound, not valid JSON on the bundle road,
    or the owning road's refusal carried verbatim).
    `coverage_complete` is false whenever any entry
    was skipped, and `entries_considered` always
    equals `entries_searched` plus the skip count.
  - Cap honesty (the P-190 law): `MAX_MATCHES` is 100;
    `total_matches` carries the true total and
    `truncated` names a capped answer. The capped
    matched entries are handed to P-187's
    `list_document` and embedded whole as `list`, so
    `list.count` always equals `match_count` and the
    by-kind / by-locator-state counts are the
    registry's own arithmetic over the matched set.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/content-search?q=&kind=`, bearer-gated and
  owner-scoped exactly like the search road. A blank
  or missing query and an unknown kind answer 422 with
  the search's own refusal; every outcome answers 200
  as data, skips included.

## The laws this slice keeps

- The cost law, stated in the document itself: a
  content search reads and verifies every ready pack
  in the searched estate, each under the 16 MiB bound
  - O(estate bytes). That is the price of searching
  contents the registry does not hold; P-190's
  metadata search stays the cheap road.
- Honest scope: registry metadata is never searched
  here (that is P-190's road); the pack envelope
  (manifest and provenance) is never searched; values
  under a `content_sha256` key are the pack's identity,
  not its content, and are never searched; dict keys
  are structure, not content. There is no fuzzy,
  semantic, ranked or scored matching: no such
  machinery is banked, and none is faked.
- The entry's registered checksum stays the caller's
  claim: it rides on the row verbatim, is never
  searched, and is never upgraded - the verified
  checksum beside it is the owning road's own.
- Query law: the query is required and stripped; an
  empty or blank query is refused plainly (422 on the
  road), never treated as match-everything. The kind
  filter narrows the estate before searching, so an
  unsearched kind's entries are not considered, not
  skipped and not counted.
- Pure read: the search writes nothing - the registry
  file and every pack file are byte-unchanged by a
  search (pinned in the battery) - and it imports,
  installs, copies and grants nothing.
- Owner scoping: a foreign owner's entries are never
  in the searched list, so they cannot match, appear,
  be skipped, or leak through any count (unit + HTTP
  pinned).
- Named open for later Part XII: unified hub search
  (metadata + content in one document - it presupposes
  this slice, as P-182 presupposed P-180) and a hub
  content census (the house order puts content search
  before its census, as P-180 before P-183). Entry
  lifecycle depth stays declined, not open: removal
  already exists banked (P-187) and an update road
  would contradict the banked remove-then-register
  law. Signing / attestation stays declined (no key
  machinery is banked) and friend-instance exchange
  stays declined (no banked pack transport exists).
- VX-59's shape stands: no central store, no
  catalogue, no creator profiles.
- The P-186 carried items are untouched, exactly as
  recorded: the binding label update stays named open,
  automatic retention / bulk clear of history still
  awaits Volmarr's ruling (none invented), and
  unified-search history stays named open.
- No migration (head stays 0041); no existing module
  changed except the hub router; no README touched.

## Tests

- `tests/test_p191_hub_content_search.py` - see
  `hidden_files/P191_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.
