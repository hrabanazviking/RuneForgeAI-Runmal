# P-048 — Part III Gate (2026-11-06)

*The Part III gate. The roadmap's own text for this slice is:
"P-048 Part III gate: the ST-shaped lore test pack (logic, recursion, timing) passes on Rúnmál's engine; inspector explains every firing"
Part III's goal, in the roadmap's own words, is: "world info at the mirrors' full strength — the quiet engine that makes long worlds stay true".
This record is that gate, judged only from Part III's banked records, the battery modules, and the tester's logs filed with this slice; no mirror source consulted (clean-room).*

## Gate verdict

**Part III is COMPLETE and the gate PASSES with named pinned limitations and carried findings.** This record claims only what the battery proves.

Verdict per area: Logic PASS, Recursion PASS, Timing PASS, Inspector PASS, plus cross-cutting (placement/scopes/vector/tokens/RNG/windows/binding/packs/perf-light/migration-light/editor) PASS.

## §1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| Logic: the ST-shaped lore test pack (logic) passes on Rúnmál's engine | tests/test_p048_part3_gate.py — A-LOG-1, A-LOG-2, A-LOG-3, A-LOG-4 | DONE HERE |
| Recursion: the ST-shaped lore test pack (recursion) passes on Rúnmál's engine | tests/test_p048_part3_gate.py — B-REC-1, B-REC-2, B-REC-3, B-REC-4, B-REC-5 | DONE HERE |
| Timing: the ST-shaped lore test pack (timing) passes on Rúnmál's engine | tests/test_p048_timing_leg.py — C-TIM-1, C-TIM-2, C-TIM-3, C-TIM-4 | DONE HERE |
| Inspector explains every firing | tests/test_p048_inspector_leg.py — X-INS-1, X-INS-2 | DONE HERE |
| Cross-cutting: placement, scopes, vector, tokens, RNG, windows, binding, packs, perf-light, migration-light, editor | tests/test_p048_inspector_leg.py — X-PLC-1, X-SCO-1, X-VEC-1, X-VEC-2, X-TOK-1, X-RNG-1, X-WIN-1, X-BIND-1, X-PACK-1, X-PERF-1, X-MIG-1, X-ED-1 | DONE HERE |
| Measured counts at the gate | §6 of this record, from the tester's logs | DONE HERE |

Part III spans P-031..P-048, eighteen slices continuous: P-031 through P-048, no gaps. Per-slice coverage map: P-031→B-REC-1..5, P-032→A-LOG-1/2, P-033→C-TIM-1..4, P-034→A-LOG-3, P-035→A-LOG-4, P-036→X-RNG-1, P-037→X-WIN-1, P-038→X-PLC-1, P-039→X-BIND-1, P-040→X-SCO-1, P-041→X-VEC-1/2, P-042→X-ED-1, P-043→X-INS-1/2, P-044→X-TOK-1, P-045→X-PACK-1, P-046→X-PERF-1 + carried bench evidence, P-047→X-MIG-1, P-048→this gate. No roadmap text was edited.

## §2 "Passes" means, per verdict area

- **Logic PASS.** The truth table is exact at the core AND at the scanner: the P-032 secondary-gate truth table holds at the pure-function level and through the scanner, hit sets row-for-row. Inclusion groups pick exactly one deterministically under rank -group_weight,-priority,entry_id — at the resolver level and in preview, the winner is included and losers are group_excluded with the winner recorded. The three activation kinds run on one engine: constant fires with no keys, selective only on a key hit, vectorised only on a vector hit; hit kinds never cross except the labelled vector_fallback.
- **Recursion PASS.** Chains carry depth + triggered_by attribution, breadth-first over keyword links in fired entries' content. The depth clamp is at MAX_RECURSIVE_SCAN_DEPTH=5. Cycles terminate via the seen-set, each entry firing at most once. The budget gates depth>0 admissions; round-0 admission is unconditional — pinned (see §4 (b)): tokens_used may exceed a budget smaller than the round-0 cost alone.
- **Timing PASS.** The 4-turn sticky/cooldown/delay life table is reproduced as the contract: sticky fires via "key" then carries over, cooldown suppresses then re-fires, delay arms, pends, then fires via "delay" with no key. Preview ticks copies, caller state unmutated — preview_activation ticks a copy of the supplied states and nothing persists in the pure leg. Persistence = fresh session per tick: the DB leg runs each tick in a fresh session and reproduces the pure columns exactly; absence of a row IS the default state.
- **Inspector & cross-cutting PASS.** Every firing is explained with a concrete reason code and its factual block: included rows carry a reason in the inspector's included map, every other row carries a concrete reason code, and facts_not_recorded is carried verbatim (see §4 (a)). Placement is asserted in the composed prompt (X-PLC-1). Scopes are FOUR layers (global, character, persona, chat) with the per-layer minimum-budget rule — the gate brief's "global < character < chat" is realised with persona between character and chat. Vector/fallback set-equivalence holds with honest via labelling. The token account reconciles in each of P-044's two regimes — with an explicit counter the account recounts exactly while preview rows keep budget-pass estimates. Seeded rolls are reproducible and context-bound; unseeded rolls are labelled seeded: False.

## §3 The ST-shaped pack leg

The pack's shared world is Gateworld, fresh-authored in the battery modules (P-005 discipline, no real user files). Gateworld tally: 18 entries in the inspector sweep: 8 included / 7 not_triggered / 2 group_excluded / 1 disabled. The reconciliation holds: included+discarded+not_triggered+group_excluded+disabled == entries for every tick shape in the pack — in the inspector sweep that is 8 included + 0 discarded + 7 not_triggered + 2 group_excluded + 1 disabled == 18 entries. And firings explained == firings: every included row carries its reason code and factual block, and explanations == entries in the sweep.

