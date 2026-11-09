# Inspector Overview (P-203) — 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218)
opener. Scope is DERIVED per the P-101/P-117/P-131 opener
precedent: the governing roadmap gives Part XIII only its
part-table line and names the Inspector only as a CONSUMER
of P-043 activation inspection, the P-059 prompt-preview
glass box, and P-075 message provenance. There is no
verbatim P-203 entry, and this slice is never presented as
roadmap-verbatim.

## What lands

A read-only composed Inspector overview: a new package
`src/runmal/inspector/` whose service assembles ONE
schema-versioned document (`runmal-p203-inspector-overview-v1`)
per owned chat, on ONE road:

```
GET /api/v1/inspector/chats/{chat_id}
```

Owner-scoped like every chat road; an unknown or foreign
chat answers the house 404 idiom ("chat not found").

The document declares `generated_from: [P-043, P-059,
P-075, scenario bindings]` and carries four sections, each
with an honest status in the P-075 idiom — one of
`available` / `empty` / `not_applicable` / `unavailable`,
plus a plain `reason` string whenever a section is not
available. A section whose upstream read fails reads
`unavailable` + the reason, never a faked empty.

- **provenance** — the P-075 chat summary carried VERBATIM
  from the banked read (`list_chat_provenance`): totals,
  by origin, by model status. Counts and statuses only,
  exactly what P-075 itself already returns; no per-message
  records and no new content exposure. A chat with no
  messages reads `empty`; a legacy chat's summary honestly
  reports its `not_recorded` counts — nothing is
  reconstructed.
- **prompt** — availability of the banked P-059 roads,
  pointed at, never run: `POST /api/v1/debug/prompt-inspect`
  and `POST /api/v1/debug/prompt-preview`.
- **lore_activation** — the lorebooks bound to the chat,
  resolved through the banked P-040 layered scope
  resolution (`resolve_scoped_books`), each with a pointer
  at the banked P-043 inspect road and its schema
  (`runmal-p043-activation-inspection-v1`). No books reads
  `empty`.
- **scenario** — the chat's scenario-binding state from the
  banked binding store: when bound, the record's own
  summary shape (identity + counts read from the record
  itself); when unbound, `empty` with `bound: false`. No
  flag values and no seeded content are carried.

## What it deliberately does not do

- **No live prompt composition or activation rolls inside
  the GET.** Composing a prompt or running an activation
  inspection can consume probability rolls; a read must not
  spend them as a side effect. The overview points at the
  banked POST roads instead.
- **No re-implementation.** The service CALLS the banked
  surfaces (P-075 read model, P-040 scope resolution, the
  scenario binding store, and the P-043/P-059 road
  pointers); the P-059 one-source-of-truth rule, generalised.
- **Nothing is persisted.** No migration — head stays 0041;
  0042 is NOT taken. The document is assembled fresh on
  each call.
- **No write or execution roads, no bot runtime.** The
  Inspector foundation is read-only by design; Part XIII
  execution machinery, if any, is a later slice's explicit
  scope.
- **No Assistant-View reasoning display.** The tree holds
  no reasoning/thinking content anywhere (no backend stores
  or returns reasoning traces), so there is nothing honest
  to view; building the shell now would ship an empty
  promise. It becomes buildable only after a slice gives
  backends a reasoning-content record.

## Carried limitations

- The overview is per-chat only; no cross-chat or global
  Inspector roll-up in P-203.
- Sections are pointers + banked summaries, not deep
  drill-downs; each banked source keeps its own road.
- The scenario section's depth is bounded by what the
  banked binding record's summary returns; no new scenario
  introspection is invented.

## Verification

Battery `tests/test_p203_inspector_overview.py` pins: the
schema id, the P-075 summary carried verbatim, legacy-chat
honesty, no prompt text / no activation outcomes in the
document, bound-vs-unbound scenario honesty, lore pointer
shape, unknown/unowned chat refusal, no content/secrets,
the pure-read law, and migration head 0041 with no 0042.
Neighbours and the full suite run on purplelongship;
counts are recorded in the slice evidence.
