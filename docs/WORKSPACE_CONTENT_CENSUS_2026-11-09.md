# P-183 - Workspace Content Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-183 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P183_SCOUT.md;
design: hidden_files/P183_DESIGN.md):

- P-169 banked the binding foundation, P-170 the read-only
  folder listing, P-171 the census of the owner's whole binding
  estate, P-172 the read of one named file under a strict text
  law (strict UTF-8, stated cap, binary / oversize / unreadable
  as named outcomes), P-173 the binding history, P-174 the
  aggregate of one folder at ONE level, P-175 owner-hand history
  deletion, P-176 the depth-limited tree, P-177 the history
  census, P-178 filename search over the tree, P-180 content
  search over the tree, and P-181 the aggregate of the whole
  composed tree. Every one of those aggregates judges files by
  NAME and SIZE only - P-174 and P-181 open no file, so in their
  counts a binary or oversize file is indistinguishable from
  readable text. The only surface that judges readability at
  all, P-180, reveals it solely as the skip list of a search
  for a query - and both banked searches refuse an empty query
  plainly, so no query-free document states how much of one
  chat's bound folder the companion can actually read as text.
  That is the cell this slice takes: the aggregate of P-172
  readability over the whole composed tree, in the house census
  pattern (P-171 / P-174 / P-177 / P-181) - a pure aggregate
  composing the owning surfaces verbatim, classified under a
  closed law, counts summed from the composed reads' own
  fields, and NO content retained or returned anywhere.
