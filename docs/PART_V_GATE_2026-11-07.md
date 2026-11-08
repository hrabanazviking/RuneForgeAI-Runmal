# P-080 - Part V Gate (2026-11-07)

*The Part V gate. The roadmap's own text for this slice is:
"P-080 Part V gate: a surgery drill script (branch, checkpoint,
swipe-storm, group scene) runs green; no operation loses data"
Part V's goal, in the roadmap's own words, is: "the conversation
as a malleable document -- every operation the mirrors' users
do a hundred times a day".
This record is that gate, judged only from Part V's banked
records, the battery module, the drill script, and the tester's
logs filed with this slice; no mirror source consulted
(clean-room).*

## Gate verdict

**Part V is COMPLETE and the gate PASSES with named pinned
limitations and carried findings.** This record claims only
what the battery proves.

Verdict per area: Drill PASS, Accounting PASS, Citizens PASS.

## S1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| A surgery drill script runs green | scripts/drill_p080_surgery.py (10 steps, exit 0); tests/test_p080_part_v_gate.py - J | DONE HERE |
| Branch in the drill | drill steps branch + merge-back; battery B | DONE HERE |
| Checkpoint in the drill | drill step checkpoint; battery C | DONE HERE |
| Swipe-storm in the drill | drill step swipe-storm; battery A | DONE HERE |
| Group scene in the drill | drill step group; battery E | DONE HERE |
| No operation loses data | the account discipline in S2, applied in drill + battery A-I | DONE HERE |
| Measured counts at the gate | S6 of this record, from the tester's logs | DONE HERE |

Part V spans P-065..P-080, sixteen slices continuous:
P-065 through P-080, no gaps. Per-slice coverage map:
P-065->A/J + drill swipe-storm, P-066->B + drill branch/
merge-back, P-067->C + drill checkpoint, P-068->A/F +
drill edit/delete, P-069->neighbours at the gate (its own
battery green in the gate run; no drill step claims it),
P-070->E + drill group, P-071->neighbours at the gate (the
digest road E shares), P-072->neighbours, P-073->neighbours,
P-074->neighbours, P-075->neighbours (provenance rides every
copy the drill makes, per the P-078 _copy_message contract),
P-076->F + drill undo, P-077->G + drill long-chat-pages,
P-078->H + drill import, P-079->I, P-080->this gate.
No roadmap text was edited.

## S2 "Passes" means, per verdict area

- **Drill PASS.** The drill script builds one surgery world
  on a throwaway database and walks seed -> account ->
  swipe-storm -> branch -> checkpoint -> merge-back -> group
  -> undo -> import -> final-accounting, asserting after
  every step and exiting non-zero on the first failure. Run
  standalone it prints PASS (10 steps); run as battery test J
  (a subprocess against this tree) it is green again, with
  every named step ok.
- **Accounting PASS.** One discipline everywhere: an account
  is the multiset of every string a chat holds -- every
  swipe-deck entry of every message plus every variant-history
  content, read through message_to_dict. Against that account:
  a swipe-storm (8 added alternates across two messages,
  every index selected in turn) only grows the account and
  content == deck[swipe_id] at every stop; edit grows the
  account by exactly the new text (the replaced text stays
  as a variant); move changes order and nothing else; pin
  changes nothing; copy-to-branch and fork never change
  their source; a fork's prefix decks equal the source decks
  exactly, swipe_ids and variant histories included;
  merge-back holds the target's full history plus the
  branch's divergent suffix with both parents unchanged;
  a checkpoint restore reproduces the checkpoint-time
  account exactly in a NEW chat while the source keeps its
  later append and edit; delete removes exactly its own
  message's deck from the account, and undo after delete
  (and after edit, and after append) restores the prior
  account exactly; an imported chat's account is fully live
  (fork of it loses nothing, surgery on the fork never
  touches it); the greeting deck seeds as a first-message
  deck, swiping through it loses nothing, a quiet chat
  starts empty, and undoing a seed-into-empty returns the
  chat to empty.
