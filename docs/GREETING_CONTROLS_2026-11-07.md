# P-079 — Quiet/greeting controls (Part V, Chat Surgery)

Roadmap line: *Quiet/greeting controls: alternate greetings per
card, first-message variants as swipes.*

Clean-room: built from the roadmap line, the mirrors' publicly
known behaviour (a new chat opens on the character's greeting;
alternate greetings are swiped through on that first message),
and Runmal's own contracts only. Base bd36434 (P-077 banking
record), migration head at base 0041. **No migration taken.**

## What existed before

- Cards already carried `first_mes` + `alternate_greetings`
  (parser/exporter round-trip, S212 editor) -- and nothing ever
  read them at chat time. `create_chat` seeded no message at
  all: a new chat against a character opened blank, and the
  card's greetings were dead text.
- P-065 gave every message a swipe deck (`swipes_json` /
  `swipe_id`, the `content == swipes[swipe_id]` invariant) and
  P-075 gave every swipe a provenance record. The greeting
  slice is the missing writer that uses both.

## The deck + choice contract (chats/greetings.py, pure)

- `greeting_entries(first_mes, alternate_greetings)` -> the
  ordered usable greetings as `{kind, source_index, text}`:
  the primary greeting first (`kind="first"`), alternates in
  card order (`kind="alternate"`, `source_index` = card-side
  position). Blank / whitespace-only / non-string entries never
  join the deck (a swipe alternate must be a non-empty string,
  the P-065 rule); duplicates and padding survive verbatim; a
  card with no usable greeting has an EMPTY deck and no text
  is manufactured for it.
- `GreetingChoice` -- the control set at chat creation or at
  seed time. `first` (default) opens on deck index 0. `index`
  opens on an explicit index, STRICT via P-065 `select_index`
  (out of range raises, even against an empty deck). `random`
  rolls an index; a `seed` makes the roll reproducible (the
  P-036 seeded-RNG discipline) and what is recorded everywhere
  is the RESOLVED index, never the intention. `quiet` is the
  quiet start: no greeting seeded, the chat opens empty.
  Decode is strict (`choice_from_data`): unknown keys, a bool
  index/seed, an index outside `index` mode, or a seed outside
  `random` mode all raise `ValueError`.

## Seeding (chats/service.py)

- `create_chat(..., greeting=GreetingChoice)` -- when a
  character is bound, the greeting is seeded as the chat's
  first message in the same commit: role `assistant`,
  `position=0`, speaker = the character (id + name snapshot),
  `swipes_json` = the WHOLE deck, `swipe_id` = the resolved
  index. Chats without a character are byte-for-byte the old
  road. `chat.created` event data gains `greeting_mode`;
  the seeded message records the ordinary `message.appended`
  event with metadata only (`greeting: true`, mode, kind,
  card-side index, swipe id/count) -- never greeting text.
- Provenance (P-075): one record per alternate, so swiping
  the opening line shows each variant's origin -- `manual`
  with `source: "card_greeting"` plus the entry's kind and
  card-side index; model and lore sections honestly
  `not_applicable` (no model produced the text, no lore ran);
  the preset section snapshots the chat's applied preset.
- `seed_greeting(chat_id, choice)` -- seeds into an existing
  EMPTY chat (created quiet, or before its character was
  bound via `set_chat_persona`). Refusals: missing/foreign
  chat `KeyError`; no character, vanished character, or a
  non-empty chat `ValueError`. The strict index is resolved
  BEFORE the P-076 journal write, so a refused seed leaves
  no undo entry and no event; a successful seed journals as
  `message.append`, and undoing it returns the chat to empty
  (battery-pinned).

## API

- `POST /chats` gains `greeting_mode` / `greeting_index` /
  `greeting_seed` (StrictInt; invalid controls and a strict
  index the card cannot satisfy -> 422; unknown character
  stays 404). Response shape unchanged.
- `POST /chats/{chat_id}/greeting` with `{mode, index, seed}`
  seeds an empty chat -> `{seeded, message}`; `seeded: false`
  when the choice resolves to no greeting (quiet mode or a
  greetingless card). Missing chat 404; refusals 422.
- `GET /characters/{character_id}/greetings` -> the deck a
  new chat would seed from: `{character_id, character_name,
  greetings: [{index, kind, source_index, text}], count}`,
  owner-scoped, 404 for missing/foreign. It reads the live
  card, so S212 editor edits are reflected immediately.

## Storage

None. The deck rides the P-065 message columns, provenance
the P-075 document, controls are request-time values whose
outcome is the seeded message itself. Migration head stays
0041; the battery pins `0042 not in MIGRATIONS`.

## Neighbour notes (discovered while building, handled)

- P-066 fork copies carry only the ACTIVE alternate of any
  message, by design (`branches._copy_message`, provenance
  records the source) -- the greeting's active line forks
  exactly like any other message's. Not a defect; the battery
  pins the universal behaviour instead of a greeting special
  case. Export (P-020/service) carries the full deck.
- `tests/test_p073_chat_metadata.py` counted messages in a
  chat built on the shared V2 fixture card (which carries
  greetings): its 3-message expectation predates greeting
  seeding. Two expectations updated 3 -> 4 with the reason
  recorded inline (3 posted + 1 seeded); the extractive
  title/summary/tag expectations were verified unchanged.
- The S602 bridge tests build their world on a persona card
  with a greeting and assert the driven conversation starts
  empty -- the bridge opens its own conversations. Their
  `_world` fixture now opts out with `greeting_mode: "quiet"`
  (the control this slice provides); every bridge assertion
  is unchanged. A bridge attaching to a user-opened chat
  still sees the seeded greeting as the persona's first
  message, which is the correct shared-history behaviour.
- Group chats never pass through `create_chat` (rooms are
  direct inserts in `groupchat/store.py`), so no group room
  can sprout a greeting; chats created by branch fork,
  checkpoint restore, and import keep their existing copy
  semantics untouched.

## Battery

`tests/test_p079_greeting_controls.py` -- pure deck/choice
contract, service seeding in every mode, per-alternate
provenance, metadata-only events, swipe-deck integration
(select/add on the greeting), seed-into-empty incl. undo,
the deck view, API controls + error mapping, and the
neighbour pins (no migration, export, fork).
