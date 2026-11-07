# P-068 — Message actions complete (Part V, Chat Surgery)

Roadmap line: *Message actions complete: edit (with variant
history), delete, move, copy-to-branch, pin-to-memory.*

Clean-room: built from the roadmap line and Runmal's own
contracts only. Base 61cad2e (P-065 banking record), migration
head at base 0036. Built from that base by design (the keeper
reconciles at banking): P-066 has since banked elsewhere (head
0037) and P-067 (in flight) reserves 0038.

## What existed before

- `edit_message` REPLACED the active swipe in place: the prior
  content was silently destroyed. `delete_message` existed but
  knew nothing of pins or ordering.
- No move/reorder at all: history order was `created_at` alone,
  so a move could only have been faked by rewriting timestamps.
- No copy-to-branch, no per-message pin. The Memory subsystem
did have the honest road for a pin: `Memory.pinned` +
  state `pinned`, and retrieval's default states already
  include `pinned`.

## Storage — PROVISIONAL migration 0039 (flagged loudly)

Storage is unavoidable, and the proof is the base schema: no
column holds an edit's replaced text, a per-message pin flag,
or an explicit order. **0039 PROVISIONAL** (`m0039_message_actions`,
idempotent ALTERs; 0037 is P-066's, 0038 is reserved for P-067;
the keeper reconciles numbering at banking, as with 0034–0036):

- `messages.variant_history_json` TEXT NOT NULL DEFAULT '[]' —
  replaced contents in edit order (see `chats/actions.py`).
- `messages.pinned` INTEGER NOT NULL DEFAULT 0 — the pin flag;
  the pin's Memory row lives in `memories` (below).
- `messages.position` INTEGER NULL — explicit in-chat order
  once materialised; NULL = legacy `created_at` order.

All migration head pins in the tree were swept 0036 → 0039
in-slice (37 test files).

## The slice

- `chats/actions.py` (pure): `parse_history` (defensive reads,
  never raises), `record_edit` (append, cap `MAX_VARIANTS = 50`,
  oldest dropped, input never mutated), `validate_move_target`
  (STRICT: no clamp, no wrap, bools rejected), `move_index`.
  Contract: the swipe deck holds ALTERNATES (parallel candidates);
  the variant history holds VERSIONS (the lineage of the active
  alternate). They compose; neither impersonates the other.
- Edit (`service.edit_message`): the replaced active content is
  appended to the variant history BEFORE the deck updates, so
  `content == swipes[swipe_id]` always holds and nothing is
  silently overwritten. Identical-content edit is a no-op (no
  history, no event). `get_message_variants` exposes the history.
  Editing a PINNED message refreshes its pin Memory content —
  memory never silently diverges from the message it pins.
- Delete (`service.delete_message`, completed): a pinned
  message's pin Memory + source link are removed first (no
  orphans); in a materialised chat the survivors are renumbered.
- Move (`service.move_message`): strict target index; the first
  move in a legacy chat materialises positions `0..n-1` for the
  whole chat in current order, then applies the move. Positions
  are always unique and contiguous in a materialised chat;
  appends after materialisation take the next position. Moving
  to the current index is a no-op (no event, no materialisation).
  `get_history` now orders by (position NULLs last-by-flag,
  position, created_at, id) — deterministic everywhere.
- Copy-to-branch (`service.copy_message_to_branch`):
  FOOTPRINT FLAG — this base predates P-066's branch columns,
  so a branch here is a CHAT. No target: a new chat is forked
  carrying every message up to and including the source (the
  fork-at-message shape), titled `<title> (branch)` unless a
  title is given. With `target_chat_id`: a copy of the single
  message is appended to that chat. Both chats must be owned
  (foreign/missing target raises KeyError → 404). Decks,
  variant history, speakers and roles are deep-copied — later
  edits never bleed across chats. Copies are never pinned and
  carry no pin Memory. KEEPER: re-target this surface onto
  P-066's branch model at banking if it differs.
- Pin-to-memory (`pin/unpin/list_pinned_messages`): pinning
  creates a REAL Memory through `runmal.memory.service` —
  `pinned=True`, state `pinned`, kind `episodic`, scope `chat`,
  salience/stability 1.0 — plus a `MemorySource`
  (`message`, message_id, chat_id) link and an FTS index row,
  so pinned content surfaces through the existing retrieval
  road (battery proves an FTS hit). Pinning is idempotent.
  `list_pinned_messages` takes its truth from the source link,
  so it stays correct even if a pin Memory is removed elsewhere.
  Unpin deletes the Memory and clears the flag.
- Events (`message.edited` now carries `variant_count`;
  `message.moved` indexes only; `message.copied_to_branch` ids +
  count + mode; `message.pinned_to_memory` memory id;
  `message.unpinned_from_memory`): metadata only — never message
  text (battery scans all events for a planted secret).
- REST: `GET .../messages/{id}/variants`,
  `POST .../messages/{id}/move`,
  `POST .../messages/{id}/copy-to-branch` (201),
  `POST .../messages/{id}/pin` (201, returns the Memory),
  `DELETE .../messages/{id}/pin`,
  `GET /chats/{id}/pinned-messages`. Missing/foreign → 404;
  bad move target → 422. `message_to_dict` gains
  `variant_history` / `variant_count` / `pinned` / `position`.
  Cross-user isolation holds for every action. Group chats share
  the `messages` table, so their messages gain the same actions
  through the same service.

## Honest boundaries

- Copy-to-branch targets the chat-level fork verifiable in this
  base, NOT P-066's branch columns (not in tree) — flagged for
  the keeper above and in the evidence.
- No prompt-assembly change: pinned messages surface through
  the memory system's existing retrieval, which is where pins
  honestly live; nothing fakes a second prompt road.
- Variant history is capped at 50 entries per message (oldest
  dropped); the cap is part of the pure contract and tested.
