# P-170 - Workspace Folder Listing / Files Browser (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-170 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P170_SCOUT.md;
design: hidden_files/P170_DESIGN.md):

- P-169's banked record names this cell twice: its evidence
  carries honest limitation (1) - "The binding has NO consumer
  yet" - and its design's declined list names the folder
  listing / files browser "a real second cell... Named open
  (natural P-170)", adding that file reads ride the listing
  cell. P-170 is that consumer, at exactly that scope.
- The census (P-003, docs/VOXTA_CENSUS_2026-10-30.md section H)
  VX-54 names a files browser as part of the workspace
  surface; the delta table (P-004) judges VX-54 MISSING and
  homes it in Part XI. P-169 landed VX-54's binding clause;
  this slice lands its listing clause, read-only.
- Alternatives weighed in the design and declined as less
  grounded: file-content reads (they presuppose this entry
  law; P-169's design says reads ride the listing cell), the
  VX-57 guard (no workspace tool calls exist to guard until
  a consumer lands), writes (fenced until VX-57), execution
  backends (VX-55/56; P-027 absolute), watching (declined by
  P-169, stays declined).

The keeper reviews this derived scope at banking.

Base: d949e6029502fa01f36e80b290be827687d97c99 (P-169 banking
record; banked P-001..P-169, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042.

## What landed

- `src/runmal/workspaces/listing.py` (new) - the listing truth
  layer, composing `runmal.workspaces.bindings` VERBATIM (same
  store, same `folder_state()`, the P-169 binding document
  embedded unchanged):
  * `build_listing(binding_document, folder_path, subpath="")`
    - the listing document (schema
    `runmal-p170-workspace-listing-v1`): the P-169 binding
    document, the folder state judged live, the normalised
    subpath listed (`""` = the bound folder itself), the
    entries, honest counts, a truncated flag, four notes.
  * Entry law: kinds are a closed set (directory / file /
    symlink / other) judged by lstat - a symlink is always a
    symlink, never dressed as its target. Sizes are honest: a
    regular file's exact bytes; null for directories,
    symlinks and others rather than an invented number.
    Hidden entries (dotfiles) are listed and flagged, never
    silently filtered. Deterministic order (directories,
    files, symlinks, other; then name). Cap: 500 entries
    returned, `total_count` always honest, `truncated` set
    when the folder holds more.
  * `resolve_chat_listing(session, store, user_id, chat_id,
    subpath="")` - None exactly when P-169's
    `resolve_chat_workspace` is None (missing / foreign /
    unbound; existence never leaks), else the document.
- `src/runmal/workspaces/router.py` (additive) - ONE new road:
  `GET /workspaces/files?chat_id=&subpath=` on the existing
  /api/v1 mount. Chat missing/foreign -> 404 "chat not
  found"; known chat unbound -> 404 "workspace binding not
  found"; refused subpath -> 422. Non-ready folder states
  are DATA at 200 with empty entries (the house pattern),
  never an error and never a scan.
- `src/runmal/workspaces/__init__.py` (additive) - one map
  bullet for `listing`.
- `tests/test_p170_workspace_listing.py` (new, 13 tests).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one entry, appended.

## Path safety law (the slice's spine)

- Folder state is judged FIRST through P-169's own
  `folder_state()`; a non-ready folder is never scanned.
- A subpath is refused plainly when it is absolute, carries
  a NUL, contains any `..` component (even one that would
  stay inside), names nothing inside the bound folder, or
  names a non-directory. `.` and empty components are
  normalised away and the normalised subpath is echoed.
- The candidate's realpath must equal or sit inside the
  bound folder's realpath: a subpath through or to a
  symlink that leaves the folder is refused by name,
  never followed. A symlink ENTRY pointing out is listed
  as a symlink with `escapes: true` - shown honestly,
  never followed, and its target's size is never claimed.
- The listing writes nothing anywhere: not into the bound
  folder, not into the binding store (battery-pinned
  byte-identical).

## Hard declines kept

No file-content reads (the viewer/read cell is named open
and rides after this entry law), NO writes / edits /
deletes (they wait for the VX-57 guard), NO command
execution / program launch / coding-agent backends
(VX-55/56; P-027 absolute), NO watching, no recursive
tree dump (one level per call; the browser walks by
subpath), no chats-table column, no migration.

## Honest limitations

(1) A listing is a point-in-time judgement: an entry can
vanish or change between the listing and any later
consumer's read; an entry that vanishes mid-scan is
listed as kind `other` with no size, never a crash.
(2) The containment judgement and the scan are two
filesystem moments - a symlink swapped between them is a
race no read-only listing can close; consumers that act
on paths must re-judge at use (that is the VX-57 guard's
future work, named here plainly). (3) `escapes` for a
broken symlink is judged on its lexical realpath - where
the link WOULD point - and is stated as such.
