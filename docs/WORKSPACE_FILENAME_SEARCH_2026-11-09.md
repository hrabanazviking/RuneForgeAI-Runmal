# P-178 - Workspace Filename Search (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-178 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (survey: hidden_files/P178_SCOUT.md;
design: hidden_files/P178_DESIGN.md):

- P-169 banked the binding, P-170 the one-level listing, P-171
  the estate census, P-172 the read of one named file (whose
  path the caller must already know), P-173/P-175 the binding
  history and its owner-hand deletion, P-174 the one-level
  folder census, and P-176 the depth-limited tree. P-176's own
  record names the untaken cell twice, in its slice doc and
  its carried-forward list: "Content search and filename
  search over the tree." An owner with a deep bound folder
  had no way to FIND a file by name. This slice takes the
  filename half, in its smallest honest form.
- Threads weighed and declined WITH REASONS: content search
  (presupposes opening every file - P-172 is one named file
  under a strict text law; a whole-tree content sweep needs
  a new honesty law for binary/oversize/partial reads across
  a walk - named open, next), binding label update (declined
  again, now grounded in bindings.py's own verbatim law:
  rebinding is unbind-then-bind, never a silent in-place
  update - a label verb would contradict the in-tree law and
  touch P-169's store), a history census (P-177's cell,
  team-03, in flight in parallel - disjointness), automatic
  retention / bulk clear-all (thresholds are Volmarr's
  ruling), a single-file stat surface (P-170/P-172 already
  carry the facts), an owner-wide folder census (declined
  by name at P-174), writes / edits / deletes inside bound
  folders (fenced until the VX-57 guard), execution and
  coding-agent backends (VX-55/56; P-027 absolute - content
  is data, never code), watching (declined by P-169, stays
  declined), and any image-byte surface.
- Disjointness from P-177 (team-03, in flight: Workspace
  History Census, commit 2e8a8e1 - history_census.py,
  history_census_router.py, GET /workspaces/history-census;
  NOT in this slice's base): this slice touches NO
  history_census file, NO bindings.py, NO history file and
  NO census file. Shared surfaces are only app.py and
  workspaces/__init__.py - purely additive in both (import +
  include_router beside the tree router's; one doc bullet in
  a different region) - flagged here and in the evidence for
  the keeper's banking reconciliation.

Base: f490afd65eac3a172e34e542a8336c057d5a8aaf (P-176 banking
record; banked P-001..P-176, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `src/runmal/workspaces/search.py` (new) - the truth layer,
  composing `runmal.workspaces.tree` VERBATIM
  (resolve_chat_tree at P-176's own MAX_DEPTH ceiling; the
  tree document embedded whole; no second walk, listing
  law, folder-state law or scan):
  * `resolve_chat_search(session, store, user_id, chat_id,
    query, subpath="")` - the query validated BEFORE the
    tree is composed (fail fast); None exactly when P-176's
    resolve is None (missing / foreign / unbound; existence
    never leaks); a refused subpath raises P-170's own
    WorkspaceListingError unchanged.
  * `build_search(tree_document, query)` - pure filter.
    Query law: required, stripped; empty/blank/non-string
    raises WorkspaceSearchError - refused plainly, never
    treated as match-everything. Match law: the query,
    casefolded, as a substring of the entry's own NAME
    only - never a path component, never content. Coverage
    law: expanded nodes only, depth-first in the tree's
    own order. Each match carries the node's P-170 fields
    verbatim (name / kind / size_bytes / hidden / escapes)
    plus `path`, folder-relative and subpath-prefixed -
    exactly the input P-172's read consumes. Cap law:
    MAX_MATCHES 100 returned; `total_matches` counts all
    found; `truncated` is set by the tree's own truncation,
    by ANY unexpanded directory node present in the tree
    (coverage was partial - read from the composed document
    itself, no new scan), or by the match cap. Five
    standing honesty notes ride every document.
- `src/runmal/workspaces/search_router.py` (new, disjoint) -
  GET /workspaces/search?q= in the tree_router shape: the
  two 404s kept apart ("chat not found" vs "workspace
  binding not found"), refused subpath and refused query
  at 422, every folder state DATA at 200.
- `src/runmal/app.py` - additive import + include_router
  beside the tree router's. `src/runmal/workspaces/
  __init__.py` - additive doc bullet only.
- `tests/test_p178_workspace_search.py` (new, fresh-
  authored, P-005 discipline) - 13 tests.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. Coverage is the expanded tree at P-176's ceiling
   (depth 4, 500 nodes): a name deeper than that, or past
   the node cap, is not found - and the document says so
   (truncated), never dressing a partial search as whole.
2. Names only: the search cannot say what a file IS or
   contains; content search stays named open and P-172
   remains the only content road.
3. The underlying tree is point-in-time per level (P-176's
   limitation, inherited honestly): a folder changing
   mid-walk can yield a search no single instant had.
4. No write, execution, watching or image surface landed,
   and nothing about the binding store changed.

## Carried forward, named open

- P-177 (team-03) banks in parallel; the keeper reconciles
  the additive app.py / __init__.py hunks.
- Content search over the tree (needs its own honesty law
  for binary / oversize / partial reads across a walk).
- Writes under a VX-57-style guard and execution VX-55/56
  (declined ABSOLUTELY, P-027) stay fenced.