## §4 Pinned limitations — named and deliberate

The gate passes with these limitations pinned, not hidden. Each is exact in the battery modules or the engine source; this section names them so no later part mistakes them for clean ground.

- **(a) Inspector FACTS_NOT_RECORDED, carried verbatim.** From src/runmal/lorebooks/inspector.py, the FACTS_NOT_RECORDED tuple is:
  - "probability rolls exist only for gated entries (probability < 100); ungated entries make no roll by design (P-036)"
  - "vector scores exist only when the vector matcher ran; caller-supplied vector_hit_ids carry no scores, and a precomputed matcher outcome does not record the threshold it used"
  - "recursive-round (depth > 0) secondary-gate near misses are not recorded; the near-miss scan covers the round-0 scan window only"
  - "reference-expansion ({{lore:...}}) provenance records via and depth only; the referring entry is not recorded by the activation engine"
  - "timed-effect counters are reported only when entry_states are supplied; a clean-state inspection records the config and no live counters"
  - "scope_over_budget outcomes are produced by the P-040 layered pass and appear when a layered preview dict is explained, not from a single-book inspection"
- **(b) Round-0 recursion admission is unconditional.** Budget flags, never blocks, the first round: round-0 (direct) hits are admitted unconditionally by design; the token budget gates depth>0 expansion admissions only.
- **(c) Unseeded probability rolls are system-entropy.** Irreproducible by design, labelled seeded: False. Only seeded rolls are reproducible and context-bound.
- **(d) P-046's performance numbers are laptop measurements.** They carry a x4.0 Pi derating, never Pi measurements: no Pi was available to that slice (see §5 F1 and §6).
- **(e) X-PLC-1 composer ordering as built.** Persona precedes lore_before in the baseline order; at_depth distance is measured from the end of the chat history, not from the end of the whole prompt.
- **(f) Timing effect vocabulary as built.** The sticky carryover effect is "sticky_carryover", a plain key firing is "fired", and a cooldown tick with no trigger present decrements with effect None.

## §5 Carried limitations — findings for the keeper

- **F1 — P-046's vector cache is in-process only, and the Pi 4 bench is still owed.** The vector cache dies with its process; there is no persistent or database-backed vector store. And the direct Pi 4 run of the 10,000-entry bench is still owed: P-046's numbers are laptop measurements with a x4.0 Pi derating (carried from P-046).
- **F2 — binding.normalise_book_entry drops depth/role.** P-047's commissioned discovery: binding.normalise_book_entry returns no depth/role keys, so embedded character-book entries cannot carry P-038 placement into materialisation. This is commissioned as the immediate slice AFTER this gate; NOT fixed here, NOT part of this gate.
- **F3 — P-019's interop preservation is file-layer only.** Carried from Part II: interop preservation holds at the file layer; no store-layer preservation is claimed for it here.
- **F4 — P-030 finding F1 (at_depth placement) is CLOSED here.** The Part II gate's F1 — at-depth lorebooks cannot enter the DB store — is CLOSED here by X-PLC-1's composed-prompt + DB round-trip proof: at_depth entries enter the store, round-trip, and splice into the composed prompt at their declared depth.

## §6 Evidence at the gate

Measured counts, from the tester's logs filed with this slice (hidden_files/p048_battery.log, hidden_files/p048_neighbours.log and hidden_files/p048_fullsuite.log):

- Gate battery: 32 passed — the three P-048 behaviour modules: tests/test_p048_part3_gate.py (12 tests), tests/test_p048_timing_leg.py (4 tests), tests/test_p048_inspector_leg.py (16 tests). 12 + 4 + 16 = 32 behaviour tests.
- Gate-record module: tests/test_p048_gate_record.py (10 tests) — R = 10.
- Part III neighbours: 906 passed.
- Full suite: 2199 passed, 4 skipped, 0 failed.
- The P-047 baseline B was 2157 passed, 4 skipped — the forge confirmation count at the merged P-047 tree recorded in CAMPAIGN_STATE.md's P-047 banking record (= 2142 + 15, exact). The P-047 evidence file in the team-02 worktree reports 2130 passed on its own pre-P-046 base (= 2115 + 15); the merged-tree 2157 is the baseline for this worktree, whose HEAD includes both the P-046 and P-047 merges.
- Arithmetic: full suite == B + 32 + R — 2157 + 32 + 10 = 2199, exact. The gate adds exactly the battery plus the gate-record module, no more.

Carried P-046 bench evidence, cited from docs/LOREBOOK_SCAN_PERFORMANCE_2026-11-06.md, labelled carried, not re-measured: BUDGET-P046 — median total (cold cache) 310.1 ms laptop, 1241 ms Pi-equivalent, against the <= 2000 ms budget; keyword scan 14.3 ms laptop, 57 ms Pi-equivalent, against the <= 1200 ms keyword budget; warm-cache total 65.0 ms laptop, 260 ms Pi-equivalent. Budget met there; nothing was re-measured by this gate.

## §7 Migration note

Migration note: none. The migration head remains 0032; a gate slice needs no migration and no migration was added by this slice.

## §8 What this gate does not do

- No new engine features: this gate builds no engine behaviour; it judges Part III's banked slices with the ST-shaped pack.
- No fixes: F2 is commissioned after the gate, by design, and is not fixed here.
- No re-measurement of the 10k bench: P-046's numbers are cited as carried evidence, never re-measured, and no Pi-measured performance claim is made.
- It edits no roadmap text and renumbers nothing; every P-number keeps its filed meaning. No roadmap edits.
- It touches no README.md, and it pushes nothing. No README touched; nothing pushed.
- Banking: this record and its pinning tests are committed on yrsa/runmal-team-03 for the keeper to bank in roadmap order.