- Threads weighed in the scout and declined WITH REASONS:
  binding label update (bindings.py's own verbatim law is
  unbind-then-bind, never a silent in-place update; P-181
  reopened the tree census only because every presupposition
  its decline named had since banked, and no presupposition
  has banked for a label verb - the blocker is the law itself,
  restated in every record P-175..P-182; a label verb would
  also be the first write into P-169's store from a new
  slice), unified-search census / history surfaces (their
  presupposition is P-182 itself, which is NOT in this slice's
  base - team-02 banks it in parallel and its files are
  disjoint by order; a lawful future cell once P-182 is
  banked, not composable or verifiable on this base),
  automatic retention / bulk clear of history (thresholds are
  Volmarr's ruling, awaited - NOT taken), writes / edits /
  deletes inside bound folders (fenced until the VX-57
  guard), execution and coding-agent backends (VX-55/56;
  P-027 absolute - content is data, never code), watching
  (declined by P-169, stays declined), an owner-wide form of
  any per-folder road (every per-folder road is one-chat
  scoped through the P-169 binding; declined by name at
  P-174 / P-180 / P-181 on the same grounds), a per-chat
  history census (a filtered subset of banked surfaces, too
  thin - declined by name at P-181), a search-results census
  (the searches already carry their totals honestly and
  P-182 takes their composition - too thin), and a
  single-entry history read (thinner than the cells declined
  as too thin).
- Disjointness from P-182 (team-02, in flight, NOT in this
  base): this slice touches NO unified_search.py, NO
  unified_search_router.py, NO search.py, NO
  content_search.py, NO tree.py, NO listing.py, NO content.py
  and NO bindings.py - it COMPOSES tree and content. Its only
  shared files with P-182's footprint are app.py and
  workspaces/__init__.py (purely additive hunks in separate
  blocks) and the clean-room log (append) - flagged here for
  the keeper's banking reconciliation.

Base: 0f1181e0bbcc44666a55cee86ee49d49841a8641 (P-181 banking
record; banked P-001..P-181, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `src/runmal/workspaces/content_census.py` (new) - the truth
  layer, composing `runmal.workspaces.tree` VERBATIM
  (`resolve_chat_tree` at P-176's own MAX_DEPTH ceiling, the
  tree document embedded whole; no second filesystem walk,
  listing law, folder-state law or scan) and
  `runmal.workspaces.content` VERBATIM (every candidate read
  through `build_content_read` under its stated cap):
  * `build_content_census(tree_document)` - the candidates
    are the composed tree's expanded kind=file nodes in its
    own depth-first order (P-180's candidate walk over the
    composed document); each is read through P-172 at the
    moment of this census and counted under its own outcome
    (P-172's closed OUTCOMES law, plus `refused` - P-180's
    name for P-172's refusal at the moment of use). The read
    content is judged and DROPPED: no content field and no
    excerpt exists anywhere in the document (battery-pinned
    by a recursive key scan and a known-secret absence pin).
    Axes: `files_considered`, `readable_count`,
    `binary_count`, `oversize_count`, `unreadable_count`,
    `refused_count`, `folder_not_ready_count` and the full
    `outcome_counts` dict; `unreadable_files` naming every
    non-readable candidate {name, path, size_bytes, outcome}
    in tree order (the read's own size when it carries one,
    else the node's - P-180's size law); `total_readable_bytes`
    (the ok reads' own sizes - bytes actually read, P-172's
    law); `largest_readable_file` {name, path, size_bytes}
    (first wins on a tie in depth-first order, P-174's tie
    law; None when nothing is readable); and
    `readable_extension_counts` from readable file NAMES
    only (suffix after the final dot, lowercased; no suffix
    is the honest key `(none)`) - readability itself is
    judged from the bytes through P-172, never from the name.
    The tree's `folder_state`, `subpath`, `max_depth` and
    `node_count` are carried verbatim, and P-172's cap rides
    as `max_content_bytes` data.
  * Partiality: `truncated` is True when the tree's own
    truncated flag is set, OR when any directory node in the
    composed document is unexpanded, OR when any node carries
    `expand_refused` - the P-181 document-side reading. A
    non-ok outcome does NOT set truncated here: every
    candidate under the composed coverage was judged and
    counted under its outcome - the stated distinction from
    P-180, where a skip means the search did not cover that
    file's content. `coverage_complete` carries the twin.
  * The closed `CONTENT_CENSUS_STATES` law:
    `folder_not_ready` (the tree's folder state is not
    P-169's ready - the honest zero document; no candidate
    exists and no file is opened), `empty` (no composed
    entries at all), `no_files` (entries but no file nodes),
    `none_readable`, `some_readable`, `all_readable`.
    Non-ready folders are DATA, never an error.
  * `resolve_chat_content_census(session, store, user_id,
    chat_id, subpath="")` - None exactly when P-176's
    `resolve_chat_tree` is None (missing / foreign / unbound;
    existence never leaks); a refused subpath raises P-170's
    own WorkspaceListingError unchanged.
- `src/runmal/workspaces/content_census_router.py` (new) -
  ONE road: `GET /workspaces/content-census?chat_id=&subpath=`
  on the existing /api/v1 mount. Chat missing/foreign -> 404
  "chat not found"; known chat unbound -> 404 "workspace
  binding not found"; refused subpath -> 422; every census
  state DATA at 200.
- `src/runmal/app.py` (additive only) - one import + one
  include in its OWN block beside the P-181 tree-census
  router's (the P-174 fused-call defect class checked
  explicitly).
- `src/runmal/workspaces/__init__.py` (additive only) - one
  doc bullet for `content_census`.
- `tests/test_p183_workspace_content_census.py` (new, 21 tests).
- This doc, and one clean-room log entry.

## Honesty law (stated as data)

- Coverage is one stated coverage: P-176's tree at its own
  MAX_DEPTH ceiling (depth 4, 500 nodes). What sits below an
  unexpanded directory was not seen and is not counted, and
  `truncated` / `coverage_complete` name every partial census.
- No silent omission: `files_considered` always equals the
  sum of the outcome counts, and every file P-172 did not
  judge readable is named in `unreadable_files` with its
  outcome - a partial estate is never dressed as readable.
- No content is retained: this census opens files ONLY
  through P-172 and ONLY to judge readability; a readable
  file contributes its size, its name's extension and its
  candidacy for largest-readable - never its bytes - so the
  document can be shown anywhere the tree census can.
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
store, no second folder-state law, no second listing law,
no second content law, no second filesystem walk, no
chats-table column, no migration.

## Honest limitations

(1) Counts are a point-in-time judgement composed from one
tree read and the per-file reads at this call; the folder can
change between the tree walk and a file's read (a file that
vanishes or changes kind between them is a named refusal,
never a crash and never a silent drop - P-180's two-moment
law, inherited honestly), and between this census and any
later consumer. (2) The tree's caps bound the census: depth
4 and 500 nodes are the stated ceilings, and beyond them
directories are present-but-unexpanded, never absent and
never counted below. (3) `largest_readable_file` is the
largest readable file among the composed nodes; on a
truncated census a larger readable file may sit below an
unexpanded directory, unseen - the document's `truncated`
flag says exactly that. (4) Readability is P-172's law and
nothing wider: strict UTF-8 with no NUL byte under the
262144-byte cap - a file one byte over the cap is oversize
here exactly as it is unreadable-in-full to every banked
consumer. (5) Still no write, execution, watching or
image-viewing surface landed.

## Carried forward, named open

- P-182 banks in parallel; the keeper reconciles the additive
  app.py / __init__.py / clean-room-log hunks. Once P-182 is
  banked, census / history surfaces over the unified search
  become lawful future cells on that base.
- A binding label update stays named open (bindings.py's own
  law is unbind-then-bind, never a silent in-place update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Writes inside bound folders stay fenced behind the VX-57
  guard; execution is declined ABSOLUTELY (VX-55/56, P-027);
  watching stays declined (P-169).
- Part XI runs to its gate at P-186; P-184..P-185 remain for
  the derived cells this slice declines by name.
