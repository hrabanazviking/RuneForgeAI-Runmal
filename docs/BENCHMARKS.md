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