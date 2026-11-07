# Group chats deepened (P-070) — 2026-11-07

Part V (Chat Surgery), roadmap P-070: *Group chats deepened:
activation strategies (natural order, list, pooled), per-member
overrides, group lore/persona handling — measured against the
delta census.*

## Measured against the delta census

- **ST-11** (group chats: members, mute, re-order, force-trigger)
  — depth added here: force-trigger is the per-member `force`
  override; mute/re-order were already S210/S211.
- **ST-12** (reply-order strategies Manual/Natural/List/Pooled) —
  already HAVE as pure S211 selection. The gap this slice closes:
  the policies were stored configuration that **no persistent-room
  road ever consumed**. `POST /groups/{id}/next` now builds the
  S211 `SelectionContext` from the real transcript.
- **ST-13** (generation handling: swap vs join cards, join
  templates) — built: `generation_mode` `swap` | `join`, with
  `join_prefix` / `join_suffix` templates (`{{char}}` per member).
- **ST-14** (auto-mode, self-response, group scenario override,
  peek/edit member) — built: bounded auto run, the self-response
  rule, `scenario_override`, member peek + room-scoped override
  edits.

## Storage — no migration

Everything lives in the existing `groups.speaker_config` JSON
under the `"p070"` key (migration head stays 0038; the S211 keys
`order` / `seed` are untouched):

```json
{"p070": {
  "generation_mode": "swap",
  "join_prefix": "", "join_suffix": "",
  "scenario_override": null,
  "allow_self_responses": false,
  "auto_mode": {"enabled": false, "max_turns": 3},
  "member_overrides": {"<character_id>": {
    "activation": "default | force | never",
    "persona_override": null,
    "lore_enabled": true}},
  "state": {"list_cursor": 0, "pool_spoken": []}
}}
```

## Activation (`POST /groups/{id}/next`, `/run`)

Selection delegates to the S211 policies with a context built
from the transcript: history speakers, the last user text, the
configured list order / seed, and the persisted list cursor and
pool (written back after every pick, so consecutive calls advance
the list and drain the pool exactly like the pure policies do in
their seeded tests).

Overrides apply around the policies:

- `never` — excluded everywhere, including a manual designation
  (distinct from muted, same silence; reason
  `manual_speaker_never`).
- `force` — pre-empts natural / list / pooled (roster order among
  forced members; for list, the configured order ranks them).
  Reason `forced`.
- self-response — with `allow_self_responses: false` (default),
  the member who spoke immediately before is filtered out when
  anyone else is eligible; a lone eligible member may repeat.

Every selection records a metadata-only `group.next_selected`
event (strategy, speaker id, reason — never text). `POST /run`
drives a bounded loop (1..10 turns), further capped by
`auto_mode.max_turns` when auto-mode is enabled, stopping early
on silence. There is **no background daemon** — auto-mode is a
driven loop behind an explicit call.

## Persona handling (ST-13)

With `generate: true`, the prompt is assembled per pick:

- **swap** — the system prompt is only the speaking member's
  persona (card slots via `persona/slots`); the group
  `scenario_override`, when set, replaces the card's scenario
  slot.
- **join** — every member's persona is wrapped in the join
  prefix/suffix templates and joined into one system prompt; the
  speaking member's block is marked `[Now speaking: <name>]`;
  card scenarios are dropped and the group scenario, when set,
  is appended exactly once.
- a member's `persona_override` replaces their card persona for
  this room only. The card is never mutated (peek + a fresh group
  prove it in the battery).

History keeps the group core's viewpoint shape: the speaker's own
messages as assistant turns, the user's as user turns, everyone
else's as `Name: text` user turns.

## Group lore

Activated lore comes from the P-040 scoped-lore road
(`lorebooks.scopes.layered_preview` over the room chat: global ->
character -> persona -> chat), scanned on the last user text.
Included entries ride in the prompt under a `Group lore:` section
and are reported (scope, lorebook, entry) in the response. A
member's `lore_enabled: false` drops the **character** layer for
that member; other layers still apply.

## Peek / edit member (ST-14)

`GET /groups/{id}/members/{cid}/peek` returns the member row, its
override, the effective persona and its source (`card` |
`override`), plus the card's slot manifest — reads never mutate.
`PATCH /groups/{id}/members/{cid}/override` edits the room-scoped
override only.

## Honest boundaries

- Generation runs through the generation service's default
  backend seam and does **not** route through the prompt
  composer / inspector; with no backend profile configured the
  backend is the deterministic fake (the S305 precedent), so
  generated text is stub text.
- Generation failure (error event or empty text) raises and
  stores nothing; the selection event from that tick remains.
- Activation state lives in `speaker_config`, so concurrent
  next/run calls are last-writer-wins — the room config's
  existing semantics.
- Cross-user isolation follows the room road: every entry
  resolves the group through the owner-scoped lookup; foreign or
  missing groups/members are 404 and nothing is selected or
  generated for them.

## Files

- `src/runmal/groupchat/deepening.py` (new)
- `src/runmal/groupchat/router.py` (deepening endpoints appended)
- `tests/test_p070_group_deepening.py` (battery)
