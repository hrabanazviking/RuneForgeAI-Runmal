# Inspector Events (P-204) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
second slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line and names the Inspector, in its Voxta mirror census,
as debugging EVENTS / ACTIONS / FLAGS. There is no
verbatim P-204 entry, and this slice is never presented
as roadmap-verbatim.

## The P-203 scout correction, restated plainly

P-203's scout said there is NO persisted event log or
event-history read surface in the tree, and P-203's
design declined a persisted event/action/flag log on the
ground that founding one is a storage decision, flagging
it as the natural P-204+ question with migration 0042
provisional if a later slice proved the log unavoidable.
For PLUGIN events that held. As a statement about the
tree it was too broad, and P-204's scout corrected it:
a persisted per-chat event log - the S107 `chat_events`
table in `src/runmal/db/models.py`, written by every
chat mutation path - HAS existed since S107
(pre-campaign base), with a banked read road
(`GET /chats/{chat_id}/events` via the chats service's
`list_events`). The P-203 decline therefore reasoned
from an incomplete census. No banked CODE was defective
- the P-203 overview simply does not join the log - but
the record is corrected here, and the consequence is
practical: P-204 needs NO migration. The storage P-203
thought might force 0042 already exists; head stays
0041 and 0042 is not needed and not flagged.

## What lands

The Inspector's second document: ONE read-only,
schema-versioned events document
(`runmal-p204-inspector-events-v1`) per owned chat, on
ONE new road:

```
GET /api/v1/inspector/chats/{chat_id}/events
```

Owner-scoped like every chat road; an unknown or foreign
chat answers the house 404 idiom ("chat not found").
`app.py` wiring is unchanged - the inspector router was
already registered once at P-203, so the app route set
grows by exactly this one road. The service
(`src/runmal/inspector/events.py`) composes the document
by CALLING the banked chats-service read (`list_events`)
- never re-implementing it, never opening a second query
path (the P-059 one-source-of-truth rule, generalised).

The document declares `generated_from: [S107 chat event
log]` and carries four sections, each with an honest
status in the P-075 idiom - one of `available` / `empty`
/ `not_applicable` / `unavailable`, plus a plain `reason`
string whenever a section is not available.

- **events** - the by-kind census over the log: `total`
  row count, `by_kind` counting every kind PRESENT under
  its stored string verbatim (legacy kinds are counted,
  never renamed or dropped against the 20-kind S107
  catalogue), `first_at` / `last_at` timestamps, and
  `latest` (kind + timestamp of the newest row only),
  plus the `raw_road` pointer at the banked raw road.
  A chat with zero recorded rows reads `empty`, total 0,
  `by_kind {}` - never a faked census, never an error.
  An upstream read failure reads `unavailable` + reason.
- **actions** - the triad's actions leg, counted FROM
  THE SAME census: occurrences of the five action kinds
  (`message.edited`, `message.pinned_to_memory`,
  `message.unpinned_from_memory`, `message.moved`,
  `message.copied_to_branch`), plus a pointer at the
  banked message reads, where per-message action STATE
  (variant history / pin / position, m0038, P-068)
  already rides. The section counts occurrences; it does
  not rebuild per-message state.
- **flags** - `not_applicable`, with the reason stated:
  scenario flags are bind-time bool seeds in the binding
  record ("flags hold bool only", seeded through P-093);
  nothing mutates a flag after binding, so no flag event
  stream exists to census. Pointers name the P-203
  overview's scenario section and the banked scenario
  censuses, where binding state already reads.
- **not_recorded** - the honest coverage statement as
  data: exactly three families, each `not_applicable`
  with its reason - generation events
  (`generation.before` / `after` / `failed` are
  dispatched fire-and-observe; the generation and plugin
  packages write no ChatEvent rows), plugin dispatch
  outcomes (P-081 handler results live in the plugin
  registry's own records), and `chat.deleted` (the
  cascade removes the log with the chat, so no row
  survives to read).

## The no-payload law

The document carries NO event `data` payloads and NO
message content anywhere - counts, kind names and
timestamps only. Payload drill-down stays on the banked
raw road (`GET /api/v1/chats/{chat_id}/events`), which
the events section points at. Widening this document to
carry payloads was declined: it would add exactly the
content exposure the P-203 idiom exists to prevent.

## Read-only, and what this slice is not

The slice writes nothing, records nothing and persists
nothing; the document is assembled fresh from the banked
truth on each call. It builds NO retention, pruning or
bulk-clear machinery over the log: that is carried item
K-B, awaiting Volmarr's ruling. Carried items K-A
(binding label update) and K-C (unified-search history)
are likewise untouched. The P-203 overview document
(`runmal-p203-inspector-overview-v1`) is untouched - its
shape is pinned unchanged by this slice's battery.

## Carried limitations

- The census is per-chat only; no cross-chat event
  roll-up in P-204.
- `by_kind` counts what is stored, including legacy kind
  strings; rows are not validated against the 20-kind
  catalogue.
- `not_recorded` is a fixed coverage statement, not a
  probe: if a later slice starts recording generation
  events, that slice must revise this section.
- Ordering follows the banked read's `created_at` order;
  same-timestamp ties inherit the raw road's behaviour.

## Part XIII roads still open

Assistant View and Bots remain substrate-free (no
reasoning / thinking surface and no bot package exist in
the tree - grep-verified again at P-204's scout), so
founding either now would ship a shell over nothing.
Persisting generation / plugin events into the log
remains declined for the reasons in the P-204 design
(hot-path write machinery and a founding storage
decision); P-204 states that gap honestly instead.
Part XIII runs P-203..P-218, with P-218 its gate.
