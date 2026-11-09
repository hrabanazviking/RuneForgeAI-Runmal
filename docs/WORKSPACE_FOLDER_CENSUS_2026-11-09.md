# P-174 - Workspace Folder Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-174 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P174_SCOUT.md;
design: hidden_files/P174_DESIGN.md):

- P-169 banked the binding foundation, P-170 the read-only
  folder listing, P-171 the census of the owner's whole binding
  estate (which by its own law lists no folder and reads no
  contents), and P-172 the read of one named file. The cell no
  surface took is the aggregate of ONE chat's bound folder at
  ONE level: kind counts, total file bytes, the shape of the
  file extensions, hidden entries, escaping symlinks, and the
  largest file. The house pattern for exactly this is the
  census (P-148 / P-164 / P-171): a pure read composing the
  owning surface verbatim, classified under a closed law,
  counts summed from the composed document's own fields.
- Threads weighed in the scout and declined WITH REASONS:
  writes / edits inside bound folders (fenced until the VX-57
  guard; the guard presupposes workspace tool calls and none
  exist yet - a write surface first would open exactly the
  hole the P-003 census flags), execution and coding-agent
  backends (VX-55/56; P-027 absolute - content is data, never
  code), watching (declined by P-169, stays declined), any
  image-byte surface (no house surface honestly renders image
  bytes), and P-173's named-open history deletion/custody road
  (it presupposes P-173's history store, which is banking in
  parallel and is NOT in this base; named open for the first
  slice whose base contains banked P-173).
- Disjointness from P-173 (team-02, in flight): this slice
  touches no bindings.py, no router.py, no history.py and no
  history_router.py. Its only shared files are app.py and
  workspaces/__init__.py, additive hunks only, in the P-171
  pattern - flagged here for the keeper's banking
  reconciliation.

Base: 8ace269cf44e585c90d52cb74c6c95b64a4370db (P-172 banking
record; banked P-001..P-172, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042, battery-pinned.

## What landed

- `src/runmal/workspaces/folder_census.py` (new) - the truth
  layer, composing `runmal.workspaces.listing` VERBATIM (same
  store, same folder_state law through P-169, same listing
  document embedded whole):
  * `build_folder_census(listing_document)` - sums ONLY the
    listing document's own entry fields: kind counts under
    P-170's closed ENTRY_KINDS (`directory_count`,
    `file_count`, `symlink_count`, `other_count`,
    `kind_counts`), `total_file_bytes` (file entries' own
    sizes only - P-170 gives other kinds no size rather than
    an invented one), `hidden_count`,
    `escaping_symlink_count`, `extension_counts` (file names
    only; the suffix after the final dot, lowercased; no
    suffix is the honest key `(none)`), and `largest_file`
    (first wins on a tie, in the listing's own order; None
    when there are no files). The listing's `folder_state`,
    `subpath`, `entry_count`, `total_count` and `truncated`
    are carried verbatim.
  * The closed `FOLDER_CENSUS_STATES` law: `folder_not_ready`
    (the listing's folder state is not P-169's ready),
    `empty`, `no_files`, `has_files`. Non-ready folders are
    DATA - the honest zero document - never an error and
    never a scan. Six standing honesty notes ride every
    document.
  * `resolve_chat_folder_census(session, store, user_id,
    chat_id, subpath="")` - None exactly when P-170's
    `resolve_chat_listing` is None (missing / foreign /
    unbound; existence never leaks); a refused subpath
    raises P-170's own WorkspaceListingError unchanged.
- `src/runmal/workspaces/folder_census_router.py` (new) -
  ONE road: `GET /workspaces/folder-census?chat_id=&subpath=`
  on the existing /api/v1 mount. Chat missing/foreign -> 404
  "chat not found"; known chat unbound -> 404 "workspace
  binding not found"; refused subpath -> 422; every census
  state DATA at 200.
- `src/runmal/app.py` (additive only) - one import + one
  include beside the P-171 census router's.
- `src/runmal/workspaces/__init__.py` (additive only) - one
  doc bullet for `folder_census`.
- `tests/test_p174_workspace_folder_census.py` (new, 15
  tests).
- This doc, and one clean-room log entry.

## Honesty law (stated as data)

- Truncation: P-170 caps a listing at 500 returned entries
  while carrying `total_count` and `truncated`. Both ride in
  this document verbatim; when `truncated` is true, every
  count describes the returned entries only - stated in the
  notes, never hidden, and no second scan is made (that would
  be a second listing law).
- Extensions describe file NAMES, never contents: this census
  opens no file, so a `.txt` name never claims the bytes are
  text. The per-file content judgement is P-172's road.
- The census writes nothing anywhere: not into the bound
  folder, not into the binding store (battery-pinned
  byte-identical).

## Hard declines kept

No writes / edits / deletes (they wait for the VX-57 guard),
NO command execution / program launch / coding-agent backends
(VX-55/56; P-027 absolute), NO watching, NO recursive or
whole-tree census (P-170 lists one level under its own path
law; a tree walk would need a new path law and a new cap
law), NO content classification by opening files, NO
owner-wide folder census (P-171 already censuses the estate
of bindings; this cell is per-chat), no second binding store,
no second folder-state law, no second listing law, no
chats-table column, no migration.

## Honest limitations

(1) Counts are a point-in-time judgement composed from one
listing read; the folder can change between this census and
any later consumer's use. (2) A truncated listing bounds the
census to the returned entries, as stated above. (3)
Extension counts are name-deep only, by design. (4) Still no
write, execution, watching or image-viewing surface: those
remain named-open later Part XI cells, and the history
deletion/custody road remains named open behind banked
P-173.
