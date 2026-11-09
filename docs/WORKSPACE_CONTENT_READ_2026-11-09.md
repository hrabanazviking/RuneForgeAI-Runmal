# P-172 - Workspace File Content Read (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-172 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P172_SCOUT.md;
design: hidden_files/P172_DESIGN.md):

- P-170's banked record carries limitation (4) - "Still no
  file-content surface: reads/viewing, writes and execution
  remain named-open later Part XI cells, in that order of
  presupposition" - and limitation (2), which orders any
  future consumer that acts on paths to re-judge containment
  at use. P-172 is the first of those named-open cells (the
  read), built to answer limitation (2) directly rather than
  inherit the listing's judgement.
- The census (P-003, docs/VOXTA_CENSUS_2026-10-30.md section H)
  VX-54 names a files browser that reads text files as part of
  the workspace surface; the delta table (P-004) judges VX-54
  MISSING and homes it in Part XI. P-169 landed its binding
  clause, P-170 its listing clause; this slice lands its
  read clause, read-only.
- Alternatives weighed in the scout and declined as less
  grounded: writes/edits/deletes (fenced until the VX-57
  guard, which presupposes tool calls to guard), execution
  and coding-agent backends (VX-55/56; P-027 absolute), the
  VX-57 guard itself (still no workspace tool calls exist
  to guard), watching (declined by P-169, stays declined),
  image viewing (no house surface honestly supports
  image-byte rendering; no claim is made).

The keeper reviews this derived scope at banking. P-171
(workspace census, team-03) is in flight in parallel and is
disjoint: this slice touches no census file and no binding
store; the keeper banks P-171 before P-172.

Base: 88738b87396f367f04d465b804fb895c5a9007b5 (P-170 banking
record; banked P-001..P-170, PART XI OPEN). Migration: NONE -
head stays 0041, no 0042.

## What landed

- `src/runmal/workspaces/content.py` (new) - the content
  truth layer, composing `runmal.workspaces.bindings`
  VERBATIM (same store, same `folder_state()`, the P-169
  binding document embedded unchanged):
  * `build_content_read(binding_document, folder_path,
    path="")` - the content document (schema
    `runmal-p172-workspace-content-v1`): the P-169 binding
    document, the folder state judged live, the normalised
    path echoed, a closed outcome, the honest size, the
    decoded text (only on outcome `ok`), the cap carried
    as data (`max_bytes`), four notes.
  * Outcome law (closed `OUTCOMES` set): `ok`,
    `folder_not_ready`, `binary`, `oversize`, `unreadable`.
    Binary, oversize and unreadable are DATA in the
    document, never an error and never dressed as `ok`.
  * `resolve_chat_content(session, store, user_id, chat_id,
    path="")` - None exactly when P-169's
    `resolve_chat_workspace` is None (missing / foreign /
    unbound; existence never leaks), else the document.
- `src/runmal/workspaces/router.py` (additive) - ONE new
  road: `GET /workspaces/content?chat_id=&path=` on the
  existing /api/v1 mount. Chat missing/foreign -> 404
  "chat not found"; known chat unbound -> 404 "workspace
  binding not found"; refused path -> 422. Non-ready folder
  states and the binary / oversize / unreadable outcomes
  are DATA at 200 (the house pattern).
- `src/runmal/workspaces/__init__.py` (additive) - one map
  bullet for `content`.
- `tests/test_p172_workspace_content.py` (new, 16 tests).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one entry, appended.

## Path safety law - re-judged at use (the slice's spine)

- Folder state is judged FIRST through P-169's own
  `folder_state()`; a non-ready folder is never opened.
- The requested path is refused plainly when it is empty,
  absolute, carries a NUL, or carries any `..` component
  (even one that would stay inside). `.` and empty
  components are normalised away and the normalised path
  is echoed.
- The candidate's realpath must equal or sit inside the
  bound folder's realpath, judged NOW, at this read - a
  path resolving through any symlink out of the folder is
  refused by name. This is P-170 limitation (2) answered:
  no listing judgement is inherited.
- The final component is judged by lstat: missing,
  symlink, directory and non-regular kinds are each
  refused by name. A symlink is NEVER followed for
  content - an inside symlink is refused exactly like an
  escaping one (P-170 never follows one either; it only
  flags it in a listing).
- The open uses `O_NOFOLLOW` and the opened descriptor is
  fstat-verified as a regular file under the cap before
  any byte is read, and the read itself is bounded at
  cap+1 - a swap or growth between judgement and read
  cannot redirect the read outside the folder or past
  the cap.
- The read writes nothing anywhere: not into the bound
  folder, not into the binding store (battery-pinned
  byte-identical).

## Honesty law (size and encoding, stated as data)

- Cap: `MAX_CONTENT_BYTES = 262144` (256 KiB), carried in
  every document as `max_bytes`. A file over the cap is
  outcome `oversize` and its body is NEVER read; a file
  at exactly the cap reads whole. Content is never
  silently truncated.
- Text means strict UTF-8 with no NUL byte. A NUL in the
  bytes or any UTF-8 decode failure is outcome `binary`:
  bytes are never dumped as text, never decoded with
  replacement characters, never guessed at another
  encoding.
- `size_bytes` is the stat size judged at the read; on
  outcome `ok` it is the number of bytes actually read.
- An OSError at open or read is outcome `unreadable` -
  data, never a crash.

## Hard declines kept

No writes / edits / deletes (they wait for the VX-57
guard), NO command execution / program launch /
coding-agent backends (VX-55/56; P-027 absolute), NO
watching, NO image-byte surface or rendering claim, no
recursive or multi-file reads (one named file per call),
no second binding store, no second folder-state law, no
chats-table column, no migration.

## Honest limitations

(1) A read is a point-in-time judgement: a file can
change between this read and any later consumer's use;
the fstat + bounded-read guard closes the read's own
window, not the consumer's. (2) The two-moment race is
answered for THIS read (realpath + lstat + O_NOFOLLOW +
fstat), but a hostile process racing the folder with
write access to it is the VX-57 guard's future threat
model, named here plainly - this slice claims the
read-only guarantee, not a sandbox. (3) Text is UTF-8
only by design: a file in any other encoding is honestly
`binary` to this surface, never misdecoded. (4) Still no
write, execution or viewing surface beyond this text
read: those remain named-open later Part XI cells.
