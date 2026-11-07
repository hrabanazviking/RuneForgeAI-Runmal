# Chat Search — P-072 (2026-11-07)

Full-text and semantic search across all of your own chats, with
jump-to-message. Search is a read: it writes nothing, stores
nothing, and never searches another owner's chats.

## Endpoint

```
GET /api/v1/chats/search?q=<query>&mode=<mode>&limit=<n>&chat_id=<id>
```

Authentication is the same bearer credential as every other
chats route. There is no POST form in this slice.

| Parameter | Meaning |
| --- | --- |
| `q` | Required in effect. Blank or whitespace-only is a 422 (`q must not be empty`); over 500 characters is a 422. The query is stripped before use. |
| `mode` | `auto` (default), `fulltext`, or `semantic`. Any other value is a 422 — never a silent default. Values are the documented lowercase strings. |
| `limit` | Default 20. Clamped, not rejected: below 1 becomes 1, above 100 becomes 100. The response echoes the effective limit. `total` always reports the full hit count before limiting. |
| `chat_id` | Optional. Restricts the search to that one chat. A foreign or missing chat id is a 404, `chat not found` — exactly the same answer either way, so existence is never leaked. Absent means all of your chats. |

The route is declared before `GET /chats/{chat_id}` in the
router so the literal word `search` is not swallowed as a chat
id.

## What is searched

- Only the **active** text of each message: `content`, which is
  the currently selected swipe (`swipes[swipe_id]`). Inactive
  swipe alternates and variant history are never searched —
  they are not what the chat says now, and a hit you cannot
  jump to and see would be a lie.
- Chat **titles are not scored** and never create a hit. A hit
  is always a message; the title rides along only as display
  context. Title/metadata search is a later slice's road.
- The corpus is loaded owned-first: the query itself filters
  by your owner id, and a `chat_id` filter resolves through the
  owned-chat road first. Foreign messages are never loaded,
  scored, counted, or snippeted. `scanned_chats` and
  `scanned_messages` describe your corpus only.

## Modes

| Mode requested | What runs |
| --- | --- |
| `fulltext` | Deterministic token/phrase scoring in pure Python. Embeddings are never touched. |
| `semantic` | One batched embedding of the query plus every candidate message, scored by cosine similarity against a threshold of 0.30. |
| `auto` (default) | Semantic first. If it produces hits, those are the results. If it produces none, keyword scoring runs as a labelled fallback (see below). |

### Full-text scoring

The query and each message are tokenised the same way:
lowercased, word tokens, tokens shorter than 2 characters and
stopwords dropped, light suffix stemming applied. For one
message, with the deduped query tokens in query order:

- `token_score` — for each matched token, its frequency in the
  message, capped at 4 per token, summed. One repeated word
  cannot bury a broader match.
- `coverage_score` — `2.0 * (matched tokens / query tokens)`.
  Matching all the words beats matching one word often.
- `phrase_score` — `4.0` when the query has at least two tokens
  and the deduped query tokens, joined by single spaces, appear
  as a string in the content (lowercased, whitespace-collapsed),
  else 0.0. The phrase is built from the stemmed tokens, not the
  raw query text. An exact phrase is the strongest
  full-text signal.

`score = token_score + coverage_score + phrase_score`, rounded
to 6 decimal places.

Worked example: `q = "dragon fjord"`, content `"The dragon
crossed the dragon fjord at dawn"` — both tokens match,
`token_score = min(2, 4) + min(1, 4) = 3`, coverage `1.0`
gives `2.0`, the phrase hits for `4.0`, so `score = 9.0`.

A query whose tokens all vanish in tokenising (for example
`"the and of"`) is not an error on the full-text road: it
returns 200 with no results. On the semantic and auto roads
the raw query still embeds, so such a query can legitimately
return semantic hits.

Results are ordered deterministically by
`(-score, chat_id, ordinal, message_id)`; `rank` is the 1-based
position in that order, assigned before limit truncation.
Repeated identical queries over unchanged data return identical
documents.

### Semantic scoring

Semantic search reuses the existing embedding road. One backend
is resolved per query — your active embedding profile if you
have one, otherwise the local default (below) — and the query
plus all candidate messages are embedded in **one batched
call**, in one embedding space. A message is a semantic hit
when its cosine similarity to the query is at least 0.30.
For the embed call only, message text is truncated to the
first 4000 characters (a provider safety cap, stated here so
it is not a hidden result-changer); full-text scoring and
snippets always see the full stored text.

## Fallback labelling — the honesty core

When embeddings cannot do the job, keyword scoring may still
answer — but it is **always labelled as what it is**. No result
produced by token scoring is ever returned under
`mode_used = "semantic"`. Mode is a property of the whole
response, not of individual rows.

