# Long-Chat Performance (P-077)

A 10,000-message chat now stays fluid: opening it, paging
back through it, searching it, assembling prompts from it,
and appending to it no longer pay whole-history costs. The
founding UI campaign's standard — the thread renders only
the newest 100 messages (THREAD_WINDOW) behind a "Show
earlier" reveal — is finally honoured by the server roads
underneath it. BUDGET-P077 (stated before measuring, in the
slice design) gates the six hot operations; the bench is
`scripts/bench_p077_longchat.py`, the battery is
`tests/test_p077_longchat_performance.py`.

## The paged history road

- `service.get_history_page(session, user_id, chat_id, *,
  limit, offset, tail)` returns one page in the exact
  `_ordered_messages` display order plus the total count,
  via SQL LIMIT/OFFSET — a page never materialises the
  whole chat.
- `GET /chats/{id}/messages` with no parameters returns the
  legacy full list, byte-identical to before. With
  `limit` / `offset` / `tail=true` it returns
  `{messages, total, limit, offset, has_more}`.
- Equivalence is proven, not asserted: pages concatenated
  in order are canonical-JSON sha256-equal to the legacy
  road, for materialised and for legacy NULL-position
  chats (battery).

## The web UI uses it

`selectChat` fetches the tail page (100) instead of the
full embedded history; chat fields come from the chat-list
row the UI already holds (falling back to the chat
endpoint only for a chat not in the list). "Show earlier"
fetches the next older page and prepends it; the hidden
count is `total - loaded`. `renderer.js` is untouched.
`GET /chats/{id}` remains as the compatibility road.

One road deliberately keeps full-history semantics:
`streamGeneration` sends the whole conversation as the
generation context, as it always has — that is a product
behaviour (what the model sees), not a rendering cost, and
changing it is not this slice's call. It is recorded as a
reported-only road in the evidence.

## Append no longer renumbers the world

`append_message` used to load every message and, in a
materialised chat, renumber all of them on every append —
O(N) reads and O(N) dirty rows per append. Now a single
SQL aggregate (count / count(position) / min / max /
count-distinct) proves whether positions are exactly
dense 0..N-1; if they are, the new message takes position
N and no prior row is touched. ANY irregularity —
duplicates, gaps, non-zero-based, mixed legacy NULLs —
falls back to the exact old road (load, renumber in
display order, new position = len). Legacy all-NULL chats
and empty chats keep position NULL, exactly as before.
Same position assignment, same `message.appended` event
either way; the battery pins the fallback on six irregular
shapes plus the dense, legacy, and empty cases.

## Migration PROVISIONAL 0041 — read this, keeper

This slice takes migration **PROVISIONAL 0041**:
`ix_messages_chat_position` on
`messages(chat_id, position, created_at, id)`. The number
is provisional; the keeper composes final numbering at
banking (P-076, banked ahead of this slice, took no
migration, so 0041 was free at muster).

Why it is unavoidable: the density aggregate and the
paged ORDER BY had only `ix_messages_chat_id` (chat_id)
to work with, so every position was fetched by a full
table-row lookup scattered across the messages table, and
SQLite's plans showed TEMP B-TREE for both
count(DISTINCT) and the paged ORDER BY. Measured on the
bench corpus, the aggregate alone was ~14 ms of the
16.76 ms append at 10k — append-at-10k / append-at-1k was
4.03 against the budget's 2.0 ratio gate, while the
absolute append gate (200 ms) passed twelve times over.
No exact code-only density proof can beat the row
lookups — any proof must at least stream the positions;
the index makes that stream index-only and ordered.
Probability-based shortcuts (sum / sum-of-squares
fingerprints) were considered and rejected: they are not
exact (Prouhet–Tarry–Escott collisions exist), and a
wrong "dense" verdict would silently corrupt positions.
With the index the same aggregate is a covering-index
stream. Older tests that pin migration head "0040" fail
on the head pin alone until the keeper's banking heal
(the established pattern, e.g. the P-075/P-076 banking
heals) — they are enumerated in the slice evidence.

## Two more quadratic pockets, closed

- Prompt composer: the splittable-slot trim dropped the
  oldest part and re-joined + re-counted the whole
  surviving history per drop — O(N²) at 10k parts
  (15,958 ms on the bench corpus). When the counter is
  the default `estimate_tokens` — a pure function of the
  joined length, `max(1, len // 4)` — the drop count is
  now computed exactly from prefix sums of part lengths.
  Custom counters keep the original loop verbatim.
  Output is byte-identical either way (battery vs an
  in-test oracle loop, including empty parts and
  drop-everything budgets).
- In-chat full-text search (P-072): a message can only
  score when some content token stems to a query token,
  and stemming only strips suffixes, so a scoring token
  always equals or starts-with a query token. A C-speed
  regex word-prefix scan now skips provably-unscorable
  messages; `score_fulltext` still computes every
  returned score with the pinned formula. No stored
  index; the P-072 contract is intact, and the battery
  pins the necessity direction on adversarial stemming
  cases (including the stemmer's non-confluence:
  stem("cross") = "cros" vs stem("crosses") = "cross" —
  pre-existing P-072 behaviour, untouched).
- `message_to_dict` parses the variant history once
  instead of twice.

## Budget and results

BUDGET-P077 (purplelongship, one core via taskset,
median of 15, service layer incl. serialisation):
latest page ≤ 150 ms; deepest page ≤ 200 ms and
deepest/latest ≤ 1.5; chat list ≤ 300 ms; in-chat search
≤ 500 ms; composer trim ≤ 500 ms; append at 10k ≤ 200 ms
and append-10k/append-1k ≤ 2.0. Final measured numbers
and per-gate verdicts live in the slice evidence
(`hidden_files/P077_EVIDENCE.md`, bench transcripts
`hidden_files/P077_BENCH_BEFORE.txt` /
`P077_BENCH_AFTER.txt`).

Reported only (no gate): legacy full-history
load+serialise, the legacy `GET /chats/{id}` payload,
semantic search, export. Out of scope (equivalence only):
delete / move / branch / checkpoint bulk roads —
legitimately full-history operations.

## Honest limits

- Pi-equivalent figures are the laptop median × 4.0
  derating (the P-046 convention) — a derating, never a
  Pi measurement. A direct Pi run of the bench is owed.
- The bench corpus is one deterministic seeded fixture
  (seed 77077); real chats with much larger individual
  messages will shift absolute numbers, though not the
  shape of the roads.
