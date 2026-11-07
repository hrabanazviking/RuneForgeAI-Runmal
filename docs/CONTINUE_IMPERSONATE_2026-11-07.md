# P-069 — Continue & Impersonate (2026-11-07)

*Part V (Chat Surgery). The roadmap's own text for this slice
is: "P-069 Continue & impersonate: nudge-generation and
user-turn drafting by the model, the mirrors' pair." Built
clean-room from the roadmap and Runmal's own contracts only.*

## The pair

The two operations are mirror images, and this slice keeps
them that way — one generation road, opposite landing rules.

**Continue** asks the model to move the conversation forward
from the current chat state, and the result LANDS:

- `extend` — the last message is the assistant's, and the
  model continues it. The generated text is a fragment: it is
  appended onto that message in place, swipe-deck aware, so
  the deck invariant (`content == swipes[swipe_id]`) keeps
  holding and the message count does not change.
- `next` — the model writes the next assistant turn, the
  nudge that raises the next beat. The text lands as a NEW
  assistant message carrying the chat character's speaker
  snapshot.
- `auto` (the default) picks `extend` when the last message
  is the assistant's and `next` otherwise. An explicit
  `extend` against a non-assistant last message refuses, as
  do an unknown mode, an empty chat (nothing to continue),
  and a generation that errors, is cancelled, or produces no
  text — in every failure case nothing is stored.

**Impersonate** asks the model to draft the next USER turn,
in the voice the user's own earlier messages evidence — and
the result NEVER lands on its own:

- The response is a draft document, visibly a draft:
  `status: "draft"`, `draft: true`, `role: "user"`,
  `message_id: null`, `generation_state: "candidate_ready"`,
  plus the message the draft was based on and the prompt
  fingerprint. The chat's history is byte-for-byte untouched.
- The draft becomes a message only when the user accepts a
  final text through the accept road — the draft verbatim,
  or the user's own edit of it. The user always supplies the
  text that lands; nothing impersonated is ever stored as if
  the user wrote it unreviewed.
- Discarding a draft stores nothing — there is nothing to
  delete, because a draft was never stored.

In `generation/modes.py` terms (S209, where the impersonate
mode has lived since the mode machine): a draft is an
IMPERSONATE candidate at CANDIDATE_READY that has not been
committed; accept is the commit, performed by the user with
the final text in hand. A continue walks a NORMAL session
all the way to COMMITTED before it lands.

## The generation road

Both halves compose their prompt the same way, through the
road the bridge generation already walks
(`bridge/conversation.py`): the persona system prompt from
the chat character's card slots (`runmal.persona`), then the
stored history in order, then exactly ONE trailing system
instruction — the extend text, the next text, or the
impersonate text. A caller may add one instruction of their
own; it is appended to the nudge, never substituted for it.

Generation runs through `generation/service.generate_events`
with the chat's backend resolution (the chat's pinned
backend profile, else the offline fake default), and the
text is collected under the bridge's store-only-on-clean-
finish contract.

**Honest boundary (Part IV gate finding F2, carried).** Live
generation in this tree does not route through the prompt
composer/inspector, so this slice composes through the
persona-slot + history road and claims nothing about
composer assembly. Wiring generation through the composer
remains a separate future slice, and it inherits both halves
unchanged. With no backend profile pinned, the backend is
the deterministic fake and the generated text is the stub
text — the slice claims the machinery, not literary quality.

## Storage and the event log

No migration is taken (the head stays at 0037; provisional
0040 is not used). Continue needs no new storage: extend
grows an existing message, next appends one. A draft needs
no storage by design: candidate state lives with the
caller, exactly where `GenerationSession` candidates live,
and the final text rides back on the accept call.

The chat event log records the pair as metadata only —
`message.continued` (mode, generated character count,
backend), `impersonate.drafted` (count, backend,
fingerprint), `impersonate.accepted`, `impersonate.discarded`
— and never carries generated or drafted text, following the
tree's metadata-only event precedent (P-056, P-065).

## Surface

Service layer: `src/runmal/chats/continue_impersonate.py`
(pure builders `build_continue_messages` /
`build_impersonate_messages` / `resolve_continue_mode`, and
`continue_chat` / `impersonate_draft` / `accept_impersonate`
/ `discard_impersonate`), exported from `runmal.chats`.

REST (all under the local bearer credential):

- `POST /chats/{id}/continue` → 201 landing document;
  422 invalid mode / empty chat; 502 generation failed;
  404 chat missing or foreign.
- `POST /chats/{id}/impersonate` → 201 draft document;
  422 empty chat; 502 generation failed; 404 as above.
- `POST /chats/{id}/impersonate/accept` → 201, the stored
  user message; 422 empty content; 404 as above.
- `POST /chats/{id}/impersonate/discard` → 200
  `{"discarded": true}`; 404 as above.

Cross-user isolation is the owned-chat check on every entry:
a foreign chat is indistinguishable from a missing one, and
no generation runs for a chat the caller does not own.

## Limitations, named

- **Stateless drafts.** A draft the client loses is gone;
  there is no draft list, no draft history, and no
  server-side edit endpoint — editing is the client's text
  until accept. Server-side draft persistence would need a
  store this slice deliberately does not invent.
- **One instruction, no sampler surface.** Continue and
  impersonate accept an optional free-text instruction but
  no per-call sampling parameters; generation uses the
  backend's defaults, as the bridge generation does.
- **Extend is text append.** Extending a message appends to
  its active swipe alternate; the other alternates are
  untouched, and no new alternate is created for the
  continuation.
- **Group chats.** The pair operates on ordinary chats;
  in a group room chat it drafts/continues against the
  room's stored history and the chat's pinned character,
  with no per-member speaker selection.
