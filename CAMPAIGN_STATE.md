# Rúnmál — Two Mirrors Campaign State

Campaign: Two Mirrors clean-room parity road (232 slices P-001–P-232 as
commissioned, 14 parts). Roadmap filed at
`docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md` in commit
cf9ae3f (pushed to origin/yrsa/two-mirrors-build, verified via
ls-remote cf9ae3f5a0c6aaaea51478bb06f7577e824998cc).
Branch: yrsa/two-mirrors-build (own clone at ~/workspace/runmal-build).
Banking: LOCAL per-slice commits only; no pushes beyond the roadmap
filing without Volmarr's word. README.md files: never touched.

## Roadmap file discrepancy (recorded 2026-10-30, opening tick)

The roadmap file as received at
~/workspace/your_files/runmal/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md
(sha256 3155917fcd86a33757ebcbf40db8bdbec571007ab934d52d0903800b62184e48,
380 lines) contains Parts I–VI only (P-001–P-100) plus the §3 table
promising Parts VII–XIV (P-101–P-232). Parts VII–XIV slice definitions
are NOT in the file. Filed byte-identical as instructed. Work proceeds
on Parts I–VI as written; Parts VII–XIV cannot be sliced until their
definitions exist — flagged for Volmarr / the roadmap author, not
invented by the keeper.

## Status

- Opening: DONE 2026-10-30 ~21:14 EDT (clone, branch, roadmap filing
  + push verified).
- BANKED (local commits):
  - P-006 continuation audit — 2c73cf7. Verdicts: founding 94/94,
    S504 gate, Chatterbox, S805 threads CLOSED; pre-S101 review
    STALE. Correct+open: Evaluation Sitting (Volmarr-gated at
    purplelongship, scheduled FIRST, cannot be run by keeper),
    CosyVoice CPU performance fact (feeds P-009/P-010), S806
    license unknowns (recheck at P-014). No ADR follow-ups open.
    Doc: docs/CONTINUATION_AUDIT_2026-10-30.md
  - P-007 fresh baseline — 72692e1. VM run, reproduced twice:
    685 passed, 6 skipped, 0 failed, 691 collected. Skips are named
    host absences (no Ollama / voice extras on VM). Earlier shifting
    failures proven a VM env artefact (bracketed IPv6 in no_proxy
    misparsed by httpx) — not a repo defect; suite runs on this VM
    must sanitise proxy env (command in
    docs/TWO_MIRRORS_BASELINE_2026-10-30.md). Purplelongship
    confirmation leg still owed at P-014 (Part I gate).
- P-001 founding audit — banked this tick (see git log). Doc:
    docs/FOUNDING_AUDIT_2026-10-30.md — all 94 founding slices stated
    as behaviour with proving tests named (111 test files matched by
    slice number; only S101/S112 lack a dedicated file and are named
    as such), the extra UI campaign inventoried separately (18 items,
    287-green wave close 5bd28cd), post-founding additions and honest
    caveats recorded (CosyVoice CPU speed = HAVE-THIN; Windows leg
    not run by ruling). Full suite re-run this tick on the VM
    (sanitised proxy env): 685 passed, 6 skipped, 0 failed — matches
    the P-007 baseline exactly.
- P-002 SillyTavern census — banked this tick (see git log). Doc:
    docs/SILLYTAVERN_CENSUS_2026-10-30.md — 74 behaviour rows
    (ST-01–ST-74) in P-001's language, from SillyTavern's official
    public documentation + published release notes only (1.19
    release line as baseline; 1.13.0 notes read in full; no source
    code and no source-derived analysis used — clean-room law).
    Full suite re-run this tick on the VM (sanitised proxy env):
    685 passed, 6 skipped, 0 failed — matches the P-007 baseline
    exactly.
- IN PROGRESS: none (tick closing cleanly).
- Next slice: P-003 Voxta census (then P-004, P-005,
  P-008…P-014 in roadmap order).

Last updated: 2026-10-30 21:53 EDT
