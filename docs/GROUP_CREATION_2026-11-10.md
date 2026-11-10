# Group Creation (P-216) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line; there is no verbatim P-216 entry, and this slice is
never presented as roadmap-verbatim. The derivation is
the banked trail: P-213 founded the saved-groups picker
and the display-only transcript loader, P-214 wired the
persistent composer, and P-215 made the composer mode
visible and leavable - three slices that all presuppose
a saved group, while no web surface anywhere could
CREATE one. The banked creation road, POST
/api/v1/groups, had no web consumer at all: the picker
P-213 founded starts empty for a web-only user and could
never become non-empty from the web. P-216 founds that
one missing act, UI-only, on the banked road.

## Why this slice exists

After P-215 the group page could open, compose into and
close a saved group, but groups came only from raw API
calls. A web user could never bring a saved group into
existence, so the whole P-213..P-215 arc was unusable
end-to-end from the browser. P-216 completes the
group-web arc - P-213 loader -> P-214 composer -> P-215
toggle -> P-216 creation - UI-only: no new endpoint, no
migration (head stays 0042), no server change of any
kind, route census unchanged at 356 paths / 439
operations, no stylesheet change.

## What was built

group.html and group.js only (plus this doc, the battery
and one clean-room ledger line):

- group.html, in the aside's Saved groups block directly
  after the P-215 group-mode line: a labelled text input,
  `<input id="new-group-name" type="text"
  aria-label="New group name">` inside a "New group"
  label, and a create control,
  `<button id="create-group" type="button">Create
  group</button>`. No other markup change; every existing
  id and the script order are unchanged (renderer.js
  still loads before group.js).
- group.js, new createGroup(), placed directly after
  selectedIds() and before sendPersistent (the P-216
  design's segment-placement contingency: placed first
  after loadSavedGroups per the design's section 2, it
  fell inside the banked loader segments whose no-POST
  pins are pinned over spans that include that position,
  so it was moved within group.js - function declarations
  hoist, placement is free - and every banked segment pin
  then held literally of its own block; no pin was healed
  for placement). It is wired on DOMContentLoaded beside
  the open-group and close-group wiring.
- createGroup() reads the trimmed value of
  input#new-group-name as the name and selectedIds() -
  the roster boxes ticked at click time, in page order -
  as member_character_ids, and POSTs through the
  existing api() helper to /api/v1/groups with
  {name, member_character_ids}. On success ONLY, in
  order: the name input is cleared, loadSavedGroups()
  re-runs (the picker is rebuilt from the banked list
  road), and select#saved-group's value is set to the
  returned group's id. On failure the catch surfaces the
  error via the existing showError banner and nothing
  else happens.

## The members truth

Creation from this page honestly means "a group of the
currently ticked roster": the members are exactly the
checked .roster-check boxes at click time, read through
the page's existing selectedIds() helper - the same
selection the stateless room speaks with. No second
member picker is founded. The selection may be empty: a
memberless group is a road-legal shape (the banked road
defaults member_character_ids to []), and the page
invents no minimum the road does not have.

## The empty-name fence

A trimmed-empty name creates NOTHING: no POST is issued
and showError is called ("Give the new group a name
first."). The banked road would accept an empty name
(its default is ""), but the page's contract is stricter
and honest: the P-213 picker labels groups by name plus
message count, so a nameless group would render as a
blank label. Creation therefore requires the one thing
only the user can supply - a name.

## Selected, never opened

Creation NEVER opens the group it creates: createGroup
contains no openSavedGroup call, no openGroupId
assignment and no transcript fetch. The new group is
selected in the picker and nothing more. Mode entry
remains Open's act alone and mode exit Close/reload
(the P-215 picker discipline, restated): changing the
#saved-group selection alone never switches mode, and
creating a group does not either. Creation is
mode-neutral - it may be used with no group open or with
a group open; in neither case does it alter openGroupId,
the stateless history, sentHistory, rrCursor, storage or
the visible thread. It touches nothing but the name
input and the picker.

## The failure contract

The failure contract is inherited from the banked road
and surfaced whole: an unknown member id answers 422
and NOTHING is half-created (the S210 contract - the
list road still reads as it did), and any failure (422,
network) reaches the page's catch, which surfaces it via
the existing showError banner. On failure the name
input, the picker, the thread and every composer/mode
state are left exactly as they were - there is no picker
rebuild on failure. No error is silently swallowed (the
anti-D1 discipline the loader already follows).

## Declined, with reasons

- Group management surfaces (rename via PATCH /groups,
  member add/remove/settings, delete): real banked roads
  with no web consumer, like creation was - but each is a
  founding of its own size, none is named by the trail,
  and deletion is destructive. Creation is the one
  management act the P-213..P-215 arc presupposes.
  Declined for P-216; named honestly as un-named
  territory, not as a queued candidate.
- Manual speaker pick for /next (NextIn's
  manual_speaker_id): the substrate exists, but no banked
  record names it, and P-214 has just established in its
  slice doc that the group's own stored policy governs
  speaker choice on this page; a per-send override
  control would cut against that freshly banked truth.
  Declined.
- The /run multi-turn road and the raw message-append
  road (POST /groups/{id}/messages) from this page:
  declined at P-214 (one composing act must not be
  duplicated across roads; /next is the wired road).
  Stands.
- Per-swipe thinking browsing in the Assistant View
  panel: conditional on Volmarr's word under the P-206
  ruling - DECLINED-PENDING-WORD.
- Bot runtime: no substrate (chat.write still RESERVED,
  honoured nowhere; re-verified at this base).
- Cross-subject Inspector roll-up: declined at P-211
  under the per-subject law; stands.
- New Inspector documents: coverage complete at P-211.
- Live rendering on stored roads: the P-206 stored-only
  position stands; creation renders nothing.
- D1 (the stateless groupchat road's error-swallowing):
  FENCED since P-208, restated at every banking since.
  Not taken; creation touches no error/done handling on
  the stream path or any other path.
- Carried items K-A / K-B / K-C: untouched.

## The honest remainder (named for P-217, not founded here)

After creation banks, the group-web arc (loader,
composer, toggle, creation) is founding-complete. The
only further items this slice can honestly name are
REFINEMENTS of the just-banked surface, each small and
none yet named by any banked record: (a) disabling the
Roster checkboxes and the Strategy select while
persistent mode is open (P-214's speaker-choice truth is
currently carried by that slice's prose and P-215's mode
line only); (b) refreshing the picker's message_count
labels after a persistent send (P-214's /next stores
turns server-side; the in-page label goes stale until
reload or a creation refresh). Either could honestly
fill P-217; anything larger would be invention, and the
P-218 gate - not a new founding - is the road's own
close.

## Fences

No migration (head stays 0042, no provisional 0043), no
new or changed road (route census stays 356 paths / 439
operations, zero census heals), no Python source change,
no stylesheet change, no README touched. The S311 group
golden moves BY DESIGN (the two new elements), healed
only via RUNMAL_UPDATE_GOLDENS on the group golden
alone, every other golden verified byte-unmoved. Two
banked pins are healed at equal-or-greater strength with
P-216 heal comments: the P-214 and P-215 batteries' pin
14 exact control censuses, restated in their true P-216
form (every prior id PLUS new-group-name and
create-group, no other ids) - the P-216 battery pin 14
asserts that same exact census. Escaping: the name
travels as a JSON string in the POST body and returns
into the picker only as an <option> textContent (the
existing loadSavedGroups construction) - no innerHTML
path is introduced anywhere; group.js remains
textContent-only.