- **Citizens PASS.** The Part V citizens hold together in
  one world each: a group scene (P-070 list activation,
  persisted cursor A,B,A) posts three lines that all survive
  exactly once in order in the transcript while the surgery
  chat next door keeps its account untouched; a 1,200-message
  chat's paged road concatenates to the legacy full history
  with an equal canonical hash (P-077); the Part V neighbour
  batteries (P-065..P-079, P-020, the Part IV gate) run green
  in the same gate run, with the single named exception of
  finding F1.

## S3 The Surgeryhall world

The battery's and drill's shared world is Surgeryhall,
fresh-authored in the battery and drill modules (P-005
discipline, no real user files): a chat seeded with numbered
lines, stormed with ZqxGate80 / ZqxDrill80 alternates, forked,
checkpointed, merged, edited, deleted and undone, beside a
Mead Hall group room and an imported ferry chat. The final
union check is the gate's centre: after every operation,
every seed string still exists somewhere across
{source, branch, merged, restored} -- no operation lost it.

## S4 Pinned limitations - named and deliberate

The gate passes with these limitations pinned, not hidden.
Each is exact in the battery module, the drill, or the banked
slices' own records; this section names them so no later part
mistakes them for clean ground.

- **(a) Fork and merge copies carry the FULL deck -- that is
  the current contract.** P-078 fixed branches._copy_message
  so deck, active index, variant history and per-swipe
  provenance ride along on every copy. Any older text
  describing a branch copy as carrying the active alternate
  only describes the pre-P-078 tree and is superseded (see
  finding F1 for the one live pin that still says it).
- **(b) Delete is intentional loss, exactly scoped.** A
  delete removes its message and, per P-068, that message's
  pin Memory with it (no orphaned memory may point at a dead
  message). The gate's no-loss law judges delete by its own
  contract: exactly that message's deck leaves the account,
  every other string survives, and the deletion is
  recoverable only through the undo journal (see (c)).
- **(c) The undo journal is bounded: MAX_ENTRIES = 50 per
  chat, oldest pruned first.** Beyond fifty operations the
  oldest before-image is gone by design, so undo depth is
  finite. The gate pins the cap value; no battery pretends
  the journal is bottomless.
- **(d) Undo covers a named operation set, not everything.**
  The journal records message and chat operations on ONE
  chat (append / edit / delete / move, swipes, settings,
  branch rename, pin, metadata, greeting seed). Fork,
  checkpoint restore, merge-back and import create NEW chats
  and are not journaled on their source -- they need no
  undo, being non-destructive by construction, and the gate
  proves that non-destruction directly instead.
- **(e) Checkpoints live outside the database.** A
  checkpoint is a checksum-sealed file under the data dir,
  not a DB row; restore is always restore-as-new, never an
  in-place rewind. Deleting a chat removes its checkpoint
  directory with it (the P-067 contract).
- **(f) The group scene is a transcript + activation claim,
  not a live-generation claim.** The gate's scene posts
  lines through the room road and drives the list activation
  strategy; generated turns ride the same road in the P-070
  battery with the tree's test backend. No live model was
  called at this gate.
- **(g) Gate scales are drill scales.** The battery proves
  the paged road at 1,200 messages and the drill at 300;
  the 10,000-message fluidity claim itself stands on
  P-077's own bench evidence, re-run as a neighbour at this
  gate, not re-measured here.

## S5 Carried limitations - findings for the keeper

- **F1 - P-079's fork pin contradicts the banked P-078
  contract; heal at P-079 banking.** The P-079 battery
  (team-02 commit c9a0b2c, written on a P-077 base) pins
  test_export_full_deck_and_fork_active_line to the
  pre-P-078 behaviour: fork state swipes == [active line],
  swipe_id == 0. On the merged tree (P-078 banked first)
  the fork carries the full deck, and that one test fails:
  at the gate, the P-079 battery ran 49 passed / 1 failed on
  the P-078 + P-079 overlay tree, the failure exactly this
  pin (actual fork deck == the full greeting deck,
  swipe_id == 1). The governing contract is P-078's: the
  gate battery asserts full-deck forks (area B, area H,
  area I neighbours). The heal belongs to the keeper at
  P-079 banking -- re-pin that test to the full deck at
  equal strength -- and is NOT made in this slice, whose
  commit must not collide with the P-079 banking. The
  P-079 slice doc's neighbour note ("fork copies carry
  only the ACTIVE alternate") is the same stale text and
  should be corrected in the same banking record.
