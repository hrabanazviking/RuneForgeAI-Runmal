# P-168 - Part X Gate (2026-11-08)

*The Part X gate. The filed roadmap gives Part X only
its part line - "X | Faces That Speak | P-155 - P-168"
- and no per-slice entries; every Part X slice scope is
DERIVED, as each slice doc states plainly. This gate
therefore judges Part X against the census its own
banked slice docs declare: the face presentation, the
character roster, the speaking face, the selection
history, the speaking roster, the face-chats board,
the speaking history, the character history board, the
character speaking-history board, the face census, the
face history census, the character speaking-chats
board, the face speaking census, and this gate. Judged
only from Part X's banked records, the battery module,
and the tester's logs filed with this slice; no mirror
source consulted (clean-room).*

*P-167 shape, stated honestly.* P-167 (Face Speaking
Census, team-02 commit c18d1e38) banks in parallel with
this gate and is NOT in this gate's base by design. Its
surface is measured here by overlay: the battery loads
its committed module read-only from the team-02
worktree (the P-116 / P-154 precedent) and reconciles
it against the in-base P-164 census and P-166 board,
and its HTTP road is asserted ABSENT on this base. The
gate doc therefore names BOTH shapes: this base
(P-001..P-166 banked, P-167 absent - the base shape:
the speaking-census road absent) and the merged tree
after P-167 banks (the overlay shape: the
speaking-census road present and passing - P-167's
additive union: two new modules, one additive road,
additive __init__ exports, disjoint hunk ground from
this gate's files). The base shape is pinned honestly
in the battery; the keeper heals that one pin to the
merged truth at banking if needed, at equal strength.
The expected merged-tree gate outcome is stated in S6.

## Gate verdict

**Part X is COMPLETE and the gate PASSES with named
carried items and two findings.** This record claims
only what the battery proves.

Verdict per area: Census PASS, Together PASS, Custody
PASS, Accounting PASS.

Verdict per row:

| Row | Slice | Verdict |
|---|---|---|
| Face presentation foundation | P-155 | PASS |
| Character face roster | P-156 | PASS |
| Speaking face | P-157 | PASS |
| Face selection history | P-158 | PASS |
| Speaking roster | P-159 | PASS |
| Character face chats | P-160 | PASS |
| Speaking history | P-161 | PASS |
| Character face history | P-162 | PASS |
| Character speaking history | P-163 | PASS |
| Face census | P-164 | PASS |
| Face history census | P-165 | PASS |
| Character speaking chats | P-166 | PASS |
| Face speaking census (overlay) | P-167 | PASS |
| Part X gate | P-168 | this gate |

## S1 The gate checklist

| Gate requirement (task census) | Evidence | State |
|---|---|---|
| Presentation + roster + speaking face | battery A + B | DONE HERE |
| History + speaking history | battery A + B + C | DONE HERE |
| Chats board + speaking-chats board | battery A + B | DONE HERE |
| Character history + speaking-history boards | battery A + B | DONE HERE |
| Face census + history census | battery A + B + C | DONE HERE |
| Speaking census P-167 (overlay) | battery A + B + C | DONE HERE |
| Custody: no voice in silent documents | battery C | DONE HERE |
| Honesty: current_only wherever history rides | battery C | DONE HERE |
| Accounting: carried items pinned, not loosened | battery D | DONE HERE |
| Measured counts at the gate | S6 of this record, from the tester's logs | DONE HERE |

Part X spans P-155..P-168, fourteen slices continuous:
P-155 through P-168, no gaps. Per-slice coverage map:
P-155->A/B/C, P-156->A/B, P-157->A/B/C/D, P-158->A/B/C/D,
P-159->A/B/D, P-160->A/B, P-161->A/B/C/D, P-162->A/B/C,
P-163->A/B/C/D, P-164->A/B/C, P-165->A/B/C/D,
P-166->A/B/C/D, P-167->A/B/C/D, P-168->this gate.
No roadmap text was edited.

## S2 "Passes" means, per verdict area

- **Census PASS.** Every P-155..P-166 faces module,
  resolver function, schema name and HTTP road the
  slice docs declare is present: the twelve pure-read
  services and their twelve roads on the /api/v1
  mount, every schema name accounted once (thirteen
  with the overlay's, each exactly once in its own
  tree), the faces __init__ module map naming them,
  the slice docs for P-155..P-166 all in docs/, and app
  OpenAPI generation succeeds and names the faces
  roads. P-167's module is measured by overlay from
  its committed tree (see the P-167 shape note above)
  and its road is honestly absent here: 12 roads on
  this base, 13 roads after P-167 banks.
- **Together PASS.** One composed world walks the
  whole part over the same characters and chats: the
  face a ready chat shows is the same descriptor in
  the presentation, the speaking document, the
  face-chats board row, the speaking-chats board and
  the census row, and history judges that same
  selection still_ready with the same descriptor; the
  roster's entries are the presentation's entries and
  the speaking roster composes the roster whole; the
  census counts sum to the boards they compose (the
  P-164 counts are the two P-160 boards' own
  arithmetic added); the history documents reconcile
  (the per-chat history rides whole inside the
  character board, the speaking history and the
  speaking-history board, and the history census sums
  the boards' arithmetic); one character's voice is
  the same resolution in every pairing that states it
  (P-157 / P-159 / P-161 / P-163 / P-166), a second
  character's default voice stays distinct, and the
  P-167 overlay census reconciles with P-164's census
  row for row - same rows, same counts - plus each
  row's own voice, equal to that character's P-166
  board voice.
- **Custody PASS.** The laws hold as shipped: no
  voice key in any silent document (the presentation,
  roster, history, chats board, character-history
  board, face census and history census carry no
  voice, no paired and no voice_scope key anywhere);
  wherever history is involved the voice is
  current_only (P-161 / P-163 state voice_scope:
  current_only on every document, and no kept event
  or chat row carries any voice field, so no past
  face is ever claimed spoken in today's voice);
  the P-167 overlay keeps voice inside character rows
  only - no census-level voice, no paired, no
  voice_scope and no face at envelope level, and no
  chat row carries a voice field (the blur pin); no
  document carries image bytes anywhere - a ready
  face's descriptor carries the P-023 content and
  thumbnail URLs as data only, and an unbound entry's
  URLs are None; message text never selects a face
  (a chat whose messages name expressions stays
  no_selection with an empty history - P-092's law);
  no document carries audio, waveform, lip-sync or
  animation keys (no playback - P-027); and every
  resolve is a pure read (the P-092 store
  byte-identical and the voice row untouched after
  every document, the overlay included, is resolved).
- **Accounting PASS.** Every carried item named in S4
  is pinned by a battery measurement at this gate, at
  full strength: the owner speaking-history census is
  absent on both shapes - no module and no road in
  this base or in P-167's committed tree - so Part X
  closes with that one cell unmade, as P-167's own doc
  names it; the faces package is exactly its twelve
  services and twelve router files with no renderer,
  stage, animation, lip-sync or playback module
  anywhere (data only, by design); the P-109 affect
  rides consumed:False in every voice-bearing
  document (eight voices measured, overlay rows
  included); the kept window is the P-092 per-chat
  law stated as data (kept_limit 100, never summed
  into an owner window, the history notes naming the
  window never as a complete record); and the paired
  flags follow their law (an unready or unselected
  face never pairs, while the voice half is still
  stated honestly). Nothing was loosened to make an
  area pass.

## S3 The gate world

The battery's world is ZqxGate168, fresh-authored for
this gate (P-005 discipline, no real user files): one
owner, two characters (Asta, with a three-entry set -
neutral unbound, amused bound to a sprite, wrong bound
to a wrong-kind asset - a declared default, and a
stored voice profile carrying the whispering affect;
Bera, with a one-entry bound set and no voice profile),
and four chats (Asta ready, Asta unbound, Asta quiet
with no selection, Bera ready), every selection a
P-092 explicit act. Every Part X surface is then read
against that one world, so agreement between surfaces
is the proof, not any single surface's word. The
P-167 overlay world is the same world judged by the
overlay module against the in-base P-164 census and
P-166 boards.

## S4 Carried items - named and deliberate

The gate passes with these items carried, not hidden.
Each is exact in the battery module or the banked
slices' own records; this section names them so no
later part mistakes them for clean ground.

- **K1 - The owner speaking-history census stays OPEN
  - the one unmade cell.** P-164 named the owner
  speaking cells open under the blur objection (voice
  is per character under S512); P-167 answered the
  objection by construction for the CURRENT speaking
  census (voice inside character rows only) and
  expressly declined the owner speaking-HISTORY census
  (the grid takes current speaking before history
  speaking in every row, and the current_only hazard
  rides at owner scale there). The battery pins its
  absence on both shapes: no module and no road exist
  in this base or in P-167's tree. Part X closes with
  that one owner speaking cell unmade, and this gate
  does NOT take it. Commissioned road: a future slice
  under the per-row discipline P-167 proved, if a
  consumer ever needs it.
- **K2 - No renderer, stage or lip-sync exists
  anywhere in Part X - data only, by design.** Every
  Part X document is presentation data a client
  renders; Runmal renders, animates and synthesizes
  nothing, no timing, viseme or animation contract
  exists in-tree, and the faces package contains no
  renderer, stage, animation, lip-sync or playback
  module (battery D pins the package's exact file
  census). Commissioned road: none - a stage would be
  its own part with its own timing contract, not a
  gate item.
- **K3 - The P-109 affect is consumed:False
  everywhere.** Every voice-bearing Part X document
  carries the affect as data with consumed False -
  the speaking face, roster, history and boards, the
  speaking-chats boards and the overlay census rows
  (eight voices measured at this gate). No Part X
  surface consumes the affect; it is named, never
  acted on. Commissioned road: none - consumption
  belongs to a voice-performance surface, which Part
  X is not.
- **K4 - The kept window is per chat and the record
  is never complete.** Face history is P-092's kept
  window (kept_limit 100 per chat): events older than
  the window per chat are gone by that law, the
  history documents state the limit as data and never
  claim a complete record, the history census states
  the limit once and never sums it into an owner
  window, and a cleared-only history counts as
  history (the slices' own pinned law). Commissioned
  road: none - the bound, not a gap.
- **K5 - There is no owner-wide face and no single
  current face per character.** Selection stays per
  chat and always an explicit act (P-092): the roster
  names no current face, the boards and censuses name
  faces only per chat row, and no document invents an
  owner or character face above the chat rows.
  Commissioned road: none - the law, not a gap.
- **K6 - No voice history exists anywhere.** S512
  stores no voice history - no versioned rows, no
  change log, no per-event voice record - so wherever
  history is involved the voice half is today's
  resolution only under voice_scope: current_only
  (P-161 / P-163), and no kept event is ever claimed
  to have been spoken in today's voice. A voice-history
  store would be a write-side capture law, a campaign
  decision, not a pure read's to invent. Commissioned
  road: a voice-history slice only if a capture law
  is ever commissioned.
- **K7 - Scenario VN stage integration stays open.**
  No in-tree record joins scenario cast role names to
  characters or faces (named open by the Part X
  slices' own candidate lists); Part IX's cast and
  Part X's faces remain unjoined. Commissioned road:
  a joining slice only if a record ever names the
  join.
- **K8 - Generated expression sprites via P-087 stay
  open.** Generation is a landing-contract change on
  the P-087 line, not a faces read; Part X reads the
  assets P-023 already landed and names their roads
  as data. Commissioned road: the P-087 line, if it
  ever takes sprite landing.

Also carried from the slices' own records, without
separate rows: the character roster census and the
merged owner-wide streams P-164 / P-165 / P-167 each
declined (an owner roster census duplicates P-156 /
P-159 ground; a merged stream invents an ordering no
owner recorded), and each slice's honest limitations
as recorded in its own banking entry (the presentation
renders nothing, the boards are current only where
they say so, and the fallbacks are named as data,
never substituted).

## S5 Findings for the keeper

- **F1 - No new engine defect was found by this gate.**
  Every Part X surface produced exactly its promised
  result in the battery. The gate's only correction
  during construction was its own probe error (the
  OpenAPI document is served at /openapi.json, not
  under the /api/v1 mount - the probe was corrected
  to the banked app's actual shape, as the P-154
  battery probes it; no engine code was touched).
  Nothing was left unfixed in this slice's own files,
  and no banked code was patched by this gate.
  Commissioned road: none required.
- **F2 - P-167 banks in parallel; its shape is named,
  not assumed.** On this base its module is measured
  by overlay only and its road is asserted absent; the
  merged tree after it banks is the additive union the
  P-167 record and this gate's S6 name (two new
  modules, one additive road, additive __init__
  exports). The keeper confirms it at banking: forge
  confirmation 5273 (5254 + 19, exact) and the gate
  battery run on the merged tree, healing the one
  base-shape pin (the speaking-census absence
  assertions) to the merged truth if needed, at equal
  strength. Commissioned road: the keeper's banking
  reconciliation, already the standing pattern.

## S6 Evidence at the gate

Measured counts, from the tester's logs filed with
this slice (hidden_files/P168_BATTERY.log,
hidden_files/P168_NEIGHBOURS.log and
hidden_files/P168_FULLSUITE.log):

- Gate battery: 24 passed, 0 skipped, 0 failed - the
  one P-168 behaviour module:
  tests/test_p168_part_x_gate.py (24 tests).
  5 + 6 + 6 + 5 + 2 = 24 behaviour tests
  (Area A 5, Area B 6, Area C 6, Area D 5, hygiene 2).
- Gate-record module: tests/test_p168_gate_record.py
  (10 tests) - R = 10.
- Neighbours batch as run by the tester: 233 passed,
  0 failed - the full P-092 + P-155..P-166 faces fence
  on this gate's base, exactly the P-166 banking
  expectation (faces 209 + P-092 24).
- Overlay battery as run by the tester: 19 passed,
  0 failed - P-167's own battery
  (tests/test_p167_face_speaking_census.py) run on the
  team-02 tree it ships in.
- Full suite: 5288 passed, 5 skipped, 0 failed in
  338.06s on this gate's base.
- Baseline: the P-166 banking confirmation read 5254
  passed, 5 skipped, 0 failed on the forge tree
  (forge log), with the combined faces fence at 209
  passed, 0 failed.
- Merged-tree expectation after P-167 banks: forge
  confirmation 5273 passed (5254 + 19, exact - the
  P-167 battery) and the gate battery run on the
  merged tree, for a committed merged suite of 5307
  passed (5273 + 24 + 10 = 5307) by the same
  arithmetic.

Migration note: none. This gate adds no migration; the
migration head remains 0041 and no migration was added
by this slice. This slice is committed on
yrsa/runmal-team-03 for the keeper to bank in roadmap
order.
