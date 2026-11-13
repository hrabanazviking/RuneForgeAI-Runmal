# Inspector Group Reasoning (P-211) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218).
Scope is DERIVED per the P-203..P-210 precedent: the
governing roadmap gives Part XIII only its part-table
line and names the Inspector as a consumer; there is no
verbatim P-211 entry, and this slice is never presented
as roadmap-verbatim.

## Why

P-210 joined the P-205 reasoning record into the
Inspector for one-to-one chats and stated its own first
carried limitation plainly: chats-store coverage only.
Group reasoning, recorded since P-208 in the separate
groupchat store, was NOT in that census, and a group join
would be its own document if ever commissioned. This
slice is that document: the Inspector's reasoning
coverage becomes whole, and it adds the one
group-native debugging fact no Inspector document
carried - WHO spoke. An owner asking why a group reply
has no thinking can now learn from the Inspector which
speaker produced which record, and whether any group
record exists at all, without querying the transcript
message by message outside the Inspector.

## What lands

ONE new read-only, schema-versioned document
(`runmal-p211-inspector-group-reasoning-v1`) per owned
group, on ONE new road:

```
GET /api/v1/inspector/groups/{group_id}/reasoning
```

Owner-scoped like every group road; an unknown or
foreign group answers the house 404 idiom for groups
("group not found"). `app.py` wiring is unchanged - the
inspector router was already registered once at P-203,
so the app route set grows by exactly this one road
(356 paths / 439 operations).

The truth layer is ONE new groupchat-store read,
`list_group_reasoning` (`src/runmal/groupchat/store.py`,
after `list_messages`), mirroring the banked
`list_chat_reasoning` in shape. The owned fence IS
`list_messages` itself: the read calls it, its None for
a missing or foreign group propagates as None, and no
second fence is written, so existence never leaks. The
room chat is resolved through the banked `_room_chat`;
per message, in transcript order, the read carries the
banked `runmal.chats.reasoning` `active_view` (resolved
exactly as `message_to_dict` resolves it) and
`full_view`, plus `speaker_id` / `speaker_name`.

The document service (`src/runmal/inspector/
group_reasoning.py`) composes the census by CALLING
that read and the banked `summarise_reasoning` from
`runmal.inspector.reasoning` UNCHANGED - one source of
truth for the census vocabulary (the P-059 rule,
generalised a fourth time after P-203, P-204, P-210).
No parsing is re-implemented anywhere: all parsing
stays in the P-205 tolerant readers.

## The document

```json
{
  "schema": "runmal-p211-inspector-group-reasoning-v1",
  "group_id": "...",
  "room_chat_id": "...",
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
  "speakers": [
    {
      "speaker_id": "...",
      "speaker_name": "...",
      "messages_total": 0,
      "active_by_status": {
        "recorded": 0, "not_present": 0,
        "not_recorded": 0, "unknown": 0
      },
      "messages_with_recorded": 0
    }
  ],
  "messages": [
    {
      "message_id": "...",
      "role": "assistant",
      "speaker_id": "...",
      "speaker_name": "...",
      "active_status": "recorded",
      "recorded": true,
      "recorded_at": "...",
      "swipes_recorded": [0]
    }
  ],
  "raw_road": "/groups/{group_id}/messages"
}
```

No other keys exist. `room_chat_id` is the room
transcript Chat id - the id `describe_group` already
exposes for the group. `summary` is EXACTLY the P-210
summary shape, produced by the banked summariser.
`speakers` holds one entry per distinct speaker, in
first-appearance transcript order, keyed by the
(speaker_id, speaker_name) pair the store itself
serves: user and manual turns carry whatever speaker
identity the store serves (null where the store serves
null), carried verbatim, never invented. Per message,
in transcript order: the P-210 entry shape plus the
two speaker fields - `active_status` is the ACTIVE
swipe's reasoning status; `recorded` and `recorded_at`
are the full document's own values, carried verbatim;
`swipes_recorded` is the list of swipe indexes whose
stored record is `recorded`.

