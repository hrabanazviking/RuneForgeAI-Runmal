# Rúnmál Benchmark Ledger

Internet benchmark numbers belong in research. **Rúnmál performance claims belong here only after they are measured on a recorded configuration.**

## Rules

1. Define the metric and acceptance threshold before judging the result.
2. Record hardware, OS, dependency versions, model IDs/quantization, relevant configuration and commit SHA.
3. Report distributions such as p50/p95 when measuring interactive latency, not one lucky run.
4. Keep warm/cold results separate when model load/cache state matters.
5. Do not compare unlike quality/configuration as if speed were the only variable.
6. A failed benchmark is evidence. Do not rewrite the threshold after seeing the result merely to make the slice green; revise the contract explicitly if the original target was wrong.

## Reference hardware targets

Populate exact machine details during S503/S504/S514. Initial known target class is Volmarr's Ryzen 9 laptop for CPU-oriented voice work, with local-model inference hardware varying by selected profile.

Do not fill exact CPU/GPU/RAM values here from memory. The benchmark command should record them from the actual test host.

## Voice benchmark template

```text
Date:
Commit:
OS/kernel:
CPU:
GPU:
RAM:
Power mode:

VAD:
  package/model/version:
  config:
  fixture corpus:
  speech-on latency p50/p95:
  false-positive/negative metric:

STT:
  model/quantization:
  threads/config:
  corpus:
  quality metric:
  RTF p50/p95:
  finalization latency p50/p95:

TTS:
  runtime/model/voice:
  text corpus:
  first-audio latency p50/p95:
  synthesis RTF:

Predeclared per-backend TTS thresholds (declared 2026-10-13, BEFORE any
measurement of these backends — S514/BENCHMARKS rule: thresholds are
never rewritten after results merely to pass). Reference hardware:
purplelongship (Ryzen 9, RTX 2060 Max-Q), model warm/loaded; model-load
time is reported separately and is not part of first-audio. Corpus: the
fixed S504 corpus (`TTS_CORPUS_TEXTS`).

  cosyvoice (CosyVoice2-0.5B, native streaming, GPU):
    first-audio p50 <= 1.5 s; synthesis RTF p50 <= 1.0
  chatterbox (Chatterbox, sentence-chunk streaming at the seam, GPU):
    first-chunk-audio p50 <= 4.0 s; synthesis RTF p50 <= 1.0

User-installed backends (kitten, piper) carry no predeclared thresholds:
they are not shipped, and any numbers measured for them are reported as
information only.

End-to-end:
  endpoint hangover:
  LLM model/backend:
  user-end-of-turn → first audio p50/p95:
  interruption detection → playback stop p50/p95:
```

## LLM backend benchmark template

```text
Date/commit:
Backend/provider:
Model:
Quantization/runtime:
Context size:
Prompt fixture:
Output length:
Cold/warm:

TTFT p50/p95:
Tokens/sec p50/p95:
Cancellation latency:
Errors/timeouts:
```

Provider billing/pricing belongs in a separate cost note because it changes faster than software performance.

## Memory benchmark/evaluation

Memory has correctness metrics before speed metrics.

Record:

- retrieval precision on deterministic scenario corpus;
- witness-scope leakage count (target zero);
- current-vs-superseded truth errors (target zero on fixture corpus);
- duplicate consolidation correctness;
- reindex/rebuild duration and post-rebuild semantic equivalence;
- retrieval latency p50/p95 at representative memory counts.

## Database/migration benchmark

For large personal histories, record:

- migration time by source schema/version;
- backup time/size;
- restore time;
- integrity-check time;
- vector/FTS rebuild time.

Performance never excuses data loss or bypassing validation.

## Results

No authoritative local Rúnmál benchmark results have been recorded yet. Campaign V/VII/VIII slices will append dated result sections rather than replacing old evidence, so regressions and hardware changes remain visible.

### 2026-10-13 — Campaign V voice benchmark (S514, `--real`, purplelongship)

Reference host: purplelongship (Ryzen 9, RTX 2060 Max-Q — GPU present but the shipped TTS tree runs the **CPU** torch build; see the license note in `docs/VOICE_LICENSE_MATRIX.md`). Environment: clean uv Python 3.12.13 venv, backends installed in one pass by the one-button machinery (`runmal.voice.install.run_install`); model warm/loaded, load time reported separately; corpus: the fixed S504 corpus (`TTS_CORPUS_TEXTS`).

