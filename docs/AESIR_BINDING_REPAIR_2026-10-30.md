# F-02 — Aesir Binding Repair (2026-10-30)

*Part I follow-on F-02, homed by the P-014 gate from P-009's
first recommendation: "the minimum honest repair P-009 named —
stop sending `stream_options`, re-declare the OpenAI-route
sampler set to the served subset or rebind to the native
route, correct the default base URL, map 422, and require
the terminal marker before yielding Done. Aesir embeddings
bind to Ollama, never to Aesir, per P-009 D3." This record
is that build. No external source was consulted and no
mirror was read for this slice: its inputs are P-009's
ledger (which binds to Aesir's own v1 API matrix), the
P-014 gate's homing, and this tree.*

## Headline, kept honest

The code repair is banked and fixture-proven. **Aesir chat
through Rúnmál is still NOT PROVEN LIVE**: F-02's completion
also requires the owed live smoke (one real Aesir serve, one
Rúnmál chat, one model listing, run where Aesir runs), and
that smoke is a purplelongship leg the keeper cannot run.
Nothing in this record retires that claim.

## What was repaired

- **D1 — `stream_options` no longer sent.** The chat payload
  is now model, messages, `stream: true`, and served samplers
  only. Usage is surfaced whenever the server volunteers it;
  Aesir's matrix says its stream carries none, and none is
  requested.
- **D2 — sampler truth re-declared to the served subset.**
  The gate offered two cures; this repair takes the first.
  `SAMPLERS` is now exactly {temperature, top_p, max_tokens,
  seed} — what Aesir's OpenAI chat route accepts — with
  identity wire names. top_k, min_p, repetition_penalty and
  stop moved to the declared-unsupported set (with
  presence/frequency penalty and context_length): cleared
  with structured warnings, never sent, never pretended
  honoured (INV-005). Declared + unsupported still account
  for every canonical control. The native `/v1/generate`
  route, where the full set is served, remains the recorded
  alternative binding choice (P-009 D9) — not taken here,
  because it changes the paradigm, not just the binding.
- **D4 — default base URL corrected.** The adapter default,
  the profile builder's fallback, and the doctor's assumed
  default are now all `http://127.0.0.1:18434/v1` — Aesir's
  native serve port. The doctor keeps its copy as an
  import-light literal (it must work on a broken install);
  a test pins the two equal so they cannot drift apart
  silently again. Profiles may still configure any base URL,
  including the `--ollama` mode's 11434.
- **D8 — 422 maps to `ContextOverflow`.** Aesir's context /
  generation admission refusal now lands on the honest error
  class directly, not on a message heuristic.
- **D6 — no fabricated `Done`.** A stream ending with
  neither the `[DONE]` terminal marker nor a finish reason
  raises `ProviderError` ("stream ended without a terminal
  marker") — the same honesty rule F-01 built generically.
- **D5 / VX-19, narrowed home — resident readiness.**
  `AesirChatBackend.readiness_check()` reads Aesir's
  `/health/ready` at the server root (native mode; the route
  is not under `/v1`) and reports the resident-model truth,
  naming the resident model when the response carries it.
  A catalog listing is explicitly not readiness, and no VRAM
  quantity is estimated anywhere — the general VRAM
  estimator the gate dropped stays dropped. `health_check`
  remains the `/models` reachability probe that works in
  both modes, and is not upgraded into readiness.
- **D3 — the embeddings binding rule, recorded in code.**
  `AesirEmbeddingBackend`'s own docstring now states the
  rule where the next builder will read it: Aesir serves no
  embeddings route, the class is the S703 contract shape
  proven against fixtures only, and parity work binds
  embeddings to Ollama, never to Aesir, until Aesir
  publishes an embeddings route in a new matrix version.
  No embedding behaviour changed: against a real server the
  calls already 404-degraded to FTS by design.

## Deliberately updated pins

Three founding/Part I test files pinned the pre-repair tree
and were updated on purpose, each with its reason recorded
in the test itself:

- `tests/test_s701_aesir.py` — the wire-payload test now
  expects the served subset (and no `repeat_penalty`).
- `tests/test_s702_aesir_mapping.py` — `map_params`, the
  wire-never-carries test, and the S208 filter test now
  expect the re-declared sets.
- `tests/test_p009_aesir_readiness.py` — its pins now record
  the repaired tree; the ledger it guards gained the
  appended F-02 follow-on section (its original divergence
  record stands, unrewritten, as the record of the gap).

The new pin for this slice is `tests/test_f02_aesir_binding.py`
(11 tests): the shared backend contract suite, the three
default sites agreeing, sampler truth against the canonical
control set, the wire shape, the 422 mapping, the
incomplete-stream refusal, readiness at the server root and
its honest not-ready report, and the recorded D3 rule.

## What remains open after F-02

- **The live smoke — still owed, still the completion
  criterion that matters.** Until it runs on purplelongship,
  every "Aesir-ready" statement in parity work reads
  NOT PROVEN LIVE.
- **D7 (admission bounds) is not repaired here.** The
  adapter still sends full history unbounded against
  Aesir's 131072-byte / 128-message caps; the gate's F-02
  minimum did not name it, and history policy belongs to
  Part V (chat surgery) reckoning with it knowingly, as
  P-009 §3 assigned.
- **D9/D10 stand as recorded options**, not defects: the
  native `/v1/generate` binding, `/v1/completions`, the
  Boolean `response_format` subset, Gemma tool calls, and
  the unproven Ollama-mode interop path.
- No live endpoint was called, no README.md was touched,
  and nothing was pushed: banking is local.
