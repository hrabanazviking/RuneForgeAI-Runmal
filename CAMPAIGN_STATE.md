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
- P-003 Voxta census — banked this tick (see git log). Doc:
    docs/VOXTA_CENSUS_2026-10-30.md — 67 behaviour rows
    (VX-01–VX-67) in P-001's language, from Voxta's official
    public site + official documentation (doc.voxta.ai: Scenarios,
    Events, Actions & tools, Buttons & controls, Contexts, Memory
    books, Scripting, Templates, Messages, Packages, HUD & stage
    effects — read in full) + published release notes only
    (v1.11.0 baseline; v1.9.0/v1.9.3 read in full; no source
    code exists in public and none was sought — clean-room law).
    Honest flags carried in the doc: live docs are not
    version-pinned (doc-only rows may post-date 1.11.0), one
    flagged unofficial corroboration on VX-15 only, MP4/AVIF
    video avatars + vision folder-watcher rest on roadmap §1,
    and the Assistant view / full Inspector surface are recorded
    as surveyed-but-not-yet-read, not rows. Full suite re-run
    this tick on the VM (sanitised proxy env): 685 passed,
    6 skipped, 0 failed — matches the P-007 baseline exactly.
- P-004 delta table — banked this tick (see git log). Doc:
    docs/DELTA_TABLE_2026-10-30.md — all 141 mirror rows judged
    (ST 74 + VX 67, counted mechanically from the tables):
    combined 14 HAVE, 69 HAVE-THIN, 55 MISSING, 3
    DELIBERATELY-DIFFERENT (VX-01 no cloud/subscription tier,
    VX-42 no arbitrary-code scripting, VX-59 no central store —
    each with its sovereign replacement named). SillyTavern
    splits 11/45/18/0 (a depth problem: cores exist, deltas are
    named sub-depths); Voxta splits 3/24/37/3 (a territory
    problem: scenarios/stage/workspaces/generation). Re-cut
    verdict: Parts II–VI stand as shaped; Parts VII–XIV cannot
    be re-validated (titles only in the filed roadmap — the
    recorded discrepancy, now confirmed material, since most
    MISSING rows live there — 34 of 55 MISSING rows carry a
    title-only road home, counted from the table); the flagged
    NO-HOME rows (ST-26, ST-30, ST-40, ST-69, ST-70, ST-71/VX-64,
    ST-73, VX-11, VX-18) plus the kin-only rows (ST-27, ST-44,
    ST-50, VX-19) are P-014's explicit agenda, assigned
    or dropped by the gate, never silently. Full suite re-run
    this tick on the VM (sanitised proxy env): 685 passed,
    6 skipped, 0 failed — matches the P-007 baseline exactly.
- P-005 interop corpus — banked this tick (see git log). Corpus:
    tests/fixtures/interop/ (12 fixtures + manifest with sha256
    pins + make_corpus.py), tests/test_p005_interop_corpus.py
    (15 tests), doc docs/INTEROP_CORPUS_2026-10-30.md. Provenance
    decision recorded in the doc: no redistributable public user
    corpus exists, so all fixtures were authored fresh for Rúnmál
    (shapes from public specs/docs only) rather than scraping
    strangers' content. Measured: cards travel well (unknowns of
    every JSON type + extension zoo survive v2/v3 round trips;
    v3 assets + group-only greetings survive; dual-chunk PNG
    imports as ccv3). Lorebook still-dropped set pinned exactly
    in the test (23 world-info fields + at-depth position) with
    Part III homes. Presets/chat/persona have NO importer yet
    (P-021/P-020/P-018) — pinned as well-formedness targets.
    Four bugs found by the corpus and FIXED in-slice: lorebook
    import crashed with bare TypeError on null numerics (now
    tolerant _as_int); world-info matchWholeWords ignored
    (whole_word forced True — now honoured); world-info
    sticky/cooldown/delay zeroed despite native *_prompts fields
    (now mapped); card string lists stringified nulls into
    literal "None" greetings/tags (now genuine strings only).
    Full suite re-run this tick on the VM (sanitised proxy env):
    700 passed, 6 skipped, 0 failed — baseline 685 + 15 new.
- P-008 backend parity ledger — banked this tick (see git log).
    Doc: docs/BACKEND_PARITY_LEDGER_2026-10-30.md + pinning tests
    tests/test_p008_backend_ledger.py (5 tests). Rúnmál side from
    the tree: chat backends fake/ollama/openrouter/aesir,
    embeddings fake/ollama/aesir + FTS-degrading unavailable.
    Mirror side: 22 distinct named backends/sources (ST 13 chat
    sources + 7 text backends, VX 3 engines, duplicates counted
    once) judged 2 HAVE (Ollama, OpenRouter), 14 WANTED-GENERIC,
    6 UNWANTED. Key gap: ONE generic OpenAI-compatible adapter
    covers all 14 wanted rows — the connection layer (S211)
    already names an "openai" kind but no chat adapter exists
    behind it; the Aesir adapter proves the shape in-tree. Parts
    II–VI contain no backend slice, so the generic adapter is
    flagged NO HOME for the P-014 gate (first recommendation),
    with text-completion paradigm WANTED-TEXT (kin Part IV).
    AI Horde judged UNWANTED deliberately (privacy on volunteer
    machines, no capability truth, local zero-setup already
    exists) — the verdict P-004 reserved to this slice; P-014
    should carry ST-44 as DELIBERATELY-DIFFERENT. Other unwanted:
    Vertex (bespoke), Electron Hub (bespoke), NovelAI, ExLlamaV3
    direct (covered via TabbyAPI), Voxta Cloud. Vice versa
    recorded: Aesir, contract/fake backend, per-modality
    profiles, FTS-degrading embeddings are Rúnmál-only.
    Full suite re-run this tick on the VM (sanitised proxy env):
    705 passed, 6 skipped, 0 failed — P-005 baseline 700 + 5 new.
- IN PROGRESS: none (tick closing cleanly).
- Next slice: P-009 Aesir readiness check (then P-010…P-014 in
  roadmap order).

Last updated: 2026-10-30 22:37 EDT
