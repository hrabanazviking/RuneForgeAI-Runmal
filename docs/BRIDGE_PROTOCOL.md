# Rúnmál Bridge Protocol

Bridges let VRChat, games and external companions use Rúnmál as a conversational brain without gaining unrestricted application access.

## 1. Versioning

External bridge APIs live under a versioned namespace such as:

`/api/v1/bridge/...`

Breaking changes require a new version boundary or an explicit compatibility transition. Internal web UI routes do not define the public bridge contract.

## 2. Bridge identity and scopes

Each bridge receives its own revocable credential and declared scope set, for example:

- `chat:read:<chat-id>`
- `chat:write:<chat-id>`
- `persona:select:<persona-id-or-set>`
- `tts:request`
- `events:read:<chat-id>`

A valid bridge token is not an application-admin token.

**As implemented (S601).** A scope string is `<capability>` or
`<capability>:<resource>`. Capabilities: `chat:read`, `chat:write`
(append turns and request/cancel generation for the chat),
`events:read` (poll/ack the outbox), `persona:select` (resource is a
character id) — these four require a resource — and `tts:request`,
which takes none. The resource `*` wildcards within its capability
only. Matching is exact on capability, exact-or-wildcard on resource;
nothing prefix-matches, so a grant cannot quietly widen.

Credentials are created by the owner through the local-auth admin API
(`POST /api/v1/bridge/credentials`, list + `.../revoke` alongside).
The token (`rmb_` + 32 random bytes, URL-safe) is shown **once** at
creation; only its SHA-256 hash is stored. Bridges authenticate with
`Authorization: Bearer <token>` on `/api/v1/bridge/...` routes only —
the local application credential is not a bridge token, and a bridge
token is not an application credential. `GET /api/v1/bridge/whoami`
returns the bridge's id, name and granted scopes (never token or hash)
as a pairing/scope probe.

## 3. Core resources

The v1 contract should provide:

- conversation-state read;
- append user/environment/companion turn;
- generation request/cancel;
- persona selection where scoped;
- TTS request/playback lifecycle where scoped;
- event outbox / poll or callback mechanism;
- health/capability discovery.

**As implemented (S602).** Under `/api/v1/bridge`, every response
carries the protocol version (`protocol_version` field / the
`X-Bridge-Protocol` header on streams):

- `GET /bridge/chats/{chat_id}` (`chat:read`) — state: chat metadata,
  active persona, ordered messages with speaker snapshots.
- `POST /bridge/chats/{chat_id}/turns` (`chat:write`) — one turn per
  §6; 201 with the stored message.
- `POST /bridge/chats/{chat_id}/generate` (`chat:write`) — SSE stream:
  `turn_started` (with `request_id`), the normalized generation
  events, and `turn_stored` after a clean finish persists the reply
  as the active persona. Cancelled/errored generations store nothing.
- `POST /bridge/chats/{chat_id}/generate/cancel` (`chat:write`) —
  `{request_id}` → `{cancelled: bool}`.

## 4. Idempotency

Externally retried writes accept an idempotency key. Repeating the same key with the same logical request returns the existing result instead of duplicating messages/actions.

Conflicting reuse of the same key is an error.

**As implemented (S610).** Keys arrive via the `Idempotency-Key`
header or the body's `idempotency_key` field (max 200 chars), scoped
per credential + operation in `bridge_idempotency_keys` (migration
0018). A SHA-256 fingerprint of the canonical request detects
conflicting reuse: same key + different request = **409**. Turn
retries replay the stored 201 response verbatim with an
`Idempotency-Replayed: true` header. Generation retries replay the
stored terminal summary (`turn_started`, `done`, `turn_stored`) —
the outcome, not a re-performance of the token stream — and never
persist a second companion turn. Discovery lives at
`GET /api/v1/bridge/capabilities` (any valid bridge token): protocol
version, granted scopes, feature flags, event kinds, and limits.

## 5. Event outbox

Bridges need more than request/response when a companion may initiate speech.

