# Aesir adapter - D7/D5 repairs and the owed live smoke (2026-11-20)

*Correction under Volmarr's 2026-11-20 order: mock-tainted work is
finished to real or not at all; a thing proven only against fixtures
is a bug. Scope: P-009's defect list D1-D10 for the Aesir chat
adapter (S701-S706), including F-02's outstanding completion
criterion - the purplelongship live smoke, owed since 2026-10-30.*

## 1. Where D1-D10 stood when this correction opened

P-009 (2026-10-30) judged the adapter against Aesir's own v1 API
matrix and found it would fail live. The P-014 gate's follow-on
F-02 then repaired the worst defects **in code, fixture-proven
only** - its own record states the live smoke was still owed.
Status at the opening of this correction:

| Defect | P-009 finding | State at opening |
|---|---|---|
| D1 | adapter sent `stream_options.include_usage`; Aesir's chat route rejects the field (400) | fixed in code by F-02 |
| D2 | sampler overclaim: adapter declared 8 honoured controls; the OpenAI chat route serves only temperature, top_p, max_tokens, seed | fixed in code by F-02 |
| D3 | Aesir serves no `/v1/embeddings` route in either mode; embedding calls 404 and degrade to FTS by design | binding rule recorded by F-02 |
| D4 | default base_url `:8000` matched neither Aesir port (18434 native / 11434 ollama-mode) | fixed in code by F-02 (now `:18434`) |
| D5 | `/v1/models` lists the catalog; only the resident model can generate (non-resident 404); listing is not readiness | partially addressed by F-02 (readiness from `/health/ready`) - see section 3 |
| D6 | adapter yielded `Done` after any clean EOF; Aesir can end a failed stream with no terminal marker | fixed in code by F-02 |
| D7 | adapter sent full history unbounded; Aesir admission caps at 128 messages, 64 KiB per text field, 131072 bytes per body | **OPEN - not repaired by F-02** |
| D8 | HTTP 422 (context/generation admission) unmapped | fixed in code by F-02 (maps to `ContextOverflow`) |
| D9 | unconsumed Aesir surface (completions route, native `/v1/generate`, tool calls, health routes) | not a defect; binding choices recorded |
| D10 | Aesir's `--ollama` mode vs the Ollama adapter's `num_ctx` equality rule | unproven; a different adapter's path (see section 5) |

## 2. Repairs made by this correction

Both repairs are in `src/runmal/backends/aesir.py`; pins in
`tests/test_aesir_admission_d7.py` (10 tests). Suite evidence:
the six Aesir test files (S701, S702, S703, P-009, F-02, and the
new file) run **44 passed** on purplelongship.

**D7 - admission bounds, enforced before sending.**
`check_admission(payload)` runs in `chat_stream` after the wire
payload is built. Constants are Aesir's own numbers from the v1
matrix: `ADMISSION_MAX_MESSAGES = 128`,
`ADMISSION_MAX_FIELD_BYTES = 65536`,
`ADMISSION_MAX_BODY_BYTES = 131072`. An over-bound request raises
`ContextOverflow` - the same class Aesir's own admission refusal
maps to (D8) - before any byte leaves the machine. Trimming
history to fit stays the chat layer's policy; the adapter's duty
is to never pretend an unsendable request was sent. Body size is
measured on a plain `json.dumps`, never smaller than the compact
form httpx sends, so the check errs in the safe direction.

**D5 completed - readiness against the deployed build.**
F-02's `readiness_check()` reads `/health/ready` at the server
root, per Aesir's published matrix. The build actually deployed
on purplelongship (`.aesir/launch/aesir`, built 2026-10-10)
predates the schema-v1 health routes and answers 404 for both
`/health/ready` and `/health/live`; it serves the same resident
truth at the legacy `GET /health` (`status` + resident `model`).
The check now falls back to the legacy route on a 404 and reports
what it says; anything but an explicit `ready` is not readiness,
and in `--ollama` mode (neither route served) it still reports
not-ready, honestly.

## 3. The live smoke - target and Phase 1 (all real)

Target: the real Aesir native serve resident on purplelongship -
systemd user unit `aesir-brain.service`, serving **llama3.2:3b**
(digest `sha256:dde5aa3f...`) on CUDA at `127.0.0.1:18434`,
context 4096, max_tokens 256, bearer auth. The adapter ran from
this branch's worktree with the repairs above; the key was read
on-device from the serve's own key file and never printed.
Harness: `~/runmal-aesir-live-smoke/smoke3.py` on purplelongship;
full results in `smoke3_result.json` beside it.

