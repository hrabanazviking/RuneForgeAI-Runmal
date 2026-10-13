# Skyrim-Style HTTP Bridge (S607) — the mod contract

Code: `src/runmal/bridges/skyrim_http.py`. For the family of game
mods (Skyrim AI-companion mods are the archetype) that talk plain
HTTP: **the mod is the client; the adapter hosts a small local HTTP
server.** The adapter translates between the mod and the stable
Rúnmál bridge API; no game-specific code enters Rúnmál core
(`docs/BRIDGE_PROTOCOL.md` §11).

## Endpoints the mod calls

Base: `http://127.0.0.1:8770` by default (loopback; configurable).
Every endpoint except `/health` requires the header
`X-Mod-Token: <shared local token>` — a wrong or missing token gets
`401`. Bodies are JSON, capped at 64 KiB.

### `GET /health`

`200 {"status": "ok", "bridge": "skyrim-http"}` — liveness only,
no auth, no data.

### `POST /events` — game → companion

```json
{"kind": "player_speech", "speaker": "Dovahkiin", "text": "We need to move."}
{"kind": "world_event", "text": "A dragon appears over the ridge."}
```

- `player_speech` becomes a bridge **user** turn; `speaker` is kept
  as the turn's speaker name.
- `world_event` becomes a bridge **environment** turn.
- Success: `202 {"accepted": true}`. Malformed events (unknown
  kind, empty text): `400`. If Rúnmál itself is unreachable: `502` —
  the mod can retry; nothing was silently dropped.

### `GET /lines` — companion → game

```json
{"lines": [{"id": "<message-id>", "text": "Then we run.", "speaker": "Aella"}]}
```

Each companion line is handed out **exactly once**, in conversation
order. The adapter tracks what it has already delivered from the
bridge conversation state, so a mod that polls on a timer never
repeats a line and never misses one that arrived between polls.
History from before the adapter started is not replayed.

## Running

```
RUNMAL_BRIDGE_TOKEN=<chat:write+chat:read token> \
RUNMAL_MOD_TOKEN=<a local secret you choose> \
python -m runmal.bridges.skyrim_http --chat-id <chat-id>
```

The bridge token needs `chat:read:<chat-id>` and
`chat:write:<chat-id>` (S601). Tokens travel in the environment,
never on the command line.
