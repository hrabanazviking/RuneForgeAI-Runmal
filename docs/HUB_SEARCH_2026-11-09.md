# Hub search over entries (P-190) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's, P-188's
and P-189's were - see `hidden_files/P190_SCOUT.md` and
`P190_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-189's banking record names hub search
over entries open for a later Part XII slice and fixes
the house order - census precedes search, as P-171
preceded P-178. The registry's own fields support a
literal search over entry data; they do not support
content or semantic search, and none is claimed here.
Nothing here is roadmap verbatim.

## What was built

- `src/runmal/hub/search.py` - the search truth layer:
  `search_document(entries, query, kind=None)` (schema
  `runmal-p190-hub-search-v1`) returns the query verbatim
  (stripped), the optional kind filter, `matches` (rows
  in store order), `match_count`, `total_matches`,
  `truncated`, `by_matched_field`, `searched_fields`,
  the embedded `list`, `kind_formats` and `notes`, with
  `search_state` under the closed `SEARCH_STATES` law:
  `no_matches` / `matches` / `matches_truncated`.
  - A match is LITERAL only: the query casefolded as a
    substring of a searched field's casefolded value
    (the P-178 match law). The searched fields are the
    closed `SEARCH_FIELDS` law - `title`, `locator`,
    `note`, `kind`, `format` - and every row carries
    `matched_fields`, the fields that matched, in that
    law's order.
  - Composition verbatim: the capped matched entries
    are handed to P-187's `list_document` and that
    document is embedded whole as `list`; the rows are
    its own rows (entry verbatim, `locator_state`
    judged live by P-187 itself) plus `matched_fields`,
    so `list.count` always equals `match_count` and the
    by-kind / by-locator-state counts are the
    registry's own arithmetic over the matched set.
  - Cap honesty (the P-178 law): `MAX_MATCHES` is 100;
    `total_matches` carries the true total and
    `truncated` names a capped answer, never dressed
    as complete. `by_matched_field` is zero-filled
    under `SEARCH_FIELDS` and sums the returned rows'
    `matched_fields` - a row matching two fields counts
    under both, so the axis sums fields, not rows.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/search?q=&kind=`, bearer-gated and
  owner-scoped exactly like the list road (the router
  hands the search only the caller's own entries).
  A blank or missing query and an unknown kind answer
  422 with the search's own refusal.

## The laws this slice keeps

- Honest scope: this search reads registry metadata
  only. Pack CONTENTS are never searched - the search
  opens no pack and reads no file at any locator (the
  locator state is P-187's stat-only judgement), so a
  word inside a pack is not findable here; content
  stays behind P-188's per-entry browse and each pack
  layer's own inspect road. The claimed
  `content_sha256` is never searched (it is the
  caller's claim, and not search text), and neither are
  `id`, `owner_id` or `created_at`. There is no fuzzy,
  semantic, ranked or scored matching: no such
  machinery is banked, and none is faked.
- Query law: the query is required and stripped; an
  empty or blank query is refused plainly (422 on the
  road), never treated as match-everything.
- Pure read: the search writes nothing - the registry
  file is byte-unchanged by a search (pinned in the
  battery) - and it imports, installs, copies and
  grants nothing.
- Owner scoping: a foreign owner's entries are never
  in the searched list, so they cannot match, appear,
  or leak through any count (unit + HTTP pinned).
- Named open / declined, on this record: pack-content
  search (not supported by the registry; it would need
  its own slice with its own cost law), semantic or
  ranked search (no machinery), and entry lifecycle
  depth (P-187's remove-then-register law stands).
  Signing / attestation stays declined (no key
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

- `tests/test_p190_hub_search.py` - see
  `hidden_files/P190_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.
