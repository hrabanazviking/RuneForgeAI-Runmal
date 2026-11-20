# Aesir serve generation fault - root cause and fix (2026-11-20)

*Fault repair under Volmarr's direct order of 2026-11-20 ("fix the
fault in Project Aesir"), following the generation-leg block recorded
in `docs/AESIR_ADMISSION_REPAIR_AND_LIVE_SMOKE_2026-11-20.md`.
Scope: the one fault only. Aesir's roadmap campaign remains paused;
no roadmap slices, no QS-5, no soak.*

## Symptom

The resident Aesir native serve (systemd user unit
`aesir-brain.service`, llama3.2:3b on CUDA, 127.0.0.1:18434) answered
every read/admission request correctly but returned HTTP 500 to
every chat/generation request in ~25-90 ms, after which the process
exited with "Native session failed; service stopped" (raise site:
`aesir_engine/cli/native_serve.mojo` line 514 - the serve stops when
the session reports unhealthy after a request). systemd restarted
it each time. Reproduced four times in total: three by the
correction crew (06:36, 06:37, 06:41 EST) and once by this repair
(10:54 EST, canonical curl, HTTP 500 in 25 ms, journal request 11
status=500 elapsed_ms=25, then the same crash). Generation had
never succeeded through this serve: in 18 days its request counter
had only ever carried reads.

## Root cause (proven from disk)

The deployed executable was built for the wrong GPU architecture.

- `.aesir/launch/manifest.json` recorded `"target": "sm_89"` and
  the binary contains only sm_89 code (strings: 34x sm_89, 0x sm_75).
- purplelongship's GPU is an RTX 2060 Max-Q, compute capability 7.5
  (`nvidia-smi`), i.e. sm_75 (Turing). CUDA kernel images built for
  sm_89 cannot execute on an sm_75 device.
- Everything the serve does before generation - model load, weight
  upload (copies), HTTP admission - launches no compute kernels, so
  reads all worked. The first compute-kernel launches happen in the
  CUDA session's forward path (`aesir_engine/core/llama3_cuda.mojo`
  `forward()` / `begin_turn()`); the launch failure left the session
  unhealthy, which the serve maps to HTTP 500 and then stops itself.
  The serve deliberately swallows the inner driver error, which is
  why the journal only ever showed the outer message.
- `scripts/launch.py` defaults `--target` to sm_89 (line 122); the
  project's own `docs/SECOND_BRAIN.md` prescribes
  `python3 scripts/launch.py --build --target sm_75` for this
  machine and warns that "an sm_89 build is not a Turing execution
  proof." The 2026-10-10 deployment was built without the target
  override.

## Fix (Aesir-side change: rebuild only - no source changes)

1. Backed up the faulty build to
   `.aesir/launch.bak-2026-11-20-sm89/` (binary + manifest) on
   purplelongship.
2. Rebuilt from the same source with the documented command:
   `python3 scripts/launch.py --build --target sm_75`
   (pixi run --frozen mojo build --target-accelerator sm_75
   aesir_engine/main.mojo). The new manifest records target sm_75
   with the SAME source fingerprint
   (16af808b12ce3ac65a09bee6a1eed07f6b2f70407df3a821a53ff5eb74101597)
   as the faulty build - the only change is the target
   architecture. Binary strings: 34x sm_75, 0x sm_89.
   `scripts/launch.py --check` passes. `git status` in the Aesir
   checkout is clean: no tracked Aesir source file was modified.
3. Restarted `aesir-brain.service` (`systemctl --user restart`);
   the new instance (PID 3592889) reported "Native inference ready"
   and has NRestarts=0 since.

## Proof (all real, no fixtures/mocks/stubs)

- Direct canonical chat (same payload that crashed the old build):
  HTTP 200 in 0.52 s, content "Hello", finish_reason "stop";
  journal: [request=1 phase=generation] -> [request=1 status=200
  elapsed_ms=520]; service stayed active.
- Full live smoke re-run (`~/runmal-aesir-live-smoke/smoke3.py` ->
  `smoke4_result.json`), real requests through this branch's Aesir
  adapter against the real serve: every check passes except the
  pre-existing D7 oversized-body expectation (server refuses with
  413, the script expects 400 - unchanged before and after this
  fix; the refusal itself is correct). Generation leg now proven
  live: chat_stream_text PASS (streamed "Four."), chat_stream_done
  PASS (finish "stop"), chat_with_unserved_sampler_completes PASS
  ("Hello!"). Journal during the smoke: generation requests 19 and
  20, both status=200.

## Verdict

- The generation leg owed by the 2026-11-20 correction is now
  PROVEN LIVE end to end: real adapter -> real Aesir serve -> real
  completion. D1-D9 remain closed; D10 unchanged (Ollama adapter's
  path, unproven by this work).
- Left honestly open: the smoke script's 413-vs-400 expectation nit
  (not a server or adapter defect); the default in launch.py
  (`--target` defaults to sm_89) remains as upstream wrote it -
  noted here, not changed, as it is Aesir roadmap territory.
