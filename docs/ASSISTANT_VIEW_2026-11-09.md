# Assistant View (P-206) - 2026-11-09

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
fourth slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line and names the Assistant view, in its Voxta mirror
census, as GPT-style, reasoning models with VISIBLE
THINKING. There is no verbatim P-206 entry, and this slice
is never presented as roadmap-verbatim.

## Why this slice exists

P-205 banked the reasoning record and the reads that carry
it - `message_to_dict` already serves every message's
ACTIVE reasoning view on the chat payload and on GET
/chats/{id}/messages (bare and paged) - but nothing
rendered it: a person chatting in the web surface never
saw that a reply had thinking, nor honestly learned that
none was recorded. P-205's own doc named this slice: "the
live SSE type and the stored document are the two surfaces
a view renders from". P-206 builds the view over the
STORED surface. It is UI-only: no new endpoint, no
migration (head stays 0042), no server change of any kind.

## What lands

1. `src/runmal/web/static/renderer.js` - ONE pure function
   added to the existing `RunmalRenderer` api (and its
   node-test exports): `reasoningView(reasoning)` maps a
   P-205 active view to a panel model or null.
   - recorded + a non-empty string text ->
     `{kind: "recorded", label: "Thinking", text}`.
   - not_present -> the status line "No thinking was
     returned for this reply."
   - not_recorded -> "Thinking was not recorded for this
     reply."
   - unknown -> "Thinking record state is unknown for
     this reply."
   - recorded WITHOUT usable text, or any other status
     value -> the unknown status model (text is never
     fabricated; an unrecognised status is never echoed
     raw).
   - null / undefined / non-object input -> null (no
     panel). The reader is tolerant and never throws.
   The status is read from `status` only - the
   `reasoning_status` duplicate key is not consulted (one
   source of truth). The function is pure: no DOM, no
   fetch, no swipe handling; per-swipe resolution stays
   server-side and banked, so a re-read after a swipe
   change shows the new swipe's record with no view-side
   swipe logic.
2. `src/runmal/web/static/app.js` - DOM rendering only.
   `reasoningPanel(view)` builds the panel: for a recorded
   model, a native `<details class="reasoning">` disclosure
   (keyboard-operable, no JS state), COLLAPSED by default -
   the reply stays primary, thinking is visible on demand,
   the GPT-style view the roadmap phrase names - with a
   `<summary>` carrying the label "Thinking" and the
   thinking text in a child div set via `textContent`
   ONLY: never `innerHTML`, never `renderMarkdownLite`
   (the markingBadge rule transposed: thinking is data
   shown as text, not message content). For a status
   model, a `<div class="reasoning-status">` whose
   textContent is the status line. `appendMessage` gains
   ONE trailing parameter (`reasoning`); after the marking
   badge it appends the panel when the model is non-null,
   and every existing call site keeps working unchanged
   (a missing argument yields no panel). `renderThread`
   passes `m.reasoning || null` for every message it
   renders, so panels appear exactly when the banked reads
   are (re-)fetched: on thread load and on "Show earlier
   messages" paging.
3. `src/runmal/web/static/style.css` - `.reasoning`,
   `.reasoning summary`, `.reasoning-text` and
   `.reasoning-status` rules beside `.voice-marking`,
   referencing design tokens only (`var(--dim)`,
   `var(--line)`, `var(--space-*)`): muted, smaller than
   body text, visually subordinate to the reply bubble.
4. `src/runmal/web/templates/chat.html` - NO change;
   renderer.js and app.js were already loaded in the
   right order.

## The live-SSE position (stated verbatim, keeper-ruled)

P-206 renders the STORED record only, at thread read
time. It does NOT render live reasoning during a web
stream, does NOT buffer or display "reasoning" SSE
events, does NOT persist anything client-side, and no UI
copy claims or implies live thinking. `streamGeneration`
is deliberately UNTOUCHED by this slice, and the battery
pins that: it still handles token/done only and contains
no reasoning handling, so the wiring cannot sneak in
unreviewed.

The facts behind the position (all banked at P-205): the
generation service DOES bridge reasoning live as
`{"type": "reasoning", ...}` SSE events, but the web
surface does not consume them, and the web road does not
STORE reasoning either - after a stream it saves the
assistant message with {role, content} only, so that
message's stored record is `not_recorded`. A reply made
through the web surface therefore shows the honest
"Thinking was not recorded for this reply." line on
re-read - true, because on that road it was not. Showing
live thinking that is never stored would be the dishonest
outcome: the view would contradict its own re-read.
Stored-only rendering is ACCEPTED for P-206 by the
keeper's ruling; wiring the live road (consuming the SSE
events AND a persistence change so live-shown thinking
and the stored record cannot diverge) is a server-side
change for its own later slice, if Volmarr wants it.

## The four-status honesty idiom (P-205, rendered)

- `recorded`: this swipe's generation produced thinking
  and the producing road captured it - shown verbatim as
  text in the collapsed disclosure.
- `not_present`: the producing road DID capture and the
  generation produced no thinking - a positive fact,
  shown as its own line, never merged with the others.
- `not_recorded`: the road never captured (legacy rows,
  manual / imported messages, producers not yet wired).
- `unknown`: stored data was missing, corrupt or foreign.

Three distinct status lines, no invented text anywhere:
a non-recorded served view carries no `text` key at all,
so there is nothing for the UI to leak.

## Deliberately not built (named, not gaps)

- Live SSE reasoning display in the web surface -
  declined above; stored-only is the keeper-ruled,
  honest position for this slice.
- A "show all swipes' thinking" toggle - the
  full-document endpoint exists (banked at P-205,
  pinned unchanged by this battery), but P-206 renders
  the ACTIVE view only, matching what the thread read
  already carries; per-swipe browsing is a later slice
  if Volmarr wants it.
- Rendering thinking through renderMarkdownLite -
  declined: thinking is shown as plain text only
  (injection-safe, and it is data, not authored prose).
- Any Inspector-side reasoning section - the P-203 /
  P-204 Inspector documents are pinned schemas; joining
  reasoning into the Inspector is not this thread.
- Editing, deleting or re-recording reasoning from the
  view - the view is read-only, full stop.
- Any server change: no new endpoint, no migration, no
  change to chats/*, generation/*, app.py or any
  template. The app's route census is pinned equal to
  the P-205 census by the battery.

## Part XIII roads still open

- Live reasoning wiring for the /generate web road (its
  own slice, per above), and wiring the other producing
  roads (continue / impersonate, groupchat, swipe
  regeneration) to record reasoning at all - until then
  they read `not_recorded` honestly, and the view says so.
- Per-swipe thinking browsing in the panel.
- An Inspector reasoning join.
- The rest of Part XIII (P-207..P-218) in roadmap order.
