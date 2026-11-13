# Group Transcript Loader (P-213) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line; there is no verbatim P-213 entry, and this slice is
never presented as roadmap-verbatim. The derivation is
the banked trail: P-212's design named the persistent-
group transcript loader, in so many words, "the standing
next group-web candidate", and P-212's slice doc restated
it as a declined founding - "founding a persistent-group
transcript loader for the group page (a founding UI
surface, named the standing next group-web candidate)".
P-213 is that founding.

## Why this slice exists

The group page spoke only the stateless road. It had no
group picker, no transcript fetch and no re-render path:
a person whose group conversation had been stored on the
persistent road (the deepening road, the groupchat store)
could never see that transcript again in the web surface,
even though the banked API already served everything
needed - GET /api/v1/groups lists the owner's groups in
the describe shape (id, name, chat_id, members,
member_count, message_count) and
GET /api/v1/groups/{group_id}/messages serves the stored
transcript as message dicts whose reasoning field is the
stored active reasoning view. The Inspector censuses
(P-210, P-211) already point at that transcript road as
their raw_road; the group page itself never called it.
P-213 closes that gap with a loader on the group page -
UI-only, in the exact P-206/P-212 shape: no new endpoint,
no migration (head stays 0042), no server change of any
kind, route census unchanged at 356 paths / 439
operations.

## What was built

group.html gains one block in the aside, above the Roster
heading: a "Saved groups" heading, a label wrapping
<select id="saved-group">, and
<button id="open-group" type="button">Open</button>.
No other markup changes; the script tags are unchanged
(renderer.js already loads before group.js since P-212,
so the banked reasoningView view-model is already on the
page, called unchanged, never edited). The picker uses
the aside's existing label/select styling, as the
strategy select already does; no stylesheet changes.

group.js gains two functions and one wiring block,
nothing else:

- loadSavedGroups() fetches the list road through the
  existing api() helper and appends one <option> per
  group (value = the group id, textContent = the name
  plus the message count in parentheses). An empty list
  leaves the picker empty and the page otherwise exactly
  as before.
- openSavedGroup() reads the selected id, fetches the
  transcript road, and - on success only - clears
  #group-thread and renders one bubble per stored
  message in served order through the existing addBubble:
  author = the stored speaker_name, body = the stored
  content. Stored user rows carry speaker_name null in
  the banked shape; those render under the page's own
  "user" author label, exactly as the live path authors
  the user's bubble. When a message's stored reasoning
  view is present, the group-local reasoningPanel is
  built from window.RunmalRenderer.reasoningView over
  that view - the same pair the P-212 stream path uses,
  no second view model, no second panel builder -
  and appended under the bubble: recorded thinking as a
  collapsed <details> with the text as textContent; any
  other status as its one honest status line; nothing
  fabricated.
- Wiring: on DOMContentLoaded beside the banked
  loadRoster call, the picker populates and the Open
  button's click calls openSavedGroup.

## The display-only fence (the slice's centre)

The loader is a reader, never a composer. Fetched
messages are never copied into the stateless history
state, nothing is appended to sentHistory, the loader
issues no POST, and nothing is written to local or
session storage. Opening a saved group therefore never
changes what the composer sends: a stateless turn started
afterwards carries only its own history, exactly as
banked. The composer is NOT wired to the opened group -
sending into a stored group from this page (persistent-
group composer wiring) is a larger founding that no
banked record names; it is declined here and named below
as a separate later candidate. This shared-thread
behaviour is stated plainly so no reader mistakes the
loader for a persistent composer: after a transcript is
opened, starting a stateless turn behaves as it does
today - the submit handler renders its own bubbles into
the same thread.

## Failure behaviour

A failed fetch - including the banked 404 "group not
found" for an unowned or unknown group - surfaces via
the existing showError banner, and the previously visible
thread is left in place: the thread clear happens only
after a successful fetch returns.

## Stored-only position

The loader renders STORED records only - the P-206
stored-only shape applied to the group surface. The
P-212 transient stream rendering is untouched in shape
and behaviour; no live rendering is added on any stored
road, and the P-206 position stands.

## Declined, with reasons

- Persistent-group composer wiring (sending into a
  stored group from this page): a larger founding; no
  banked record names it. Named here as a separate later
  candidate, not folded in.
- Per-swipe thinking browsing in the Assistant View
  panel: conditional on Volmarr's word under the P-206
  ruling - DECLINED-PENDING-WORD.
- Bot runtime: no substrate (chat.write still RESERVED,
  honoured nowhere; re-verified at this base).
- Cross-subject Inspector roll-up: declined at P-211
  under the per-subject law; stands.
- New Inspector documents: coverage complete at P-211.
- Live rendering on stored roads: the P-206 stored-only
  position stands.
- D1 (the stateless groupchat road's error-swallowing):
  FENCED, awaiting a keeper / Volmarr ruling. Not taken;
  no pin in this slice's battery blesses it.
- Carried items K-A / K-B / K-C: untouched.

## Fences

No migration (head stays 0042, no provisional 0043), no
new or changed road (route census stays 356 paths / 439
operations, zero census heals), no Python source change,
no README touched. The one consequential fixture update
is the S311 group golden: the picker markup moves the
group page's golden, healed only via the fixture's own
prescribed RUNMAL_UPDATE_GOLDENS road, group page only,
every other golden verified byte-unmoved (the P-212
precedent).
