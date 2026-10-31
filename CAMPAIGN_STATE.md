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
- P-009 Aesir readiness check — banked this tick (see git log).
    Doc: docs/AESIR_READINESS_2026-10-30.md + pinning tests
    tests/test_p009_aesir_readiness.py (6 tests). Headline: Aesir
    chat through Rúnmál's adapter is NOT PROVEN LIVE (S701–S706
    proved against fixtures/mocks only) and as shipped would fail
    against Aesir's real server, judged from Aesir's own v1 API
    matrix + capability ledger (Aesir repo @ 1eed9706). D1:
    adapter sends stream_options on every request — Aesir's chat
    route rejects it (400), so no real request can complete. D2:
    sampler overclaim — of the adapter's 8 declared-honoured
    controls the OpenAI route accepts only temperature/top_p/
    max_tokens/seed; top_k/min_p/repeat_penalty/stop are rejected
    fields (the full set is served on the native /v1/generate
    route instead). D3: Aesir embeddings NOT SERVED (no
    /v1/embeddings route; calls 404 → honest FTS degradation;
    Aesir's own posture: "Embeddings remain Ollama"). D4: default
    base_url :8000 matches neither Aesir port (18434 native /
    11434 ollama-mode) — ready only if configured. Also recorded:
    catalog-vs-resident listing trap (D5), incomplete-stream
    Done-on-EOF honesty gap (D6), 128-msg/131072-byte admission
    bounds vs full-history sends (D7), unmapped 422 (D8),
    unconsumed served surface incl. /v1/completions (D9), and an
    unproven Ollama-mode interop path (D10). First recommendation
    to P-014 (kin to P-008's): an Aesir binding-repair slice,
    NO HOME in Parts II–VI; plus the owed live smoke on
    purplelongship. No live server was run by this tick — the
    ledger binds documents to documents and says so. Full suite
    re-run this tick on the VM (sanitised proxy env): 711 passed,
    6 skipped, 0 failed — P-008 baseline 705 + 6 new.
- P-010 voice provider census — banked this tick (see git log).
    Doc: docs/VOICE_PROVIDER_CENSUS_2026-10-30.md + pinning tests
    tests/test_p010_voice_provider_census.py (5 tests). Mirror
    side from official public docs only (ST's official TTS page
    read in full 2026-10-30: 16 listed + OpenAI-compatible = 17;
    Voxta names from P-003's attested sources). 23 distinct
    providers judged (18 TTS + 5 STT): 10 WANTED-CONNECT,
    4 WANTED-GENERIC, 2 FAIL-SHIP (Kokoro — eSpeak heart;
    XTTS — CPML NC weights), 4 UNWANTED (Electron Hub, NovelAI,
    Voxta Cloud ×TTS/STT — P-008 verdicts inherited), 2 REVERIFY
    (Silero TTS papers unread — VAD's MIT papers clear nothing
    else; WhisperLive), 1 DEPRECATED (Coqui-TTS, by ST itself),
    0 HAVE / 0 PASS-SHIP (the zeroes are findings). ElevenLabs
    is the only TTS provider both mirrors name. Key gap: ONE
    generic OpenAI-compatible speech adapter covers all 4
    WANTED-GENERIC rows — NO HOME in Parts II–VI, flagged for
    P-014 kin to P-008's chat adapter. 2026 refresh: Voxtral
    TTS (CC-BY-NC-4.0 weights) FAIL-SHIP pre-emptively
    (secondary evidence, flagged). Honest flags: ST's STT list
    and Voxta's full TTS catalogue are surveyed-but-not-
    enumerated in official docs — not invented. Vice versa:
    CosyVoice/Chatterbox named by neither mirror's official
    docs; Rúnmál's STT registry is broader than mirrors'.
    Full suite re-run this tick on the VM (sanitised proxy
    env): 716 passed, 6 skipped, 0 failed — P-009 baseline
    711 + 5 new.
- P-011 mobile reality check — banked this tick (see git log).
    Doc: docs/MOBILE_REALITY_CHECK_2026-10-30.md + pinning tests
    tests/test_p011_mobile_reality.py (6 tests). Decision record,
    from the tree: the responsive web UI is real and pinned
    (8 templated pages carry the viewport; S310 breakpoints
    1024/720, 44px coarse-pointer targets, safe-area insets) but
    there is NO PWA layer (no manifest, service worker,
    theme-color, or icons anywhere in the web layer), the server
    is loopback by law (127.0.0.1:8098 default, ADR-0003;
    phone reach = explicit --host on a trusted network), and
    voice is host audio only (no getUserMedia anywhere; the
    /voice page polls host status). Decisions D1–D5: D1 client
    is the browser everywhere — no native Android/iOS/Windows
    apps (Voxta's Android companion is a thin client doing what
    a browser tab already does; stores contradict sovereignty);
    D2 PWA is the install shape as a named future slice, shell
    only, never caching /api/v1 or the credential, with the
    secure-context limit stated plainly (install + mic/camera
    need localhost or HTTPS — plain-HTTP LAN gets neither);
    D3 phone reach stays an explicit user act under ADR-0003,
    remote access out of scope; D4 no on-phone server (phone is
    a client; server hosts stay laptop/desktop/Pi); D5 mobile
    voice/camera belong to Part VII via a browser-capture slice
    whose precondition is D2's HTTPS gate — honest mobile claim
    today is full text surface, voice stays on the host. Thin
    spot recorded: server-inline /voice and /memories pages
    carry no viewport. PWA shell slice + viewport repair flagged
    NO HOME in Parts II–VI for P-014. No device was tested.
    Full suite re-run this tick on the VM (sanitised proxy
    env): 722 passed, 6 skipped, 0 failed — P-010 baseline
    716 + 6 new.
- P-012 clean-room log — banked this tick (see git log). Doc:
    docs/CLEAN_ROOM_LOG_2026-10-30.md + pinning tests
    tests/test_p012_clean_room_log.py (6 tests). The log is
    opened as a living deliverable in the founding RESEARCH.md
    pattern: §0 states the rule (behaviour studied, code never
    read; allowed source classes in preference order;
    secondary/unofficial sources never carry a row alone;
    every future slice appends its entry before banking,
    entries never rewritten); §1 summarises the founding
    ledger's sources per area (card v2/v3 public specs, ST
    public docs, Ollama/OpenRouter official docs, SQLite /
    sqlite-vec, voice licence papers, stack/testing docs);
    §2 gives every Part I slice P-001–P-011 its entry —
    P-002's ST official docs (14 pages) + 1.13.0 notes in full
    + 1.19 line, P-003's Voxta official site + 10 doc pages +
    v1.11.0/v1.9.0/v1.9.3 notes, P-005's authored-fresh corpus
    provenance, P-009's Aesir entry as a different class
    (Volmarr's own engine, own-repo v1 matrix @ 1eed9706, no
    mirror), P-010's official ST TTS page + founding licence
    papers, and own-tree/no-new-reading entries for
    P-001/P-004/P-006/P-007/P-008/P-011. Flagged uses are
    recorded as flagged, never laundered: ST 1.19 secondary
    corroboration (version note only, not rows), Voxta's
    unofficial voxta.axailotl.ai on VX-15 only, Voxtral's
    secondary HF-card reporting, roadmap-§1 rows as weakest
    evidence. §3 carries six open-reading gaps forward
    (ST STT enumeration, Voxta full TTS catalogue, Voxta
    Assistant/Inspector, ST 1.19 full notes read directly,
    Voxtral card read directly, Silero TTS / WhisperLive
    REVERIFY papers); §4 states the log proves provenance,
    not correctness, and licenses no copying. Full suite
    re-run this tick on the VM (sanitised proxy env):
    728 passed, 6 skipped, 0 failed — P-011 baseline
    722 + 6 new.
- P-013 priority order ratified — banked this tick (see git log).
    Doc: docs/PRIORITY_ORDER_2026-10-30.md + pinning tests
    tests/test_p013_priority_order.py (7 tests) + the P-013
    entry appended to the clean-room log per its §0(5) rule.
    Verdict: the roadmap §3 order STANDS — no part renumbered
    or re-sequenced, no roadmap text edited. Ratified sequence:
    (0) Evaluation Sitting first, Volmarr-gated, its findings
    interrupt parity slices in flight (P-006's rule kept);
    (1) P-014 gate next; (2) Parts II–VI in numeric order —
    the only defined parts, forming the dependency chain the
    slices themselves declare (P-093 store + P-082 sandbox law
    → Part IX; P-087 → Part X; P-028/P-045/P-063/P-083 packs
    → Part XII; P-043/P-059 → Part XIII Inspector);
    (3) Parts VII–XIII in numeric order once definitions
    exist, with VII (Voice) and IX (Scenarios) FIRST in the
    definition queue as the block's daily-use peaks, XII
    (Hub) late by sovereign design, XIII after IX and waiting
    on P-012's direct Assistant/Inspector reading;
    (4) Part XIV last by definition. The literal move —
    VII/IX executed ahead of II–VI — was considered and
    REJECTED with three recorded reasons (would not deliver
    sooner: voice already HAVE, scenarios need II–VI
    substrates; neither part has slice definitions to
    execute; P-004's priority note supports the order as
    shaped). Two priority rulings inside the order: A — the
    NO-HOME adapter family (P-008 generic chat adapter,
    P-009 Aesir binding repair, P-010 generic speech adapter)
    ranks FIRST among P-014's homing candidates (ranking is
    P-013's act, homing remains the gate's); B — P-011's PWA
    shell + browser-capture items ride with Part VII as its
    run-up, viewport repair rides the first web slice.
    Census basis: 141 rows 14/69/55/3 (P-004); scenario block
    VX-28–VX-47 = 20 rows, 0 HAVE (17 MISSING, 2 HAVE-THIN
    substrates, 1 DELIBERATELY-DIFFERENT); 34 of 55 MISSING
    rows carry a title-only road home. Full suite re-run this
    tick on the VM (sanitised proxy env): 735 passed,
    6 skipped, 0 failed — P-012 baseline 728 + 7 new.
- P-014 Part I gate — banked this tick (see git log). Doc:
    docs/PART_I_GATE_2026-10-30.md + pinning tests
    tests/test_p014_part1_gate.py (9 tests) + the P-014 entry
    appended to the clean-room log. VERDICT: Part I COMPLETE,
    gate PASSES. Parts II–VI re-validated by mechanical count
    (100 defined slices P-001–P-100 continuous, no gaps or
    duplicates; II–VI = 86 slices) and STAND as written; no
    roadmap text edited, nothing renumbered. Every flagged
    row homed, queued, or explicitly dropped: the NO-HOME
    adapter family is homed as a Part I follow-on block
    executed before P-015 — F-01 generic OpenAI-compatible
    chat (+embeddings) adapter, F-02 Aesir binding repair,
    F-03 generic OpenAI-compatible speech adapter (P-013
    ruling A honoured, family first), then F-04 clean-up
    tool (ST-73, over runmal doctor). Scope homes: ST-26 →
    P-035/P-037, ST-27 → P-081/P-093 kin, ST-30/VX-18 →
    P-052/P-053, ST-39 split P-049/P-052 + Part VIII queue,
    ST-50 → P-068, VX-26 → P-085, text-completion paradigm
    confirmed in Part IV. Definition queues: ST-55/VX-07 →
    XIII (after the direct Assistant/Inspector reading),
    VX-08/VX-17 → IX/XIII, VX-11/VX-58/cloud voice
    connectors (ElevenLabs first) → VII, VX-52/VX-53 → X.
    Explicit drops: ST-40 (re-open only if P-053 measures a
    logprob-serving backend), ST-69 (curated tokens are the
    shipped answer), ST-70, ST-71/VX-64 (single-owner by
    ADR-0003); ST-44 carried DELIBERATELY-DIFFERENT per
    P-008 §5; VX-19 homed narrowed inside F-02 (resident
    readiness, no VRAM estimator); VX-23 no dedicated slice
    (substance HAVE); Silero TTS / WhisperLive still
    REVERIFY. Parts VII–XIV recorded AWAITING DEFINITIONS,
    not validated; VII and IX first in the definition queue.
    S806 re-check run this tick with the project's own
    release tooling on the VM venv: 33 distributions,
    28 permissive, 5 unknown (certifi MPL 2.0, greenlet
    MIT AND PSF-2.0, packaging Apache-2.0 OR BSD-2-Clause,
    sqlite-vec MIT/Apache, typing_extensions PSF-2.0),
    0 forbidden — unknowns NOT cleared; the original
    purplelongship set (7 unknowns) was not re-measured
    there. Named debts still open at the gate: Evaluation
    Sitting (Volmarr-gated, first, interrupt rule stands),
    purplelongship baseline confirmation leg, Aesir live
    smoke (inside F-02's completion criteria; Aesir chat
    still NOT PROVEN LIVE), CosyVoice CPU performance fact,
    HTTPS-for-LAN decision (Volmarr's), P-012's six
    open-reading gaps. Full suite re-run this tick on the
    VM (sanitised proxy env): 744 passed, 6 skipped,
    0 failed — P-013 baseline 735 + 9 new.
    PART I (P-001–P-014) IS COMPLETE — a part completion,
    reportable to Volmarr under the keeper's reporting rule.
- F-01 generic OpenAI-compatible adapter — banked this tick
    (see git log). Build: src/runmal/backends/openai_compat.py
    (OpenAICompatibleChatBackend, backend_key "openai" — the
    S211 connection kind made real) + OpenAICompatibleEmbedding
    Backend in backends/embeddings.py + profile wiring
    (CHAT_BACKENDS / EMBEDDING_BACKENDS gained "openai",
    config base_url honoured for both). Doc:
    docs/GENERIC_OPENAI_ADAPTER_2026-10-30.md + fixtures
    tests/fixtures/backends/openai_{chat,models,error}.* +
    tests/test_f01_openai_compat.py (9 tests). Sampler truth is
    exactly the S208 openai profile's set, pinned against
    compat.py itself; unsupported canonical controls (top_k,
    min_p, repetition_penalty, context_length) cleared with
    warnings, never sent. Wire discipline from P-009: no
    stream_options / usage toggle sent, 422 mapped, and a
    stream ending with neither [DONE] nor a finish reason
    raises instead of yielding a fabricated Done. P-008's
    pinning tests updated deliberately (its own instruction)
    and the ledger gained its §8 F-01 follow-on closing entry;
    the 14 WANTED-GENERIC rows are covered as profiles on this
    one adapter wherever the named service offers the
    compatible surface — no live endpoint was called. Clean-
    room log gained the F-01 entry (own tree only). Full suite
    re-run this tick on the VM (sanitised proxy env):
    753 passed, 6 skipped, 0 failed, 759 collected — P-014
    baseline 744 + 9 new, collected delta verified against
    HEAD (750 → 759).
- F-02 Aesir binding repair — banked this tick (see git log).
    Build: src/runmal/backends/aesir.py repaired per P-009's
    minimum — no stream_options sent (D1); SAMPLERS
    re-declared to the served OpenAI-route subset
    {temperature, top_p, max_tokens, seed}, top_k/min_p/
    repetition_penalty/stop now declared unsupported (D2 —
    the native-route rebind remains the recorded
    alternative, not taken); DEFAULT_BASE_URL corrected to
    Aesir's native serve port http://127.0.0.1:18434/v1 at
    the adapter, the profile builder, and the doctor (D4,
    doctor literal pinned equal by test); 422 maps to
    ContextOverflow (D8); a stream with neither [DONE] nor a
    finish reason raises instead of yielding Done (D6);
    readiness_check() surfaces resident-model readiness
    from /health/ready at the server root (D5 / VX-19
    narrowed home — no VRAM estimated). D3's binding rule
    recorded in AesirEmbeddingBackend's docstring:
    embeddings bind to Ollama, never to Aesir (no behaviour
    change; real-server calls already 404-degrade to FTS).
    Doc: docs/AESIR_BINDING_REPAIR_2026-10-30.md + tests
    tests/test_f02_aesir_binding.py (11 tests). Deliberately
    updated pins, each with its reason in the test:
    test_s701_aesir.py, test_s702_aesir_mapping.py,
    test_p009_aesir_readiness.py; the readiness ledger gained
    its appended §5 F-02 follow-on (original record stands)
    and the clean-room log its F-02 entry (own tree + Aesir's
    own ledger only, no live server run). NOT PROVEN LIVE
    STANDS: the owed live smoke on purplelongship is still
    F-02's open completion criterion, and D7 (admission
    bounds) remains Part V's reckoning, as P-009 assigned.
    Full suite re-run this tick on the VM (sanitised proxy
    env): 764 passed, 6 skipped, 0 failed — F-01 baseline
    753 + 11 new. (One early targeted run in this tick
    reported 5 failures that did not reproduce: the same
    targeted set then passed twice clean, 62 passed, and
    the full suite is green — recorded as a transient,
    not hidden.)
- F-03 generic OpenAI-compatible speech adapter — banked
    this tick (see git log). Build:
    src/runmal/voice/openai_compat.py — OpenAICompatibleTTS
    Backend (POST /audio/speech, response_format "pcm":
    PCM16 24 kHz chunks unmodified at sample_rate 24000,
    seam sentence splitter per piece, is_final sentinel,
    caller's voice wins, speaking_rate clipped to the served
    0.25–4.0 speed range) + OpenAICompatibleSTTBackend
    (POST /audio/transcriptions, multipart WAV framed by
    stdlib wave, verbose_json normalized into segments/words;
    a segment-less reply becomes one segment spanning the
    audio). Both seams name the adapter "openai"; both
    registries gained an "openai" spec with a DISABLED
    install plan (CONNECT class, P-010: Rúnmál ships only
    its adapter code; the plan note is the configuration
    instruction — OPENAI_API_KEY + RUNMAL_SPEECH_BASE_URL
    env fallbacks; default base URL pinned equal to F-01's
    chat default by test). Both factories build it, so
    voice settings + character voice profiles can select
    it; the STT entry is distinct from the registered
    local "openai-whisper" reference implementation, which
    stands unchanged. Key travels only as an Authorization
    header; errors are generic-worded by status, bodies
    never echoed. Doc:
    docs/GENERIC_OPENAI_SPEECH_ADAPTER_2026-10-30.md +
    fixture tests/fixtures/voice/openai_transcription.json
    + tests/test_f03_openai_speech.py (11 tests). The
    census gained its appended §7 F-03 follow-on (original
    verdicts stand) and the clean-room log its F-03 entry
    (own tree only; no live endpoint was called).
    Deliberately updated pins, each with its reason in the
    test: tests/test_p010_voice_provider_census.py (both
    registry tuples), tests/test_s504_tts.py (known set +
    connect class + thresholds). Unchanged and re-verified:
    KNOWN_* == registry + fake formulas, shipped defaults
    still CosyVoice / faster-whisper only. Full suite
    re-run this tick on the VM (sanitised proxy env):
    775 passed, 6 skipped, 0 failed — F-02 baseline
    764 + 11 new. Ruff: no new findings (the 5 in
    voice/backends.py are pre-existing on the baseline).
- F-04 clean-up tool — banked this tick (see git log). Build:
    src/runmal/diagnostics/cleanup.py (scan_cleanup /
    clean_cleanup) + CLI `runmal cleanup` (dry-run by default;
    --apply, --category, --allow-high-risk, --stale-backup-days
    30 / --stale-staging-days 7, --json). Six categories, each
    item carrying its risk + warning (ST-73): orphan character
    assets (no character row at all), unreferenced character
    files, chats of deleted characters (HIGH — soft-deleted or
    dangling, message counts named; removal needs
    allow-high-risk, one FK-on transaction, chat_summaries
    deleted explicitly, memories untouched so the doctor's
    dangling-source warning tells that story), stale backups
    (never the newest of a kind), stale staging, and
    unrecognized backup-dir files (NEVER removable). Removal
    discipline pinned by tests: re-validation at delete time
    (a character re-created between scan and apply saves its
    directory), containment inside the data dir, symlinks
    never followed/removed, and a missing/unreadable database
    judges NO database category (filesystem categories still
    scan). Doctor bug found by the scan and FIXED in-slice:
    check_assets counted a directory orphaned unless its
    character currently had an avatar — now every character
    row owns its directory (soft-deleted included, S303
    restore custody), only no-row directories are orphaned;
    S804 suite stays green. Doc: docs/CLEANUP_TOOL_2026-10-31.md
    + tests tests/test_f04_cleanup.py (14 tests). The delta
    table gained its appended F-04 follow-on closing ST-73
    (original verdict stands) and the clean-room log its F-04
    entry (own tree only). Full suite re-run this tick on the
    VM (sanitised proxy env): 789 passed, 6 skipped, 0 failed
    — F-03 baseline 775 + 14 new. Ruff clean on all touched
    files. THE PART I FOLLOW-ON BLOCK (F-01–F-04) IS NOW
    COMPLETE — every NO-HOME row the P-014 gate homed is built.
- IN PROGRESS: none (tick closing cleanly).
- Next slice: P-015, character card v2 import with full field
  fidelity (Part II — Cards & Content Interop, first slice).

Last updated: 2026-10-31 00:31 EDT tick (F-04 banked)
