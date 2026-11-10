# Reasoning Wiring for Groupchat (P-208) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
sixth slice. Scope is DERIVED per the P-203..P-207 precedent:
the governing roadmap gives Part XIII only its part-table
line. There is no verbatim P-208 entry, and this slice is
never presented as roadmap-verbatim.

## Why this slice exists

P-205 founded the reasoning record and wired the bridge;
P-207 wired continue / impersonate and named groupchat
wiring as the natural P-208 candidate in its own record:
"it is two surfaces, not one family (a stateless road that
stores nothing, plus a persistent road on a second store
whose append has no reasoning param and whose read model
exposes no reasoning view)". Groupchat was the first-named
remaining debt in both the P-205 and P-207 records, and the
only remaining producing road that STORES messages still
reading `not_recorded`. This slice wires BOTH surfaces in
one slice, each with its own honest landing.

## What lands

THREE production files change:
`src/runmal/groupchat/store.py`,
`src/runmal/groupchat/deepening.py`,
`src/runmal/groupchat/router.py` (the last fenced to ONE
new SSE branch). No other production file moves.

1. The persistent store (store.py). `append_message` gains
   ONE keyword param beside `provenance`: `reasoning: dict |
   None = None`. Inside, mirroring `chats/service.py`
   exactly, the stored document is
   `reasoning_mod.build_document(reasoning if reasoning is
   not None else reasoning_mod.not_recorded_record())` and
   lands as `reasoning_json` on the Message beside
   `provenance_json`. None therefore stores an EXPLICIT
   not_recorded document at swipe 0 -- never an invented
   record, and no longer a reliance on the "{}" column
   default. `message_to_dict` gains ONE key beside
   `"provenance"`: `"reasoning":
   reasoning_mod.active_view(message, swipe 0)` with the
   same swipe fallback its provenance line already uses.
   That single key wires the transcript read
   (GET /groups/{id}/messages) AND the next/run result
   documents, which both render through this function.
   Callers who pass nothing (both manual/user callers)
   change no behaviour they can observe: their messages
   read not_recorded, as today -- correctly, because no
   generation produced them.
2. The persistent collector (deepening.py). `_generate` is
   rewritten to the P-207 collector shape and returns
   `tuple[str, dict]`: it streams `generate_events(...,
   plugin_events=False)` as today, collects "token" dicts
   into the text and `{"type": "reasoning"}` dicts' text
   into reasoning parts, BOTH in arrival order, and
   remembers any "error" dict's message and the "done"
   dict's finish_reason. On success it builds the strict
   P-205 record with the bridge/P-207 rule: joined
   reasoning text non-empty -> `recorded` with the
   verbatim joined thinking; empty -> `not_present`.
   Reasoning text is NEVER merged into the answer text.
   `next_turn`'s ONE producing append now passes
   `provenance=prov_record, reasoning=reasoning_record`
   (locals renamed so the provenance record and the
   reasoning record are never confused); its user_text
   append and every other append pass nothing.
   `run_turns` needs NO change: it loops `next_turn`, so
   each turn lands its own message with its own record.
   NO combination rule exists on this road and none is
   built: no group generation grows an existing message
   (there is no group regenerate / swipe / extend path),
   so P-207's `_combine_extend_reasoning` is NOT copied
   here. Each record describes exactly its own production;
   run_turns turns never concatenate into one another's
   records.
3. The stateless road (router.py, FENCED). In
   `group_turn`'s `sse()` loop ONLY, ONE branch is added
   beside the token branch: when an event's type is
   "reasoning", the loop yields
   `{"type": "reasoning", "author": speaker.name,
   "text": event["text"]}` at the point the dict arrives
   -- interleaved with that speaker's tokens in true
   arrival order, per speaker. Nothing is collected,
   stored, or merged into text / the message event; the
   typing/token/message/turn_end sequence is otherwise
   byte-identical to the banked S305 contract. group.js
   is NOT edited: it ignores unknown SSE types harmlessly
   (verified in the scout).

## The D2 fix (in-slice)

The old `_generate` raised on an "error" dict and on empty
text, but never read "done": a cancelled stream (the
service yields done/cancelled after partial tokens)
returned the partial text as a complete turn and
`next_turn` STORED it as one. Because P-208 rewrites this
exact collector, the new collector adopts the P-207
failure contract whole: raise `GenerationFailedError`
when an error was seen, when finish is None / "cancelled"
/ "error", or when the joined text is empty. On any
failure NO record is built and the caller stores nothing,
exactly as the error/empty raises behaved today
(next_turn propagates; the router maps it to 502).
Pinned by battery pin 4 (cancelled finish with partial
text emitted stores nothing).

