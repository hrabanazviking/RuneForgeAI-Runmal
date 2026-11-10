# Reasoning Wiring for Continue / Impersonate (P-207) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
fifth slice. Scope is DERIVED per the P-203..P-206
precedent: the governing roadmap gives Part XIII only its
part-table line. There is no verbatim P-207 entry, and this
slice is never presented as roadmap-verbatim.

## Why this slice exists

P-205 founded the reasoning record but wired only ONE
producing road (the bridge); its own record and P-206's
both carry the same debt list, with continue / impersonate
named FIRST. P-206 then made the record visible in the
Assistant View, so every continue reply honestly showed
"Thinking was not recorded" - the most visible remaining
gap in daily chat use. Continue / impersonate is ONE
coherent family: one module
(`src/runmal/chats/continue_impersonate.py`, the P-069
pair), one shared generation seam, and one landing store
that already accepts a reasoning record. Wiring it retires
that gap with no new storage, no new endpoint and no new
store.

## What lands

ONE production file changes:
`src/runmal/chats/continue_impersonate.py`.

1. The shared seam. `_generate_text(backend, messages)`
   now returns `tuple[str, dict]`: beside the text it
   collects the generation service's `{"type": "reasoning"}`
   dicts in arrival order, exactly as the bridge loop
   collects them, and builds a strict P-205 record -
   `recorded` with the verbatim joined thinking when the
   joined text is non-empty, else `not_present` (the
   bridge's own rule; empty-string reasoning dicts join to
   `""` and therefore read `not_present`). Reasoning is
   never merged into the answer text. The failure contract
   is UNCHANGED: an error, a cancelled/error finish, or
   empty text raises `GenerationFailedError`, the caller
   stores nothing, and no record is built for a failed
   generation - there is nothing to land.
2. Continue NEXT. The landing passes `reasoning=record`
   to the existing `append_message(...)` call beside
   `provenance=record` - the bridge producer's exact
   pattern. Nothing else in that call changes. The new
   message's active reasoning view, and the full document
   on the GET reasoning road, read the landed record;
   P-206's Assistant View renders it on re-read for free.
3. Continue EXTEND. The extension is a second generation
   contributing to the SAME active swipe, so its record
   may only COMBINE with a record the seam already owns -
   never retro-attribute. The active record is read via
   `reasoning.active_view(message, idx)` BEFORE
   `_store_deck` grows the deck; the combination lives in
   one small pure helper, `_combine_extend_reasoning`, and
   the combined record is written back with
   `with_record_for_swipe(parse_reasoning(message), idx,
   combined)` + `dump_document` - the same helpers
   `add_swipe` uses. The table:

   | existing active | new generation | combined |
   |---|---|---|
   | recorded | recorded | recorded, text = existing text + new text |
   | not_present | recorded | recorded, with the new text |
   | recorded | not_present | recorded, existing text unchanged |
   | not_present | not_present | not_present |
   | not_recorded or unknown | any | NOT touched (see below) |

   Recorded + recorded concatenates in production order:
   the two productions' thinking is the thinking behind
   the swipe's full current text. Not_present + recorded
   becomes recorded because the seam ran both times and
   the first production verifiably produced no thinking.
   When the existing record is `not_recorded` or `unknown`
   (legacy, manual, imported or unwired origin), the
   helper returns None and the swipe's `reasoning_json`
   is left byte-untouched: that swipe's earlier production
   was never captured, so no record for the whole swipe
   can be honestly claimed. The extension still lands as
   text plus its provenance continuation amendment,
   exactly as before P-207.
4. Impersonate. `impersonate_draft` carries the record
   TRANSIENTLY: the draft document gains one key,
   `"reasoning"`, holding the record dict itself
   (`{"status": ..., "text"?}` - text only when
   recorded). Draft reasoning is a fact about the DRAFT
   generation only; it is persisted NOWHERE.
