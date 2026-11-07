# P-065 — Swipes deepened (Part V opener)

Roadmap line (Part V — Chat Surgery): *Swipes deepened: unlimited
alternates per message, swipe navigation everywhere (incl. voice
turns), swipe-specific regen settings.*

Clean-room: built from the roadmap line and Runmal's own contracts
only. Base 3b39823 (P-064 banking record, Part IV complete), migration
head at base 0035.

## What existed before

- A persisted chat message held exactly ONE text (`messages.content`).
  No alternate could be stored, let alone navigated.
- `generation/modes.py` GenerationSession already modelled swipe /
  regenerate candidates — ephemerally, per generation, never persisted
  onto a message (swipe clamps at both ends; candidates never
  destroyed). P-065 keeps that machine untouched and gives its
  candidates a durable home.
- The P-020 file layer already spoke swipes (`ImportedMessage.swipes` /
  `swipe_id`), and its bridge said the quiet part out loud: alternates
  beyond the active one "cannot be held by the live projection".
  P-065 removes that limitation at the live layer; making imported
  chats fully live remains P-078's slice.

## Storage — PROVISIONAL migration 0036 (flagged loudly)

Durable alternates cannot be conjured from existing columns, so this
slice takes migration **0036 PROVISIONAL** — the number is PROVISIONAL
and the keeper reconciles numbering at banking, exactly as 0034 (P-056)
and 0035 (P-057) were carried. `m0036_message_swipes` adds, idempotently:

- `messages.swipes_json` TEXT NOT NULL DEFAULT '[]' — the ordered
  alternates, INCLUDING the active one.
- `messages.swipe_id` INTEGER NOT NULL DEFAULT 0 — the active index.
  (Vocabulary matches the P-020 file layer: `swipes` / `swipe_id`.)
- `chats.swipe_settings_json` TEXT NOT NULL DEFAULT '{}' — ONE validated
  JSON document, the P-056/P-057 per-chat pattern.

**Deck invariant:** `content == swipes[swipe_id]` at all times, so every
existing reader of `content` (prompt assembly via
bridge/conversation.py, history, export) sees the ACTIVE alternate and
never a hidden one. Legacy rows (`swipes_json = '[]'`) read as the deck
`[content]` at id 0; corrupt or mismatched stored decks read the same
way (defensive reads, P-056/057 law — reads never raise) and the first
mutation materialises a clean deck.

## The slice

- `chats/swipes.py` (pure): `deck_for` defensive reads; `navigate`
  (next/prev clamped like GenerationSession.swipe, first/last, goto
  clamped); `select_index` STRICT (no clamp, no negative wrap);
  `SwipeRegenSettings` — strict validated data {enabled, params}, the
  params bag judged by presets' own `validate_params`, so swipe regen
  speaks exactly the canonical sampler vocabulary; `resolve_params`
  merges settings over a base bag into a NEW dict (inputs never
  mutated); `swipes_from_session` adapts GenerationSession candidates.
- `chats/service.py`: append seeds deck `[content]`; `add_swipe`
  appends and activates (no count cap — unlimited alternates);
  `select_swipe` (exactly one of action/index); `delete_swipe`
  (refuses the last alternate; deleting the active picks next else
  prev; deleting an earlier inactive shifts the active id down);
  `edit_message` edits the ACTIVE alternate only; per-chat
  `get/set_chat_swipe_settings`; `resolve_swipe_params` (chat preset
  params as base, swipe settings override when enabled);
  `import_session_swipes` (a finished generation session's candidates
  become a message's deck, active index preserved). Events
  (`message.swipe_added/selected/deleted`, `swipe_settings.changed`)
  record indexes, counts and param KEYS only — never alternate text,
  never param values (battery scans for a planted secret).
- `chats/router.py`: POST `.../messages/{id}/swipes` (201),
  POST `.../swipes/select`, DELETE `.../swipes/{index}`,
  GET/POST `/chats/{id}/swipe-settings`,
  GET `/chats/{id}/swipe-regen-params`. Missing chat/message and
  cross-chat message ids are 404; bad input is 422. No role gating:
  user, assistant and system messages may all carry alternates
  (impersonate-mode user candidates are the honest reason).
- `message_to_dict` gains `swipes` / `swipe_id` / `swipe_count`;
  `chat_to_dict` gains `swipe_settings`; chat export carries the deck
  per message. Group chats share the same `messages` table, so their
  messages are swipe-navigable through the same service unchanged.

## Voice turns — the honest boundary

Swipe navigation applies to every PERSISTED message through the one
service/API above. The voice orchestrator's turns are ephemeral
`TurnRecord`s: they are never persisted as chat messages today, so
there is no stored voice-turn row to navigate — stated plainly rather
than faked. The bridge that exists: a voice turn's responder speaks
through generation candidates, and `import_session_swipes` lands any
finished GenerationSession's candidates — voice-origin included — as
a persisted, navigable deck the moment the turn is committed as a
message. Persisting voice turns themselves is a voice-campaign
decision, not smuggled into this slice.

## Evidence

Battery `tests/test_p065_swipes.py`: 79 tests. Neighbour and full-suite
counts live in the team worktree's hidden_files/P065_EVIDENCE.md,
read from the run logs. Neighbour batteries' migration head pins were
moved 0035 -> 0036 in this commit, the established migration-slice
pattern (P-057 did the same); historical assertions about 0035 itself
were left untouched.
