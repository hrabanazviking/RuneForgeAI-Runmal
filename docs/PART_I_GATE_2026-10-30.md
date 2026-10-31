# P-014 — Part I Gate (2026-10-30)

*The Part I gate. The roadmap's own text for this slice is:
"delta table + continuation audit + fresh baseline all banked;
every later part's slice list re-validated against the table."
This record is that gate, judged only from Part I's banked
records, this tree, and one fresh own-tree measurement (the
S806 licence re-check in §5). No new external source was
consulted and no mirror was read for this slice.*

## Gate verdict

**Part I is COMPLETE and the gate PASSES.** All fourteen
Part I slices are banked, Parts II–VI are re-validated and
stand as written, every flagged NO-HOME and kin-only row from
Part I is homed, queued, or explicitly dropped in §3 — none
is silently dropped — and Parts VII–XIV are recorded as
awaiting definitions, not as validated, in §4. The gate
passes with the named Volmarr-gated debts in §6 still open;
each debt is named there with its owner and its re-open
condition, and none of them is claimed as done.

## §1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| Delta table banked | P-004, commit 0f2ad64: 141 mirror rows judged 14 HAVE, 69 HAVE-THIN, 55 MISSING, 3 DELIBERATELY-DIFFERENT | BANKED |
| Continuation audit banked | P-006, commit 2c73cf7: every open repo thread judged correct / stale / closed | BANKED |
| Fresh baseline banked | P-007, commit 72692e1: 685 passed, 6 skipped, 0 failed on the VM, reproduced twice; the purplelongship confirmation leg is a separate named debt (§6), not part of this count | BANKED |
| Every later part's slice list re-validated | §2 of this record (Parts II–VI) and §4 (Parts VII–XIV) | DONE HERE |

Every Part I slice, with its banking commit in this tree:

| Slice | Commit | Slice | Commit |
|---|---|---|---|
| P-001 founding audit | 9ee6402 | P-008 backend ledger | c1b0572 |
| P-002 SillyTavern census | a8f6dc8 | P-009 Aesir readiness | d13a092 |
| P-003 Voxta census | 24f0433 | P-010 voice census | 268ec36 |
| P-004 delta table | 0f2ad64 | P-011 mobile reality | d316f69 |
| P-005 interop corpus | d08fc58 | P-012 clean-room log | 4589d32 |
| P-006 continuation audit | 2c73cf7 | P-013 priority order | 819cdd8 |
| P-007 fresh baseline | 72692e1 | P-014 this gate | this commit |

The suite grew only by Part I's own pinning tests across the
part: from the P-007 baseline of 685 passed, 6 skipped,
0 failed to the P-013 close of 735 passed, 6 skipped,
0 failed, re-measured again at this gate in §7.

## §2 Parts II–VI re-validated against the delta table

Counted mechanically from the filed roadmap this tick:
Parts I–VI define 100 slices, P-001–P-100 continuous, with
no gaps and no duplicates. Parts II–VI are 86 slices:

| Part | Slices | Count | Verdict |
|---|---|---|---|
| II Cards & Content Interop | P-015 – P-030 | 16 | STANDS |
| III Lorebook Depth | P-031 – P-048 | 18 | STANDS |
| IV Prompt & Sampler Depth | P-049 – P-064 | 16 | STANDS |
| V Chat Surgery | P-065 – P-080 | 16 | STANDS |
| VI The Extensions Row | P-081 – P-100 | 20 | STANDS |

Per part, against P-004's table:

- **Part II stands.** The THIN card, persona, lorebook-file,
  chat-file and preset rows it serves (ST-02, ST-05, ST-34,
  VX-27 among them) are exactly the rows P-005's corpus
  stressed, and P-005's four importer fixes already landed
  inside its territory. No slice in II is made unnecessary
  by the table and none is missing its delta row.
- **Part III stands.** The lore rows are the densest
  HAVE-THIN concentration in either mirror (ST-15–ST-25),
  and each named sub-depth has its slice: recursion P-031,
  selective logic P-032, timed effects P-033, inclusion
  groups P-034, entry states P-035, scan and position
  P-037/P-038, scopes P-039/P-040, vectorised lore P-041.
  The gate adds one scope item in §3 (ST-26), it does not
  re-cut the part.
