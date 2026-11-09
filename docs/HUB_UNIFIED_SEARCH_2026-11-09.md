# Unified hub search (P-192) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's through
P-191's were - see `hidden_files/P192_SCOUT.md` and
`P192_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-190 banked the hub metadata search
and P-191 the hub pack-content search, and P-191's
record names unified hub search open. An owner hunting
one word otherwise runs two searches as two separate
documents - two point-in-time judgements that can
disagree - and merges the answers by hand; no document
says, for one entry, whether the metadata spoke, the
content spoke, or both did. The workspace line took
exactly this cell at exactly this point (P-178 + P-180
-> P-182). Nothing here is roadmap verbatim.

Base and banking note: this slice was built on the
P-190 banking record (banked P-001..P-190). P-191 banks
in parallel ahead of it; the only file both slices
touch is `src/runmal/hub/router.py` (one additive road
each), reconciled by the keeper at banking.

## What was built

- `src/runmal/hub/unified_search.py` - the unified
  search truth layer:
  `unified_search_document(entries, query, kind=None)`
  (schema `runmal-p192-hub-unified-search-v1`) returns
  the query verbatim (stripped), the optional kind
  filter, `matches` (union rows in store order),
  `match_count`, `total_matches`, `truncated`,
  `coverage_complete`, the count axes
  (`metadata_match_count`, `content_match_count`,
  `both_count`), both source totals
  (`metadata_total_matches`, `content_total_matches`),
  the coverage fields carried from the content search
  (`entries_considered`, `entries_searched`,
  `skipped_entries`), both banked documents embedded
  whole (`metadata_search`, `content_search`), the
  embedded `list`, `kind_formats` and `notes`, with
  `search_state` under the closed `SEARCH_STATES` law:
  `no_matches` / `matches` / `matches_truncated`.
  - Composition verbatim, no new search law: the same
    entry list, cleaned query and kind are handed to
    P-190's `search_document` and P-191's
    `content_search_document`; both documents are
    embedded whole and their match laws are unchanged.
    The query and kind are validated FIRST under this
    module's own law (`HubUnifiedSearchError`) so the
    road answers one refusal shape.
  - The union is by entry id, in store order. Each row
    carries `matched_by` under the closed `MATCHED_BY`
    law (`metadata` / `content` / `both`),
    `metadata_match` / `content_match`, the metadata
    side's `matched_fields` verbatim (empty for a
    content-only match - the metadata road's true
    answer), and the content side's `occurrences`,
    `excerpt` and `verified_content_sha256` verbatim
    (null for all three on a metadata-only match - no
    content fact is invented, the P-182 law).
  - Cap honesty composed (P-182): the union is over
    the two RETURNED match lists; `total_matches` is
    the union's true size before this module's cap;
    `truncated` is true when either source truncated
    or the union runs past `MAX_MATCHES` (100, P-190's
    cap, the value both sources carry).
  - Coverage honesty is P-191's, carried verbatim:
    `coverage_complete` is false whenever the answer
    was truncated OR the content search skipped any
    entry. A skipped entry can still metadata-match -
    its row carries null content facts and the skip is
    named in `skipped_entries`.
  - Composition of the list: the capped merged entries
    are handed to P-187's `list_document` and embedded
    whole as `list`, so `list.count` always equals
    `match_count` and the by-kind / by-locator-state
    counts are the registry's own arithmetic.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/unified-search?q=&kind=`, bearer-gated and
  owner-scoped exactly like the search roads. A blank
  or missing query and an unknown kind answer 422 with
  the unified search's own refusal; every outcome
  state answers 200 as data.

## The laws this slice keeps

- Cost law, stated on every document: a unified search
  pays the content search's full cost - it reads and
  verifies every ready pack in the kind-narrowed
  estate, each through its own layer's verified parse
  road and each under the browse size bound. The
  metadata search alone (P-190) stays the cheap road.
- A match is a literal match only, under each banked
  search's own law; there is no fuzzy, semantic,
  ranked or scored matching here and this composition
  adds none.
- Pure read: the search writes nothing, registers
  nothing, imports nothing, installs nothing, copies
  nothing and grants nothing (registry and pack bytes
  unchanged, battery-pinned).
- Judged and not taken, with reasons in the scout:
  hub content census (named open for a later Part XII
  slice - the house order puts the unified search
  first, P-182 before P-183, and a query-free parse
  census would recount the parse verdict P-189's
  browse axis already counts, since each layer's
  inspect road stands on its parse road), entry
  lifecycle depth (P-187's remove-then-register law
  stands), signing/attestation and friend-instance
  exchange (still DECLINED - no key or transport
  machinery is banked), semantic/ranked search (no
  machinery banked), and the VX-59 ruled-out forms
  (central store, catalogue, creator profiles -
  declined by ruling, not named open).
- The P-186 carried items stay untouched exactly as
  recorded: binding label update (unbind-then-bind
  law), history retention / bulk clear (awaits
  Volmarr's ruling), unified-search history (this
  unified search is a pure read and records nothing).
- No migration (head stays 0041), no README touched.
