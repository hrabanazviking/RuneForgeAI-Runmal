# F-01 — Generic OpenAI-Compatible Adapter (2026-10-30)

*Part I follow-on F-01, homed by the P-014 gate from P-008's first
recommendation: "one adapter covering the 14 WANTED-GENERIC backend
rows, chat plus embeddings, passing the shared backend contract
suite, with the connection layer's already-promised `openai` kind
made real behind it." This record is that build. No external
source was consulted and no mirror was read for this slice: the
wire shape is the one this tree already speaks twice (the S303
OpenRouter adapter and the S701 Aesir adapter) and that the S208
compatibility layer already declares as its `openai` profile.*

## What was built

- **Chat adapter** — `src/runmal/backends/openai_compat.py`,
  `OpenAICompatibleChatBackend`, `backend_key="openai"`. Speaks
  `POST /chat/completions` (SSE) and `GET /models` against a
  profile-configured `base_url` (default
  `https://api.openai.com/v1`), with an optional bearer key from a
  profile secret reference, resolved server-side only (INV-023).
- **Embeddings adapter** — `OpenAICompatibleEmbeddingBackend` in
  `src/runmal/backends/embeddings.py`, `backend_key="openai"`,
  `POST /embeddings`, provenance `{provider="openai", model, dims,
  version}` on every result (INV-019), independent of the chat
  adapter per ADR-0001, degrading through `embed_or_fallback`
  exactly like every other embedding backend.
- **Profile wiring** — `CHAT_BACKENDS` and `EMBEDDING_BACKENDS` in
  `backends/profiles.py` both gained `"openai"`;
  `build_chat_backend` / `build_embedding_backend` construct the
  adapters from the profile's model, secret reference, and
  `config.base_url`. The connection layer (S211) already named
  this kind; it now has an engine behind it, so no connection-layer
  change was needed.

## Sampler truth

The adapter declares exactly the S208 `openai` compatibility
profile's key set — temperature, top_p, max_tokens,
frequency_penalty, presence_penalty, stop, seed — pinned by test
against `generation/compat.py`'s `OPENAI_PROFILE` itself, so the
two declarations cannot drift apart silently. The remaining
canonical controls (top_k, min_p, repetition_penalty,
context_length) are the declared unsupported set: together the two
sets account for every canonical control, and unsupported values
are cleared by `filter_params` with structured warnings — never
sent, never pretended honoured (INV-005). An endpoint that serves
more gets its own adapter or a measured declaration change, never
a silent field added here.

## Wire discipline (P-009's lessons, applied generically)

- **No `stream_options`, no usage toggle is sent.** P-009 proved a
  compatible server (Aesir) rejects `stream_options` outright;
  the generic request therefore carries only model, messages,
  `stream: true`, and declared samplers. Usage is surfaced
  whenever the server volunteers it in a chunk.
- **No fabricated `Done`.** A stream that ends with neither the
  `[DONE]` terminal marker nor a finish reason raises
  `ProviderError` ("stream ended without a terminal marker")
  instead of yielding a successful completion — the incomplete-
  stream honesty gap P-009 recorded as D6 for Aesir, closed here
  by construction. (F-02 carries the same repair to Aesir.)
- **422 maps to InvalidRequest**, alongside 400: compatible
  servers split between the two spellings for the same refusal.

## Coverage claim, stated exactly

The 14 WANTED-GENERIC rows of P-008 (OpenAI, Claude, Google AI
Studio, Mistral, DeepSeek, AI21, Cohere, Perplexity, Fireworks,
Custom/OpenAI-compatible, llama.cpp, Text Generation WebUI,
TabbyAPI, KoboldCpp) are covered **as profiles on this one
adapter, wherever the named service offers the OpenAI-compatible
surface** — which is the exact claim P-008 made for the build.
No bespoke per-brand adapter was built, none is implied, and no
live endpoint was called by this slice: the proof is the shared
contract suite plus fixture transports in
`tests/test_f01_openai_compat.py` (9 tests), including the
no-secret-leak canary check inside `contract.run_all`. The
ledger's closing entry is §8 of
`docs/BACKEND_PARITY_LEDGER_2026-10-30.md`, appended — its
original verdicts stand as the record of the gap.

## Deliberately updated pin

`tests/test_p008_backend_ledger.py` pinned the pre-F-01 tree
(four chat backends, the `openai` gap open) and instructed the
closing slice to update it on purpose. F-01 did: the pins now
record five chat backends and the closed gap, and the test
docstring names the change. No other Part I pin needed to move.

## What this slice does not do

- It calls no live endpoint and proves no named service's current
  surface; a profile against a real server is the user's act.
- It builds no text-completion paradigm (P-008 §4's WANTED-TEXT
  stays with Part IV) and no speech adapter (that is F-03).
- It touches no README.md and pushes nothing; banking is local.
