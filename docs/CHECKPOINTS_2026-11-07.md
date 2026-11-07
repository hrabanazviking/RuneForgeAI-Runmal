# Chat Checkpoints — P-067 (2026-11-07)

Named snapshots of a chat — bookmarks — restored as a **new**
chat. A checkpoint freezes one chat's history and settings into a
single self-contained, checksum-sealed JSON file; restoring it
brings that moment back as a fresh chat you can continue in.
Storage is file-based: **no database rows, no migration** — the
migration head stays at PROVISIONAL **0037** (P-066).

## What shipped

- `src/runmal/chats/checkpoints.py` — the checkpoint service:
  `create_checkpoint`, `list_checkpoints`, `get_checkpoint`,
  `restore_checkpoint`, `delete_checkpoint`,
  `remove_chat_checkpoints`, `checkpoint_to_dict`, and the
  dedicated `CheckpointError`.
- Five routes in `src/runmal/chats/router.py`, immediately after
  the branch routes (see the API table below).
- `service.delete_chat` removes the chat's checkpoint directory
  after the deletion commits (lazy import inside the function —
  `checkpoints.py` imports from `service.py`, so a module-level
  import would cycle), wrapped best-effort so a filesystem error
  can never turn a completed chat deletion into a failed request.
- Battery: `tests/test_p067_checkpoints.py` (areas A–H).

## What a checkpoint is

A checkpoint is a bookmark of one chat's life at one moment: the
chat row plus its full message history — roles, content, speaker
snapshots, and complete swipe decks — captured exactly as they
were. Names are labels, not identity: a checkpoint's identity is
its id (a uuid), names need not be unique, and a checkpoint made
with no name gets a timestamp default of the form
`Checkpoint 2026-11-07 06:15:02 UTC`.

An example checkpoint file (field names are real; values trimmed):

```json
{
  "format": "runmal-checkpoint",
  "format_version": 1,
  "id": "<checkpoint uuid>",
  "chat_id": "<source chat id>",
  "user_id": "<owner id>",
  "name": "Before the reveal",
  "created_at": "2026-11-07T11:15:02+00:00",
  "message_count": 3,
  "chat": { "...": "the chat row, archive shape" },
  "messages": [ { "...": "one message row, archive shape" } ],
  "checksum": "<sha256 hex>"
}
```

No event log is stored, and no secrets are involved: the payload
is the chat and message rows only, exactly like a portable
archive member.

## Storage: files, not a table — and the tradeoff

Checkpoints live at:

```
data_dir()/checkpoints/<user_id>/<chat_id>/<checkpoint_id>.json
```

One checkpoint is one file. There is no index file: listing is a
directory scan of the chat's own directory, so the directory can
never disagree with an index that does not exist. Files are
written atomically — canonical bytes to a `.tmp` sibling in the
same directory, `chmod 0o600` (checkpoints hold full chat
content; owner-readable only, like the auth credential), then
replace — so a crashed create never leaves a half-written
checkpoint behind.

Why files rather than a table? A checkpoint is a snapshot
*document*, not relational data: nothing else queries into it,
nothing joins against it, and the archive machinery already
defines exactly the document shape it needs. Keeping it out of
the database keeps the slice migration-free.

The tradeoff, stated plainly: checkpoints are
**installation-local**. They live in the local data directory and
are **not carried by portable (`.runmal`) archives or full
backups in this slice** — moving an installation to another
machine moves its chats, but not its bookmarks. The payload
deliberately uses the archive's own row shape (next section), so
a future slice can lift checkpoints into the archive without a
format change; this slice makes no portability claim beyond that
shared shape.

## Payload = archive member shape, sealed with a checksum

The `chat` and `messages` values are produced by
`runmal.portable.archive.row_to_dict` — never a hand-rolled
serialiser — so the pair is the same shape (and, for an unchanged
chat, the same value) as the `chats/<id>.json` member of a
`.runmal` archive. Every table column rides along, including
`swipes_json` / `swipe_id`, so swipe decks survive in the payload
by construction. Message order is the archive's order
(`created_at`, then `id`) — deterministic even on timestamp ties,
because determinism is what the checksum seals.

The seal covers exactly the history: `checksum` is the SHA-256 of
the canonical bytes (`json.dumps(..., sort_keys=True,
separators=(",", ":"))`) of `{"chat": ..., "messages": ...}` —
the archive manifest's per-member discipline, shrunk to one
member that carries its own seal. Metadata (name, id) is not
sealed and may be inspected freely; the history may not change
without breaking the seal. Verification recomputes over the
*parsed* document's `chat` / `messages` re-serialised canonically
— never over the raw file bytes — so harmless file-level
reformatting does not fail verification, but any value change
does. `message_count` is re-checked against the stored messages
at load time.

