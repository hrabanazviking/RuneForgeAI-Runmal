# Reasoning Record (P-205) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
third slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line and names the Assistant view, in its Voxta mirror
census, as GPT-style, reasoning models with VISIBLE
THINKING. There is no verbatim P-205 entry, and this slice
is never presented as roadmap-verbatim.

## Why this slice exists

P-203's design named the prerequisite verbatim: the
Assistant View "becomes buildable only after a slice gives
backends a reasoning-content record". The P-205 scout
re-verified the absence as TWO absences: no capture (every
wire adapter read only the answer-text field and silently
dropped the reasoning/thinking field its provider stream
already carried; the backend event contract had no
reasoning event) and no record (no storage anywhere could
keep thinking if it were read - provenance is barred by
its own no-content law, the swipe deck by its
content-equals-deck invariant, the event log by its
grain). P-205 founds both halves plus the live seam
between them.

## What lands

1. CAPTURE - `src/runmal/backends/events.py` gains a
   frozen `ReasoningDelta` event beside `TextDelta`. The
   four wire adapters yield it tolerantly from the public
   wire spellings their streams already carry, reasoning
   BEFORE the answer text of the same chunk, empty strings
   skipped: openai_compat (`reasoning_content`, fallback
   `reasoning`), openrouter (`reasoning`, fallback
   `reasoning_content`), aesir (`reasoning_content`,
   fallback `reasoning`), ollama (`thinking`). Capture is
   opportunistic: no request field ever asks a provider
   for reasoning, and nothing is synthesised. The fake
   backend gains scriptable `reasoning_chunks`, yielded in
   order before the text chunks. INVARIANT, pinned by the
   battery: concatenating a stream's TextDelta texts
   yields exactly the answer text - reasoning is never
   merged into it, so stored message content is unchanged
   for every existing road.
2. STREAM - the generation service's `bridge_event` maps
   ReasoningDelta to `{"type": "reasoning", "text": ...}`.
   Token / usage / done / error shapes are byte-identical;
   plugin payloads never gain reasoning text (PLG-05
   holds). A reasoning delta counts as visible output for
   the retry contract: no retry may start after thinking
   has been shown.
3. RECORD - `src/runmal/chats/reasoning.py`: one JSON
   document per message in the NEW column
   `messages.reasoning_json` (PROVISIONAL migration 0042,
   mirroring m0040's storage proof), schema
   `runmal-p205-message-reasoning-v1`, one record per
   swipe: `{"status": ..., "text": ...}` with text present
   ONLY when the status is `recorded`.

## The honesty idiom (P-075, carried exactly)

- `recorded`: this swipe's generation produced thinking
  and the producing road captured it; text is the verbatim
  concatenation of that generation's ReasoningDelta texts,
  in arrival order.
- `not_present`: the producing road DID capture (it ran
  the P-205 seam) and the generation produced no thinking
  - a positive fact about that generation.
- `not_recorded`: the road never captured (legacy rows,
  manual / imported messages, producers not yet wired).
- `unknown`: stored data was missing, corrupt or foreign;
  readers land here, never on an exception.

Builders are STRICT (a record that would lie is refused
with ValueError); readers are TOLERANT (`'{}'`, corrupt or
foreign stored data reads as the explicit not_recorded
document). CONTENT LAW, differing from provenance by
design: this record's whole purpose is one content-class
fact - the model's OWN emitted thinking. It records never
prompt text, never message answer text, never secrets or
provider payloads beyond the reasoning field itself.

## Plumbing and the one producer

`append_message` gains a `reasoning` param beside
`provenance` (one swipe's record, or None). None means the
road did not capture: swipe 0 stores `not_recorded` -
there is deliberately NO default-record builder inventing
facts. `message_to_dict` carries the active swipe's
reasoning view beside its provenance view, and ONE new
road serves the full document:

```
GET /api/v1/chats/{chat_id}/messages/{message_id}/reasoning
```

Owner-scoped, house 404 idiom; the app route set grows by
exactly this one road. Swipe lifecycle mirrors
provenance: a new swipe starts `not_recorded`, deleting a
swipe drops and renumbers its record, a branch copy
carries the document under document-for-copy semantics,
and session import records `not_recorded` per swipe.

The ONE producing road at bank time is the bridge
conversation - the road that already builds the full
P-075 record at append: it collects the stream's
reasoning dicts in arrival order and records `recorded`
(verbatim joined text) or `not_present` at append.
Every other producing road (continue / impersonate,
groupchat, swipe regeneration, the /generate web road)
records `not_recorded` until a later slice wires it -
stated here and pinned by the battery, never faked.

## Deliberately not built (named, not gaps)

- Assistant View UI / any rendering: the NEXT slice's
  work, now foundable - the live SSE type and the stored
  document are the two surfaces a view renders from.
- Wiring the other producing roads (each has its own
  landing semantics; continue's extend mode grows an
  EXISTING swipe, a design question of its own).
- Client-supplied reasoning on the message POST road:
  unverifiable thinking would let a caller fabricate a
  record - the exact failure the strict-builder law
  exists to refuse.
- A reasoning capability flag on Capabilities / ModelInfo:
  no in-tree truth source declares per-model reasoning
  support; the flag would be invented data.
- Persisting generation / plugin events (P-204's named
  later thread): a separate founding, not folded in.
- An Inspector reasoning section or per-chat roll-up:
  the P-203 / P-204 documents are pinned schemas; the
  Inspector joins this record in a later slice.
- Bot runtime / lifting the chat.write reservation: no
  substrate, no roadmap definition (unchanged verdict).

## Carried limitations (stated plainly)

- Only the bridge road produces recorded / not_present
  records at bank time; all other roads read not_recorded.
- Reasoning is stored verbatim and in full: no truncation,
  summarisation or redaction layer exists in P-205.
- The record is per message; there is no per-chat
  reasoning census or Inspector join in P-205.
- Wire spellings are captured tolerantly (two spellings on
  the OpenAI-shaped adapters); a provider inventing a
  third spelling is silently not captured, and its
  messages read not_present when the road ran - which
  cannot distinguish "model did not think" from "spelling
  not recognised".

## Migration and banking heals

Migration 0042 is PROVISIONAL (keeper composes final
numbering at banking; P-204 took no migration, so 0042
was free). The slice's banking heals move the suite's
0041 head pins to 0042 at equal strength (the P-075 /
P-077 precedent): head values, positional pins shifted
with a comment naming P-205, exact revision lists
extended by 0042, and the no-m0042 pins restated as
taken-once-by-P-205. No assertion was weakened.