```text
VAD: pass (predeclared segmentation contract)

STT (default shipped, faster-whisper small int8):
  WER 0.1111 (contract <= 0.25) — pass
  RTF p50 0.7095 (contract <= 1.0) — pass

TTS cosyvoice (CosyVoice2-0.5B, CPU build, zero-shot default voice):
  model load: 10.25 s (reported separately, per the rules)
  first-audio p50 23.15 s (predeclared <= 1.5 s) — NOT MET
  first-audio p95 23.63 s
  synthesis RTF p50 6.73 (predeclared <= 1.0) — NOT MET
  synthesis RTF p95 7.50
  Independent synthesis-evidence run, same host/build: first-audio
  p50 18.78 s, RTF p50 6.42, load 10.71 s (3 texts, run-to-run
  variance on a shared laptop; same order of magnitude).

TTS chatterbox: not run — backend HELD at admission (see matrix);
  its predeclared thresholds (first-chunk p50 <= 4.0 s, RTF <= 1.0)
  stand unmeasured and unrewritten.
TTS kitten / piper: not run — user-installed class, not installed;
  no predeclared thresholds bind them.

Interruption: pass (stop latency 0 ms vs 100 ms budget, fake TTS)
```

**Reading of the CosyVoice result, recorded plainly:** the thresholds were predeclared for the GPU reference configuration. The license gate (NVIDIA's wheels declare no license metadata) forces the shipped tree onto CPU torch builds, on which CosyVoice2-0.5B is roughly 6–7× slower than real time on this host. The backend is **admitted** (license gate green, real synthesis, streaming seam works) and its performance contract is **not met on the shipped build** — the thresholds were not adjusted after measurement, per this ledger's rule. A user who installs CUDA torch themselves (their own choice under the interoperability principle) would close most of this gap; re-measurement on a GPU build is future evidence, not a promise.
## S705 — Aesir cutover: adapter performance validation

*Declared 2026-10-13, BEFORE the benchmark exists or has run (ledger rule 1/6).*

**Question this benchmark answers.** Campaign VII moves profiles from Ollama/OpenRouter to Aesir behind the same seam. The part of that cutover *this repo owns* is the adapter layer: does speaking the Aesir surface cost more — in latency or throughput — than speaking Ollama's, for identical work? Live engine throughput (the Ollama server's or the Aesir server's tokens/sec) is **not** measured here: those are different programs in different repos, and Aesir's own benchmarking belongs to that project. What is measured is Rúnmál-side cost only, by replaying identical recorded token streams through both adapters over in-process fixture transports (`runmal.backends.benchmark`).

**Workload.** One stream of 256 text tokens (fixed texts `tok0 `…`tok255 `), wire-shaped per adapter: Ollama NDJSON lines for the Ollama adapter, OpenAI-style SSE `data:` lines for the Aesir adapter; identical token texts, identical usage totals. 15 runs per adapter; medians reported.

**Metrics per adapter:** time-to-first-normalized-token (ms, median), total stream time (ms, median), normalized tokens/sec (median).

**The bar (predeclared):**

1. Aesir median total stream time ≤ **1.5 ×** Ollama median total stream time (same host, same session).
2. Aesir median time-to-first-token ≤ Ollama median **+ 5 ms**.
3. Each adapter sustains ≥ **20,000** normalized tokens/sec median on the benchmark host — the seam must never be the bottleneck beside real engines, which generate at tens of tokens/sec.

**Configuration recording:** host CPU/OS/Python and the commit SHA are read from the benchmark host at run time by the benchmark command and appended with the results below.

**Results — run 2026-10-13 on purplelongship** (the forge laptop; config read from the host by the benchmark command):

```text
CPU: AMD Ryzen 9 4900HS with Radeon Graphics
OS: Linux-7.0.0-34-generic-x86_64-with-glibc2.43
Python: 3.14.4
Commit: e763c3269903ad85d2189bd008b5692873b4a67b
Workload: 256-token recorded stream, 15 runs per adapter, medians

Ollama adapter: TTFT p50 0.221 ms; total p50 0.768 ms; 333,391 tok/s
Aesir  adapter: TTFT p50 0.222 ms; total p50 0.928 ms; 275,848 tok/s
Token texts byte-identical through both seams (sha256 equal).

Bar 1 (total ratio <= 1.5):      1.209 — PASS
Bar 2 (TTFT delta <= +5 ms):     +0.001 ms — PASS
Bar 3 (>= 20,000 tok/s each):    333,391 / 275,848 — PASS
```

**Reading:** at the seam this repo owns, the Aesir surface costs ~21% more per-stream adapter time than Ollama's NDJSON path — inside the predeclared 1.5× bar, and in absolute terms under a millisecond for a 256-token stream (both adapters run two orders of magnitude faster than any real engine generates). The cutover is performance-neutral for Rúnmál's own layer. Live engine throughput remains, as declared, unmeasured here.
