# P-180 - Workspace Content Search (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-180 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (survey: hidden_files/P180_SCOUT.md;
design: hidden_files/P180_DESIGN.md):

- P-169 banked the binding, P-170 the one-level listing, P-172
  the read of one named file under a strict text law, P-176
  the depth-limited tree, and P-178 the filename search over
  that tree. The P-176, P-177 and P-178 records each name the
  untaken cell in the same words: content search - which
  would have to open files under a new partial-read honesty
  law - stays named open. An owner who could find a file by
  name (P-178) still had no way to find which file SPEAKS OF
  a thing. This slice takes that cell, and states the new
  honesty law up front, in the design note and in every
  document the search returns (see below).
- Threads weighed and declined WITH REASONS (full scout in
  hidden_files/P180_SCOUT.md): binding label update (declined
  again, grounded in bindings.py's own verbatim law:
  rebinding is unbind-then-bind, never a silent in-place
  update - a label verb would contradict the in-tree law and
  write in P-169's store), automatic retention / bulk clear
  of history (thresholds are Volmarr's ruling, never
  invented), a single-file stat surface (P-170/P-172 already
  carry the facts), an owner-wide multi-chat content search
  (every banked road is one-chat scoped through the P-169
  binding; P-174 declined the owner-wide census by name), a
  recursive whole-tree census (declined by name at P-174), a
  caller-chosen search depth (P-178 set the precedent:
  compose at the tree's own ceiling, one stated coverage),
  boolean match-only results (too thin: the caller needs
  where the text is), image/binary searching (P-172's text
  law is the only content law), writes / edits / deletes
  inside bound folders (fenced until the VX-57 guard),
  execution and coding-agent backends (VX-55/56; P-027
  absolute - content is data, never code), and watching
  (declined by P-169, stays declined).
- Disjointness from P-179 (team-02, in flight: the P-176
  truncated fix, inside workspaces/tree.py; NOT in this
  slice's base): this slice touches NO tree.py, listing.py,
  content.py, search.py or bindings.py file - it COMPOSES
  them. Its truncated law reads the composed tree document
  (the tree's own flag, OR any unexpanded directory node in
  it, OR any skipped file, OR the match cap), so it is
  correct on this base and stays correct once P-179's fix
  lands. Shared surfaces are only app.py and
  workspaces/__init__.py - purely additive in both (import +
  its own include_router block beside the search router's,
  the P-174 fused-call defect class checked explicitly;
  one doc bullet) - flagged here and in the evidence for
  the keeper's banking reconciliation.

Base: b6982a098886af713c2ea26153dbdd36b3b286aa (P-178 banking
record; banked P-001..P-178, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## The honesty law (stated up front, per the P-178 condition)

1. Coverage is the EXPANDED tree only, composed at P-176's
   own MAX_DEPTH ceiling (depth 4, 500 nodes) and embedded
   whole: a directory left unexpanded was not searched.
2. Per-file cap: every candidate is read ONLY through
   P-172's build_content_read under its stated cap
   (max_content_bytes 262144, carried as data). An oversize
   file is NOT searched at all - never searched in part,
   never silently truncated - it is named as a skip.
3. No silent omission: every candidate file node ends as a
   match, a counted searched non-match, or a named entry in
   skipped_files with its P-172 outcome (binary / oversize /
   unreadable / folder_not_ready) or refused (P-172 refused
   at the moment of use - the two-moment race). Always:
   files_considered == files_searched + len(skipped_files).
   Only kind=file nodes are candidates; directories,
   symlinks (never followed for content) and other kinds
   are visible as themselves in the embedded tree.
4. Partial is named partial: truncated is set by the tree's
   truncation, by any unexpanded directory, by any skip, or
   by the match cap; coverage_complete carries the same
   truth as explicit data.
5. A match is content only: the query, casefolded, as a
   substring of the decoded strict-UTF-8 content - never
   the name (P-178), never a path component. Each match
   carries its folder-relative path (the input P-172
   consumes), its non-overlapping occurrence count, and one
   bounded excerpt (40 characters either side of the first
   occurrence) quoted verbatim from P-172's content.

## What landed

- `src/runmal/workspaces/content_search.py` (new) - the
  truth layer, composing `runmal.workspaces.tree` VERBATIM
  (resolve_chat_tree at MAX_DEPTH; the tree document
  embedded whole; no second walk, listing law,
  folder-state law or scan) and `runmal.workspaces.content`
  VERBATIM (build_content_read per candidate; its outcomes,
  cap and refusal law unchanged):
  * `resolve_chat_content_search(session, store, user_id,
    chat_id, query, subpath="")` - the query validated
    BEFORE the tree is composed (fail fast); None exactly
    when P-176's resolve is None (missing / foreign /
    unbound; existence never leaks); a refused subpath
    raises P-170's own WorkspaceListingError unchanged.
  * `build_content_search(tree_document, query)` - the
    search over one composed tree document. Query law =
    P-178's: required, stripped; empty/blank/non-string
    raises WorkspaceContentSearchError. Cap law:
    MAX_MATCHES 100 returned; `total_matches` counts all
    matching files; matches in the tree's own depth-first
    order. Five standing honesty notes ride every document.
- `src/runmal/workspaces/content_search_router.py` (new,
  disjoint) - GET /workspaces/content-search?q= in the
  search_router shape: the two 404s kept apart ("chat not
  found" vs "workspace binding not found"), refused
  subpath and refused query at 422, every folder state
  DATA at 200.
- `src/runmal/app.py` - additive import + include_router in
  its own block beside the search router's.
  `src/runmal/workspaces/__init__.py` - additive doc bullet
  only.
- `tests/test_p180_workspace_content_search.py` (new,
  fresh-authored, P-005 discipline) - 16 tests.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. Coverage is the expanded tree at P-176's ceiling (depth
   4, 500 nodes): text deeper than that, or past the node
   cap, is not found - and the document says so (truncated),
   never dressing a partial search as whole.
2. Files over P-172's cap and binary files are not searched
   at all and are named as skips; the search cannot say what
   a skipped file contains.
3. The walk and the reads are point-in-time judgements
   composed from live reads (P-176/P-172's limitation,
   inherited honestly): a file that changes kind or
   vanishes between them is a named refusal, never a crash
   and never a silent drop.
4. Matches are literal casefolded substring matches over
   decoded text - no ranking, no stemming, no semantic
   claim. The excerpt is a bounded quote around the FIRST
   occurrence only; occurrence counts are exact,
   non-overlapping substring counts.
5. No write, execution, watching or image surface landed,
   and nothing about the binding store changed.

## Carried forward, named open

- P-179 (team-02) banks before this slice; the keeper
  reconciles the additive app.py / __init__.py /
  CLEAN_ROOM_LOG hunks.
- A binding label update stays named open (bindings.py's
  own law is unbind-then-bind, never a silent in-place
  update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Writes under a VX-57-style guard and execution VX-55/56
  (declined ABSOLUTELY, P-027) stay fenced.