- **F2 - No new engine defect was found by this gate.**
  Every Part V operation produced exactly its promised
  account in the drill and the battery. The gate's only
  failures during construction were its own over-assertions
  and stale step names, corrected to the banked contracts
  and recorded in the slice evidence. Nothing was left
  unfixed in this slice's own files.

## S6 Evidence at the gate

Measured counts, from the tester's logs filed with this
slice (hidden_files/p080_battery.log,
hidden_files/p080_neighbours.log and
hidden_files/p080_fullsuite.log):

- Gate battery: 15 passed - the one P-080 behaviour
  module: tests/test_p080_part_v_gate.py (15 tests).
  2 + 2 + 1 + 1 + 2 + 1 + 1 + 3 + 1 + 1 = 15 behaviour tests
  (Area A 2, Area B 2, Area C 1, Area E 1, Area F 2,
  Area G 1, Area H 1, Area I 3, Area J 1, hygiene 1).
- Gate-record module: tests/test_p080_gate_record.py
  (10 tests) - R = 10.
- Drill: scripts/drill_p080_surgery.py standalone -
  DRILL P-080: PASS (10 steps), exit 0.
- Neighbours batch as run by the tester: 567 passed, 1 failed -- the one failure is finding F1 (the P-079 fork pin); every other test in that batch is green.
- Full suite: 3401 passed, 1 failed (F1 only), 4 skipped -- measured on the overlay tree described below, before the gate-record module existed; with the gate-record module the same tree reads 3401 + R passed, 1 failed, 4 skipped.
- Baseline arithmetic. The P-078 forge baseline was
  3337 passed, 4 skipped (CAMPAIGN_STATE.md's P-078
  banking record). This gate's full-suite run was made
  on the P-078 tree plus an uncommitted overlay of the
  P-079 commit (c9a0b2c) plus this slice's battery --
  the post-banking shape with F1 unhealed. That run
  minus this slice's 15 battery tests gives the merged
  pre-gate baseline as measured here: 3386 passed,
  1 failed (F1), 4 skipped; with the F1 heal applied it
  reads B = 3387 passed, 4 skipped on the overlay shape.
  F1 was healed at P-079 banking. Honest note: the
  actual P-079 banking confirmation measured
  3388 passed / 4 skipped / 0 failed
  (CAMPAIGN_STATE.md's P-079 banking record) -- one
  more than B, because that banking also added the
  +1 guard heal test, which was not in the overlay.
  Arithmetic: full suite == B + 15 + R, exact on the
  overlay shape -- the healed overlay tree with the
  gate-record module reads 3387 + 15 + 10 = 3412 passed,
  4 skipped, 0 failed; on the banked tree the gate adds
  exactly the battery plus the gate-record module (25),
  so the expected merged full suite is
  3388 + 25 = 3413 passed, 4 skipped, 0 failed, no more.

## S7 Migration note

Migration note: none. The migration head remains 0041; a
gate slice needs no migration and no migration was added
by this slice.

## S8 What this gate does not do

- No new engine features: this gate builds no chat
  behaviour; it judges Part V's banked slices with the
  Surgeryhall drill and the account discipline.
- No fixes to other slices: finding F1 is recorded for
  the keeper's P-079 banking heal, not fixed here (S5).
- No live-model claim: the gate never calls a real
  backend; the group scene is transcript + activation
  (S4 (f)).
- It edits no roadmap text and renumbers nothing; every
  P-number keeps its filed meaning. No roadmap edits.
- It touches no README.md, and it pushes nothing.
  No README touched; nothing pushed.
- Banking: this record and its pinning tests are committed
  on yrsa/runmal-team-03 for the keeper to bank in roadmap
  order (P-079 banks before P-080).
