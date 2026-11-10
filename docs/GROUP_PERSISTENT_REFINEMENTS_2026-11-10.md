# Group Persistent Refinements (P-217) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line; there is no verbatim P-217 entry, and this slice is
never presented as roadmap-verbatim. The derivation is
the banked trail: P-213 founded the saved-groups picker
and the display-only transcript loader, P-214 wired the
persistent composer, P-215 made the composer mode visible
and leavable, and P-216 founded saved-group creation.
P-216's scout then honestly named what remained after
creation banked: no foundings at all, only two REFINEMENTS
of the just-banked surface - (a) the Roster and Strategy
controls disabled while persistent mode is open, and
(b) the picker's message_count labels refreshed after a
persistent send. P-217 takes exactly those two, together,
in group.js only: no backend change, no new road, no
migration (head stays 0042), no markup change (group.html
untouched), no stylesheet change, route census unchanged
at 356 paths / 439 operations.

## What was refined

group.js only (plus this doc, the battery and one
clean-room ledger line):

- openSavedGroup(), on its SUCCESS path only, directly
  after the P-215 mode restatement: the strategy select
  is disabled and every roster checkbox is disabled. A
  header comment in the function states the reason: the
  roster and strategy controls govern only the stateless
  room, so opening a saved group disables them - the
  group's own stored policy governs speaker choice here.
  Opening a second group while one is open re-runs the
  same success path; the controls simply stay disabled.
- closeSavedGroup(), inside its block after its null
  guard, among its existing restatements: the strategy
  select and every roster checkbox are re-enabled. The
  lifecycle is symmetric or it is a bug: P-217 disables,
  so P-217's close re-enables.
- sendPersistent(): the P-214 null guard (an early
  return on a null message) becomes a guarded render,
  and after the guarded render, still inside the try,
  the picker is refreshed - loadSavedGroups() is awaited
  and select#saved-group's value is set to openGroupId.
  The catch is unchanged.

Nothing else in group.js moves: loadRoster,
loadSavedGroups' body, createGroup, selectedIds, the
submit handler (both branches), the SSE loop,
reasoningPanel and addBubble are unchanged, and
sendPersistent keeps its banked placement.

## The lifecycle contract

- Page load (resting state): the roster boxes and the
  strategy select are ENABLED (the markup default; this
  slice adds no disabled attribute anywhere). The
  close-group control is disabled and the mode line
  reads "Stateless room" (the P-215 resting state).
- Successful open: the controls are disabled, beside
  the openGroupId set and the mode restatement - the
  mode line reads "Saved group mode" and the close
  control is enabled.
- Failed open: NO control state changes - neither the
  disable pair nor the mode line nor the close control;
  the catch only surfaces the error via showError (the
  P-213/P-214/P-215 failure fence).
- Close: the page is exactly as after a reload -
  controls live, mode line "Stateless room", close
  control disabled, stateless state reset - except
  roster and picker stay loaded (no loadRoster /
  loadSavedGroups re-run on close; P-217 adds none).
  Close still issues no request of any kind, writes no
  web storage and deletes nothing.
- Stateless send: no disable, no refresh - the
  stateless turn stores nothing and reads the live
  controls, byte-unchanged from the banked body.
- Persistent send: the controls stay disabled
  throughout (a send never re-enables; only Close
  does), and the picker count refresh below runs on
  success.

## The speaker-choice truth, restated

On an opened group, speaker choice is the group's own
stored policy and roster, applied server-side by the
banked /next road. The page's Roster checkboxes and
Strategy select govern ONLY the stateless room: the
persistent branch reads neither. Before this slice both
controls stayed live in persistent mode while being
silently ignored - visibly inert is the honest form of
that truth, so the page now disables them. Disabling is
the opposite of an override: no manual speaker pick is
founded here, and none of the picker, Open, Close or
Create controls, nor the composer input, is ever
disabled in any mode.

## The frozen-roster consequence for creation

While a group is open the roster is frozen, so a Create
click in persistent mode files the new group under the
roster as ticked at open time: selectedIds() still
matches disabled checked boxes, so the read stays sound,
but changing the roster for a creation requires Close
first. That is the refinement's own truth - in
persistent mode the roster is not a live control for
anything - stated plainly so creation in persistent
mode surprises no one. Creation itself is unchanged and
stays mode-neutral in every other respect (P-216).

## The refresh road truth

The P-213 picker labels each saved group with its stored
message_count at load. A successful /next send stores
turns server-side - the user turn always, the reply when
one is generated - so the opened group's stored count
rises by 1 (user turn only, the null-message case) or 2
(user turn plus reply) on every successful persistent
send, while before this slice the picker's label kept
the count from page load until a reload or a creation
refresh.

