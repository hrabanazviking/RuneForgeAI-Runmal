# D10 - Ollama adapter num_ctx path: live proof (2026-11-20)

*Final item of the 2026-11-20 correction (Volmarr's order: mock-tainted
work finished to real or not at all). P-009's D10: a second, unproven
interop path - Aesir's `--ollama` mode speaks the Ollama subset
Runmal's Ollama adapter targets, but its `num_ctx` must equal the
loaded context exactly, while the adapter sends `num_ctx` from the
canonical `context_length` control. Whether that pair works live was
NOT PROVEN. This record settles the adapter's path on real evidence
and states exactly what remains owed, and why.*

## 1. The code path, read from this tree

`SamplingParams.context_length`
(`src/runmal/backends/params.py`) reaches the wire as
`options.num_ctx` via `OllamaChatBackend._options` and
`_OPTION_NAMES` (`src/runmal/backends/ollama.py:44,102-105`); the
S208 compatibility profile maps the same control to the same wire
name (`src/runmal/generation/compat.py`, `OLLAMA_PROFILE`), and
`runmal.backends.capabilities.audit_truth` pins the two truth
sources to each other. The control is forwarded only when set; the
adapter neither clamps it nor invents a default.

**No defect was found in this path.** The num_ctx pins already
stand in `tests/test_p021_preset_interop.py` and
`tests/test_p053_capability_truth.py`; the S302 contract tests pin
the rest of the adapter's wire shape.

## 2. Leg A - live proof against the real Ollama server

Harness: `~/runmal-aesir-live-smoke/d10_smoke.py` (leg a), run
2026-11-20 on purplelongship. Target: the resident real Ollama
server (100.67.240.22:11434), driven end to end through this
branch's `OllamaChatBackend`, model `llama3.2:3b`. Every call a
real HTTP request to a real server running a real model; no
fixtures, mocks, or stubs anywhere in the path. Full result:
`~/runmal-aesir-live-smoke/d10_result_a.json`.

- `health_check` ok; `list_models` returned phi3:mini,
  llama3.2:3b, nomic-embed-text:latest.
- `context_length=4096`: streamed generation completed
  ("Four.", done_reason stop, usage 46 prompt / 3 completion
  tokens); `GET /api/ps` then reported the loaded runner's
  `context_length` = **4096**.
- `context_length=16384` (after a full unload): same generation;
  `/api/ps` reported `context_length` = **16384**.
- `context_length` unset: the adapter sent no `num_ctx`; the
  server ran its own default (4096 on this build) and generation
  completed.

The context size the adapter asks for is the context size the
server actually runs, demonstrated at two distinct values; and
the unset case - the only safe posture against an equality-rule
server - behaves exactly as designed.

## 3. Leg B - Aesir `--ollama` mode: attempted, blocked by the machine

A transient Aesir serve in `--ollama` mode was attempted for the
literal D10 pair (harness `~/runmal-aesir-live-smoke/d10_run_b.sh`;
scratch catalog store in the smoke dir, templated byte-for-byte
on the real catalog's entry format; the rebuilt sm_75 binary;
port 11437; the serve was stopped after every attempt and nothing
was left running; Aesir's own store, code, and standing serves
were never touched). Three serve-side facts, each proven on the
box:

1. The small model cannot serve at all. The 1B heretic GGUF
   (807,691,680 bytes) fails plan selection: `aesir inspect`
   reports Architecture llama, variant 1B, "no strict native
   variant profile matches", CUDA support: no, Compatibility:
   EXPERIMENTAL. The serve refuses it before any request.
2. The only strict-profile models on the box are the resident
   catalog's llama3.2:3b Q4_K_M (inspect: COMPATIBLE, CUDA yes;
   weights 2,019,377,376 bytes; estimated VRAM 2,961,552,100
   bytes at context 4096) and the L3-8B-Stheno set (>= 2.9 GB).
3. The 6 GB card already carries two standing serves this
   correction may not disturb - `aesir-brain.service` on :18434
   (2,462 MiB) and the team01-e02 serve on :18435 (2,068 MiB) -
   leaving ~1.6 GB free: less than the 3B's weights alone.

A live Aesir `--ollama`-mode instance therefore cannot run on
purplelongship today without stopping a standing serve. That leg
remains owed, with its reason now exact - P-009 could only say
"unproven"; the blocker is named and measured here. The owed run
stands scripted (`d10_run_b.sh` + `d10_smoke.py` leg b: equal
num_ctx must generate; a mismatched num_ctx is recorded raw and
through the adapter; unset must generate) for the first card
window in which a standing serve is legitimately down.

## 4. The binding rule D10 leaves behind

Against real Ollama, Runmal's `context_length` control is honest
and exact (section 2). Against an Aesir `--ollama` endpoint, the
same binding must either leave `context_length` unset - the serve
then uses its loaded context - or set it exactly equal to the
serve's loaded context (for the resident catalog model: 4096,
per its catalog `PARAMETER num_ctx 4096` and the brain serve's
`--context 4096`). Any other value is the server's to refuse; the
adapter's duty is to send exactly what the profile says and to
surface the server's answer in the S301 taxonomy - the behaviour
Leg A proves live.

## 5. Verdict

- **D10 is closed as to Runmal's code.** The num_ctx path was
  already correct; it is now PROVEN LIVE against a real Ollama
  server. No code change was made, and none was warranted -
  changing correct code to look busy would have been churn, not
  repair.
- The Aesir `--ollama`-mode instance proof remains owed for a
  measured machine-window reason (section 3), with its harness
  ready. It does not hold D10 open: D10 indicted the adapter's
  unproven path, and that path is now proven where Runmal's
  Ollama bindings actually run.