Coverage is the P-210 closed pair: `empty` when the
transcript has no messages (reason stated), `available`
otherwise. A transcript whose messages all read
`not_recorded` is AVAILABLE - the census is the fact,
honestly reported.

The `raw_road` is ONE document-level pointer at the
banked transcript road, whose `message_to_dict` serves
each message's active reasoning view (thinking text
included when recorded). This deliberately diverges
from P-210's per-message `raw_road`, for a plain
reason: no per-message group reasoning road exists, and
fabricating per-message pointers at a road that does
not exist would be a false pointer; the transcript road
is the banked surface that actually serves the text.

## Census semantics: two families, never confused

- `active_by_status` counts each message's ACTIVE view
  - one count per message. It is a fact about the
  transcript's CURRENT active swipes, so it moves when
  the active swipe changes. The per-speaker roll-up
  counts over active views too, and sums to the
  summary's active family exactly.
- `swipes_by_status` counts EVERY swipe record in
  every message's full document - the stable
  all-documents census.
- `swipes_total` is the number of swipe records
  present in the stored documents, and
  `swipes_recorded` the number of those records whose
  status is `recorded`. `messages_with_recorded`
  counts messages whose full document is recorded -
  the banked P-205 document-level vocabulary, identical
  in both stores: an explicitly built document is
  recorded as a document whatever its swipe's status;
  only rows with no document at all (the legacy `"{}"`
  default) read unrecorded at the document level.

Both families always carry all four statuses
(`recorded` / `not_present` / `not_recorded` /
`unknown`), zero-filled. Malformed stored reasoning
censuses as `unknown` through the banked tolerant
readers - joined, never re-implemented, never an
exception on this road.

## No-text discipline

The document carries NO thinking text and NO message
content anywhere - statuses, counts, timestamps,
speaker identity and pointers only. This is the P-204
no-payload discipline applied to the one content-class
record, exactly as P-210 applied it: the Inspector
answers "what exists and where", not "what it says".
Reading the thinking itself still goes through the
banked group transcript road (which the document's
`raw_road` names). The build is a pure read: it
persists nothing, and two consecutive GETs are
identical.

## Deliberately not built

- Per-swipe thinking browsing in the web UI:
  DECLINED-PENDING-WORD. Conditional on Volmarr's word
  under the P-206 ruling ("if Volmarr wants it"); that
  word is not given in this commission. Nothing is
  hidden meanwhile: the banked transcript road already
  serves every message's active reasoning view.
- Bot runtime: no substrate exists (no bots package;
  `chat.write` remains a reserved, honoured-nowhere
  permission). A founding, not a join - it needs its
  own commission.
- D1 (the stateless groupchat road's
  error-swallowing): FENCED, untouched, exactly as the
  P-208 / P-209 / P-210 records left it, awaiting a
  keeper / Volmarr ruling.
- Group Assistant-View rendering in group.js: real
  debt, a disjoint web-UI family; the transcript API
  already serves the data. Named the standing next
  Assistant-View candidate.
- Cross-chat / cross-group Inspector roll-up: the
  per-subject law held at P-203, P-204 and P-210; no
  banked owner-wide Inspector list read exists.
- Folding group rows into the P-210 chat document:
  declined - it would break the one-chat document
  shape both banked Inspector reasoning semantics rest
  on; the group join is its own document, per P-210
  itself.
- Any live or editable reasoning surface: the document
  is a stored-truth census, read-only by design.

## Carried limitations

- Per-group coverage only: the census is one owned
  group's transcript. One-to-one chats stay in the
  P-210 document; neither document folds in the other.
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
  moves none of them. Carried items K-A, K-B and K-C
  and the P-207 carry-overs stand as banked.

## Migration note

None. Head stays 0042: the `reasoning_json` column
(0042) already sits on the shared messages table every
group transcript row lives in (proven at P-208), and
the join is a pure read over banked reads and readers.
No provisional 0043 is taken.