The refresh is a display-only re-read through the
banked road only: loadSavedGroups() re-reads GET
/api/v1/groups, the P-213 picker construction, called
unchanged. There is NO new road, no per-group GET, and
no count computed or incremented client-side - the
displayed count is always the server's stored truth,
re-read. Because loadSavedGroups() rebuilds the
options, the select's value is set to openGroupId
immediately after the awaited re-run (the P-216
createGroup precedent: refresh, then set the value), so
the picker shows the group the composer is speaking
into.

The trigger is the SUCCESS tail of sendPersistent only,
after the /next response is parsed and the reply, when
one exists, is rendered. It runs in BOTH success cases:
a rendered reply, and a null message (the user turn was
stored; the count rose by 1) - which is why the null
guard became a guarded render instead of an early
return. It NEVER runs on the failure path: a failed
/next stored nothing (the P-207/D2 contract), and the
catch keeps its showError-only shape. The refresh
touches no thread content, no stateless turn state and
no web storage. If the refresh itself fails, showError
surfaces it (the refresh is awaited inside
sendPersistent's try); the send stands and the rendered
reply stays. No other refresh point is founded: open,
close, selection change and stateless sends refresh
nothing (P-216's creation refresh and this send tail
are the only refresh points).

## Declined, with reasons

- Per-swipe thinking browsing in the Assistant View
  panel: conditional on Volmarr's word under the P-206
  stored-only ruling; no word given -
  DECLINED-PENDING-WORD, as at P-210..P-216.
- Bot runtime: no substrate (chat.write still RESERVED,
  honoured nowhere).
- D1 (the stateless groupchat road's error-swallowing):
  FENCED since P-208, restated here untouched - neither
  refinement alters any error/done handling on any
  path; the refresh adds a success tail only and
  failures still surface via showError.
- Cross-subject Inspector roll-up: declined under the
  per-subject law; stands.
- The /run multi-turn road and the raw message-append
  road from this page: declined at P-214 (one composing
  act must not be duplicated across roads); stands.
- New Inspector documents: coverage complete at P-211.
- Live rendering on stored roads: the P-206 stored-only
  position stands.
- Manual speaker pick for /next: declined; disabling
  the aside controls is the opposite of an override and
  founds none.
- Group management surfaces (rename via PATCH, member
  add/remove/settings, delete): real banked roads with
  no web consumer, none named by the trail, deletion
  destructive. Declined for P-217.
- Picker refresh at any other point (open, close,
  selection change, stateless send): declined as
  unfounded; counts change on this page only when
  stored turns are appended or a group is created.
- Disabling the picker / Open / Close / Create controls
  or the composer input, in any mode: declined; only
  Roster and Strategy are disabled, only in persistent
  mode.
- Carried items K-A / K-B / K-C: untouched.

## Fences

No migration (head stays 0042, no provisional 0043), no
new or changed road (route census stays 356 paths / 439
operations, zero census heals), no Python source change,
no markup change, no stylesheet change, no README
touched. The S311 group golden is expected UNMOVED -
group.html is untouched, so there is nothing for a
golden to move with - and it is verified unmoved. One
banked pin is healed at equal-or-greater strength with
a P-217 heal comment, named in advance in the design:
the P-214 battery's pin 8 (the null-message rule), which
pinned the early-return form this slice replaces by
design; it is restated in its true P-217 guarded-render
form (the if (m) guard precedes the render, no early
return remains, a null message renders nothing AND
reaches the refresh), and the P-217 battery's pin 7
asserts exactly that form - strength preserved, never
weakened. Escaping: no new text path is introduced;
counts and names still reach the picker only as an
<option> textContent (the existing loadSavedGroups
construction). group.js remains textContent-only - no
innerHTML anywhere.

## The honest closing note

After P-217 the group-web arc is complete: loader
(P-213), composer (P-214), toggle (P-215), creation
(P-216) and these refinements (P-217) - every act the
arc presupposes exists on the web, the mode is visible,
leavable and honest in its controls, and the picker's
counts track the stored truth after the page's own
sends. No further founding or refinement can honestly
be named from the trail: everything else standing is
word-conditional (per-swipe), fenced (D1),
substrateless (bot runtime), law-declined
(cross-subject roll-up, /run duplication, live
rendering, manual speaker pick) or a carried item
(K-A/K-B/K-C). P-218, the gate, is the road's own close.