Use a durable/pollable event outbox or equivalent with:

- monotonically ordered event IDs per stream;
- acknowledgement/checkpoint semantics;
- replay after temporary disconnect;
- bounded retention;
- event types such as `companion_turn_ready`, `tts_ready`, `playback_complete`, `persona_changed`, `generation_cancelled`.

Webhook delivery may be added, but the durable outbox is the recovery source of truth.

**As implemented (S609).** `bridge_events` (migration 0017) is the
outbox: integer AUTOINCREMENT ids, one stream per chat. Producers:
turn writes (`turn_appended`), finished generations
(`companion_turn_ready`), cancelled generations
(`generation_cancelled`), persona switches (`persona_changed`), TTS
jobs first observed ready with a chat attached (`tts_ready`), and
bridge-reported playback completion (`playback_complete`).
Consumers: `GET /api/v1/bridge/chats/{id}/events` (scope
`events:read:{id}`) with `after`/`limit`; omitting `after` resumes
from the caller's checkpoint; `POST .../events/ack {event_id}` moves
the per-credential checkpoint forward (monotonic, clamped to the
newest existing event). Retention keeps the newest 1000 events per
chat; a consumer that falls behind the window resyncs from the
conversation-state read (§3).

## 6. Conversation writes

A bridge-submitted turn declares:

- bridge ID;
- target chat;
- speaker/source identity;
- content;
- timestamp supplied by bridge plus server receive time;
- idempotency key;
- optional environment metadata allowed by scope.

The server owns final ordering/IDs.

## 7. Generation

Generation requests reference existing conversation state rather than shipping an entire secret-bearing application prompt from the bridge.

Return a generation/turn ID immediately enough to support cancellation. Streaming transports may be SSE/WebSocket depending on consumer needs, but events normalize to the same application model.

## 8. Persona switching

Persona changes are explicit state changes. Prompt traces and subsequent turns record which persona version was active.

Switching persona does not retroactively rewrite previous speakers/history.

## 9. TTS lifecycle

TTS bridge requests may return audio, a stream or a playback job reference depending on integration. Playback completion/interruption feeds the voice playback-truth ledger when Rúnmál owns the audio path.

## 10. VRChat reference bridge

VRChat support consists of distinct concerns:

1. OSC/avatar/control integration;
2. Rúnmál conversation bridge;
3. companion speech output routing;
4. **PC-host room/game audio ingress** if the companion is expected to hear other participants.

OSC alone does not provide whole-room voice capture. Room listening requires an explicit host audio route and must be tested separately.

## 11. Game bridges

Conan/Skyrim-style adapters translate game events into the stable bridge protocol. Game-specific RCON/mod/network quirks remain outside Rúnmál core.

The core should not acquire `if game == ...` branches.

## 12. Latency classes

Consumers may declare a latency class:

- `realtime_voice` — optimize first-audio latency and interruption;
- `interactive_text` — token streaming desired;
- `game_turn` — seconds of latency acceptable;
- `background` — non-interactive work.

This is guidance for scheduling/metrics, not permission to violate correctness.

## 13. Security boundaries

- Bridge credentials are server-side secrets.
- Scope enforcement occurs on every operation.
- Logs identify bridge ID but redact token.
- Bind-to-localhost remains the default unless the user deliberately exposes the service.
- Remote exposure requires the security model's transport/auth requirements.

## 14. Contract tests

Every reference bridge must prove:

- wrong-scope denial;
- revoked-token denial;
- duplicate idempotency request does not duplicate turns;
- disconnect/reconnect resumes event outbox correctly;
- persona switch affects future prompt only;
- cancellation stops generation;
- a bridge cannot read unrelated private chat state.

**Where these live:** `tests/test_s608_bridge_conformance.py` walks
this list end-to-end for everything the core API implements;
slice-level suites (`test_s601`–`test_s607`, `test_s609`,
`test_s610`) prove the same properties at their own layer.

## 15. Builder quickstart

You are building a bridge if your program — a game mod, a VR client
companion, a robot, another app — should hold conversations through
Rúnmál. Five steps:

1. **Get a credential.** The owner creates one for you (owner UI or
   `POST /api/v1/bridge/credentials` under the local credential)
   with exactly the scopes you need (§2). You receive the token
   **once**; store it like a password (environment variable or your
   platform's secret store — never in source, never in logs).
2. **Probe.** `GET /api/v1/bridge/whoami` with
   `Authorization: Bearer <token>` returns your bridge id and scopes.
3. **Read state.** `GET /api/v1/bridge/chats/{chat_id}` gives the
   conversation: metadata, active persona, ordered messages with
   speaker snapshots. Poll it, or (from S609) consume the event
   outbox for push-style updates.
4. **Write turns.** `POST /api/v1/bridge/chats/{chat_id}/turns`
   with a speaker kind (`user` / `companion` / `environment`), and
   ask Rúnmál to speak with
   `POST /api/v1/bridge/chats/{chat_id}/generate` (SSE; cancel via
   `.../generate/cancel`).
5. **Speak aloud (optional).** `POST /api/v1/bridge/tts` starts a
   synthesis job; poll it, fetch the WAV, play it in your world,
   and report playback back (§9).

Two reference implementations ship in the repo and are meant to be
copied: the VRChat OSC follower (`runmal/bridges/vrchat_osc.py`,
docs/bridges/VRCHAT_OSC.md) and the Skyrim-style HTTP adapter
(`runmal/bridges/skyrim_http.py`, docs/bridges/SKYRIM_HTTP.md); the
Conan RCON skeleton is `runmal/bridges/conan.py`
(docs/bridges/CONAN_RCON.md).

## 16. Endpoint reference (v1, as implemented)

All under `/api/v1/bridge`, bridge-token authenticated (§2):

| Method & path | Scope | Purpose |
| --- | --- | --- |
| `GET /whoami` | any valid token | bridge id, name, scopes |
| `GET /chats/{id}` | `chat:read:{id}` | conversation state (§3) |
| `POST /chats/{id}/turns` | `chat:write:{id}` | append one turn (§6) |
| `POST /chats/{id}/generate` | `chat:write:{id}` | SSE generation turn (§7) |
| `POST /chats/{id}/generate/cancel` | `chat:write:{id}` | cancel a generation |
| `POST /chats/{id}/persona` | `persona:select:{target}` | switch future-turn persona (§8) |
| `POST /tts` | `tts:request` | start a TTS job (§9) |
| `GET /tts/{job}` | `tts:request` | job status + lifecycle events |
| `GET /tts/{job}/audio` | `tts:request` | the WAV, when ready |
| `POST /tts/{job}/cancel` | `tts:request` | cancel synthesis |
| `POST /tts/{job}/playback` | `tts:request` | report playback lifecycle |

Owner-side administration (local application credential, NOT a
bridge token): `POST /bridge/credentials`, `GET /bridge/credentials`,
`POST /bridge/credentials/{id}/revoke`.

Remaining contract pieces land in this campaign, in roadmap order:
the durable event outbox (§5) in S609, idempotency enforcement (§4)
and capability discovery in S610, and the VRChat room-audio ingress
contract (§10.4) in S611. Until a piece lands, this document's
normative sections describe the contract it will implement.

## 17. Error model

Errors are JSON: `{"detail": "..."}` with a stable HTTP status —
bridges branch on status, never on message text.

| Status | Meaning |
| --- | --- |
| 400 | malformed request at an adapter boundary (reference bridges) |
| 401 | missing, invalid, or **revoked** bridge token; or a local credential presented to a bridge route (and vice versa) |
| 403 | valid token, insufficient scope for this operation/resource |
| 404 | the chat/job/credential does not exist — or is not yours (existence is not leaked across owners) |
| 409 | state conflict (e.g. audio requested before a TTS job is ready; conflicting idempotency-key reuse, from S610) |
| 422 | well-formed request, semantically invalid (unknown scope at creation, unknown speaker, unknown persona) |
