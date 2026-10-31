# P-007 — Fresh Baseline (2026-10-30)

*The full suite re-run at campaign start; counts from the runner
only. The remembered 686 passed / 3 skipped (purplelongship, S805
evidence run `538c918`) is a rumour until re-measured — this file is
the re-measurement for the Two Mirrors tree.*

## Measured baseline (banked)

- Tree: `yrsa/two-mirrors-build` at cf9ae3f (roadmap filing on top
  of main 61ef166), clone `~/workspace/runmal-build`, Python 3.12.3
  venv, core + dev extras only (no voice extras).
- Host: Yrsa's VM (the purplelongship leg is the platform-discipline
  confirmation leg and remains owed at the Part I gate, P-014; this
  VM run is the fresh baseline for this tree, recorded as such).
- Command: full `pytest -q` with the VM's proxy environment
  sanitised for local tests (see the environment finding below).
- Result, reproduced twice in a row (89–91 s each):
  **685 passed, 6 skipped, 0 failed — 691 collected.**
- The 6 skips, named by the runner: live Ollama not required
  (test_s302_ollama), no local Ollama (test_s307_seam), sounddevice
  unavailable on this host (test_s501_audio), real silero_vad.onnx
  not downloaded (test_s502_vad), faster-whisper/ffmpeg not
  installed (test_s503_stt), UDP send unavailable in this
  environment (test_s605_vrchat_osc). All six are host-absence
  skips, consistent with a VM without the voice extras or a local
  Ollama — they explain the difference from purplelongship's
  686 passed / 3 skipped rather than contradicting it.

## Environment finding (why two earlier runs in this tick lied)

Two unsanitised full runs in this same tick reported shifting
failures (first 689 passed / 3 skipped / 2 failed, then 680 passed /
6 skipped / 5 failed, with changing failing tests). Root cause was
proven, not guessed:

- This VM's `no_proxy`/`NO_PROXY` contains bracketed IPv6 entries
  (`[::1]`, `[fd8b:…::1]`, …). The installed httpx version misparses
  them when any client is built with the default `trust_env=True`,
  raising `httpx.InvalidURL: Invalid port: ':1]'` for an ordinary
  `base_url="http://127.0.0.1:9000/v1"`.
- Minimal repro: the client construction fails with the VM env and
  succeeds with `no_proxy` unset; the Aesir/profile tests
  (test_s701, test_s703, test_s706, test_s306, test_s311) fail
  under the VM env in isolation and the full suite is green and
  stable with proxy variables removed and
  `NO_PROXY=localhost,127.0.0.1,::1`.

Verdict: **environment artefact of the VM, not a Rúnmál defect.**
No repo code was changed for it. Any future suite run on this VM
must sanitise the proxy env first, or its counts are not evidence.
The purplelongship evidence runs never carried this env, which is
why the founding counts were clean.

## Standing instruction for this campaign's runs on the VM

```sh
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 \
    .venv/bin/python -m pytest -q
```