## The D1 fence (NOT fixed, by design)

Defect D1: the stateless POST /group/turn SSE loop never
reads "error" or "done" dicts. On a backend error the
service yields error + done/error; the loop simply ends
the per-speaker stream and still emits a "message" event
carrying whatever partial text accumulated (possibly "")
followed by turn_end -- a failed generation is presented
as a completed turn. That behaviour is the banked S305
stream contract. P-208 does NOT silently fix it: any fix
(a new error surface mid-stream) moves that contract and
awaits a keeper/Volmarr ruling. The router edit in this
slice touches ONLY the new reasoning branch, and no
battery pin blesses D1's behaviour.

## Deliberately not built

- Fixing D1 (stateless error semantics): DECLINED -- it
  moves the banked S305 stream contract; named above for
  a keeper/Volmarr ruling, not silently absorbed.
- Rendering forwarded reasoning in group.js (or any web
  UI): DECLINED -- a UI choice on a stream that now
  carries the data; the client tolerates the new event
  today. A later Assistant-View-side slice may render it.
- Wiring manual swipes or the web /generate road:
  DECLINED by name -- separate debts under existing
  rulings (no swipe-generation road exists; live
  /generate wiring is Volmarr's to call per P-206/P-207).
  Nothing drifts into chats swipe code,
  generation/router.py, or web stream code.
- A group reasoning census / Inspector join: DECLINED --
  the Inspector joins the record in its own later slice,
  as P-205/P-207 both ruled.
- Persisting stateless-road turns (any storage for POST
  /group/turn): DECLINED -- that road's contract is
  client-held state; founding storage for it is a
  different slice, not a wiring.
- A per-message reasoning read on the GROUP router (e.g.
  GET /groups/{id}/messages/{mid}/reasoning): DECLINED --
  the chats full-document road already resolves room-chat
  messages by chat_id once stored (battery pin 9); a
  duplicate road would double the census for no new
  truth.

## Carried limitations (honest, by design)

- Stateless reasoning is transient: forwarded live,
  never stored, gone when the stream ends -- by design,
  mirroring impersonate drafts (P-207).
- Group reasoning renders in the Assistant View only
  insofar as that view reads stored message documents;
  no group-specific view work is in this slice.
- Extend-onto-legacy style honesty is preserved by
  absence: group generations never rewrite an existing
  message, so no group record can ever claim coverage of
  a production that was not captured -- manual and user
  rows keep reading not_recorded beside generated
  recorded rows in the same transcript, and the
  transcript shows both, plainly.
- Manual swipes and web /generate replies still read
  not_recorded after P-208 (separate, already-ruled
  debts). The Assistant View keeps saying so.
- Reasoning is stored verbatim and in full (the P-205
  position): no truncation or redaction layer is added
  here.

## Migration note

NONE. Head stays 0042: migration 0042 already added
`messages.reasoning_json` to the SHARED messages table,
and every group transcript row is a row of that table
(its chat is the room chat). The store change is a write
of an existing column; the read change is a view over
it. No provisional 0043 is taken. Pinned by the battery
(MIGRATIONS last revision "0042"; no m0043 module
exists). No new endpoint: the route census stays the
P-207 census (354 paths / 437 operations), pinned by
the battery.

## Battery

`tests/test_p208_groupchat_reasoning.py` -- 18 pins:
the persistent seam (recorded in arrival order, never
merged; not_present; failing backend stores nothing;
cancelled finish stores nothing -- the D2 pin), the
persistent landing (recorded beside provenance in the
result document and re-read via the transcript; 
not_present as a positive fact; run_turns per-turn
records with no cross-turn concatenation; store honesty
-- explicit not_recorded documents for manual/user
appends; the chats full-document road resolving a
group-generated message), the stateless road (per-
speaker reasoning events in arrival order before the
message event; the banked sequence otherwise unchanged
with no reasoning text in the message content; the
banked S305 shape exactly with a non-reasoning backend;
the road stores nothing), and the fences (migration
head 0042 with no m0043; the P-207 route census;
add_swipe still not_recorded; the P-071 presence digest
excerpting content only, with the thinking string
nowhere in the digest or its prompt message; a prompt
marker never entering a stored reasoning record).
NO neighbour heal was needed: P-205 E3 and P-207 pin 16
assert only the MANUAL group append, which stays
not_recorded by design (battery pin 8).
