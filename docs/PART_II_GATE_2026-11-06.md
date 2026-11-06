# P-030 — Part II Gate (2026-11-06)

*The Part II gate. The roadmap's own text for this slice is:
"P-030 Part II gate: the P-005 corpus round-trips clean; a
stranger's real library imports whole with an honest report."
Part II's goal, in the roadmap's own words, is: "Whatever
the mirrors can hold, Rúnmál can receive, keep whole, and
hand back." This record is that gate, judged only from
Part II's banked records, the P-005 corpus, the two P-030
battery modules, and the tester's measured logs filed with
this slice. No new external source was consulted and no
mirror was read for this slice.*

## Gate verdict

**Part II is COMPLETE and the gate PASSES with named
pinned losses and carried limitations.** The P-005 corpus
round-trips clean under the gate contract in §2, a
stranger's library imports whole with an honest report
under §3, and every loss or limitation the gate found is
named in §4 or §5 — none is silently dropped, and this
record claims no fidelity the tests do not prove.

## §1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| The P-005 corpus round-trips clean | §2 of this record; tests/test_p030_part2_gate.py (29 tests) | DONE HERE |
| A stranger's real library imports whole with an honest report | §3 of this record; tests/test_p030_stranger_library.py (16 tests) | DONE HERE |
| Measured counts at the gate | §6 of this record, from the tester's logs | DONE HERE |

Part II spans P-015 – P-030 in the filed roadmap: sixteen
slices, P-015 through P-030 continuous, covering cards
(P-015 – P-017, P-023), persona (P-018), lorebooks (P-019),
chats (P-020), presets (P-021), bulk and store paths
(P-022), organisation, duplicates and safety rails
(P-024, P-025, P-027), scenarios (P-026), the portable
archive (P-028), provenance (P-029), and this gate (P-030).
No roadmap text was edited by this gate.

## §2 The corpus leg — what "clean" means, per type

Corpus tally: 12/12 fixtures by type — 12 fixtures in
total: 5 cards, 3 lorebooks, 2 presets, 1 chat, 1 persona.
No scenario fixture exists in the corpus — the scenario
leg is supplementary, authored in-module. The gate
contract per type, exactly as the battery pins it:

- **Cards — clean means:** normalised fields + unknowns
equal, a byte fixed point on second export, the file leg
full, and the store leg full except spec_version
collapses to "2" by construction, because the character
store stores the v2 export shape (see pinned loss (d)).
- **Lorebooks — clean means:** the file leg FULL — all
fields, including the 23 world-info fields P-005 pinned
as dropped, survive as data in extra/raw carriage — and
the store leg MAPPED-ONLY, with the dropped set pinned
by name: the exact frozenset of dropped field names
lives in the test module, and §4 (a) names the loss.
- **Presets — clean means:** the canonical params bag
exact, mirror-only keys in raw carriage only, and the
seed -1 sentinel restored on export.
- **Chat — clean means:** the file leg field_diff == []
with a byte fixed point, and the live projection losses
pinned exactly via loss_report — 6 items for the corpus
chat (see pinned loss (b)).
- **Persona — clean means:** file-model only. No persona
store exists yet in Part II, so there is no store leg to
claim, and this gate claims none.
- **Scenario — supplementary leg:** parse->export fixed
points, with unmappable elements re-emitted verbatim,
authored in-module because the corpus holds no scenario
fixture (see the tally above).

## §3 The stranger's library leg

Stranger's library tally: 19 files submitted to the bulk
folder import. The report reconciles exactly:
totals == compute_totals, and
accepted+repaired+refused+skipped == submitted, every
non-accept is reason-coded, and DB reality 6 characters /
3 lorebooks matching the report — 6 characters and
3 lorebooks in the database, no more and no fewer.

