# P-053 Evidence — Per-backend capability truth

- Slice: P-053 (Part IV), team-03, branch `yrsa/runmal-team-03`.
- Base: 6fc65f0 (P-050 banking record), worktree reset by keeper.
- Slice code commit: `491a6f9 (full hash in git log; this evidence amended onto it)` (evidence amended onto it; final
  HEAD reported in the team lead's handoff to the keeper).
- Commit-only: NOT pushed, NOT merged. Keeper banks in roadmap order
  (P-051, then P-052, then P-053).

## What was built
- `src/runmal/backends/capabilities.py` (new): the capability-truth
  layer. Per backend+model, every canonical sampler control is
  accounted for exactly once as `available` / `greyed` (reason_code +
  reason + source as data) / `hidden` (non-canonical, never offered).
  Truth derives from the adapters' own published sets (imported,
  never copied). `AESIR_LEDGER` carries Aesir's route ledger as data
  (openai-chat subset vs native-generate full set, P-009 D2); rows
  name their route + provenance (`declared` / `ledger`; no row claims
  `measured`). `audit_truth()` returns drift findings across adapter
  sets, default models, S208 profiles, and the ledger.
  `partition_bag()` is the pre-flight mirror of clamp_params.
- `src/runmal/prompt/router.py`: `GET /debug/backend-capabilities`
  (matrix + audit) and `GET /debug/backend-capabilities/{backend_key}`
  (404 unknown; `?aesir_route=` for Aesir's native ledger view),
  following the P-050 /debug pattern.
- `docs/BACKEND_CAPABILITY_TRUTH_2026-11-06.md`: the slice doc.
- `tests/test_p053_capability_truth.py`: 40-test battery pinning the
  honesty contract (accounting per backend, provenance, ledger rows,
  unknown→hidden, audit clean, clamp agreement, partition, API).

## Defect found + fixed in scope (never-leave-a-bug law)
- S208 drift: `generation/compat.py`'s OLLAMA_PROFILE dropped the
  Ollama adapter's declared `min_p` and `context_length` as "unknown
  parameter", while the adapter's own options path honours both —
  through the generation-manifest path (P-021) those controls were
  silently lost. Fixed: profile maps `min_p→min_p`,
  `context_length→num_ctx` (the adapter's own wire names);
  OPENAI_PROFILE gained named unsupported reasons for `min_p` /
  `context_length` instead of the generic unknown drop.
- Two P-021 tests pinned the drifted behaviour
  (`test_imported_preset_drives_generation_manifest`,
  `test_s208_ollama_filter_on_imported_bag`); both were updated
  deliberately in place with P-053 comments recording why (the P-008
  ledger pattern: a pin recording a changed fact is updated
  deliberately, never silently). No other test files changed.

## Counts (purplelongship, PYTHONPATH=worktree/src, venv312)
- Battery `tests/test_p053_capability_truth.py`: 40 passed.
- Neighbours (s208, s310 ×2, f01, p008, p049, p050, s701, p009):
  127 passed.
- Post-patch check (p021 + p053 + s208): 100 passed.
- FULL suite, first run: 2348 passed, 4 skipped, 2 failed — the two
  P-021 drift pins above (log: hidden_files/P053_FULL_SUITE.log).
- FULL suite, final run: **2350 passed, 4 skipped, 0 failed**
  (log: hidden_files/P053_FULL_SUITE2.log). No s503 contention noise
  appeared in either run.

## Migration statement
NO migration. Head stays 0032. No schema change; the truth layer is
pure data derived from adapter declarations at runtime.

## P-052 overlap flags (for keeper reconciliation at banking)
- P-052 (team-02 ed01f90, unbanked) extends the sampler VOCABULARY
  (DRY/XTC-class controls). This slice was built, per orders, against
  the 11-control canonical vocabulary at base 6fc65f0
  (`negotiation.CANONICAL_CONTROLS`).
- Reconciliation expectation: P-051 and P-052 bank first. When
  P-052's vocabulary lands, P-053's rows derive from the adapters'
  declared sets, so new controls flow through the same accounting
  automatically IF P-052's adapters declare them in their
  SAMPLERS/SUPPORTED sets; `audit_truth()` will flag any control a
  P-052 adapter declares but an S208 profile (or vice versa) does
  not account for. If P-052 renamed or restructured
  `negotiation.CANONICAL_CONTROLS` or the adapters' set names, the
  keeper should expect a small merge touch in
  `backends/capabilities.py` imports — the module reads
  `CANONICAL_CONTROLS`, `aesir.SAMPLERS/UNSUPPORTED_SAMPLERS`,
  `ollama.SAMPLERS/_OPTION_NAMES`, `openai_compat.SAMPLERS/
  UNSUPPORTED_SAMPLERS/WIRE_NAMES`, `openrouter.SAMPLERS/_WIRE_NAMES`,
  `fake.SUPPORTED`.
- The compat.py drift fix touches the same file a P-052 sampler
  extension may also touch (PROFILES): merge surface is the two
  profile literals; P-053's changes are additive keys only.

## Carried limitations (honest)
- Truth is `declared`/`ledger`, never `measured`: no live-server
  probing exists in this tree, and no row pretends otherwise. A
  future slice could add a probe that upgrades a row's source to
  measured with the probe result as data.
- Aesir's native-generate ledger row is Aesir's published matrix
  (via P-009), not a route this adapter speaks; rows judged against
  it are labelled with the route so the distinction is never blurred.
- Backends without an explicit UNSUPPORTED set (ollama, openrouter,
  fake) derive it as the exact complement of their declared set;
  the derivation is stated in the module docstring, not hidden.

## Team muster note
Work executed solo-sequentially by the team lead: the worktree lives
on the shared laptop where parallel device invokes race (AGENTS.md),
and the campaign's gradual-muster rule caps concurrent spawns; the
six Forge plugs (scout, design, build ×3 surfaces, test) were run in
sequence and are all evidenced above (P053_SCOUT.md, P053_DESIGN.md,
this file, suite logs in hidden_files/).