- **Part IV stands.** Prompt, template, sampler and preset
  depth (ST-28–ST-39) maps slice-for-slice onto
  P-049–P-063, with P-053's per-backend capability truth
  as the honesty spine P-009's Aesir findings require.
  The gate adds the reasoning scope in §3 (ST-30/VX-18)
  and confirms the text-completion kin home in §3.
- **Part V stands.** Swipes, branches, checkpoints, message
  actions, group depth and the data bank (ST-46–ST-56,
  VX-06) map onto P-065–P-079. The gate adds one explicit
  scope item in §3 (ST-50, inside P-068).
- **Part VI stands.** The plugin row is Rúnmál's sovereign
  shape for both mirrors' extension systems (ST-57–ST-68,
  VX-20): API P-081, sandbox law P-082, manager P-083, and
  the citizen plugins P-084–P-095. VX-42's refusal of
  arbitrary-code scripting rests on P-082 exactly as
  P-004 recorded. The gate adds one scope note in §3
  (VX-26, inside P-085).

No part in II–VI is renumbered, removed, or re-sequenced,
and no roadmap text was edited by this gate. The filed
roadmap stands byte-identical; this record and §3's
assignments are filed beside it.

## §3 Every flagged row homed, queued, or explicitly dropped

P-013 ruled that the NO-HOME adapter family ranks first
among the gate's candidates. This gate homes that family
as a **Part I follow-on block**, executed immediately
after this gate and before P-015, under F-numbers so no
roadmap P-number is touched:

