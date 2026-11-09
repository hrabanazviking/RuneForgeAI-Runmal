# P-182 - Workspace Unified Search (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-182 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (survey: hidden_files/P182_SCOUT.md;
design: hidden_files/P182_DESIGN.md):

- P-169 banked the binding, P-170 the one-level listing, P-172
  the read of one named file, P-176 the depth-limited tree,
  P-178 the filename search over that tree and P-180 the
  content search over it - as two DISJOINT roads. An owner
  hunting one file had to run both searches, over two
  separately composed trees (two point-in-time judgements
  that can disagree about the same folder), and merge the
  answers by hand; no document ever said, for one path,
  whether the name spoke, the content spoke, or both did.
  This slice takes that composing cell, in the house census
  pattern (P-171 / P-174 / P-177): a pure read over banked
  documents, stating no new search law of its own.
- Threads weighed and declined WITH REASONS (full scout in
  hidden_files/P182_SCOUT.md): binding label update (declined
  again, grounded in bindings.py's own verbatim law:
  rebinding is unbind-then-bind, never a silent in-place
  update - a label verb would contradict the in-tree law and
  write in P-169's store), content/filename search depth
  beyond P-176's ceiling (P-178 set the precedent: compose
  at the tree's own ceiling, one stated coverage; a deeper
  walk is a tree slice, not a search slice), automatic
  retention / bulk clear of history (thresholds are
  Volmarr's ruling, never invented), an owner-wide
  multi-chat unified search (every banked search road is
  one-chat scoped through the P-169 binding; P-174 declined
  the owner-wide form by name), writes / edits / deletes
  inside bound folders (fenced until the VX-57 guard),
  execution and coding-agent backends (VX-55/56; P-027
  absolute - content is data, never code), and watching
  (declined by P-169, stays declined).
- Disjointness from P-181 (team-01, in flight: the workspace
  tree census, in workspaces/tree_census.py +
  tree_census_router.py; NOT in this slice's base): this
  slice touches NO tree_census, tree, listing, content,
  search, content_search or bindings file - it COMPOSES
  them. Shared surfaces are only app.py and
  workspaces/__init__.py - purely additive in both (import +
  its own include_router block beside the content-search
  router's, the P-174 fused-call defect class checked
  explicitly; one doc bullet) - and this log (+1 entry),
  flagged here and in the evidence for the keeper's banking
  reconciliation.

Base: 9300cd5ad803f4bfce6b53b905d3b90eae6a8622 (P-180 banking
record; banked P-001..P-180, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## The honesty law (stated up front)

1. ONE tree: P-176's tree is composed once, verbatim, at its
   own MAX_DEPTH ceiling (depth 4, 500 nodes) and embedded
   whole. Both banked searches are built from THAT document,
   so the name answer and the content answer describe the
   same walk of the same folder at the same moment - never
   two walks that could disagree.
2. No new search law: the name document is P-178's
   build_search and the content document is P-180's
   build_content_search, composed verbatim and embedded
   whole. Their match laws are unchanged - a name match is
   the query casefolded in the entry's own name; a content
   match is the query casefolded in the file's decoded
   strict-UTF-8 content, read only through P-172 under its
   stated cap (max_content_bytes 262144, carried as data).
3. The union is by folder-relative path, each path once, in
   the tree's own depth-first order, carrying matched_by
   under the closed law (name / content / both). A
   name-only match carries occurrences / excerpt as None -
   no content fact is invented for a file the content road
   did not read as a match; a content match carries its
   occurrence count and bounded excerpt verbatim.
4. Cap honesty: each banked search returns at most its own
   MAX_MATCHES (100, the same value both carry) and keeps
   its true total in its own total_matches. The union is
   over the two RETURNED lists, exactly as banked;
   name_total_matches / content_total_matches carry the
   sources' true totals verbatim into this document, and
   truncated - either source's truncation (which already
   names tree partiality and, on the content side, any
   skip), or this document's own cap - names every partial
   answer, with coverage_complete as its explicit twin.
   A capped union is never dressed as complete.
5. File honesty is P-180's, carried verbatim:
   files_considered == files_searched + len(skipped_files),
   always; every candidate file is a match, a counted
   searched non-match, or a named skip (binary / oversize /
   unreadable / folder_not_ready, or refused - P-172's own
   refusal at the moment of use). A file the content road
   could not search can still name-match: the name answer
   is a fact of the composed tree and is never erased by a
   content refusal - a file that vanishes after the walk
   keeps its name match beside its refused skip, and the
   battery pins exactly that.

## What landed

- `src/runmal/workspaces/unified_search.py` (new) - the
  truth layer, composing `runmal.workspaces.tree` VERBATIM
  (resolve_chat_tree at MAX_DEPTH, composed ONCE; the tree
  document embedded whole), `runmal.workspaces.search`
  VERBATIM (build_search over that document) and
  `runmal.workspaces.content_search` VERBATIM
  (build_content_search over that document):
  * `resolve_chat_unified_search(session, store, user_id,
    chat_id, query, subpath="")` - the query validated
    BEFORE the tree is composed (fail fast); None exactly
    when P-176's resolve is None (missing / foreign /
    unbound; existence never leaks); a refused subpath
    raises P-170's own WorkspaceListingError unchanged.
  * `build_unified_search(tree_document, query)` - the
    union over one composed tree document. Query law =
    P-178/P-180's: required, stripped; empty/blank/
    non-string raises WorkspaceUnifiedSearchError. Cap
    law: MAX_MATCHES 100 returned; the union's own
    total_matches counts the union of the two returned
    lists, and both source totals ride verbatim beside
    it. Six standing honesty notes ride every document.
- `src/runmal/workspaces/unified_search_router.py` (new,
  disjoint) - GET /workspaces/unified-search?q= in the
  banked search-router shape: the two 404s kept apart
  ("chat not found" vs "workspace binding not found"),
  refused subpath and refused query at 422, every folder
  state DATA at 200.
- `src/runmal/app.py` - additive import + include_router in
  its own block beside the content-search router's.
  `src/runmal/workspaces/__init__.py` - additive doc bullet
  only.
- `tests/test_p182_workspace_unified_search.py` (new,
  fresh-authored, P-005 discipline) - 17 tests.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. Coverage is the expanded tree at P-176's ceiling (depth
   4, 500 nodes), inherited from both banked searches:
   entries deeper than that are not matched by either law -
   and the document says so (truncated), never dressing a
   partial search as whole.
2. The union is over the two banked searches' RETURNED
   (capped) match lists. When a source runs past its cap,
   paths it did not return cannot join the union from that
   side; the source's true total rides verbatim in this
   document and truncated is true, so the partiality is
   data - but the union cannot name what a capped source
   never returned.
3. Files over P-172's cap and binary files are not
   content-searched at all (P-180's law, unchanged) and are
   named as skips; such a file can still name-match, and
   its entry then honestly carries no content fact.
4. The walk and the reads are point-in-time judgements
   (P-176/P-172's limitation, inherited honestly): a file
   that changes or vanishes between them is a named
   refusal on the content side, never a crash, never a
   silent drop - and never an erasure of its name match.
5. Matches are literal casefolded substring matches under
   the two banked laws - no ranking, no stemming, no
   semantic claim. No write, execution, watching or image
   surface landed, and nothing about the binding store
   changed.

## Carried forward, named open

- P-181 (team-01) banks in parallel; the keeper reconciles
  the additive app.py / __init__.py / CLEAN_ROOM_LOG unions.
- A binding label update stays named open (bindings.py's
  own law is unbind-then-bind, never a silent in-place
  update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Writes under a VX-57-style guard and execution VX-55/56
  (declined ABSOLUTELY, P-027) stay fenced.
