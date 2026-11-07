# Chat Branches — P-066 (2026-11-07)

Part V (Chat Surgery) opens with the conversation becoming a
tree: any chat can be forked at any message, branches can be
listed and named, and a branch can be merged back — always as a
new branch, never by changing anything that already exists.

## What shipped

- `src/runmal/chats/branches.py` — the branch service:
  `fork_chat`, `list_branch_family`, `rename_branch`,
  `merge_back`, `branch_info`.
- `chat_to_dict` gains an additive `branch` sub-document
  (kind, parent_id, fork_message_id, fork_index, merge_of,
  is_branch) — the P-056/P-057 additive precedent.
- Routes: `POST /chats/{id}/branches` (201),
  `GET /chats/{id}/branches`, `POST /chats/{id}/merge-back`
  (201), `POST /chats/{id}/branch-name`.
- PROVISIONAL migration **0037** (see below) and the five
  lineage columns on the `Chat` model.
- Battery: `tests/test_p066_branches.py`.

## Semantics

**Fork.** Forking copies the source history up to and including
the chosen message (the whole history when no message is given;
an empty chat forks to an empty branch). The branch is a full
chat of its own: fresh chat and message ids, original timestamps
and speaker snapshots on the copies, and the source's character,
preset, backend profile, author's note and post-history carried
over. Its event log is NOT copied — it starts with a
`branch.created` event stating exactly what was copied, and the
source records `branch.forked`. Default name:
`<source title> (branch)`; an explicit name wins.

**List.** `GET /chats/{id}/branches` returns the family: root,
ancestors, self, children, descendants and the whole family set,
every member a full chat document named by its title. The walk
is cycle-guarded; a deleted parent simply ends the chain.

**Name.** `POST /chats/{id}/branch-name` sets the branch's own
title (event `branch.renamed`). Blank names are refused (422).

**Merge-back.** Always a NEW chat: the target's full history
followed by the branch's divergent suffix — the branch messages
after its fork index when it forked directly from the target,
otherwise the branch's whole history. The target defaults to
the branch's parent. Refusals (422): merging into itself,
a parentless chat with no target, a blank name, and a branch
with nothing divergent to contribute. A missing branch or
target is 404.

## The never-destructive law

No branch operation mutates or deletes a source chat, branch or
message. Fork copies; merge creates; rename touches only the
branch's own title. `branch_parent_id` is a plain id with NO
foreign key on purpose: deleting a parent can never cascade
into a branch — a branch outlives its parent with its copied
history intact (battery-pinned).

## Migration — PROVISIONAL 0037 (flagged)

Branch lineage must be first-class, queryable data (P-067
checkpoints, P-068 copy-to-branch and P-078 import surgery all
build on it), so the append-only event log was not used as a
lineage store. 0037 adds `branch_parent_id`,
`branch_fork_message_id`, `branch_fork_index`, `branch_kind`
('root' | 'fork' | 'merge') and `branch_merge_of_json` to
`chats`. **0036 is reserved for P-065** (swipes deepened,
team-03), which banks before this slice; the keeper inserts it
beneath 0037 and heals the older 0035 head pins at banking
(the P-056/P-057 precedent).

## Honest limitations

- Merge is message-grain concatenation, not a three-way text
  merge: divergence inside a single message is never reconciled;
  the suffix is appended whole.
- Ordering is timestamp-only (no sequence column). Fork copies
  keep original timestamps, so a branch and its parent share
  `created_at` values across the prefix. A merge suffix whose
  timestamps would interleave into the target is shifted as one
  block (gaps preserved) to start just after the target's last
  message — concatenation order wins over wall-clock purity.
- Branches of group-room chats are standalone: the group-room
  link (`group_id`) is deliberately NOT carried, so a branch can
  never impersonate the group's room. Group membership context
  is therefore not part of a branch.
- Swipes interplay (P-065, banking before this slice): a fork
  copies each message's current stored content; per-message
  swipe alternates are P-065's storage layer, and the keeper
  reconciles any overlap at banking.
- Pre-existing quirk noticed, not fixed here (app-wide, predates
  this slice): message `created_at` serialises with `+00:00` in
  creation responses but naive on read-back. Recorded as a
  finding in the slice evidence.

## Neighbours this enables

P-067 checkpoints can anchor to branch tips; P-068's
copy-to-branch reuses `fork_chat`'s copy discipline; P-078
import surgery can record imported lineages in the same columns.