5. Accept / discard: NO change. `accept_impersonate`
   appends user-supplied text; its message keeps reading
   `not_recorded` (the `append_message` default). The
   draft's reasoning is NEVER attached at accept - the
   landed text is the user's act, verbatim or edited, and
   attaching the draft generation's thinking to it would
   fabricate a record for text the model did not land.

The module docstring gains a P-207 paragraph stating the
wiring, the extend combination rule and its legacy
exclusion, and the draft-only impersonate position.

NO other production file changes. No new endpoint, no
route change (the app route census is identical to the
P-206 census, pinned by the battery), no web/UI change,
no groupchat / store / swipe changes.

## Deliberately not built

- Groupchat wiring - declined for this slice, named the
  natural P-208 candidate: it is two surfaces, not one
  family (a stateless road that stores nothing, plus a
  persistent road on a second store whose append has no
  reasoning param and whose read model exposes no
  reasoning view). Wiring it is a wider slice.
- A swipe-regeneration executor - there is no server-side
  generation road that produces a swipe to wire:
  `add_swipe` appends caller-supplied content and its
  `not_recorded` is CORRECT. Building the executor is a
  founding slice, not this wiring slice.
- Live-SSE wiring of the web `/generate` road -
  EXCLUDED by name: conditioned on Volmarr wanting it by
  the P-206 record; his to call, not the campaign's to
  take. Nothing here drifts into
  `src/runmal/generation/router.py` or the web
  streamGeneration path.
- The bot runtime - no substrate exists in-tree
  (`chat.write` is still a reserved, honoured-nowhere
  permission); P-203's decline stands, re-verified at
  this base.
- The Inspector reasoning join and per-swipe browsing -
  named Part XIII threads of their own, not folded into
  this slice.

## Carried limitations (honest, by design)

- Extend onto a legacy / manual / imported swipe drops
  the extension generation's thinking on the floor BY
  DESIGN: recording it would claim coverage of text
  whose production was never captured. Those swipes keep
  reading `not_recorded` until re-generated whole.
- Impersonate reasoning lives only in the draft
  document; once a draft is dropped or accepted, its
  thinking is gone - nothing persists it, deliberately.
- The extend combination concatenates two productions'
  thinking with no separator or per-part marker: the
  record stays verbatim per production, in order, but a
  reader cannot see where part one ends.
- Groupchat generations and manual swipes still read
  `not_recorded` after P-207; web `/generate` replies
  too (the excluded road). The Assistant View keeps
  saying so.

## Migration note

NONE. Head stays 0042: the `reasoning_json` column
(migration 0042), the record module and the
`append_message` reasoning param all already exist, and
the impersonate half persists nothing by design. No
provisional 0043 is taken - there is no schema change.
Pinned by the battery (MIGRATIONS last revision "0042";
no m0043 module exists).

## Battery and heal

`tests/test_p207_continue_impersonate_reasoning.py` -
16 pins: the seam (recorded in order, never merged;
not_present; failure stores nothing), continue NEXT
(recorded landed and re-read three ways; not_present as
a positive fact), continue EXTEND (the four seam-owned
combinations plus the legacy byte-untouched pin, with
content growth and the provenance amendment still
landing), impersonate (draft carries recorded /
not_present transiently and stores nothing; accept never
attaches it; discard stores nothing), and the fences
(migration head 0042 with no m0043; the P-206 route
census unchanged; groupchat manual append and chats
`add_swipe` still `not_recorded`).

One named neighbour-pin heal, at equal strength:
`tests/test_p205_reasoning_record.py::test_e3_unwired_
roads_read_not_recorded` asserted continue reads
`not_recorded` - P-207 supersedes THAT HALF by design.
The heal restates only the continue half to the new
wired truth (recorded, with the fake's scripted thought
verbatim) with a comment naming P-207, adds one
assertion and weakens none, and leaves the group-manual
half byte-identical. The pin's count is unchanged.
