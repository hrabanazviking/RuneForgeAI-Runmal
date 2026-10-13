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

## 4. Idempotency

Externally retried writes accept an idempotency key. Repeating the same key with the same logical request returns the existing result instead of duplicating messages/actions.

Conflicting reuse of the same key is an error.

## 5. Event outbox

Bridges need more than request/response when a companion may initiate speech.

Use a durable/pollable event outbox or equivalent with:

- monotonically ordered event IDs per stream;
- acknowledgement/checkpoint semantics;
- replay after temporary disconnect;
- bounded retention;
- event types such as `companion_turn_ready`, `tts_ready`, `playback_complete`, `persona_changed`, `generation_cancelled`.

Webhook delivery may be added, but the durable outbox is the recovery source of truth.

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