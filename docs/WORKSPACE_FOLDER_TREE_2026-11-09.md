# P-176 - Workspace Folder Tree (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-176 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P176_SCOUT.md;
design: hidden_files/P176_DESIGN.md):

- P-169 banked the binding, P-170 the read-only folder listing
  (stated plainly in its own record: ONE level deep), P-171 the
  census of the owner's whole binding estate (which lists no
  folder), P-172 the read of one named file (whose path the
  caller must already know), P-173 the binding history, and
  P-174 the aggregate of one folder at ONE level. The cell no
  surface took is NAVIGATION below the first level: an owner
  cannot see the shape of a bound folder deeper than one level
  without issuing one listing per directory by hand and
  stitching the results client-side.
- This slice is NOT the recursive census P-174 declined: a
  census aggregates a walked tree under a new honesty law for
  partial walks. The tree aggregates nothing - it returns the
  entries themselves, every level composed from P-170's own
  listing, and a partial tree is honest by construction
  (unexpanded directories are flagged, never dressed as empty
  or as counted).
- Threads weighed in the scout and declined WITH REASONS:
  a history census over P-173 (it composes the exact surface
  P-175 is changing in flight, and P-173's document already
  carries its own counts - named open for the first slice
  whose base contains banked P-175), binding-history deletion
  (P-175 itself, in flight on team-01), binding label update
  (touches P-175's bindings.py footprint), content search and
  filename search (a new walk law; named open), a single-file
  stat surface (P-170/P-172 already carry the facts), an
  owner-wide folder census (declined by name at P-174), a
  single-chat overview (three laws at once, P-175 adjacency),
  writes / edits inside bound folders (fenced until the VX-57
  guard), execution and coding-agent backends (VX-55/56;
  P-027 absolute - content is data, never code), watching
  (declined by P-169, stays declined), and any image-byte
  surface.
- Disjointness from P-175 (team-01, in flight: Workspace
  Binding-History Deletion): this slice touches NO bindings.py,
  NO history.py, NO history_router.py and NO router.py. Its
  only shared file with P-175's footprint is
  workspaces/__init__.py - additive doc lines in a different
  region - plus additive app.py wiring in the P-174 pattern.
  Flagged here for the keeper's banking reconciliation.

Base: d3c5b353ff69ca8b8429c4c387b1a10108e3d012 (P-174 banking
record; banked P-001..P-174, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `src/runmal/workspaces/tree.py` (new) - the truth layer,
  composing `runmal.workspaces.listing` VERBATIM at every
  level (same store, same binding document, same
  folder_state law through P-169, same path law re-judged
  per level at this read; no second listing law, no second
  folder-state law, no second scan):
  * `resolve_chat_tree(session, store, user_id, chat_id,
    subpath="", max_depth=2)` - None exactly when P-170's
    `resolve_chat_listing` is None (missing / foreign /
    unbound; existence never leaks); a refused root subpath
    raises P-170's own WorkspaceListingError unchanged.
  * `build_tree(root_listing, max_depth)` - the root
    listing embedded whole (`root_listing`), its binding
    document, folder_state and subpath carried verbatim.
    Nodes carry P-170's entry fields verbatim (name, kind,
    size_bytes, hidden, escapes); directories alone carry
    `children` / `expanded`. Depth law: max_depth counts
    expanded levels, root included (default 2, closed
    range 1..MAX_DEPTH 4; outside raises WorkspaceTreeError
    - refused plainly, never clamped). Node cap: MAX_NODES
    500 (P-170's per-level cap carried to the whole tree);
    expansion is depth-first in P-170's own entry order,
    and a level that would pass the cap is attached only
    up to it, with the document's `truncated` set.
    `truncated` is also set when any composed level's own
    listing was truncated. A directory whose expansion is
    refused at this read (vanished or uncontained between
    the parent listing and its own - the two-moment race)
    carries `expand_refused: True` with children None as
    DATA; the tree still answers. Symlinks are leaves,
    never descended. Non-ready folders are DATA: the root
    node present, unexpanded, node_count 0. Five standing
    honesty notes ride every document.
- `src/runmal/workspaces/tree_router.py` (new, disjoint) -
  GET /workspaces/tree in the folder_census_router shape:
  the two 404s kept apart ("chat not found" vs "workspace
  binding not found"), a refused subpath at 422 with
  P-170's own refusal, a refused max_depth at 422 with the
  tree's own refusal, every folder state DATA at 200.
- `src/runmal/app.py` - additive import + include_router
  beside the folder-census router's. `src/runmal/
  workspaces/__init__.py` - additive doc bullet only.
- `tests/test_p176_workspace_tree.py` (new, fresh-authored,
  P-005 discipline) - 17 tests: the empty root, default /
  depth-1 / depth-3 expansion, the closed depth range,
  symlinks as leaves (inside + escaping), the node cap
  (truncated, prefix-attached, unexpanded named), a
  truncated level carried, expand_refused as data, both
  non-ready shapes as data, subpath rooting + the root
  refusal, verbatim root-listing composition, the None
  trio, live re-judgement + the pure-read law, the HTTP
  road (two 404s, both 422s, states at 200), and the
  migration neighbour (head stays 0041).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. The tree is point-in-time per level, not a snapshot:
   each level is judged live at its own read inside one
   tree call, so a folder changing mid-walk can show a
   shape no single instant had - refused expansions are
   named (expand_refused) rather than hidden, and no
   stronger claim is made.
2. Caps bound the answer: depth 4 and 500 nodes are the
   stated ceilings, and beyond them directories are
   present-but-unexpanded, never absent - a consumer
   needing more issues P-170 listings itself, as before.
3. No file is opened and no content is read: the tree
   cannot say what any file IS, only where it sits and
   what P-170's entry law says of it (P-172's per-file
   read remains the only content road).
4. No write, execution, watching or image surface landed,
   and nothing about the binding store changed.

## Carried forward, named open

- P-175 (team-01) banks before this slice; the keeper
  reconciles the additive __init__.py hunks.
- A history census over P-173, once P-175 is banked.
- Content search and filename search over the tree.
- Writes under a VX-57-style guard (the guard presupposes
  workspace tool calls; none exist) and execution
  VX-55/56 (declined ABSOLUTELY, P-027) stay fenced.