## The five operations

| Route | Status | Returns |
|---|---|---|
| `POST /chats/{chat_id}/checkpoints` | 201 | checkpoint metadata |
| `GET /chats/{chat_id}/checkpoints` | 200 | list of metadata, oldest first |
| `GET /chats/{chat_id}/checkpoints/{checkpoint_id}` | 200 | checkpoint metadata |
| `POST /chats/{chat_id}/checkpoints/{checkpoint_id}/restore` | 201 | the restored chat (`chat_to_dict`) |
| `DELETE /chats/{chat_id}/checkpoints/{checkpoint_id}` | 200 | `{"deleted": true, "id": ...}` |

Create and restore accept an optional JSON body `{"name": ...}`.
Metadata is all that list and get ever return:

```json
{
  "id": "...", "chat_id": "...", "name": "Before the reveal",
  "created_at": "2026-11-07T11:15:02+00:00",
  "message_count": 3, "chat_title": "The Voyage"
}
```

`chat_title` is the title **at snapshot time**, read from the
payload: rename the chat afterwards and the checkpoint still
reports the title it actually captured. Raw message bodies never
come back from a checkpoint file — the restored chat is how
content returns.

In curl shape:

```bash
# bookmark the current moment
curl -X POST localhost:8000/api/v1/chats/<chat>/checkpoints \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"name": "Before the reveal"}'
# bring that moment back as a new chat
curl -X POST localhost:8000/api/v1/chats/<chat>/checkpoints/<id>/restore \
     -H "Authorization: Bearer $TOKEN" -d '{}'
```

## Restore-as-new: the rule and the rationale

Restore **never writes into the source chat**. It creates a
brand-new chat whose history is the checkpoint's messages, and
leaves the source — title, settings, messages — exactly as it
was. "One-click return" means *one click to get that moment back
as a chat you can continue in*, not *rewind and discard
everything since*.

Why, in the tree's own precedents:

- **Branches (P-066):** forking returns to an earlier point by
  copying into a new chat; merge-back, even merging, creates a
  new chat rather than editing a target in place. No branch
  operation ever mutates a source.
- **Archive restore:** imports into a fresh staging database and
  refuses to overwrite a working installation — the tree's
  restore verb has always meant "stage a new copy".
- **The branches law:** later work is preserved, never silently
  discarded. An in-place rewind would have to delete or exile
  every post-checkpoint message and would break branches forked
  from those messages; restore-as-new makes the question moot —
  nothing is ever discarded, so nothing needs exiling.

What the restored chat carries, field by field:

- **Identity:** a fresh chat id; the owner is the caller.
- **Title:** the explicit restore `name` if given, else
  `<snapshot title> (checkpoint: <checkpoint name>)` (falling
  back to `Untitled chat` if the snapshot title is empty).
- **Settings from the payload** — as they were when the
  checkpoint was taken, not the live chat's possibly-changed
  values: `character_id`, `preset_id`, `backend_profile_id`,
  `authors_note_json`, `post_history_json`, and
  `swipe_settings_json`.
- **Messages rebuilt verbatim** with the portable-restore decode
  discipline: fresh message ids, the new chat's id, and every
  other field exactly as snapshotted — original
  `created_at` / `updated_at` included, so the restored history
  reproduces the snapshot order, and full swipe decks with their
  selected `swipe_id`, so `content == swipes[swipe_id]` holds in
  the restored chat just as it did in the source.

What it does **not** carry:

- **Group link:** `group_id` is not carried — a restored chat is
  a standalone chat, not the group's room (the same precedent as
  branch spawning).
- **Branch lineage:** the restored chat is a root
  (`branch_kind` default, no parent). Its lineage lives in its
  `checkpoint.restored` event data — it did not fork, it was
  restored.
- **Event log:** the payload holds none; the restored chat's log
  starts with its own `checkpoint.restored` event.

And the snapshot is frozen: messages appended to, or edited in,
the source *after* the checkpoint was taken do not appear in a
restore. A checkpoint is a moment, not a view.

## Events

- **Create**, on the source chat: `checkpoint.created` with data
  `{"checkpoint_id", "name", "message_count"}` — recorded only
  after the file is durably in place, so the log never claims a
  checkpoint the disk does not have.
- **Restore**, on the source chat: `checkpoint.restored` with
  data `{"checkpoint_id", "name", "restored_chat_id"}`.
- **Restore**, on the restored chat: `checkpoint.restored` with
  data `{"source_chat_id", "checkpoint_id", "name",
  "restored_messages"}`. Both restore events land in the same
  commit as the restored chat and its messages — the restore and
  its audit trail land together or not at all.
- **Delete** records **no** event (a pinned decision): deletion
  must stay possible even for a corrupt file, and the chat's log
  is not owed a note about a file it can no longer reach.

