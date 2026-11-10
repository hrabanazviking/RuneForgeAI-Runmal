# Inspector Reasoning (P-210) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218).
Scope is DERIVED per the P-203..P-209 precedent: the
governing roadmap gives Part XIII only its part-table
line and names the Inspector as a consumer; there is no
verbatim P-210 entry, and this slice is never presented
as roadmap-verbatim.

## Why

The P-205 reasoning record is now produced by every
road (the producing side closed at P-209) and rendered
in one place (the Assistant View, P-206), but the
Inspector - the roadmap's debugging surface, which
already joins provenance, prompts, lore and events for
a chat - could not see it at all: an owner debugging
"why does this reply have no thinking" had to leave the
Inspector and query message by message. The join was
named as its own later slice by P-206 and again by
P-208, unconditionally. This slice is that join: the
reasoning trail's last named consumer.

## What lands

ONE new read-only, schema-versioned document
(`runmal-p210-inspector-reasoning-v1`) per owned chat,
on ONE new road:

```
GET /api/v1/inspector/chats/{chat_id}/reasoning
```

Owner-scoped like every chat road; an unknown or
foreign chat answers the house 404 idiom
("chat not found"). `app.py` wiring is unchanged - the
inspector router was already registered once at P-203,
so the app route set grows by exactly this one road
(355 paths / 438 operations).

The truth layer (`src/runmal/inspector/reasoning.py`)
composes the document by CALLING one new banked-shape
chats-service read - `list_chat_reasoning`, mirroring
`list_chat_provenance` line for line in shape: the
owned-chat fence, the ordered messages, and per message
the banked `active_view` and `full_view` from
`runmal.chats.reasoning`. The Inspector module then
aggregates with those views (a pure summariser in the
Inspector module - the census vocabulary is an
Inspector concern, and `runmal.chats.reasoning` gains
no summariser). No parsing is re-implemented anywhere:
all parsing stays in the P-205 tolerant readers.

## The document

```json
{
  "schema": "runmal-p210-inspector-reasoning-v1",
  "chat_id": "...",
  "coverage": {"status": "available", "reason": null},
  "summary": {
    "messages_total": 0,
    "active_by_status": {
      "recorded": 0, "not_present": 0,
      "not_recorded": 0, "unknown": 0
    },
    "messages_with_recorded": 0,
    "swipes_total": 0,
    "swipes_recorded": 0,
    "swipes_by_status": {
      "recorded": 0, "not_present": 0,
      "not_recorded": 0, "unknown": 0
    }
  },
  "messages": [
    {
      "message_id": "...",
      "role": "assistant",
      "active_status": "recorded",
      "recorded": true,
      "recorded_at": "...",
      "swipes_recorded": [0],
      "raw_road": "/chats/{chat_id}/messages/{message_id}/reasoning"
    }
  ]
}
```

No other keys exist. Per message, in chat order:
`active_status` is the ACTIVE swipe's reasoning status;
`recorded` and `recorded_at` are the full document's
own values, carried verbatim; `swipes_recorded` is the
list of swipe indexes whose stored record is
`recorded`; `raw_road` points at the banked per-message
road where the record itself - text included - already
lives.

Coverage is the overview's closed-vocabulary idiom,
reduced to the pair this census can honestly take:
`empty` when the chat has no messages, `available`
otherwise. A chat whose messages all read
`not_recorded` is AVAILABLE - the census is the fact,
honestly reported.

## Census semantics: two families, never confused

- `active_by_status` counts each message's ACTIVE view
  - one count per message. It is a fact about the
  chat's CURRENT active swipes, so it moves when the
  active swipe changes.
- `swipes_by_status` counts EVERY swipe record in
  every message's full document - the stable
  all-documents census.
- `swipes_total` is the number of swipe records
  present in the stored documents, and
  `swipes_recorded` the number of those records whose
  status is `recorded`. `messages_with_recorded`
  counts messages whose full document is recorded.

Both families always carry all four statuses
(`recorded` / `not_present` / `not_recorded` /
`unknown`), zero-filled. Malformed stored reasoning
censuses as `unknown` through the banked tolerant
readers - joined, never re-implemented, never an
exception on this road.

## No-text discipline

The document carries NO thinking text and NO message
content anywhere - statuses, counts, timestamps and
pointers only. This is the P-204 no-payload discipline
applied to the one content-class record: the Inspector
answers "what exists and where", not "what it says".
Reading the thinking itself still goes through the
banked per-message raw road (which every entry's
`raw_road` names) or the Assistant View. The build is
a pure read: it persists nothing, and two consecutive
GETs are identical.

## Deliberately not built

- Per-swipe thinking browsing in the web UI: real but
  conditional ("if Volmarr wants it", P-206 record) and
  a disjoint web-UI family. Named the natural P-211
  candidate if the keeper / Volmarr gives the word.
  Nothing is hidden meanwhile: the banked raw road
  already returns every swipe's record to any API
  reader.
- Group-transcript reasoning census: groupchat
  transcripts live in the separate groupchat store
  (P-208 landed their records there); folding them in
  would break the one-chat document shape both banked
  Inspector documents use. A group join would be its
  own document if ever commissioned.
- Bot runtime: no substrate exists (no bots package;
  `chat.write` remains a reserved, honoured-nowhere
  permission). A founding, not a join - it needs its
  own commission.
- D1 (the stateless groupchat road's
  error-swallowing): FENCED, untouched, exactly as the
  P-208 / P-209 records left it, awaiting a keeper /
  Volmarr ruling.
- Any live or editable reasoning surface: the document
  is a stored-truth census, read-only by design.

## Carried limitations

- Chats-store coverage only: group reasoning is NOT in
  this census (see above). The document says what it
  covers - one owned chat's stored messages.
- No thinking text in the Inspector, by design (see
  above).
- Active-view counts move when the active swipe
  changes; both count families are carried precisely
  so the two are never confused.
- `swipes_total` counts swipe records present in the
  stored documents; a swipe whose record was never
  written into the document (legacy rows predating
  0042 default `"{}"`) surfaces through its message's
  active `not_recorded` / `unknown` status, not as a
  phantom swipe row.
- Per-swipe browsing, bot runtime and D1 all stand
  exactly as fenced / declined above - this slice
  moves none of them.

## Migration note

None. Head stays 0042: the join is a pure read over
the existing `reasoning_json` column (0042), the
tolerant readers and both views already exist, and the
join persists nothing. No provisional 0043 is taken.