| Situation | `mode_used` | `fallback` | `fallback_reason` |
| --- | --- | --- | --- |
| `fulltext` requested | `fulltext` | `false` | `""` |
| `semantic` succeeds (even with zero hits) | `semantic` | `false` | `""` |
| `semantic`, embeddings unavailable / backend error / fallback result / embedding-space mismatch | `keyword_fallback` | `true` | `embeddings_unavailable`, `backend_error:<code>`, `fts_fallback`, or `embedding_space_mismatch` |
| `auto`, at least one semantic hit | `semantic` | `false` | `""` |
| `auto`, no semantic hits, keyword scoring runs | `keyword_fallback` | `true` | `no_semantic_hits` |
| `auto`, embeddings unavailable | `keyword_fallback` | `true` | the real reason, as above |

An explicit `semantic` request that honestly finds nothing
returns empty **as semantic** — it is not silently re-run as
keyword search. `degraded` always equals `fallback`.

An empty corpus (no chats, or no messages) short-circuits
before any embedding call: the result is 200 with no results,
`embedding` is null, and no fallback label is owed because no
road ran and nothing degraded.

## The local embedding surrogate — stated plainly

If you have no active embedding profile, the backend is the
deterministic local provider: provider `local`, model
`hash-ngram-1`. It is a **hashed token/character-ngram
lexical-semantic surrogate — it is not a neural model**. It
finds stem- and ngram-sharing paraphrases, not deep meaning.
Every response that used it names it in the `embedding`
provenance (`provider`, `model`, `dims`, `version`), so the
surrogate is never dressed up as a neural model. On the pure
full-text road, and when no backend resolved, `embedding` is
null.

## Result shape

```json
{
  "query": "dragon fjord",
  "mode_requested": "auto",
  "mode_used": "semantic",
  "fallback": false,
  "degraded": false,
  "fallback_reason": "",
  "embedding": {"provider": "local", "model": "hash-ngram-1", "dims": 0, "version": "..."},
  "chat_id": null,
  "limit": 20,
  "total": 1,
  "returned": 1,
  "scanned_chats": 2,
  "scanned_messages": 42,
  "results": [
    {
      "rank": 1,
      "chat_id": "...",
      "chat_title": "...",
      "message_id": "...",
      "role": "assistant",
      "speaker_name": null,
      "ordinal": 3,
      "snippet": "...",
      "score": 9.0,
      "matched_terms": ["dragon", "fjord"],
      "created_at": "..."
    }
  ]
}
```

`matched_terms` lists the matched tokens on the full-text and
keyword-fallback roads, and is empty on the semantic road.
Snippets are plain text, at most 240 characters of message
text (plus ... markers when truncated), with ...
marking truncation at either end; no highlight markup is
injected server-side — the client highlights `matched_terms`
itself. On the semantic road the snippet is the head of the
message, since no literal anchor is guaranteed.

## Jump-to-message contract

Every result carries the triple `(chat_id, message_id,
ordinal)`:

- **`message_id` is authoritative.** Open the chat with
  `GET /chats/{chat_id}` and locate that message.
- **`ordinal` is the fast hint**: the message's index in the
  history display order returned by that same read — not the
  stored position column, which is null on legacy chats.

If the chat was edited or its messages moved between the search
and the jump, `ordinal` may have shifted while `message_id`
still lands exactly. That redundancy is deliberate. No separate
jump endpoint exists; the existing history read is the jump
road.

## Migration: avoided

This slice adds **no migration**; the head stays at 0038 and no
provisional number is taken. Nothing needs stored state: the
full-text index is rebuilt per query from stored messages,
semantic vectors are computed per query in one batch and
discarded, and there is no search history, saved query, or
cache table. A stored index would also buy a whole invalidation
problem — edits, swipe selections, moves, deletes, and imports
all mutate content or order — for a benefit that is unmeasured
at current scale. SQLite FTS5 was considered and rejected on
the same grounds, plus its ranking cannot be pinned exactly in
a test. If a later slice adds persistence, it takes the
migration and the invalidation contract together, behind this
slice's unchanged API.

## Performance boundary — linear scan, honestly bounded

Full-text search is a **linear scan**: every query costs
O(your messages x message length) in Python, plus one ordered
history read per owned chat. Semantic search adds one batched
embed of the whole corpus per query — one round trip, but the
provider cost is per message, and there is no vector cache in
this slice.

For a personal library — tens of chats, hundreds to thousands
of messages — this is comfortably interactive, and it is
always fresh: an edit is searchable on the very next query,
with no index lag.

It will **not** stay fluid at stress scale: a 10,000-message
chat, or 10,000 chats, makes every query pay the full corpus
cost. That scale is **P-077 territory**, and the FTS or
stored-vector replacement — behind this slice's unchanged API
— is the named follow-up if, and only if, measurements demand
it. There are no silent caps: search never truncates the corpus
it scans; `limit` truncates results only, `total` reports the
full hit count, and `scanned_messages` in every response makes
the cost visible in the product itself.

## Read-only guarantee

Search writes nothing: no message, no chat event, no cache row.
The query text is never written to the event log or any stored
record.
