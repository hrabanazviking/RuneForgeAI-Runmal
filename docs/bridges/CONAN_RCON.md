# Conan Exiles RCON Reference Bridge (S606) — design + skeleton

Code: `src/runmal/bridges/rcon.py` (Source RCON protocol client) and
`src/runmal/bridges/conan.py` (the Conan translation skeleton).
Companion docs: `docs/BRIDGE_PROTOCOL.md` §11 — game adapters
translate into the stable bridge contract; **core contains no
Conan-specific branches**, and it never will: everything Conan-shaped
lives in the adapter.

## Design

```
Conan dedicated server                Rúnmál
        │  Source RCON (TCP)                │  bridge API (S602)
        ▼                                   ▼
  rcon.execute(read_command)      HTTPBridgeSink.append_turn(...)
        │                                   ▲
        └──── ConanCompanionRelay ──────────┘
              poll cycle, both ways
```

- **Game → Rúnmál.** The relay runs a deployer-chosen RCON read
  command (typically a log/tail read on the dedicated server),
  translates output lines into game events, and forwards player chat
  as bridge `user` turns with the player as speaker name.
- **Rúnmál → game.** New companion turns (polled from bridge state,
  same cursor pattern as the VRChat follower) are sent through a
  deployer-chosen RCON **say template** — a command string with a
  `{text}` placeholder.

## What is deliberately configuration, not code

Log line formats and RCON command vocabularies vary across Conan
Exiles server versions and mod stacks. The skeleton therefore takes:

- `chat_patterns` — regexes with named groups `speaker` and
  `content`. Example shape (adapt to your server's actual log):
  `\[Chat\] (?P<speaker>[^:]+): (?P<content>.*)`
- `read_command` — the RCON command returning fresh server output.
- `say_template` — e.g. a broadcast/say command ending in `{text}`.

Shipping invented defaults for these would be fiction; the machinery
around them (protocol, translation, relay, idempotent cursors) is
what this slice builds and proves against protocol fixtures.

## Protocol notes

Source RCON packets are little-endian
`size | id | type | body | 0x00 0x00`. Auth is type 3; a successful
auth is answered by an empty type-0 packet then a type-2 packet with
the request id (failure: id −1). Command output may span multiple
type-0 packets; the client detects the end by sending a sentinel
empty command behind the real one and reading until the sentinel's
response — see `runmal/bridges/rcon.py`.
