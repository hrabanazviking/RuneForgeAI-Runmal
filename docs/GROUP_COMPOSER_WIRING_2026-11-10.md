# Group Composer Wiring (P-214) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line; there is no verbatim P-214 entry, and this slice is
never presented as roadmap-verbatim. The derivation is
the banked trail: P-213's scout declined persistent-group
composer wiring for that slice - "a larger founding no
banked record names; P-213 founds the loader/renderer
only" - and named it "a possible later candidate"; the
P-213 slice doc restated it as "the declined composer
founding named as a later candidate". Its founding
premise has since changed: the loader it builds on has
banked (P-213). P-214 is that wiring.

## Why this slice exists

After P-213 the group page could OPEN a saved group and
render its stored transcript, but the composer still
spoke only the stateless road: a turn composed after
opening a saved group went to POST /api/v1/group/turn
with the page's own roster checkboxes, strategy select
and client-held history, and the opened group's stored
transcript gained nothing. The persistent composing road
already existed and was banked - POST
/api/v1/groups/{id}/next appends the user's turn
server-side, lets the group itself choose the speaker
from its stored policy and roster, generates through the
banked generation service with the P-208 reasoning
collection, appends the reply with its provenance and
reasoning record, and returns it in the same message
dict shape P-213 renders. The page simply never called
it. P-214 wires the one shared composer to that road as
a second mode of the same composer - UI-only: no new
endpoint, no migration (head stays 0042), no server
change of any kind, route census unchanged at 356 paths
/ 439 operations, and group.html is not modified.

## What was built

group.js only (plus this doc, the battery and one
clean-room ledger line):

- One piece of page state: `let openGroupId = null;`
  beside the existing state block - the id of the saved
  group currently open; null is the stateless room, the
  page's resting state at load.
- openSavedGroup() sets openGroupId from the picked
  group id, on success only: the assignment sits after
  the successful fetch and the render loop. On the
  failure path nothing changes - the catch still only
  surfaces showError - so a failed open never switches
  the composer's mode and a previously opened group
  stays the composer's group.
- The #group-form submit handler keeps its shared head
  exactly (preventDefault, trim, empty return, clear the
  input, the user's bubble via addBubble) and then
  branches on openGroupId BEFORE any sentHistory
  snapshot or history mutation:
  - openGroupId set: `await sendPersistent(text)` and
    the handler returns - the persistent branch
    structurally cannot touch the stateless turn state.
  - openGroupId null: the banked stateless body,
    byte-unchanged - roster checkboxes, strategy
    select, history, the SSE stream and the P-212
    panels all behave exactly as banked.
- New sendPersistent(text), in the file's established
  style: POST through the existing api() helper to
  "/api/v1/groups/" + openGroupId + "/next" with
  {user_text: text, generate: true} - a plain JSON road,
  no SSE reading - then renders result.message, when
  non-null, through the same pair the P-213 stored path
  uses: addBubble(m.speaker_name || "user", m.content)
  with reasoningPanel built from
  window.RunmalRenderer.reasoningView(m.reasoning)
  appended under the bubble when a reasoning view is
  present. The whole body sits in try/catch; a failure
  surfaces via the existing showError banner. The
  branch contains no reference to history, sentHistory,
  rrCursor, selectedIds or the strategy select, never
  calls /api/v1/group/turn, and writes no web storage.

## The mode model

Open group = persistent mode; resting page = stateless
mode. There is no third state and no mode indicator is
added in this slice: the opened group's transcript in
the thread is the mode's visible truth. Mode exit in
this slice is page reload - reloading returns the page
to its resting stateless state. An explicit
close/toggle control (leaving persistent mode without a
reload) is named below as a possible later candidate;
no banked record names it, so it is not founded here.

## Speaker choice in persistent mode

In persistent mode the speaker is chosen by the GROUP -
its own stored speaker policy and stored roster, applied
server-side by the banked /next road. The page's Roster
checkboxes and Strategy select govern only the stateless
room; they play no part in a persistent turn, and this
doc states that plainly so no reader mistakes the aside
controls for persistent-mode controls.

## The P-213 fence, restated

The loader fence stands unchanged: fetched messages are
never copied into the stateless history state, never
sent back as history, and nothing is written to web
storage; the loader itself still issues no POST. What
P-214 changes is only the one sentence that the wiring
makes false - opening a saved group now DOES change
what the composer does next, by putting it into that
group's persistent mode - and the loader's header
comment is restated to say exactly that, with the fence
itself carried verbatim in substance. The persistent
branch in turn never feeds the stateless state: no
persistent turn touches history, sentHistory or
rrCursor, so a stateless turn composed after a page
reload carries only its own history, exactly as banked.

## The null-message rule

When the /next road picks no speaker, it returns
message: null (with generate=false it always does). The
composer renders nothing further: the user's turn is
stored server-side and the transcript road remains the
truth; the page does not invent a reply, a placeholder
bubble or a status line for a turn that has none.

## Failure behaviour

Errors on the persistent branch - the banked 404 for an
unknown or unowned group, the banked 502 when
generation fails, network failure - surface via the
existing showError banner, as both existing paths do.
The failure contract is inherited whole from the banked
road (the P-207/D2 contract): on a generation failure
nothing is stored for the reply, and no partial or
fabricated message is rendered.

## Declined, with reasons

- Explicit mode toggle / close-group control: no banked
  record names it; mode exit here is page reload. Named
  as a possible later candidate.
- The /run multi-turn road and the raw message-append
  road from this page: /next with user_text already
  appends the user turn server-side; wiring /run or a
  manual append would duplicate one composing act
  across three roads. Declined.
- Per-swipe thinking browsing in the Assistant View
  panel: conditional on Volmarr's word under the P-206
  ruling - DECLINED-PENDING-WORD.
- Bot runtime: no substrate (chat.write still RESERVED,
  honoured nowhere; re-verified at this base).
- Cross-subject Inspector roll-up: declined at P-211
  under the per-subject law; stands.
- New Inspector documents: coverage complete at P-211.
- Live rendering on stored roads: the P-206 stored-only
  position stands; P-214 renders only the /next RESULT
  message, a fresh turn reply, never stored content
  live.
- D1 (the stateless groupchat road's error-swallowing):
  FENCED, awaiting a keeper / Volmarr ruling. Not taken;
  the persistent branch does not touch the stateless
  stream path at all.
- Carried items K-A / K-B / K-C: untouched.

## Fences

No migration (head stays 0042, no provisional 0043), no
new or changed road (route census stays 356 paths / 439
operations, zero census heals), no Python source change,
no stylesheet change, no group.html change (the S311
group golden is therefore expected unmoved, and was),
no README touched.