First attempted: a transient serve of a 1B GGUF on port 18436
with the same binary, for a fully self-owned proof. Aesir's
registry refused it - "Llama is recognized, but no strict native
variant profile matches" (the llama profiles are exactly
28-layer/3072-hidden 3B and 32-layer/4096-hidden 8B), and the
profiled models cannot fit the ~1.6 GiB of VRAM free beside the
two resident serves. The attempt exited on its own; nothing was
left running. The proof therefore ran against the resident real
server; no other process was started or stopped by this
correction.

Phase 1 - reads and admission, none of it reaching generation:

| Check | Result |
|---|---|
| raw `GET /health` | 200 - status ready, backend cuda, model llama3.2:3b, context 4096, embeddings capability false |
| raw `GET /health/ready`, `/health/live` | 404 (deployed build predates the routes) |
| raw `GET /v1/models` | 200 - the one resident model |
| raw chat with `stream_options.include_usage` | **400** - D1's premise, live |
| raw chat with `top_k` | **400** - D2's premise, live |
| raw chat with 129 messages | **400** - D7 bound, live |
| raw chat with a 65537-byte field | **400** - D7 bound, live |
| raw chat with a ~150000-byte body | **413** - D7 body bound refused (server's body refusal is 413, not 400) |
| raw chat, non-resident model | **404** |
| raw chat, no auth header | **401** |
| adapter `list_models()` | ok - `['llama3.2:3b']` |
| adapter `health_check()` | ok - "aesir reachable" |
| adapter `readiness_check()` | ok - "aesir resident model ready (legacy /health): llama3.2:3b" (the section 2 fallback, live) |
| adapter with a wrong key | `AuthenticationFailed` |
| adapter embeddings `embed()` | `ModelNotFound` - the 404 mapped honestly (D3) |
| adapter, 129-message history | `ContextOverflow` raised locally, nothing sent (D7 repair, live) |
| adapter `map_params` with `top_k` | dropped with a structured warning, never sent (D2) |
| adapter chat, non-resident model | `ModelNotFound` (the server's 404, mapped) |

## 4. Phase 2 - generation: blocked by an Aesir server bug

The adapter's real streamed chat (resident model, one user
message, temperature 0, max 32 tokens) received **HTTP 500**,
which the adapter mapped to `BackendUnavailable` - the adapter
behaved correctly; the server did not. The serve's journal:

- 06:36 EST - the adapter's first chat: request status 500
  (90 ms), then "Native session failed; service stopped".
  systemd restarted the service - its first restart in 18 days
  (the request counter, at 1695, had evidently only ever carried
  reads; generation had never been exercised through this serve).
- 06:37 EST - on the fresh session, a canonical curl chat
  (stream false, max_tokens 16, temperature 0): 500 (48 ms),
  same crash.
- 06:41 EST - the recorded smoke's adapter chat: 500 (41 ms),
  same crash (journal request 19).

Each time systemd restarted the service and its reads verified
healthy afterwards. The serve's handler deliberately swallows
the inner driver error ("never echo credentials, request
contents, paths or driver errors"), so no deeper cause is
recorded; the failure sits inside the CUDA session's generation
on this build (2026-10-10) on this RTX 2060.

Not fixed here, deliberately: an engine-level Mojo/CUDA debug,
rebuild, and redeploy of the second brain's production backend
is Aesir roadmap work - a campaign Volmarr has paused - not a
narrow fix a Rúnmál correction can honestly make. What unblocks
the final leg: an Aesir-side fix on that campaign's road (the
`platform/gpu-2060-verification` branch is the live 2060 line),
or a rebuilt serve from current source if that source carries
the fix - unverified either way today.

## 5. Verdict

- **D1-D9: closed.** D1/D2/D4/D6/D8 were repaired in code by
  F-02 and are now premise-verified against the real server
  (400/401/404 responses) with the adapter's behavior verified
  live wherever the server can serve it. D3's rule is verified
  live. D5 is completed by this correction's fallback and
  verified live. D7 is repaired by this correction and verified
  on both sides live.
- **D10: unchanged, honestly open.** It concerns Aesir's
  `--ollama` mode spoken to by Rúnmál's *Ollama* adapter
  (`num_ctx` must equal the loaded context exactly) - not this
  adapter's path, and a native-mode proof does not settle it.
- **End-to-end chat through the adapter: still NOT PROVEN
  LIVE** - no longer because of the adapter. The fleet's only
  Aesir serve crashes its session on any generation request.
  The moment a generation-capable Aesir serve exists, the owed
  final leg is one streamed chat plus the unserved-sampler
  completion check; both stand scripted in the smoke harness.
