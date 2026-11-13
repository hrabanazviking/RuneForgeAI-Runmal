# P-184 - Workspace Unified Search Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-184 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (survey: hidden_files/P184_SCOUT.md;
design: hidden_files/P184_DESIGN.md):

- Every banked census aggregates a folder (P-174 at one level,
  P-181 over the whole tree), an estate (P-171) or a history
  (P-177) - none aggregates a SEARCH. P-182 banked the unified
  search and returns its capped match list with only three
  union counts (name / content / both over the uncapped union):
  nothing states how the returned matches distribute by
  matched_by over the returned list, by kind, by extension, by
  depth, by hidden or escaping status, how many bytes and
  occurrences they carry, or how the skipped files distribute
  by outcome - the skip list rides as raw rows only. An owner
  reading one unified answer must tally all of that by hand.
  This slice takes that aggregating cell, in the house census
  pattern (P-171 / P-174 / P-177 / P-181): a pure aggregate
  composing the owning surface verbatim, classified under a
  closed law, counts summed from the composed document's own
  fields.
- P-183's record (Workspace Content Census, team-03, banking
  in parallel - NOT in this base) names this cell in so many
  words: "Once P-182 is banked, census / history surfaces over
  the unified search become lawful future cells on that base."
  P-182 IS banked in this base, so the presupposition that
  decline named is met honestly - the same reopening shape as
  P-181, which reopened the tree census only once every
  presupposition its decline named had banked.
