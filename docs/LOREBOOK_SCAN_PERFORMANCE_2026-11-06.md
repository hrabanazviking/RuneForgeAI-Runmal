# Lorebook scan performance (P-046) — 2026-11-06

Roadmap line: *Performance: a 10,000-entry book scans within a
stated budget on Pi-class hardware.*

## The budget (stated BEFORE any measurement, design Sec.1)

BUDGET-P046: median Pi-equivalent wall time for one full scan
tick over the deterministic 10,000-entry book <= 2000 ms, AND
the keyword-scan component alone <= 1200 ms Pi-equivalent.
One tick (design Sec.0) = `scan_entries_windowed` (P-037 depth
window, last 10 messages) + `match_vectorised_sync` with the
local backend (provider local / model hash-ngram-1, 256 dims
— the no-external-provider default, hence the honest Pi case)
+ `activate()` over the combined hits. Recursive scanning is
out of the budget scope (opt-in, already token-budget-bounded);
it gains an equivalence test but no wall-clock bound.

Pi-class = Raspberry Pi 4 floor (quad Cortex-A72 @ 1.5 GHz,
4 GB). No Pi was available: numbers are measured on
purplelongship (AMD Ryzen 9 4900HS) pinned to ONE core
(`taskset -c 2`) and multiplied by a conservative x4.0
derating to get the Pi-equivalent figure (operative laptop
gates: full tick <= 500 ms, keyword <= 300 ms, single-core).
Every number below is a LAPTOP number plus that stated
derating — never presented as a Pi measurement.

## Result: BUDGET MET

Median of 15 pinned ticks (3 warmups discarded), seed 46046,
book = 7,000 plain keyword + 1,000 keyword-variant + 1,000
vectorised + 500 constant + 500 disabled entries, keyword hit
rate 3.00% (240 hits, design band 2–5%):

| component | BEFORE (ms) | AFTER (ms) | Pi-equiv AFTER | budget |
|---|---|---|---|---|
| keyword scan | 1451.4 | 14.3 | 57 ms | <= 1200 ms |
| vector match (cold) | 677.3 | 280.8 | 1123 ms | — |
| activate | 17.7 | 15.2 | 61 ms | — |
| TOTAL (cold cache) | 2144.8 | 310.1 | 1241 ms | <= 2000 ms |
| TOTAL (warm cache) | — | 65.0 | 260 ms | <= 2000 ms |

BEFORE = the pre-optimisation baseline recorded before any
P-046 code landed (hidden_files/P046_BENCH_BEFORE.txt); the
book, window, hit counts and activations (240 / 1000 / 1740)
are IDENTICAL before and after — speed changed, semantics
did not (the equivalence battery below is the proof).

## What was built

- scripts/bench_p046_scan.py — the benchmark harness (design
  Sec.2): the ONE deterministic 10k book generator (seed
  46046, shared with the battery by import), component timings
  (scan / vector / activate), machine + git-sha + derating in
  every output header, `--verify` hit-rate band check, and a
  `--cache` mode that reuses one EntryVectorCache across ticks
  for the warm-cache run.
- src/runmal/lorebooks/scan.py — the keyword core:
  - C1, compiled-pattern cache: `_compile` now goes through a
    bounded `functools.lru_cache` (8192) keyed by
    (key, whole_word, case_sensitive); identical pattern string
    and flags as before.
  - C3 + scout step 4, the window index (the change that
    actually meets the budget; see Finding 1): `_scan_texts`
    and `_near_misses_texts` build ONE `_WindowIndex` per
    window — maximal-word-token -> window-positions maps
    (exact tokens for case-sensitive matching, lowered tokens
    over ASCII texts for case-insensitive matching) plus the
    lowered texts for substring pre-checks — and `_match_keys`
    answers each key from the index. Every fast path is
    restricted to the domain where it is provably identical to
    the compiled-regex search it replaces (ASCII case folding
    is exactly lower(); a whole-word all-word-char key matches
    exactly a maximal token equal to it; an escaped literal
    with no boundaries IS a substring search). Anything
    outside that domain — non-ASCII texts or keys, whole-word
    keys containing non-word characters — falls back to the
    original regex search over the affected texts, with a
    substring pre-check that may skip the regex but never
    replaces it. Keyword median 1451 ms -> 14 ms.
- src/runmal/lorebooks/vector_match.py — the vector path:
  - C2, `EntryVectorCache` (the P-041 debt, in-process half):
    an opt-in, per-process, bounded LRU (default 20,000)
    accepted via `cache=` by both matchers. Keys carry the
    embedding space — (entry id, sha256(embed text), provider,
    model, dims, version), the codebase's own
    ``EmbeddingProvenance.key()`` identity — so a space switch
    misses structurally and spaces never mix (INV-019); an
    entry edit changes its embed text, hence its hash, hence
    its key (invalidation by content hash, no hooks). The
    query vector is NEVER cached. A warm tick embeds only the
    query plus cache misses in ONE batched call; if the
    embedder ANSWERS from a different space than the cache
    was read under (provider, model, version, or dims), or a
    cached vector's length contradicts the answered query,
    the cached vectors are discarded and everything is
    re-embedded rather than mixed. Vector component on the
    bench: 281 ms cold -> 35 ms warm; whole tick 310 ms ->
    65 ms.
  - Query-norm hoist: `match_with_vectors` computes the query
    norm once per tick (was: once per candidate, inside
    cosine_similarity); the arithmetic is identical (same dot
    order, same norm_b, same quotient) — pinned to full float
    equality by the equivalence battery.
  - `_feature_bucket` memoised (lru_cache 65536): the pure
    sha256 projection was recomputed per token/trigram per
    text per tick.
