# Unified hub search census (P-194) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's through
P-193's were - see `hidden_files/P194_SCOUT.md` and
`P194_DESIGN.md` in the team worktree. The derivation,
stated plainly: P-193's scout names the unified-search
census (the P-184 workspace shape) a lawful later cell
once P-192 is banked, declined at P-193 only because
P-192 was unbanked in that base. P-192 IS banked in
this slice's base, so a census over unified-search
documents - match-axis distribution (metadata /
content / both), coverage, truncation honesty - is
buildable by pure composition. Nothing here is roadmap
verbatim.

Base and banking note: this slice was built on the
P-192 banking record (banked P-001..P-192). P-193 (hub
content census) banks in parallel ahead of it; the
only file both slices touch is `src/runmal/hub/
router.py` (one additive road each), reconciled by the
keeper at banking.

## What was built

- `src/runmal/hub/unified_search_census.py` - the
  census truth layer, in the P-184 shape:
  `build_unified_search_census(unified_document)` (the
  pure aggregator) and
  `unified_search_census_document(entries, query,
  kind=None)` (schema
  `runmal-p194-hub-unified-search-census-v1`) return
  the query and kind verbatim, the P-192 document
  embedded whole as `unified_search`, the returned
  axis, the source axis, the coverage axis,
  `kind_formats` and `notes`, with `census_state`
  under the closed `CENSUS_STATES` law judged on the
  RETURNED matches' sides: `no_matches` /
  `metadata_only` / `content_only` / `mixed`.
  - Composition verbatim, no new search law: the same
    entry list, query and kind are handed to P-192's
    `unified_search_document`, which validates first
    under its own law (a blank or non-string query and
    an unknown kind raise P-192's
    `HubUnifiedSearchError` unchanged, the P-184 law).
    The aggregator sums only that document's own
    returned-match and skipped-entry fields.
  - Returned axis (the RETURNED matches only, exactly
    `match_count` rows): `by_matched_by` zero-filled
    under P-192's `MATCHED_BY` law and summing exactly
    to `match_count`; `by_kind` zero-filled under
    `HUB_KINDS`; `by_matched_field` zero-filled under
    P-190's `SEARCH_FIELDS` (a row matching two fields
    counts under both - the axis sums fields, not
    rows); `total_occurrences`; and
    `most_occurrences` (id, title, kind, occurrences;
    first in returned order on a tie; null when no
    returned row carries an occurrence count - a
    metadata-only row contributes none, so no content
    fact is invented).
  - Source axis (P-184's two-truths law): P-192's own
    full-union counts carried verbatim beside the
    returned sums - `total_matches`,
    `source_metadata_match_count`,
    `source_content_match_count`, `source_both_count`,
    and both source totals (`metadata_total_matches`,
    `content_total_matches`). When nothing was capped
    the two truths agree; when capped they differ and
    both are stated - a capped census is never dressed
    as complete.
  - Coverage axis (P-191's truths, carried):
    `entries_considered` and `entries_searched`
    verbatim, `skipped_count`, `by_skip_outcome`
    zero-filled under P-191's skip outcomes
    (`unavailable` / `invalid`) summed from the
    composed document's skipped rows, and `truncated`
    / `coverage_complete` verbatim.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/unified-search-census?q=&kind=`,
  bearer-gated and owner-scoped exactly like the
  unified-search road. A blank or missing query and an
  unknown kind answer 422 with P-192's own refusal;
  every census state answers 200 as data.

## The laws this slice keeps

- Cost law, stated on every document: the census pays
  the unified search's full cost once - it reads and
  verifies every ready pack in the kind-narrowed
  estate, each under P-188's 16 MiB bound. The
  metadata search alone (P-190) stays the cheap road.
- Distinctness, stated on every document: P-189's
  census counts browse verdicts and checksum claims
  over the estate and P-193's counts verified payload
  string volume; neither answers for one query. This
  census counts one query's union answer only and
  measures neither browse verdicts, checksum claims
  nor string volume (battery-fenced at the document's
  top level).
- No new content text: the census's own fields carry
  counts, ids, titles and kinds only; excerpts live
  solely inside the embedded P-192 document, that
  search's own answer.
- Pure read: the census writes nothing, registers
  nothing, records nothing (no search history is
  invented - a history would need a recording write,
  the P-184 law), imports, installs, copies and
  grants nothing (registry and pack bytes unchanged,
  battery-pinned).
- Judged and not taken, with reasons in the scout:
  the hub content census (P-193's slice, banking
  ahead - its string-volume axes are never recounted
  here), any query-free recount of a P-189 axis
  (rejected as a mere recount under a second law),
  entry lifecycle depth (P-187's remove-then-register
  law stands), signing/attestation and
  friend-instance exchange (still DECLINED - no key
  or transport machinery is banked), unified-search
  history (a carried item - it presupposes a recording
  write and store), and the VX-59 ruled-out forms
  (central store, catalogue, creator profiles -
  declined by ruling, not named open).
- The P-186 carried items stay untouched exactly as
  recorded: binding label update (unbind-then-bind
  law), history retention / bulk clear (awaits
  Volmarr's ruling), unified-search history.
- No migration (head stays 0041), no README touched.