- The HISTORY half of the named cell is declined WITH REASON:
  P-182 stores nothing by its own law ("this search stores,
  binds, unbinds, writes ... nothing") and no search record,
  store or log exists anywhere in-tree - there is no history
  to compose. A history surface would first need a WRITE that
  records every search, changing a banked pure read's
  behaviour and adding a store; that is a new-surface
  decision, not a pure-read composition, and endgame weight
  (a proven gap beats new surface) takes the census half.
- Threads weighed and declined WITH REASONS (full scout in
  hidden_files/P184_SCOUT.md): binding label update (declined
  again, grounded in bindings.py's own verbatim law: rebinding
  is unbind-then-bind, never a silent in-place update - a
  label verb would contradict the in-tree law and write in
  P-169's store; no reopening presupposition has banked, the
  blocker is the law itself), automatic retention / bulk
  clear of history (thresholds are Volmarr's ruling, never
  invented), an owner-wide multi-chat form (every banked
  per-folder road is one-chat scoped through the P-169
  binding; declined by name at P-174 / P-180 / P-182), a
  census over P-178 / P-180 individually (declined at P-181 /
  P-183 as too thin - the matched_by axis this census sums
  exists only in P-182's union, in no other document), the
  content census (P-183's cell, team-03, disjoint by order),
  writes / edits / deletes inside bound folders (fenced until
  the VX-57 guard), execution and coding-agent backends
  (VX-55/56; P-027 absolute - content is data, never code),
  and watching (declined by P-169, stays declined).
- Disjointness from P-183 (team-03, in flight: the workspace
  content census, in workspaces/content_census.py +
  content_census_router.py; NOT in this slice's base): this
  slice touches NO content_census, tree, listing, content,
  search, content_search, unified_search or bindings file -
  it COMPOSES the unified search. Shared surfaces are only
  app.py and workspaces/__init__.py - purely additive in
  both (import + its own include_router block beside the
  unified-search router's, the P-174 fused-call defect
  class checked explicitly; one doc bullet) - and this log
  (+1 entry), flagged here and in the evidence for the
  keeper's banking reconciliation.

Base: c74678b18535e34bac1a6dc88dc8c9cf20577464 (P-182 banking
record; banked P-001..P-182, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## The honesty law (stated up front)

1. ONE composition: P-182's unified search is composed once,
   verbatim (one P-176 tree at its MAX_DEPTH ceiling, both
   banked searches built from that tree, the union by path)
   and embedded whole. Every count in this document is summed
   from THAT document's own fields - no second walk, listing
   law, folder-state law, search law or scan exists here.
2. Two truths, never conflated: the returned axis sums the
   composed document's RETURNED matches only -
   name_only_count + content_only_count + both_match_count
   always equals the returned match_count exactly. The source
   axis carries P-182's own uncapped counts verbatim beside
   the sums (total_matches, source_name_match_count,
   source_content_match_count, source_both_count and both
   source totals). When a source ran past its cap the two
   truths differ, and both are stated.
3. Partiality is P-182's own verdict, carried verbatim:
   truncated / coverage_complete ride exactly as composed -
   never recomputed under a second law. A capped census is
   never dressed as complete, and matches a capped source
   never returned are not counted here, because they were
   never returned.
4. No invented facts: extensions come from file-match NAMES
   only (P-174/P-181 law); bytes sum file matches only -
   other kinds carry no size rather than an invented one; a
   name-only match contributes no occurrence count (P-182's
   kept-apart law - no content fact is invented for a file
   the content road did not read as a match).
5. The skip axis is P-180's honesty, aggregated: skipped
   files are counted by their own outcomes under P-172's
   closed OUTCOMES law plus refused (P-180's name), all five
   keys always present, and P-180's arithmetic
   (files_considered == files_searched + skipped_count)
   rides verbatim beside the counts.

## What landed

- `src/runmal/workspaces/unified_search_census.py` (new) -
  the truth layer, composing
  `runmal.workspaces.unified_search` VERBATIM:
  * `build_unified_search_census(unified_document)` - sums
    only the composed document's own returned-match and
    skipped-file fields and embeds it whole as
    `unified_search_document`: the matched_by axis over the
    returned matches, the kind axis under P-170's closed
    ENTRY_KINDS (with flat per-kind match counts), hidden
    and escaping counts, extension counts from file-match
    names only, total matched file bytes, the largest match
    {name, path, size_bytes, matched_by} (first wins on a
    tie in the union's own order; None when no file
    matched), the total occurrence count, depth counts and
    deepest level (a match's depth is its path's segment
    count relative to the composed subpath), and the skip
    axis over the skipped rows' own outcomes. P-182's
    binding document, folder state, subpath, query, caps
    and partiality verdicts are carried verbatim.
  * The closed `UNIFIED_SEARCH_CENSUS_STATES` law:
    `folder_not_ready` (the honest zero document - a
    non-ready folder's union is empty by P-182's law),
    `no_matches`, `name_only`, `content_only`, `mixed`.
  * `resolve_chat_unified_search_census(session, store,
    user_id, chat_id, query, subpath="")` - None exactly
    when P-182's resolve is None (missing / foreign /
    unbound; existence never leaks); the query is validated
    by P-182 BEFORE the tree is composed (a blank or
    non-string query raises P-182's own
    WorkspaceUnifiedSearchError unchanged); a refused
    subpath raises P-170's own WorkspaceListingError
    unchanged. Six standing honesty notes ride every
    document.
- `src/runmal/workspaces/unified_search_census_router.py`
  (new, disjoint) - GET /workspaces/unified-search-census
  in the banked unified-search-router shape: the two 404s
  kept apart ("chat not found" vs "workspace binding not
  found"), refused subpath and refused query at 422, every
  census state DATA at 200.
- `src/runmal/app.py` - additive import + include_router in
  its own block beside the unified-search router's.
  `src/runmal/workspaces/__init__.py` - additive doc bullet
  only.
- `tests/test_p184_workspace_unified_search_census.py`
  (new, fresh-authored, P-005 discipline) - 20 tests.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. The census describes ONE query's answer over the
   expanded tree at P-176's ceiling (depth 4, 500 nodes),
   inherited from P-182: entries deeper than that are
   matched by neither law, and the composed document's
   truncated flag - carried verbatim - says so.
2. The returned axis is over the RETURNED (capped) match
   list, exactly as P-182 states it. When a source runs
   past its cap, paths it did not return cannot join the
   union and so cannot be counted here; the source's true
   total rides verbatim in this document and truncated is
   true, so the partiality is data.
3. No search history exists or is created: P-182 stores
   nothing and this census records nothing - each census
   is a point-in-time judgement over one composed search,
   and the folder can change between this census and any
   later consumer.
4. Matches are literal casefolded substring matches under
   the two banked laws - the census adds no ranking, no
   stemming and no semantic claim. No write, execution,
   watching or image surface landed, and nothing about the
   binding store changed.

## Carried forward, named open

- P-183 (team-03) banks in parallel; the keeper reconciles
  the additive app.py / __init__.py / CLEAN_ROOM_LOG unions.
- A unified-search HISTORY surface stays named open: it
  presupposes a recording write and a store that no banked
  slice has taken - it is not a pure-read composition.
- A binding label update stays named open (bindings.py's
  own law is unbind-then-bind, never a silent in-place
  update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Writes under a VX-57-style guard and execution VX-55/56
  (declined ABSOLUTELY, P-027) stay fenced.
- Part XI gate is P-186; P-185 remains.
