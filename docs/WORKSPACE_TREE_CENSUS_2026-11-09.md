# P-181 - Workspace Tree Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-181 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P181_SCOUT.md;
design: hidden_files/P181_DESIGN.md):

- P-169 banked the binding foundation, P-170 the read-only
  folder listing, P-171 the census of the owner's whole binding
  estate (which lists no folder), P-172 the read of one named
  file, P-173 the binding history, P-174 the aggregate of one
  folder at ONE level, P-175 owner-hand history deletion,
  P-176 the depth-limited tree, P-177 the history census,
  P-178 filename search over the tree, and P-179 the fix that
  made the tree's truncated flag true at the depth cap. The
  cell no surface took is the aggregate of ONE chat's bound
  folder over the WHOLE composed tree.
- This slice reopens, with its reason stated, the one cell
  P-174 declined by name: a recursive / whole-tree census.
  P-174's decline was conditional, not absolute - a tree walk
  would need a new path law and a new cap law (P-174's doc),
  and a census over a walk would need a new honesty law for
  partial walks (P-176's derivation). Every missing
  presupposition has since banked: P-176 IS the path law and
  the cap law (every level P-170's listing composed verbatim;
  MAX_DEPTH 4, MAX_NODES 500; unexpanded directories named,
  never dressed as empty), P-179 completed the partial-walk
  honesty at the source (truncated names a directory left
  unexpanded at the depth cap), and P-178 / P-180 proved
  document-side partiality reading over the composed tree.
  P-180's scout listed this cell "not reopened here" - a
  slice-local decline while taking content search, on a base
  that lacked P-179; the fix is banked in this slice's base.
- Threads weighed in the scout and declined WITH REASONS:
  content search (P-180's cell, team-03, banks immediately
  before this slice - rebuilding it would duplicate a slice
  and collide with its files), binding label update
  (bindings.py's own law is unbind-then-bind, never a silent
  in-place update), automatic retention / bulk clear of
  history (thresholds are Volmarr's ruling, awaited), writes /
  edits / deletes inside bound folders (fenced until the
  VX-57 guard), execution and coding-agent backends (VX-55/56;
  P-027 absolute - content is data, never code), watching
  (declined by P-169, stays declined), an owner-wide tree
  census (every per-folder road is one-chat scoped through
  the P-169 binding; P-174 declined the owner-wide folder
  census by name and P-180 declined owner-wide search on the
  same grounds), a per-chat history census (P-173's read
  already filters by chat and sums its counts; P-177 censuses
  the estate - a filtered re-census is a subset, not a new
  surface), a search-results census (P-178 already carries
  its totals honestly - too thin), a single-file stat surface
  (P-170 / P-172 already carry the facts), a single-chat
  workspace overview (three laws at once - declined by name
  in P-176's scout), a caller-chosen census depth (P-178 set
  the precedent: compose the tree at its own MAX_DEPTH
  ceiling, one stated coverage), and any content
  classification or image-byte surface (this census opens no
  file).
- Disjointness from P-180 (team-03, in flight / banked just
  before this slice in roadmap order): this slice touches NO
  content_search.py, NO content_search_router.py, NO tree.py,
  NO listing.py, NO content.py, NO search.py and NO
  bindings.py. Its only shared files with P-180's footprint
  are app.py and workspaces/__init__.py (purely additive hunks
  in separate blocks) and the clean-room log (append) -
  flagged here for the keeper's banking reconciliation.

Base: a3ddcca297887bcd8940ffa383daebebe47d81f8 (P-179 banking
record; banked P-001..P-179, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `src/runmal/workspaces/tree_census.py` (new) - the truth
  layer, composing `runmal.workspaces.tree` VERBATIM
  (`resolve_chat_tree` at P-176's own MAX_DEPTH ceiling, the
  tree document embedded whole; no second walk, listing law,
  folder-state law or scan):
  * `build_tree_census(tree_document)` - sums ONLY the tree
    document's own node fields, in the tree's own depth-first
    order: kind counts under P-170's closed ENTRY_KINDS
    (`directory_count`, `file_count`, `symlink_count`,
    `other_count`, `kind_counts` - the counted nodes are
    exactly P-176's `node_count`; the root node is the
    subpath's synthetic node and is never counted),
    `total_file_bytes` (file nodes' own sizes only - P-170
    gives other kinds no size rather than an invented one),
    `hidden_count`, `escaping_symlink_count`,
    `extension_counts` (file names only; the suffix after
    the final dot, lowercased; no suffix is the honest key
    `(none)`), `largest_file` (first wins on a tie in
    depth-first order, P-174's tie law; carries `name`, its
    folder-relative `path` - exactly the input P-172's read
    consumes - and `size_bytes`; None when there are no
    files), the tree axes `expanded_directory_count`,
    `unexpanded_directory_count`, `expand_refused_count`,
    `depth_counts` (entries per level, level 1 = the root
    level) and `deepest_level` (0 when no entries). The
    tree's `folder_state`, `subpath`, `max_depth` and
    `node_count` are carried verbatim.
  * Partiality: `truncated` is True when the tree's own
    truncated flag is set (post-P-179 it names depth caps,
    node caps and truncated levels at the source), OR when
    any directory node in the composed document is
    unexpanded, OR when any node carries `expand_refused` -
    the P-178 document-side reading kept as a safety net (a
    correct no-op for depth caps against the fixed tree,
    still load-bearing for refused expansions). Six standing
    honesty notes ride every document.
  * The closed `TREE_CENSUS_STATES` law: `folder_not_ready`
    (the tree's folder state is not P-169's ready),
    `empty`, `no_files`, `has_files` - P-174's census law
    carried to the tree. Non-ready folders are DATA - the
    honest zero document - never an error and never a scan.
  * `resolve_chat_tree_census(session, store, user_id,
    chat_id, subpath="")` - None exactly when P-176's
    `resolve_chat_tree` is None (missing / foreign /
    unbound; existence never leaks); a refused subpath
    raises P-170's own WorkspaceListingError unchanged.
- `src/runmal/workspaces/tree_census_router.py` (new) - ONE
  road: `GET /workspaces/tree-census?chat_id=&subpath=` on
  the existing /api/v1 mount. Chat missing/foreign -> 404
  "chat not found"; known chat unbound -> 404 "workspace
  binding not found"; refused subpath -> 422; every census
  state DATA at 200.
- `src/runmal/app.py` (additive only) - one import + one
  include in its OWN block beside the P-178 search router's
  (the P-174 fused-call defect class checked explicitly).
- `src/runmal/workspaces/__init__.py` (additive only) - one
  doc bullet for `tree_census`.
- `tests/test_p181_workspace_tree_census.py` (new, 18 tests).
- This doc, and one clean-room log entry.

## Honesty law (stated as data)

- Coverage is one stated coverage: P-176's tree at its own
  MAX_DEPTH ceiling (depth 4, 500 nodes). A caller wanting a
  shallower or deeper walk uses the tree road itself, as
  before; the census states the coverage it summed.
- Counts describe the composed nodes only: what sits below
  an unexpanded directory was not seen and is not counted,
  and `truncated`, `unexpanded_directory_count` and
  `expand_refused_count` name the partiality concretely -
  never hidden, and no second scan is made (that would be a
  second listing law).
- Extensions describe file NAMES, never contents: this
  census opens no file, so a `.txt` name never claims the
  bytes are text. Content judgements are P-172's per-file
  read and P-180's content search, not this surface.
- The census writes nothing anywhere: not into the bound
  folder, not into the binding store (battery-pinned
  byte-identical).

## Hard declines kept

No writes / edits / deletes (they wait for the VX-57 guard),
NO command execution / program launch / coding-agent backends
(VX-55/56; P-027 absolute), NO watching, NO binding label
update (unbind-then-bind is P-169's law), NO automatic
retention or bulk clear of history (Volmarr's ruling
awaited), NO owner-wide folder sweep, no second binding
store, no second folder-state law, no second listing law, no
second walk, no chats-table column, no migration.

## Honest limitations

(1) Counts are a point-in-time judgement composed from one
tree read; the folder can change between this census and any
later consumer's use, and each tree level is itself judged
live at its own read inside the one call (P-176's stated
shape - refused expansions are named, not hidden). (2) The
tree's caps bound the census: depth 4 and 500 nodes are the
stated ceilings, and beyond them directories are
present-but-unexpanded, never absent and never counted
below. (3) `largest_file` is the largest file among the
composed nodes; on a truncated census a larger file may sit
below an unexpanded directory, unseen - the document's
`truncated` flag says exactly that. (4) Still no write,
execution, watching or image-viewing surface landed.

## Carried forward, named open

- P-180 banks before this slice; the keeper reconciles the
  additive app.py / __init__.py / clean-room-log hunks.
- A binding label update stays named open (bindings.py's
  own law is unbind-then-bind, never a silent in-place
  update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Writes inside bound folders stay fenced behind the VX-57
  guard; execution is declined ABSOLUTELY (VX-55/56, P-027);
  watching stays declined (P-169).
- Part XI runs to its gate at P-186; P-182..P-185 remain
  for the derived cells this slice declines by name.
