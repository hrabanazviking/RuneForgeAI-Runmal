# Rúnmál Testing Strategy

Testing exists to make AI-generated implementation cheap to produce but expensive to fool the system with.

## 1. Test classes

### Unit tests
Pure domain behavior: prompt slot budgeting, lore matching, score fusion, state transitions, sampler mapping, memory supersession.

### Contract tests
One suite applied to every implementation of an interface: chat backends, embedding backends, vector stores, STT/TTS providers, bridge adapters.

### Integration tests
SQLite + API + service interactions with real local components where practical.

### End-to-end tests
User workflows through the running application: import character → chat → memory → export/restore.

### Live-provider tests
Optional/tagged tests against Ollama/OpenRouter/Aesir or real audio devices. Ordinary CI must not require paid cloud credentials or a locally running Ollama daemon.

### Benchmark tests
Latency/throughput/quality measurements with explicit hardware/model/configuration. Benchmarks report numbers; they do not silently become unit-test assertions unless an acceptance threshold was defined beforehand.

## 2. Determinism

Tests should inject sources of nondeterminism:

- fake clock for decay/cooldowns;
- seeded RNG for probabilistic lore/speaker policy;
- fake/recorded model output for extraction/director logic;
- recorded provider streams for adapter parsing;
- fixture audio for VAD/STT/interrupt behavior.

Do not assert exact natural-language output from a live LLM as an ordinary test contract.

## 3. Golden prompt tests

Prompt Composer fixtures store structured expected slot manifests and, where useful, final rendered messages. Golden tests must make intentional updates obvious.

A prompt golden includes:

- model/context budget;
- reserved output budget;
- ordered included slots;
- discarded slots with reason;
- lore activations;
- memory recall IDs/reasons;
- final token estimate/count method.

## 4. Character-card compatibility corpus

Keep legal redistributable fixtures for v1, v2 and current v3/CHARX shapes, including:

- unknown extension fields;
- assets;
- alternate greetings;
- embedded lorebook;
- unicode/multilingual content;
- PNG metadata chunks;
- malformed/truncated inputs for rejection tests.

Round-trip tests compare semantic card data and opaque fields losslessly. Binary PNG output need not be byte-identical if metadata chunk ordering/compression differs, but re-imported card data/assets must match the compatibility contract.

## 5. Migration tests

Store representative database fixtures from released schema versions. CI upgrades each fixture to HEAD and verifies invariants/content.

A migration is incomplete if only a fresh database works.

*As implemented (S803):* fixtures live in `tests/fixtures/upgrades/runmal-<revision>.db` (revisions 0001, 0009, 0016), generated deterministically by `scripts/make_upgrade_fixtures.py` — real era schemas from the migration modules themselves, seeded with sentinel rows, self-checked for FK/integrity cleanliness at their own revision. `tests/test_s803_upgrade_harness.py` upgrades a copy of each fixture to HEAD with the real runner and asserts: the exact remaining migration tail applied, row counts preserved for every era table, `integrity_check` ok, `foreign_key_check` clean, sentinel content intact, and re-running at HEAD is a no-op. The harness runs in the ordinary suite, which is the CI upgrade path.

## 6. Memory evaluation corpus

Use scenarios from `MEMORY_ARCHITECTURE.md`: duplicates, corrections, temporal changes, witness-private facts, multi-source provenance, deletion, re-embedding and decay.

Tests inspect recall candidates and provenance, not only final generated prose.

## 7. Backend adapter suite

Every chat backend is tested for normal streaming, terminal event, cancellation, timeout, authentication error, rate limit, context overflow, unsupported sampling fields, usage normalization and redaction.

Every embedding backend is tested for dimensions/provenance and incompatible-space isolation.

## 8. Voice testing

Use generated/redistributable fixture audio for:

- clean speech;
- noise/transients;
- backchannels;
- interruption;
- echo/self-trigger scenarios.

Hardware-in-loop tests are tagged separately. Acceptance thresholds such as RTF or first-audio latency must be written **before** benchmark results are judged.

## 9. Security negative tests

Assert absence as aggressively as presence:

- secret not in API response;
- secret not in log capture;
- secret not in portable export;
- wrong bridge scope denied;
- revoked token denied;
- path traversal archive rejected;
- unexpected origin rejected under browser-auth contract.

## 10. Property/fuzz testing candidates

Use property-based/fuzz testing where it has leverage:

- card parser round trips;
- lore recursion termination;
- prompt budget never exceeds allowed budget after reservation;
- arbitrary message edit/delete sequences preserve database invariants;
- bridge idempotency keys never duplicate writes;
- provider-stream parsers never crash on legal chunk boundaries.

## 11. Slice completion

A roadmap slice is complete only when:

1. its acceptance contract passes;
2. newly introduced behavior has tests at the appropriate level;
3. docs/invariants affected by the change are updated;
4. known limitations are recorded rather than hidden.

## 12. S101 correction

Pytest returns exit code 5 when no tests are collected. The repository scaffold therefore includes at least one smoke test and requires `pytest` exit code 0; "green on empty suite" is not a valid acceptance contract.