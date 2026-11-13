# Group Mode Toggle (P-215) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line; there is no verbatim P-215 entry, and this slice is
never presented as roadmap-verbatim. The derivation is
the banked trail: P-214's scout stated the mode model it
founded - a group open = the composer is in that group's
persistent mode; the resting page = stateless - and, in
substance verbatim, "Mode exit in this slice is page
reload. An explicit close/toggle control is NOT founded
here"; its declined list declined an explicit mode
toggle / close-group control for P-214 because no banked
record named it, and named it a possible later candidate
"founded only if a later slice's trail calls for it".
The P-214 slice doc restated "the mode-toggle candidate
named for later". P-215 is that later slice, and its
trail calls for it: once P-214 banked, the group page had
a real two-mode composer with exactly one defect of
shape - the persistent mode, once entered, could be left
only by reloading the page.

## Why this slice exists

After P-214 the composer had two modes but neither a
visible sign of which mode it was in nor any in-page way
back to the stateless room. A user who opened the wrong
saved group, or who simply wanted the stateless room
again, had to reload - losing nothing server-side, but
with no honest in-page equivalent of that exit. P-215
makes the mode VISIBLE and LEAVABLE, UI-only: no new
endpoint, no migration (head stays 0042), no server
change of any kind, route census unchanged at 356 paths
/ 439 operations, no stylesheet change.

## What was built

group.html and group.js only (plus this doc, the battery
and one clean-room ledger line):

- group.html, in the aside's Saved groups block directly
  after the Open button: a mode line,
  `<p id="group-mode" aria-live="polite">Stateless
  room</p>`, and a close control,
  `<button id="close-group" type="button" disabled>Close
  group</button>`. At load the line reads exactly
  "Stateless room" and the control is disabled. No other
  markup changes; every existing id and the script order
  are unchanged.
- group.js, in openSavedGroup: on the SUCCESS path only,
  beside P-214's openGroupId set (after the fetch and the
  render loop, never in the catch), the mode restatement:
  the mode line becomes exactly "Saved group mode" and
  the close control is enabled. A failed open changes
  neither the line nor the control state - the
  P-213/P-214 failure fence stands: the catch only
  surfaces showError.
- group.js, new closeSavedGroup(), placed directly after
  openSavedGroup and wired on DOMContentLoaded beside the
  open-group wiring: a guard `if (!openGroupId) return;`
  (the disabled control is the primary fence; the guard
  is belt-and-braces), then openGroupId = null,
  #group-thread cleared, history = [], rrCursor = 0, the
  mode line restored to exactly "Stateless room" and the
  close control disabled again. Nothing else: the
  function issues no fetch or POST of any kind through
  any helper, writes no web storage, and calls no load
  road - roster and picker stay loaded.

## The reload-equivalence contract

Close is the in-page equivalent of P-214's reload exit,
minus the re-fetch. What a reload does is the contract:
openGroupId returns to null, history returns to [],
rrCursor to 0, the thread empties, and the page rests in
the stateless room. A close control that only nulled
openGroupId would silently keep the pre-open stateless
history alive under an emptied thread - the page would
send context the user can no longer see. Close therefore
resets the stateless state in full: after a close, the
next submit is a stateless turn starting from an empty
history, exactly as after a reload, except that the
roster and the picker stay loaded (no loadRoster /
loadSavedGroups re-run on close). That reset lives only
inside closeSavedGroup's own block - never in the loader,
the submit handler or sendPersistent - so the banked
loader and submit pins stay literally true of their own
blocks.

## The no-delete truth

Close is a view/mode act only. It deletes NOTHING:
no delete road is called and none is founded by this
slice. The stored group and its stored transcript are
untouched by closing and can be re-opened at once; the
picker still lists the group with its stored message
count, and opening it again re-renders the same stored
transcript through the banked P-213 loader.

## Picker discipline

Changing the #saved-group selection alone NEVER switches
mode - only Open enters a mode and only Close (or a
reload) leaves it. Opening a second saved group while one
is open keeps working exactly as P-213/P-214 define it:
the thread is replaced, openGroupId is re-set, and the
mode line and the close control simply stay in their
persistent state.

## Declined, with reasons

- Delete / clear of the stored transcript on close:
  close is view/mode state only; no delete road is
  called and none is founded. Declined.
- The /run multi-turn road and the raw message-append
  road from this page: declined at P-214 (one composing
  act must not be duplicated across three roads; /next
  is the wired road). Stands.
- Per-swipe thinking browsing in the Assistant View
  panel: conditional on Volmarr's word under the P-206
  ruling - DECLINED-PENDING-WORD.
- Bot runtime: no substrate (chat.write still RESERVED,
  honoured nowhere; re-verified at this base).
- Cross-subject Inspector roll-up: declined at P-211
  under the per-subject law; stands.
- New Inspector documents: coverage complete at P-211.
- Live rendering on stored roads: the P-206 stored-only
  position stands; the toggle renders nothing.
- D1 (the stateless groupchat road's error-swallowing):
  FENCED since P-208, restated at every banking since.
  Not taken; the toggle touches no error/done handling
  on the stateless stream or any other path.
- Carried items K-A / K-B / K-C: untouched.

## Fences

No migration (head stays 0042, no provisional 0043), no
new or changed road (route census stays 356 paths / 439
operations, zero census heals), no Python source change,
no stylesheet change, no README touched. The S311 group
golden moves BY DESIGN (the two new elements), healed
only via RUNMAL_UPDATE_GOLDENS on the group golden
alone, every other golden verified byte-unmoved. One
banked pin is healed at equal-or-greater strength with a
P-215 heal comment: P-214 battery pin 14 (exact control
census), restated in its true P-215 form. The P-213
loader-fence pin is likewise restated over the loader
block proper, at equal strength, because closeSavedGroup
is a new segment after the loader which by design resets
the stateless state on close.
