# Assistant View - Group Surface (P-212) - 2026-11-10

Part XIII (Assistant View, Inspector & Bots, P-203..P-218),
DERIVED slice. Scope is DERIVED per the opener precedent:
the governing roadmap gives Part XIII only its part-table
line and names the Assistant view, in its Voxta mirror
census, as GPT-style, reasoning models with VISIBLE
THINKING. There is no verbatim P-212 entry, and this slice
is never presented as roadmap-verbatim. The derivation is
the banked trail: P-208 forwarded group reasoning and
declined, in so many words, to render it ("a later
Assistant-View-side slice may render it"), and P-211
named group Assistant-View rendering the standing next
Assistant-View candidate.

## Why this slice exists

P-208 wired groupchat reasoning on both roads. On the
persistent road the record lands in the groupchat store
and the transcript API serves it; on the stateless road -
the road the group web page actually speaks - each
speaker's reasoning is forwarded live as SSE events and
stored nowhere. The group page received those events and
silently discarded them: group.js branched on typing,
token, message and turn_end only, and group.html did not
even load renderer.js, so the banked P-206 reasoningView
view-model was not available on the page. A person in a
group chat never saw that a reply had thinking, nor
honestly learned that none was returned. P-212 is that
render - UI-only, in the exact P-206 shape: no new
endpoint, no migration (head stays 0042), no server
change of any kind.

## The premise correction (binding on this build)

P-211's scout said recorded group thinking is never
rendered in the group web surface even though the
transcript API serves it. Both halves are true, but the
loose reading - that group.js could render THAT data with
a panel addition - is false, and the P-212 scout (the
P-204 lesson, applied) corrected it plainly: group.js
never calls the persistent transcript road. No web file
loads a persistent group transcript at all - there is no
group picker, transcript fetch or re-render path in any
web file. The only reasoning data that reaches the group
page is the transient stateless event. P-212 therefore
renders the stream the page actually receives; it does
NOT load, fetch or render the persistent transcript, and
founding that loader is declined below as a founding UI
surface with its own commission, not a panel wiring.

## What lands

1. `src/runmal/web/templates/group.html` - ONE script
   line: renderer.js loaded BEFORE group.js (theme.js
   stays first, palette.js stays last). No other markup
   moves; no new element is added - the panel lives
   inside the author's existing .gmsg bubble. With it,
   window.RunmalRenderer.reasoningView - the banked
   P-206 view-model, CALLED unchanged, never edited - is
   the one source of truth for status semantics on the
   group page.
2. `src/runmal/web/static/group.js` - the wiring, fenced
   to the submit handler plus ONE new local function:
   - `reasoningPanel(view)` - a group-local panel builder
     mirroring app.js's banked construction exactly (it
     is local to app.js, which the group page does not
     and must not load, so only the DOM assembly is
     mirrored; the status semantics stay in the shared
     view-model): a null view returns null; a recorded
     view gives a native <details class="reasoning">
     disclosure, COLLAPSED by default, with a <summary>
     carrying the label and the thinking text in a child
     div set via textContent ONLY - never innerHTML,
     never the markdown renderer; any other view gives
     one <div class="reasoning-status"> status line, also
     via textContent.
   - A per-turn collector inside the submit handler,
     beside the banked bubbles / typing dicts:
     `reasoningByAuthor` (author -> array of text parts),
     declared inside the handler so it resets every turn
     exactly as bubbles and typing do. Nothing
     module-level is added.
   - ONE new SSE branch beside the token branch: a
     reasoning event pushes its text, in arrival order,
     onto its author's list. It renders NOTHING, creates
     NO bubble, and touches neither history nor the token
     path.
   - The completion render in the message branch, after
     the banked history.push: the input view is built
     exactly in the P-205 active-view shape reasoningView
     already consumes - collected parts non-empty gives
     {status: recorded, text: parts joined verbatim in
     arrival order}; no parts collected gives
     {status: not_present} - passed through
     window.RunmalRenderer.reasoningView, and the panel
     appended to the author's .gmsg container (the parent
     element of the body element addBubble returned and
     the bubbles dict holds). When no bubble exists (a
     speaker who produced no tokens has no bubble under
     banked S305 behaviour), NO bubble is founded and NO
     panel is rendered - that visible behaviour does not
     move. The user bubble never carries a panel.
3. No style.css change: the banked .reasoning /
   .reasoning-text / .reasoning-status classes already
   live in the shared stylesheet group.html loads.
   One consequential fixture update rides with item 1:
   the S311 golden structural fixture for the group page
   (tests/fixtures/ui/group.golden.txt) is regenerated
   deliberately, by its own prescribed road
   (RUNMAL_UPDATE_GOLDENS=1), for exactly the one added
   script line - the diff is the single line
   script:/static/renderer.js and no other golden moves.
   The signature now pins renderer.js's presence on the
   group page at the same strength it pinned its absence.
