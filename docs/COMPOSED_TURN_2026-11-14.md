# The Composed Turn — R-03 (2026-11-14)

The windowed-shell redo's second engine slice. Before R-03, the local
`POST /api/v1/generate` route could only stream caller-supplied raw
messages through a backend: it could not compose a prompt from a chat
(the character's system prompt never entered a locally generated
turn), it could not accept sampling parameters at all
(`GenerateRequest` was exactly `{messages, request_id, chat_id,
profile_id}`), a chat's persona could be switched only with a scoped
bridge token, and the `{{user}}` macro name was the hard-coded
default `"User"` everywhere. R-03 closes those four gaps. The
raw-messages contract is unchanged: a request carrying only
`messages` behaves exactly as it did before this slice.

## Two message sources, one stream shape

`POST /generate` now accepts two modes, both streaming the existing
SSE shape (`token` / `reasoning` / `usage` / `done` / `error`) and
both answering with `X-Request-ID` + `X-Backend-Key` (plus an
additive `X-Generation-Mode: raw|composed` header):

- **Raw mode** — the request carries `messages`; they are sent
  verbatim. This is the pre-R-03 contract, preserved byte-for-byte
  in behaviour.
- **Composed mode** — the request carries `chat_id` and no
  `messages` (or an empty list). The prompt is composed server-side
  via the bridge-proven path, `bridge.conversation.compose_messages`:
  the chat's active character's persona system prompt first (card
  slots via the S110 manifest, `{{user}}` resolved from the
  persisted user-name setting below), then the chat's stored
  history in order. The caller is expected to have already appended
  the user's new message to the chat (the ordinary chats API); the
  composed turn generates the reply to the conversation as stored.
  A chat that composes to nothing (no character prompt, no history)
  is a 422, and an unknown/foreign chat is a 404.

`/generate` never persists the reply, in either mode — exactly as
before R-03. Landing a generated turn in a chat remains the job of
the bridge generation road and of continue/impersonate, which have
their own provenance contracts.

## Backend resolution (unchanged order)

1. The request's explicit `profile_id` (unknown → 404).
2. The chat's pinned `backend_profile_id` (when `chat_id` names a
   chat; a pinned id whose profile has vanished falls back).
3. The engine default backend — the offline deterministic fake, so
   the route works with no provider configured.

There is no separate "default profile" store; step 3 IS the default,
as it was for the bridge and continue/impersonate roads.

## Sampling-parameter precedence (designed here)

`GenerateRequest` gains an optional `params` field: a param bag in
the presets shape (canonical field names; `max_tokens` spells the
output cap, as in every S207 bag). The effective params for one call
are merged **per key**, lowest precedence first:

1. **Engine defaults** — every field unset (`SamplingParams()`); the
   backend adapter's own defaults decide.
2. **The chat's preset params** — when `chat_id` names a chat with a
   preset pinned (`chats.preset_id`), that preset's stored params
   form the base layer.
3. **Per-send `params`** — this request's bag overrides the preset
   per key. Keys the request does not mention keep the preset's
   values; there is no per-send way to *unset* a preset key in this
   slice (send the value you want instead).

The merged bag is validated by `presets.service.validate_params`
(canonical types/ranges; unknown keys must be JSON-serializable) and
converted with `SamplingParams.from_bag`; the resulting typed value
is passed to the generation service and reaches the backend's
`chat_stream`. Invalid params answer 422 **before** anything
streams. Honest seam note: backends consume the canonical typed
`SamplingParams`, so only canonical fields reach them; an unknown
(backend-specific) bag key is validated and carried in the bag, but
the typed seam has no channel for it — the same limitation the
swipe-regeneration road already has.

The preset's `template_ref` and prompt material are NOT applied by
this road: R-03 applies preset *params* only, as the plan scopes it.
Prompt composition here is persona + history (the bridge road); lore
activation, author's-note injection, and the full prompt composer
remain the composer's own roads, exactly as the bridge documents
for its generation.

## Local persona route

New router `runmal.persona.router`, mounted under `/api/v1` behind
the ordinary local credential (NOT bridge-token only):

| Route | Purpose |
|---|---|
| `GET /chats/{chat_id}/persona` | The chat's active persona: `{chat_id, persona: {character_id, name} \| null}`. Unknown chat → 404. |
| `POST /chats/{chat_id}/persona` | Set/clear the persona (body `{"character_id": … \| null}`), over `chats.service.set_chat_persona` — the same service and future-turns-only semantics as the bridge route. Answers the new persona plus `previous_character_id`. Unknown chat → 404; unknown/foreign character → 422. |
| `GET /user-name` | `{user_name, is_set}` — see below. |
| `PUT /user-name` | Set the `{{user}}` name (body `{"user_name": …}`); empty clears to the default. Overlong/multi-line names → 422. |

## Persisted user name

`runmal.persona.user_settings`: one name, stored as a versioned JSON
document (`user_settings.json`) in the app data dir — the
voice-settings storage precedent, deliberately NOT a database
persona store (the plan's honesty rule: the engine's persona is a
character-card mask plus this name, and R-03 grows exactly that much
and no more). `get_user_name()` returns the stored name or the
default `"User"`; load is tolerant (missing/corrupt → default).
Composition resolves `{{user}}` from it on every road that builds a
persona system prompt from a card: `bridge.conversation.
compose_messages` (and therefore composed `/generate` and bridge
generation) and chats continue/impersonate. Callers may still pass
an explicit `user_name` to `compose_messages`, which wins.

## Verification

`tests/test_r03_composed_turn.py`: composed-mode composition (the
character system prompt leads the messages a recording backend
receives, history follows), precedence (per-send beats preset,
preset beats defaults — at the resolver and end-to-end), params
reaching the backend in both modes, invalid params as 422s, the raw
contract's exact stub reply, persona route auth + round trip +
error shapes, and user-name default/persistence/reset including its
effect on a composed prompt. The same flows are also driven with
curl against a locally served app in the slice's banking evidence.

Route-census heal (in-slice fix): the Part XIII route-census pins
(365 paths / 455 operations across 14 test files, plus the derived
remainders in the P-218 gate) were already stale at the R-03 base —
R-02's backend-profile roads (+7 paths / +12 operations) landed
without healing them. R-03 heals every pin to the measured census,
recording both deltas (its own roads: persona GET+POST, user-name
GET+PUT = +2 paths / +4 operations). One historical gate is
deliberately NOT healed: `test_p232_part_xiv_gate.py`'s tree-law
footprint asserts the diff since its own banking base is exactly
its four gate files — a point-in-time record that any later slice
breaks by construction; it fails identically at the R-03 base and
is recorded as known in the campaign state file rather than
falsified.
