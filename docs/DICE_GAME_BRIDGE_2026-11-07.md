# Dice & Game-Bridge Plugin Surface (P-096) - 2026-11-07

Roadmap line: "Dice & game-bridge plugin surface:
Sagnaskemma rolls and bridge events (VRChat/Skyrim)
exposed as plugin citizens."

## What landed

`src/runmal/plugins/game_bridge.py` - a first-class
P-081 citizen (`runmal.game-bridge`) carrying two
surfaces: seeded, inspectable dice rolls, and a
declared game-bridge event record surface.

- Dice notation: `NdM`, `dM`, `NdM+K`, `NdM-K`,
  `NdMkhJ` / `NdMklJ` (keep highest/lowest), parsed to
  a canonical form (`2D6 + 3` -> `2d6+3`). Count
  1..20, sides 2..1000, modifier -10000..10000, keep
  1..count. Everything else - empty, exploding,
  pooled, multi-term (`2d6+1d4`) - refuses plainly
  with the defect named; nothing is half-parsed.
- RNG honesty (the P-036 discipline; the roadmap's
  own name for it is "the Sagnaskemma dice
  discipline"): a seeded die draw is a pure function
  of (algorithm `runmal-p096-dice-v1`, seed, context,
  canonical notation, roll key, die index) - SHA-256,
  first eight digest bytes / 2**64. Every roll record
  carries notation, canonical form, all faces, kept /
  dropped faces, all draws, total, seed, `seeded`,
  context and roll key, so `verify_roll` reproduces
  it exactly, forever, in isolation. `seed=None` is
  the honest unseeded path: system entropy, labelled
  `seeded: False`, inspectable and never
  reproducible - verification says so.
- Persisted rolls: `roll_for_chat` stores the roll
  (fresh uuid roll key per roll, actor provenance on
  every row) and appends its `dice.rolled` bridge
  event in the SAME save, so a roll and its bridge
  announcement can never drift apart. Cap 500 rolls
  per chat: the 501st refuses - roll history is
  evidence and is never silently pruned.
- Bridge events: closed kinds (`dice.rolled`,
  `chat.message`, `game.event`) and closed targets
  (`vrchat`, `skyrim`, `generic`), per-chat sequence
  numbers, per-kind payload shapes validated strictly
  (a `chat.message` is `{role, speaker, text}`; a
  `game.event` is `{game_kind: player_speech |
  world_event, speaker, text}`, mirroring the Skyrim
  adapter's own vocabulary). Poll with `after_seq`,
  ack with monotonic per-consumer cursors - the S609
  outbox discipline at plugin scale. Retention keeps
  the newest 1000 events per chat; every prune is
  counted on the inspect document, never hidden.
  `dice.rolled` is minted ONLY by an actual roll:
  the generic emit road refuses that kind, so the
  log can never claim a roll that did not happen.
- Storage: the P-089 durable file idiom - one JSON
  document per owner at
  `data_dir()/game_bridge/<user_id>.json`, atomic
  save (tmp + chmod 0o600 + replace), stored rows
  re-validated on read (a roll whose total does not
  match its faces raises), corrupt stores raise and
  are never silently reset. NO migration: head
  stays 0041.
- Citizen wiring: `register_plugin` only;
  `build_registry` / `create_app` untouched.
  Manifest declares chat.events + ui.slots,
  chat.read + ui.contribute, so the P-082 sandbox
  grant set is EMPTY. The event handler observes
  METADATA ONLY (name, ids, role, content length -
  never message text) into a bounded in-memory list:
  a plugin event carries no owner id, so no durable
  owner-scoped write can honestly be made from it.
  `chat.deleted` removes nothing; durable rolls and
  events are deleted only by the explicit
  `clear_chat` verb.
- HTTP (plugins router): `POST /game-bridge/roll`,
  `GET /game-bridge/rolls`,
  `GET /game-bridge/rolls/{roll_id}` (roll +
  verification verdict), `POST /game-bridge/events`,
  `GET /game-bridge/events`,
  `POST /game-bridge/events/ack`,
  `GET /game-bridge/inspect`,
  `POST /game-bridge/clear`. Chat ownership is
  verified on every route; HTTP writes carry host
  provenance.

## Honest boundaries

This citizen opens NO socket, imports NO network
client and talks to NO game client. The real
transports already exist - `runmal.bridge` (the
credentialed bridge API, S601-S610) and
`runmal.bridges` (the VRChat OSC and Skyrim HTTP
adapters) - and this surface is the plugin-side
record layer they could carry, not a second bridge.
A `game.event` record is recorded only: it is never
appended to a chat from here (`chat.write` is
RESERVED in v1; turning game events into chat turns
is the bridge API's credentialed job). Transport
concerns stay with the transports (the VRChat
adapter does its own 144-char chatbox chunking when
it consumes a `chat.message` record). P-094 custody
does not yet name `runmal.game-bridge`; its export
for this id answers unknown-plugin honestly, and the
store is a plain per-owner file until a later
reconciliation adds the adapter (the gap is named
in the design, not hidden).

## Evidence

Battery tests/test_p096_game_bridge.py (33 tests);
neighbours P-081 + P-082 + P-036 + P-055 + P-093 +
P-094 + S609 outbox + P-020 chat bridge; counts in
hidden_files/P096_EVIDENCE.md.
