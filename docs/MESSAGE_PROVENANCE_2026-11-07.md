# Message-Level Provenance (P-075)

Every stored chat message now carries a provenance document —
which model, preset, and lore produced it — recorded at
production time in `messages.provenance_json` (migration
PROVISIONAL 0040), as one production record per swipe
(alternate), under schema `runmal-p075-message-provenance-v1`.

## The honesty rule

A record states only what the producing road actually knew
when the message was made. Every section (`origin`, `model`,
`preset`, `lore`) carries an explicit status:

- `recorded` / `included` — the fact was held and is stated.
- `unknown` — the road could not know it (for example, a bare
  assistant append through the API, or the model behind an
  accepted impersonation draft: drafts are never stored).
- `not_run` — the road never ran that stage. Live generation
  in Rúnmál does not route through lore activation, so bridge
  and continue generations record lore `not_run`; the group
  deepening road, which does run lore, records the entries it
  actually included (or `ran_none_included`).
- `not_applicable` — the stage does not apply to that origin
  (a typed user line has no producing model).

Legacy messages (stored before P-075) read as
`provenance_status: not_recorded` with gap sections — never
as reconstructed facts. Selecting a swipe only changes which
record is surfaced; it never rewrites storage. Edits and
continuations append `amendments` to the active swipe's
record; the original producer stays the producer of record.
Copied/branched messages record origin `copied` with the
source message/chat ids, the source text's sha256, and the
source's own record nested — copying changes where a text
lives, not what produced it.

## Reading it

- Every message dict (history, group transcripts, bridge
  state) carries `provenance` for its active swipe.
- `GET /chats/{chat_id}/messages/{message_id}/provenance` —
  the full document, all swipes.
- `GET /chats/{chat_id}/provenance` — per-message active
  records plus a summary (totals, by origin, by model status,
  how many have lore included). Part XIII's Inspector
  consumes these payloads; nothing is re-derived.

## Never recorded

Message or prompt content, secrets or secret references, and
provider payloads. Sampler params are recorded when a preset
was resolved — they are the preset's own configuration, the
receipt fact of what settings produced the turn.
