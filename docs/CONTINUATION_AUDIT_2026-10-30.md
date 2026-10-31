# P-006 — Continuation Audit (2026-10-30)

*Every open thread in the repo's docs — STATUS, FORGE-LOG, the
Evaluation Sitting brief in the goal workspace, ADR follow-ups —
judged correct / stale / closed. Correct open threads are scheduled
into the Two Mirrors campaign first, before new parity work.*

Auditor: Yrsa (keeper opening tick, 2026-10-30). Sources read in
full: `docs/STATUS.md`, `docs/fellowship/FORGE-LOG.md` (709 lines,
last entry 2026-10-13 06:16 EDT), `docs/adr/0001–0007` + ADR README,
`docs/PLATFORM_MATRIX.md` (via STATUS), and the goal-workspace files
`EVALUATION_SCORECARD.md` (2026-10-13) and
`VOXTA_1_12_FIELD_NOTES.md` (2026-10-14).

## Verdicts

### 1. Founding roadmap 94/94 — CLOSED, correct as history
STATUS.md and the FORGE-LOG close entry (2026-10-13 06:07 EDT) agree:
all eight campaigns landed, 686 passed / 3 skipped at the S805
evidence run (`538c918`). STATUS is stale only in one narrow sense:
it predates the Two Mirrors campaign and says "Active slice: none".
That is superseded by `CAMPAIGN_STATE.md` + this audit, not an error
in STATUS's founding record. No STATUS rewrite is made by this slice
(its own update rules tie it to slice status; the Two Mirrors state
file is the live surface for this campaign).

### 2. "Known open pre-S101 review" in STATUS.md — STALE / CLOSED
STATUS still carries a "Known open pre-S101 review" (ChatGPT's
request that Yrsa audit the expanded architecture before
implementation). Implementation is complete (94/94); the review
question is moot. Judged closed-by-events. Not scheduled.

### 3. S504 / Kokoro–eSpeak gate hold — CLOSED
FORGE-LOG entries 2026-10-13 01:36–02:27 EDT record the hold;
02:20–02:27 record Volmarr's multi-backend TTS/STT rulings lifting
it; 04:58 records Campaign V landed under that basis. Closed.

### 4. Chatterbox disposition — CLOSED
Held fail-closed through Campaigns V–VIII; Volmarr ruled
2026-10-13 05:45 EDT (user-installed, one-button, gate stays pure);
executed and proven 2026-10-13 06:16 EDT (stock install, synthesis,
audit FAIL shown as information only, binding: false). Closed.
CosyVoice remains the sole admitted default voice.

### 5. S805 hosted-CI credential blocker — CLOSED by owner's ruling
The GitHub-Actions shape was abandoned by Volmarr's ruling and
replaced by the self-hosted platform matrix (ADR-0007). The Windows
leg is recorded NOT RUN (no Windows machine in the fleet, none will
be rented) — a deliberate, ruled state, not open work. Closed.

### 6. CosyVoice performance thresholds — CORRECT, OPEN (fact, not a slice)
Predeclared thresholds (first-audio p50 ≤ 1.5 s, RTF ≤ 1.0, declared
for the GPU reference) were NOT met on the shipped CPU build
(measured p50 23.15 s / RTF 6.73, FORGE-LOG 2026-10-13 04:58 EDT)
and were NOT adjusted. This is an honest open performance fact.
Disposition: it feeds Part I's voice census (P-010) and Aesir
readiness (P-009) and Part VII voice work when those slices are
defined/ reached; it is not a standalone repair slice, and no
threshold is rewritten by this audit.

### 7. S806 license-manifest unknowns — CORRECT, MINOR, OPEN
The S806 release gate over the dev venv flagged 7 *unknown* license
spellings for human review, zero forbidden (STATUS, Campaign VIII).
No forbidden licence is present; the unknowns are a human-review
list, not a defect. Disposition: re-checked as part of P-014
(Part I gate) against the fresh baseline's installed set; if the
same unknowns persist they are reported to Volmarr once, plainly,
at the Part I gate — not silently cleared.

### 8. Evaluation Sitting brief — CORRECT, OPEN, VOLMARR-GATED — SCHEDULED FIRST
`EVALUATION_SCORECARD.md` (goal workspace, 2026-10-13): a ~45-minute
live-use sitting at purplelongship, Volmarr driving, six scored
items, ending in the deciding question ("Would I open this instead
of the tools I already use, tomorrow morning?"). No scores are
recorded anywhere in the repo or goal workspace — the sitting has
NOT happened. It is a correct open thread and, per P-006, is
scheduled into this campaign first. It cannot be executed by the
keeper: it requires Volmarr driving at purplelongship. Disposition:
flagged as the campaign's first Volmarr-gated item; parity census
work (P-001–P-005, P-008+) proceeds in parallel because none of it
depends on the sitting's scores, and any Broken/rough findings from
the sitting, when it happens, take priority over parity slices then
in flight. The VOXTA_1_12_FIELD_NOTES suggestion (a five-minute
Voxta 1.12 Skills/App-Assistant comparison inside the same sitting)
is folded into the sitting, not a separate thread.

### 9. ADR follow-ups — NONE OPEN
ADR-0001 through ADR-0007 are all Status: Accepted. A grep of
`docs/adr/`, STATUS, PLATFORM_MATRIX and BENCHMARKS for TODO /
follow-up / deferred / open-question markers returned no open
follow-up items. ADR-0005's addenda (Chatterbox reclassification)
are executed (verdict 4 above). Closed.

### 10. Samtal side quest — CLOSED for this campaign
STATUS and the scorecard both state Samtal stays a separate saga
unless Volmarr rules otherwise. No such ruling is in the sources.
The Two Mirrors roadmap's plugin/bridge kinship references are
design kinship only. Not scheduled.

## Schedule resulting from this audit

1. **Evaluation Sitting** — first, Volmarr-gated, awaiting his time
   at purplelongship (scorecard in the goal workspace files).
2. P-007 fresh baseline — executed in the same opening tick as this
   audit (result recorded in CAMPAIGN_STATE.md).
3. Part I census continues in roadmap order (P-001–P-005,
   P-008–P-014); item 6 (voice performance fact) feeds P-009/P-010;
   item 7 (license unknowns) is re-checked at P-014.

No other correct open thread was found in the audited sources.