4. `tests/test_p212_group_assistant_view.py` - the
   battery (14 tests): page wiring and load order, the
   shared model read under node, source-segment pins for
   the collect-only branch, the per-turn collector scope,
   completion-only rendering, both view constructions,
   panel DOM safety, placement and the untouched user
   bubble, the history law and request-body keys, the
   unmoved stateless stream surface, storage honesty
   beside the untouched persistent road, and the census
   and migration fences.

## The honesty position on transient thinking

- Transient by design: the panel lives only in the
  page's DOM for the turn that produced it. Reasoning
  text is NEVER written into history (entries stay
  exactly {author, content}), NEVER sent back to the
  server in any request, NEVER persisted client-side
  (no localStorage, no module-level store). Reloading
  the group page shows no thinking, exactly as the
  stateless road's contract has always been. This panel
  is not a stored record and no copy claims it is one.
- The not_present line is honest on this road: the
  banked stateless loop forwards EVERY reasoning dict
  the generation service emits for a speaker, in arrival
  order (total forwarding, banked at P-208). A completed
  message whose author collected zero parts is a
  production that returned no thinking - "No thinking
  was returned for this reply" - witnessed live by the
  client that renders it.
- Only two statuses are ever constructed in group.js:
  recorded and not_present. not_recorded and unknown are
  STORAGE states, and this surface stores nothing, so
  claiming either would be a falsehood. Malformed shapes
  still land on the view-model's unknown line by its own
  banked tolerance; group.js adds no second tolerance
  layer.
- The stored-only fence is honoured, not extended:
  nothing in the chat surface changes. app.js
  streamGeneration keeps collecting for storage only and
  its panels keep rendering the STORED record at thread
  read, under the P-206 / P-209 keeper ruling. P-212's
  live render is lawful precisely where P-208 left it: a
  stream that stores nothing, with no re-read for a live
  panel to contradict.
- D1 stays FENCED, untouched: group.js gains NO error or
  done handling, the message branch's banked behaviour
  is otherwise unchanged, and a failed generation's
  visible behaviour is exactly today's, panel or not. No
  battery pin asserts anything about an errored stream's
  panel.

## Carried limitations (stated, not hidden)

- Transient thinking: a group panel cannot be re-read.
  Reload the page, or come back tomorrow, and the
  thinking is gone - the stateless road stores nothing
  and P-212 stores nothing either. The persistent
  transcript keeps its stored records exactly as before,
  readable through its API and censused by P-211, but
  this page does not show them (see the declined loader
  below).
- One completion per author per turn: the collector's
  correctness rests on the banked speakers_for contract
  (each speaker speaks once per turn, pinned by S305).
  If a future strategy ever let one author speak twice
  in a turn, their parts would combine into the second
  message's panel - no such strategy exists in-tree
  today.
- Empty replies render no panel: a speaker whose
  generation produced no tokens has no bubble under
  banked S305 behaviour, so there is nothing to hang a
  panel on; P-212 does not found bubbles. This is
  adjacent to D1's territory and is one more reason D1
  stays fenced rather than quietly absorbed here.
- The not_present line is a live-witness claim: it is
  exactly as strong as the banked total-forwarding
  contract. A future backend that emitted reasoning
  after its message event (none does - the service
  interleaves reasoning before completion) would need
  that contract revisited, not a client workaround.

## Deliberately not built (named, not gaps)

- Persistent-transcript rendering / a persistent-group
  loader for the group page: DECLINED for P-212 - no
  group picker, transcript fetch or re-render path
  exists in any web file; founding one is a founding UI
  surface with its own commission, not the panel wiring
  P-211 named. Named as the standing next group-web
  candidate.
- Per-swipe thinking browsing (web UI): DECLINED-
  PENDING-WORD under the P-206 ruling (it takes
  Volmarr's word, not given). The banked raw roads
  already serve every swipe's record meanwhile.
- Bot runtime: DECLINED - no substrate in-tree (no bots
  package; chat.write RESERVED, honoured nowhere). A
  founding needing its own commission, not a join.
- D1, stateless groupchat error-swallowing: FENCED,
  untouched, awaiting a keeper / Volmarr ruling - no
  panel logic alters error / done handling and no
  battery pin blesses D1.
- Live rendering on the chat /generate road and any
  change to app.js: DECLINED - the P-206 / P-209
  stored-only keeper ruling stands exactly as banked.
- Any write, persistence or editable reasoning surface
  on the group page: DECLINED - the Assistant View
  renders; it does not store or edit.
- Carried items K-A (binding label update), K-B
  (event-log retention / bulk clear, Volmarr's ruling),
  K-C (unified-search history) and the P-207
  carry-overs: untouched, standing as banked.

## Migration and census note

NONE - stated plainly. No migration is taken (head stays
0042, no provisional 0043); the slice is UI-only over a
banked SSE contract and a banked view-model and persists
nothing on either side of the wire. No road is created,
moved or removed: the app route census stays 356 paths /
439 operations, every banked census pin stands as written,
and zero census pins are healed by this slice - the first
Part XIII slice since P-209 of which that is true.
renderer.js, app.js, style.css, every server file and
every groupchat file are untouched; reasoningView is
CALLED, never edited. README.md is never touched.