- Bulk import accepts cards + lorebooks. Preset, chat and
persona files are honestly refused unsupported_kind, with
home slices named (P-021 for presets, P-020 for chats,
P-018 for personas), and each refused shape is redeemed
whole via its home importer in the whole-library leg.
- Scenario has NO bulk home: bulk import accepts no
scenario shape, either way it is spelled (see finding F2).
- The library also survives the .runmal portable archive:
export -> validate -> restore, with counts + provenance
preserved, and re-export checksum-stable.
- All stranger fixtures were authored fresh in the test
module — P-005 discipline, no real user files. The corpus
manifest itself states its fixtures were authored fresh,
so the stranger leg is what covers "a stranger's real
library" in the roadmap line: fresh-authored shapes,
imported whole, accounted for exactly once each.

## §4 Pinned losses — named and deliberate

The gate passes with these losses pinned, not hidden.
Each is exact in the battery modules; this section names
them so no later part mistakes them for clean ground.

- **(a) Lorebook store loss.** The lorebook DB store
drops the 23 world-info fields and collapses position 4
(at_depth) to before_char. This is Part III debt, owned
by the lorebook-depth slices (the P-032/033/034/036/038
area), not a Part II claim.
- **(b) Chat live projection loss.** The chat live
projection loses alternate swipes beyond the active one,
extra, chat_metadata and send_date fidelity. The loss is
pinned exactly via loss_report — 6 items for the corpus
chat — while the chat file leg itself is clean (§2).
- **(c) PNG carrier loss.** PNG export is a synthesised
1x1 carrier at file level: the card fields ride the
carrier, the original art does not. Original art survives
only via the P-023 DB asset path.
- **(d) Stored card shape.** Stored card_json is always
v2 export text: the character store holds the v2 export
shape, which is why the card store leg collapses
spec_version to "2" by construction (§2).

## §5 Carried limitations — findings for the keeper

- **F1 — at-depth lorebooks cannot enter the DB store.**
A native lorebook carrying at_depth entries cannot enter
the DB store at all: import_book_transactional raises
ValueError, because the lorebooks/service VALID_POSITIONS
rejects at_depth. This is pinned as a limitation test;
at-depth DB carriage is P-038's road.
- **F2 — bulk has no scenario home, either way.** The bulk
classifier swallows a Voxta scenario that carries
description/scenario fields as a v1 card, accepted under
the scenario's name; the pure Voxta spelling is refused
unrecognized_content. Bulk has no scenario home either way.
- **F3 — chat refusal names its home in text only.** The
chat unsupported_kind refusal names its home slice (P-020)
in reason text only, where preset records structured
notes (detected_shape/home_slice) — a cosmetic asymmetry,
recorded as found.
- **F4 — P-005 manifest prose is stale.** The manifest's
persona/preset expectation strings predate P-018/P-021.
Recorded here; the manifest is left untouched, because
its hash pins guard the corpus.
- **F5 — provenance is character-only.** Lorebooks,
presets, chats, personas and scenarios carry no
provenance record; provenance is character-only in
Part II. The single-card API path records
original_sha256/original_byte_length as null by design.

## §6 Evidence at the gate

Measured counts, from the tester's logs filed with this
slice (hidden_files/p030-battery.log,
hidden_files/p030-neighbours.log and
hidden_files/p030-full-suite.log):

- Gate battery: 45 passed — the two P-030 modules,
tests/test_p030_part2_gate.py (29 tests) and
tests/test_p030_stranger_library.py (16 tests).
- Part II neighbours: 412 passed.
- Full suite: 1233 passed, 4 skipped, 0 failed.
- The P-029 baseline was 1188 passed, 4 skipped, so the
gate adds exactly 45 — the battery count, no more.

## §7 Migration note

Migration note: none. The migration head remains 0023;
a gate slice needs no migration and no migration was
added by this slice.

## §8 What this gate does not do

- It claims no store leg for persona, no at-depth DB
carriage for lorebooks, and no bulk home for scenarios:
those are the pinned losses and findings of §4 and §5,
not silent gaps.
- It edits no roadmap text and renumbers nothing; every
P-number keeps its filed meaning.
- It touches no README.md, and it pushes nothing.
- Banking: this record and its pinning tests are committed
on branch yrsa/runmal-team-03 for the keeper to bank in
roadmap order; commit: recorded by the keeper at banking.