- **F-01 — generic OpenAI-compatible chat adapter**
  (P-008's first recommendation): one adapter covering the
  14 WANTED-GENERIC backend rows, chat plus embeddings,
  passing the shared backend contract suite, with the
  connection layer's already-promised `openai` kind made
  real behind it.
- **F-02 — Aesir binding repair** (P-009's first
  recommendation): the minimum honest repair P-009 named —
  stop sending `stream_options`, re-declare the OpenAI-route
  sampler set to the served subset or rebind to the native
  route, correct the default base URL, map 422, and require
  the terminal marker before yielding Done. Aesir
  embeddings bind to Ollama, never to Aesir, per P-009 D3.
  F-02's completion also requires the live smoke in §6;
  the code repair alone does not retire NOT PROVEN LIVE.
- **F-03 — generic OpenAI-compatible speech adapter**
  (P-010's first recommendation): synthesis and
  transcription behind the existing TTS/STT seams, covering
  the 4 WANTED-GENERIC voice rows.
- **F-04 — clean-up tool** (ST-73): the orphan and stale
  file scan with risk warnings, built over the existing
  `runmal doctor` diagnostics (S804), which diagnose but
  do not clean. F-04 runs after the adapter family, still
  before P-015, because it is small, standalone, and was
  the only remaining NO-HOME row with no other home.

All other flagged rows, each with its gate verdict:

| Row | Gate verdict |
|---|---|
| ST-26 per-entry gating extras | HOMED as scope of Part III: character filter and generation-type triggers are explicit scope of P-035, extra scan sources are explicit scope of P-037 |
| ST-27 automation IDs | HOMED as kin scope, no dedicated slice: an entry firing is a plugin/variables act under P-081 and P-093, never lore-entry code execution |
| ST-30 reasoning controls + VX-18 reasoning budget | HOMED as scope of Part IV: reasoning visibility, effort and budget are explicit scope of P-052, declared backend-honestly under P-053 |
| ST-39 multimodal and tool toggles | SPLIT AND HOMED: prompt-level toggles are scope of P-049/P-052; the vision half goes to the Part VIII definition queue |
| ST-40 token-probability viewer | DROPPED from the defined road, explicitly: no served backend in P-008/P-009's ledgers exposes per-token probabilities Rúnmál can honestly show. Re-open condition: P-053 measures a backend that serves logprobs, and a new slice is commissioned then |
| ST-44 AI Horde | DELIBERATELY-DIFFERENT, closed: P-008 §5's UNWANTED judgement is carried as the gate's verdict, with its three reasons (privacy on volunteer machines, no capability truth, a local zero-setup default already exists). Re-open only on Volmarr's word |
| ST-50 message inclusion toggle | HOMED as explicit scope of P-068 (message actions complete): exclude-from-model-view, keep-in-chat is a message action |
| ST-55 welcome Assistant + VX-07 assistant kind | QUEUED to the Part XIII definition queue, with P-012's direct Assistant/Inspector reading as their precondition |
| ST-69 user theme editing | DROPPED, explicitly: Rúnmál's themes are curated design tokens under the project's design law; user custom CSS and movable UI would break the coherence and accessibility invariants those tokens exist to hold. The shipped answer is the token theme set itself |
| ST-70 localised UI | DROPPED, explicitly: a single-owner local app carries no UI-localisation surface in this road; chat translation is a different row and is built at P-086. Re-open only on Volmarr's word |
| ST-71 + VX-64 multi-user accounts | DROPPED as DELIBERATELY-DIFFERENT in substance: Rúnmál is a single-owner local app under ADR-0003's local boundary; multi-user server accounts are another product's job. Re-open only on Volmarr's word |
| VX-08 chat style and flow taxonomy | QUEUED to the Part IX definition queue, where scenarios give the taxonomy its meaning |
| VX-11 mishearing handling | QUEUED to the Part VII definition queue, beside the browser-capture slice whose transcripts it guards |
| VX-17 Decisions service | QUEUED to the Part IX/XIII definition queues, as P-008 §6 reassigned it: a scenario/action gating shape, not a backend |
| VX-19 VRAM awareness | HOMED IN NARROWED FORM inside F-02: Rúnmál surfaces Aesir's resident-model readiness (the `/health/ready` truth P-009 D5 named) instead of estimating VRAM; a general VRAM estimator for external engines is DROPPED, explicitly |
| VX-23 private book surface | NO DEDICATED SLICE, accepted as recorded: the substance is HAVE on the founding memory campaign (P-004); the two-kind surface naming is a presentation difference, not a missing engine, and is not silently upgraded to a slice |
| VX-26 memory provider choice | HOMED as scope of P-085: the vector-storage plugin exposes the lexical-only versus hybrid provider choice the founding stack already contains |
| VX-52 video generation + VX-53 generation plumbing | QUEUED to the Part X definition queue, under the founding licence gate for any engine proposed there |
| VX-58 done notifications | QUEUED to the Part VII definition queue inside the PWA scope, per P-011 D5: the web platform's notification surface, not a native app |
| Cloud voice connectors (P-010 §6 point 2) | QUEUED to the Part VII definition queue, ElevenLabs first as the only provider both mirrors name, after F-03 gives them the generic shape to ride |
| Text-completion paradigm (P-008 §4) | CONFIRMED kin home in Part IV: P-050/P-051 templates and P-061 grammar/JSON-mode carry it; no chat adapter is blocked on it |
| REVERIFY rows (P-010: Silero TTS, WhisperLive) | STILL REVERIFY: no adapter work names either until its exact papers are read directly; the flag is carried, not cleared |

## §4 Parts VII–XIV: awaiting definitions, not validated

Parts VII–XIV exist in the filed roadmap as titles and
slice ranges only (P-101–P-232). Their slice lists
therefore cannot be re-validated by this gate, and this
gate does not pretend otherwise. Recorded, per P-013 §3:

- Parts VII–XIII stand in numeric order once definitions
  exist; Part XIV stands last by definition.
- VII (Voice) and IX (Scenarios) are first in the
  definition queue; no other title-only part is defined
  ahead of them except where P-013 §2's dependency chain
  requires it.
- XII (Hub) sits late in the block by sovereign design.
- XIII's definitions wait on P-012's open reading: the
  Voxta Assistant view and full Inspector surface, read
  directly from official documentation.
- The §3 verdicts that queue rows into VII–XIV bind the
  defining documents: each queued row must be homed in
  that part's definitions or explicitly dropped there,
  never silently lost between this gate and the definition.

## §5 The S806 licence unknowns, re-checked

P-006 item 7 assigned this re-check to the gate, against
the fresh baseline's installed set. Measured this tick on
this VM, in this tree's venv, with the project's own
release tooling (`runmal release gate` and
`runmal release licenses`, S806):

- **33 distributions** in the measured set: **28 permissive,
  5 unknown, 0 forbidden.** The gate tooling reports FAIL
  on unknowns alone — unknowns require human review, and
  this record does not silently clear them.
- The 5 unknown spellings in this measured set:
  certifi (Mozilla Public License 2.0 (MPL 2.0)),
  greenlet (MIT AND PSF-2.0),
  packaging (Apache-2.0 OR BSD-2-Clause),
  sqlite-vec (MIT License, Apache License, Version 2.0),
  typing_extensions (PSF-2.0).
- The original S806 run flagged 7 unknowns over the dev
  venv on purplelongship. This VM's measured set is a
  different, smaller installed set, so the honest claim is
  narrow: **zero forbidden licences in both measured sets;
  the unknown-spelling class persists, with 5 spellings in
  this set.** The purplelongship set itself was not
  re-measured by this gate (see §6).
- Per P-006, this is the one plain report to Volmarr at
  the Part I gate: five licence spellings need a human's
  eyes before any release gate can pass; none of the five
  is a forbidden licence, and none blocks parity work.

## §6 Named debts the gate does not close

These are open after the gate, by name, and the gate's
pass does not claim them:

1. **The Evaluation Sitting — Volmarr-gated, still first.**
   P-006 scheduled it first and P-013 kept its interrupt
   rule: its findings, when Volmarr runs the sitting at
   purplelongship, take priority over parity slices then
   in flight. The keeper cannot run it.
2. **The purplelongship baseline confirmation leg —
   still owed.** Part I's counts are VM counts, reproduced
   and stable under the sanitised proxy environment
   P-007 recorded. No Two Mirrors count is claimed on
   purplelongship until that leg runs there.
3. **The Aesir live smoke — still owed.** One real Aesir
   serve, one Rúnmál chat, one model listing, run where
   Aesir runs. It is part of F-02's completion criteria
   (§3), and until it runs, Aesir chat through Rúnmál is
   NOT PROVEN LIVE (P-009's headline, unchanged).
4. **The CosyVoice CPU performance fact — still open.**
   The shipped CPU build measured p50 23.15 s / RTF 6.73
   against unmet GPU-reference thresholds (P-006 item 6);
   no threshold was rewritten. It feeds the Part VII
   definition queue and is part of why F-03 and the queued
   cloud connectors matter.
5. **The HTTPS-for-LAN decision — Volmarr's.** P-011 D2/D3
   named the gate (PWA install and phone mic/camera need
   a secure context) and chose no mechanism. Without it,
   phone use stays text over plain HTTP on a trusted
   network by explicit `--host`.
6. **The clean-room open reading (P-012 §3) — carried.**
   Six gaps stand as named, priced unknowns, above all
   the Voxta Assistant/Inspector direct reading that
   Part XIII's definitions wait on.

## §7 Evidence at the gate

Full suite re-run this tick on the VM, sanitised proxy
environment exactly as P-007 prescribed: the count is
recorded in `CAMPAIGN_STATE.md` beside this slice's banking
line and includes this slice's pinning tests
(`tests/test_p014_part1_gate.py`). The S806 measurement in
§5 was run in the same tick with the project's own release
tooling. No server was run, no device was tested, and no
push was made: banking is local, per the campaign's bounds.

## §8 What this gate does not do

- It edits no roadmap text and renumbers nothing; the
  F-numbers in §3 are gate assignments filed beside the
  roadmap, and every P-number keeps its filed meaning.
- It builds no adapter, tool, or feature: F-01–F-04 are
  homed work with acceptance shapes named, executed as
  their own slices after this gate.
- It clears no licence unknown, runs no purplelongship
  leg, and retires no NOT PROVEN LIVE claim (§5, §6).
- It touches no README.md, and it pushes nothing.
