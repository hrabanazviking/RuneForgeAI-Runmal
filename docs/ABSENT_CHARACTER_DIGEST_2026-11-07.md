# Absent-character history digest (P-071)

Part V (Chat Surgery), roadmap `RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`:
*multi-character scenes with absent-character history sharing — a
returning character receives a digest of what it missed.* Built
clean-room from the roadmap line and Rúnmál's own contracts.

## What a scene gains

In a persistent group room (S210), a member character can now be
**absent** for a while and **return** — and the return delivers a
**digest of what it missed**: the messages posted in the room while
it was away, built from the real stored transcript, in transcript
order, with who said what.

Presence is explicit. A character is absent only from the moment
someone marks it absent until the moment it returns:

- `POST /groups/{id}/members/{character_id}/leave` → the presence
  record (200). Records a metadata-only `presence.left` event on
  the room chat: the character id + name snapshot, the id of the
  latest room message at that moment (its *last-seen anchor*), and
  the room's message count at leave time.
- `POST /groups/{id}/members/{character_id}/return` → the digest
  (200). Builds the digest over the absence window, records a
  metadata-only `presence.returned` event (counts and message ids
  only — never text), and closes the absence. The return **is** the
  delivery: a second return refuses (422), so a character can never
  be present-but-never-caught-up, nor absent-but-already-delivered.
  Optional JSON body `{max_entries, excerpt_chars}` (defaults
  50 / 200; ranges 1..500 / 20..5000, out-of-range is 422).
- `GET /groups/{id}/members/{character_id}/digest` → the same
  digest as a **preview** while still absent (caps as query
  parameters). Previewing mutates nothing.
- `GET /groups/{id}/presence` → a bare list with one record per
  current member: present flag, `absent_since`, the last-seen
  anchor, and the live missed count while absent.

Errors follow the house split: a missing or foreign group is 404
on every route; a non-member character, a double leave, a return
while present, and a digest while present are 422.

## The digest document

```json
{
  "kind": "extractive_digest",
  "digest_version": "extractive-1",
  "group_id": "...", "chat_id": "...", "group_name": "Mead Hall",
  "character_id": "...", "character_name": "Bryn",
  "absent_since": "...", "built_at": "...", "delivered": true,
  "window": {
    "anchor_message_id": "...", "anchor_message_count": 2,
    "resolution": "by_id",
    "first_missed_message_id": "...", "last_missed_message_id": "...",
    "missed_count": 3
  },
  "missed_count": 3,
  "own_messages_in_window": 0,
  "by_speaker": [{"speaker_id": "...", "speaker_name": "Una", "count": 2},
                 {"speaker_id": null, "speaker_name": "user", "count": 1}],
  "entries": [{"message_id": "...", "speaker_id": "...",
               "speaker_name": "Una", "role": "assistant",
               "excerpt": "We feasted without you.",
               "truncated": false, "created_at": "..."}],
  "omitted_count": 0,
  "empty": false,
  "text": "While Bryn was away, 3 messages were posted in Mead Hall:\n[Una] We feasted without you.\n..."
}
```

- **Window.** The absence window is every room message strictly
  after the last-seen anchor, in the tree's canonical message
  order (materialised position, then `created_at`, then id).
  `window.resolution` says how the window was cut: `by_id`
  (anchor found — the normal case), `from_start` (the room was
  empty at leave time; everything since is missed), or
  `by_count_fallback` (below).
- **Entries are capped, honestly.** `entries` holds the FIRST
  `max_entries` missed messages; `omitted_count` is always
  present, and `missed_count == len(entries) + omitted_count`
  always holds. Each entry's `excerpt` is the stored content cut
  at `excerpt_chars` — a plain cut, no ellipsis — with `truncated`
  saying whether it bit. `text` renders exactly those capped
  excerpts, never the full content behind the cap.
- **`by_speaker`** counts missed messages per speaker in
  first-appearance order and sums to `missed_count`. The user's
  messages coalesce under `{speaker_id: null, speaker_name:
  "user"}`. Messages the returning character itself posted while
  away are not "missed": they are excluded from entries and
  counts and reported as `own_messages_in_window`.
- **`character_name`** is the snapshot taken at leave time; a
  rename during the absence does not rewrite the digest.
- **Prompt shape.** `runmal.groupchat.presence.digest_prompt_message(digest)`
  wraps the digest as one `{"role": "system", "content": ...}`
  message in the group core's `build_prompt` shape, labelled as a
  history digest for the returning character, ready to sit ahead
  of the scene history in that character's next prompt.

## If the anchor message is deleted while away

The window is normally resolved by message id, which no other
deletion can disturb. If the anchor itself was deleted (room
messages are deletable through the chats API), the digest falls
back to the recorded message-count-at-leave: the window starts at
index `anchor_count - 1` of the current transcript, and
`window.resolution` says `by_count_fallback` so no reader mistakes
it for the exact road. That slice is exact when the anchor is the
only pre-window deletion; if D pre-window messages were deleted in
total, the earliest D-1 missed messages fall before the slice and
are lost to the digest. This approximation is deliberate, labelled
in every affected digest, and pinned by the battery.

## Honest boundaries

- **The digest is extractive, not a summary.** It lists who spoke
  and excerpted what they said, in order. It does not paraphrase,
  infer, or call any backend. What it shows is exactly what was
  stored, cut at the excerpt cap.
- **It reflects current stored content.** A message edited or
  swipe-changed while the character was away digests as it now
  reads (variant history is not consulted); a message deleted
  while away is simply absent from the window.
- **Presence is never inferred.** A member who was merely quiet,
  muted (S211), or removed from the roster is not absent. Removal
  is not a leave: presence events live on the room chat, not on
  the membership row, so a character removed and re-added with an
  open absence can still return and digest the whole period —
  but while removed it is not a member and cannot return.
- **Absence does not gate speech.** Speaker policies and
  `append_message` are untouched; an absent character can still
  be posted and its own in-window messages are accounted as its
  own (above).
- **Scope** is the persistent room on its current linear
  transcript. Branches and checkpoints are separate chat rows and
  are not folded in; the stateless `/group/turn` core is
  unchanged apart from the prompt-block helper shape.
- **No migration.** Presence rides the existing `chat_events`
  log (S107) — metadata only, in the P-056/P-065/P-069 precedent
  that events never carry message text. The digest itself is
  derived on demand and is never stored as a message or a
  summary row.