- src/runmal/lorebooks/preview.py — `preview_activation` gains
  the optional `vector_cache` argument, forwarded to the sync
  matcher; the default None is exactly the pre-P-046 behaviour.
- Battery (tests/): test_p046_equivalence.py (frozen
  pre-P-046 oracle vs live: seeded books 0/1/100/1000, special
  cases — punctuation keys, multiword keys, long-s folding,
  duplicate ids, all four selective gates — windowed scans
  with external context, near misses, recursive scans, vector
  scores to full float equality, and the full 10k book),
  test_p046_vector_cache.py (cold == warm == uncached, edited
  entry re-embeds alone, provider/model switch misses,
  returned-provenance mismatch discards, LRU bound, embed-call
  counting, async parity, preview forwarding), and
  test_p046_budget.py (@pytest.mark.manual tripwire: median
  tick <= 5.0 s absolute on a shared laptop, ~10x the derated
  gate, plus the 10k tick result equals the oracle result).

## Findings and in-slice fixes

- Finding 1 (design-level, fixed in-slice): the compiled-
  pattern cache (C1) alone CANNOT meet this budget on the
  design's own synthetic book. Its keys are unique per entry,
  so a per-key compile cache never hits within a tick (the
  BEFORE profile shows 15,076 compiles for 15,076 distinct
  keys, ~1.09 s of a 2.29 s scan) and the regex SEARCH itself
  costs a further ~1.13 s. With C1 + the vector fixes landed,
  the keyword component still measured 1425 ms against the
  300 ms laptop gate. The fresh profile is the evidence the
  design's C4 clause requires, and scout step 4 names the
  remedy (indexing): the window token index above. Recorded
  here rather than silently exceeding the design: C1 is kept
  (it serves the regex fallback paths and repeated keys in
  real books), but the index is what closes the budget.
- Review defects D1–D5 (found by the independent reviewer
  AFTER the slice's first commit, all fixed in-slice in the
  follow-up review-fix commit; the keeper banks both): the
  landed cache key and space tuples dropped the provenance
  `version` (D1 — a version bump scored stale vectors against
  a new-version query; reproduced before fixing), the
  space-mismatch guard compared only provider/model and
  never dims (D2 — an answered dims change silently dropped
  every cached candidate's score and degraded the tick to a
  fallback the uncached path never takes; reproduced), the
  dims=None lookup guess that fed it (D3 — now backstopped
  by an answered-query length check that needs no
  provenance), duplicate candidate ids resolving in the
  wrong order on the cached path (D4 — now candidate-order,
  last-wins like the uncached build), and re-embedded
  vectors from an unprovenanced second call being stored
  under the discarded space (D5 — now never stored). Five
  battery tests pin the fixes; the pre-fix versions of the
  D1/D2 scenarios fail against the landed code and pass
  after. One harness artefact in
  the predecessor's BEFORE profile (a stray /tmp/inspect.py
  shadowed the stdlib module and crashed the profiler
  preamble; its counts still printed) is a profiling-environment
  artefact, not a product defect; the AFTER profile was run
  from the worktree.

## Clean-room basis

Built from Runmal's own roadmap line, the P-046 scout and
design documents written in-tree for this slice, the P-041
slice record (which assigned the stored-vector cache to this
pass), and the in-tree scan/vector modules themselves. No
SillyTavern or Voxta source was inspected; the synthetic book
is generated from an embedded word list, and the battery's
fixtures are authored fresh in the test modules (P-005
discipline).

## Carried limitations (honest record)

- The derating is an estimate, not a Pi measurement: no real
  Pi-class hardware was available to this campaign. The x4.0
  factor is deliberately conservative (published Zen 2 vs
  A72 interpreter ratios sit nearer x3–x3.5, leaving margin
  for Pi thermal throttling and slower RAM), but a single
  direct run on a real Pi 4 remains the one-off validation
  that would replace it.
- The vector cache is in-process ONLY: it dies with its
  process, and there is still NO persistent or database-backed
  vector store — that remainder of the P-041 debt is carried,
  explicitly. No migration was taken (schema head stays 0032).
- No production caller yet owns a long-lived cache:
  preview_activation accepts one, but the router / state /
  binding paths do not yet hold a cache across ticks, so the
  warm-tick numbers are proven at the matcher/preview seam,
  not yet realised by the served paths. Wiring a per-process
  cache owner is a future slice's work.
- On a cold tick the local backend's own `_vector`
  (tokenising + hashed projection) is now the top remaining
  cost (~281 ms of the 310 ms tick); it is exactly what the
  cache amortises from the second tick on.
- Recursive scanning has no wall-clock bound in this slice
  (design Sec.0); it reuses the same indexed core, so it is
  faster by the same factor, and its results are pinned
  byte-identical by the equivalence battery.

## Evidence

- Battery: tests/test_p046_equivalence.py +
  tests/test_p046_vector_cache.py + tests/test_p046_budget.py
  — counts in hidden_files/P046_EVIDENCE.md, log
  hidden_files/p046_battery.log.
- Neighbours: hidden_files/p046_neighbours.log.
- Full suite: hidden_files/p046_fullsuite.log.
- Benches: hidden_files/P046_BENCH_BEFORE.txt (baseline),
  P046_BENCH_AFTER.txt (final, uncached), 
  P046_BENCH_AFTER_CACHE.txt (final, warm cache);
  profiles P046_PROFILE_BEFORE.txt / P046_PROFILE_AFTER.txt.