## Safety and honesty rules

Every operation, in this order, no exceptions:

1. **Owned chat first.** The caller's owned chat is verified
   before any file is touched, and the path is built from the
   caller's own user id and the verified chat id — there is no
   code path that reads outside
   `checkpoints/<caller>/<that chat>/`. A missing or foreign chat
   is a 404 and no other owner's or chat's file is ever opened.
2. **Id validation before any path join.** A checkpoint id must
   be a plain filename stem (`^[A-Za-z0-9][A-Za-z0-9_-]*$`);
   traversal (`../x`, `..`, `a/b`, `a\b`) and anything else
   malformed is refused with 422 before a path is constructed —
   with a defence-in-depth check after the join that the resolved
   file's parent is the chat's checkpoint directory.
3. **Envelope and identity binding on load.** Format name and
   version, presence and types of every envelope field, and
   binding: the document's `id`, `chat_id`, and `user_id` must
   equal the requested id, the path's chat, and the caller. A
   checkpoint file copied into another chat's (or another
   user's) directory is foreign and refuses — it is never served
   and never restored from the wrong home. Each payload message's
   `chat_id` must likewise match the payload chat.
4. **Checksum verified on get and on restore.** A single flipped
   character in a stored message refuses the read. Restore
   verifies *before* any row is added, so no partial chat can
   survive a refused restore. Listing is the only unverified
   read — it exposes metadata only — but a file that does not
   even parse raises loudly (422) rather than being silently
   dropped from the list: honesty over tidiness.
5. **Unknown vs corrupt stay distinct.** A well-formed id with
   no file is 404; a file that exists but fails any check is 422.
   Never collapse the two — a 404 for a tampered file would teach
   clients it vanished. Blank explicit names are 422 on create
   and on restore.

Isolation is pinned at service level with a second user: as
another user, create / list / get / restore / delete on the
owner's chat all return `None`, a foreign restore creates no
chat, and the foreign user's list on their *own* chat never sees
the owner's checkpoints.

## Chat deletion removes its checkpoints

Checkpoints are bookmarks of one chat's life: when that chat is
deleted, its whole checkpoint directory
(`checkpoints/<user_id>/<chat_id>/`) is removed with it. A
checkpoint never outlives its chat as a restorable object —
restore needs the living source to audit against, so a dead
chat's checkpoints would be unreachable orphans anyway; deleting
them is the honest version of that fact. (Contrast branches,
which *do* outlive a deleted parent: a branch is a living chat in
its own right.) Chats **restored from** those checkpoints are
unaffected — they are independent chats with their own ids and
any checkpoints of their own.

The helper is `remove_chat_checkpoints(user_id, chat_id)`:
synchronous, best-effort, returns `True` when the directory is
absent afterwards (including "never existed") and never raises
for a missing directory. The wiring removes files *after* the
database commit succeeds: a crash in between leaves an inert,
unreachable orphan directory (collectable by hand), while the
reverse order could leave a living chat whose bookmarks were
destroyed by a rolled-back deletion — so commit-first is pinned.

## Known limitations

- **Installation-local:** checkpoints are not carried by portable
  archives or full backups in this slice (see the storage
  tradeoff above); they do not survive their chat (previous
  section) and do not move between installations.
- **Metadata-only reads:** list and get return metadata only,
  never message bodies or the checksum; content comes back
  exclusively by restoring.
- **Names are labels:** not unique, not identity; two checkpoints
  in the same second may share a default timestamp name.
- **Empty chats are legal:** a checkpoint of a chat with zero
  messages has `message_count` 0 and restores to an empty new
  chat — a bookmark of a beginning, not an error.
- **No locking:** a single local owner making sequential API
  calls is assumed, as elsewhere in the tree.

## Verification

Battery: `tests/test_p067_checkpoints.py`, following the design's
battery plan (§7) — A: create/list/get round-trip and the on-disk
document; B: payload deep-equality with `row_to_dict` and with
the exported `.runmal` archive member, checksum recomputation,
swipe-deck fidelity; C: restore-as-new correctness (fresh ids,
original timestamps, snapshot-time settings including author's
note, group link dropped, root branch kind); D: source untouched,
snapshot frozen against later appends/edits, exact
`checkpoint.created` / `checkpoint.restored` event data on both
chats, no event on delete; E: delete flow and survival of
previously restored chats; F: two-user isolation at service
level, wrong-chat ids, copied-file refusal; G: blank names,
traversal and malformed ids, unknown ids, tampered content /
checksum / envelope, non-JSON files, empty chats, missing chats
on all five routes; H: migration head pinned at 0037 with no
0038, archive-member parity, chat-deletion interplay. Measured
counts are recorded in the slice evidence file from the battery
log, not restated here.
