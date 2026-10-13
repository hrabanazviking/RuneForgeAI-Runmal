# Rúnmál Backend Contract

Rúnmál treats model providers as replaceable engines. Provider identity must not infect chat, memory, prompt or bridge code.

## 1. Separate capabilities

Do not force one provider to own every modality. A conversation profile may compose independent services:

```text
ConversationProfile
├── ChatBackend
├── EmbeddingBackend
├── STTBackend
└── TTSBackend
```

A local embedding model may therefore serve memory while the conversational model comes from OpenRouter, Ollama or Aesir.

## 2. Chat backend interface

A chat backend must expose conceptually:

- `chat_stream(messages, params, cancellation)` → async normalized event stream
- `list_models()` → normalized model metadata
- `health_check()`
- `count_tokens()` or a documented conservative estimator
- capability declaration

Only streaming needs a provider-specific implementation. Non-streaming chat may accumulate the stream.

## 3. Normalized generation events

Minimum event vocabulary:

- `TextDelta(text)`
- `UsageUpdate(...)` when available
- `ToolDelta(...)` only when tools become supported
- `Done(reason, usage)`
- `Error(code, message, retryable, provider_detail_ref)`

Raw provider bytes never cross the adapter boundary.

## 4. Sampling parameters

Rúnmál owns a canonical `SamplingParams` vocabulary. Adapters map it to provider-native names.

Possible fields include temperature, top-p, top-k, min-p, repetition penalty, presence/frequency penalty, max output tokens, stop sequences, seed and requested context length where supported.

Unsupported parameters are declared in capability metadata and omitted with a structured warning. Rúnmál must not claim that a backend honored a parameter it silently ignored.

## 5. Capability negotiation

`ModelInfo`/capability metadata should be able to represent:

- chat/text support;
- embeddings support;
- vision support;
- tool/function support;
- streaming support;
- context length;
- maximum output tokens;
- token-counting quality (`exact`, `provider`, `estimated`);
- sampler/control support;
- structured-output support when added.

The UI and prompt engine should consume these declarations rather than hard-coded provider names.

## 6. Error taxonomy

Provider errors normalize into at least:

- `BackendUnavailable`
- `AuthenticationFailed`
- `RateLimited`
- `ContextOverflow`
- `ModelNotFound`
- `InvalidRequest`
- `Timeout`
- `GenerationCancelled`
- `ProviderError`

Errors may retain a safe diagnostic reference to provider detail, but secrets/raw headers are never surfaced.

## 7. Retry contract

Automatic retry is allowed only when semantics are clear.

- Before visible output begins, a configured retry may repeat the same provider/model or use an explicitly configured fallback policy.
- After visible output begins, Rúnmál does **not** silently restart the answer on a different provider/model.
- Retried requests carry enough identity to prevent duplicate persisted assistant turns.
- Rate-limit backoff is bounded and cancellation-aware.

## 8. Cancellation

Cancellation is a first-class input. Client disconnect, user Stop, barge-in and bridge cancellation all propagate through the chat backend as far upstream as possible.

Adapters must close HTTP streams/connections promptly and must not leave orphan generation tasks.

## 9. Embedding backend interface

Embedding is independent from chat inference:

- `embed(texts)` → vectors + embedding provenance
- `model_info()` → model ID, dimensions and other stable metadata
- `health_check()`

Every stored vector records provider/model/dimensions/version provenance. Incompatible spaces are isolated.

If embeddings are unavailable, the memory/RAG layer falls back to FTS5/structured retrieval.

## 10. Backend profiles

Persist named profiles rather than scattering provider settings through chats:

```text
Profile: Local Sovereign
  chat: Ollama / model X
  embeddings: Ollama / model Y
  STT: faster-whisper small
  TTS: local selected voice

Profile: Cloud Chat + Local Memory
  chat: OpenRouter / model Z
  embeddings: Ollama / model Y
  STT: local
  TTS: local
```

A chat references a profile plus any explicit per-chat overrides.

## 11. Secrets

Backend credentials are stored through the secrets subsystem. Backend configuration stores secret references, never secret values in ordinary settings tables or API responses.

## 12. Current adapter targets

### Ollama
Use native `/api/*` for the Ollama adapter where it preserves controls/capabilities better than OpenAI compatibility. Current native embedding endpoint is `POST /api/embed`; re-verify against official Ollama docs when implementing.

### OpenRouter
Use its OpenAI-compatible chat surface but normalize namespaced model IDs, routing metadata, errors and usage inside the adapter.

### Aesir
Prefer an OpenAI-compatible external surface when that reduces integration cost, but Rúnmál's internal contract remains its own normalized interface. Aesir must declare unsupported controls rather than accepting-and-ignoring them.

*As implemented (S701/S702, `src/runmal/backends/aesir.py`):* the adapter speaks the OpenAI-compatible surface (`POST /chat/completions` SSE, `GET /models`) at a profile-configurable `base_url` and passes the shared contract suite against recorded fixtures. The canonical → wire sampling mapping is a single public table (`WIRE_NAMES`, exercised by the same `map_params` path `chat_stream` uses):

| Canonical | Aesir wire | Notes |
|---|---|---|
| temperature | temperature | |
| top_p | top_p | |
| top_k | top_k | |
| min_p | min_p | |
| repetition_penalty | repeat_penalty | the one rename |
| max_tokens | max_tokens | |
| stop | stop | |
| seed | seed | |
| presence_penalty | — | **declared unsupported**: dropped with a structured warning, never sent |
| frequency_penalty | — | **declared unsupported**: dropped with a structured warning, never sent |
| context_length | — | **declared unsupported**: an engine property, not a per-request control |

Mapped and unsupported sets together account for every canonical control; there is no silently-ignored third category (INV-005). Token counting is the conservative estimator; server-reported usage surfaces as `UsageUpdate` events.

## 13. Contract tests

Each adapter must pass the same fake/recorded contract suite for:

- streaming text;
- terminal completion;
- cancellation;
- timeout;
- authentication failure;
- rate limiting;
- context overflow;
- unsupported sampler filtering;
- model metadata normalization;
- secret redaction.

Live-provider tests are separate and optional in ordinary CI.

## 14. Implementation status (Campaign III, S301–S308)

Implemented in `src/runmal/backends/` unless noted:

| Contract area | Module | Notes |
|---|---|---|
| Messages, events, errors, params, models (§2–§6) | `messages.py`, `events.py`, `errors.py`, `params.py`, `models.py`, `base.py` | `ChatBackend` ABC; `SamplingParams.to_bag()` uses S207 canonical names |
| Fake backend + contract checks (§13) | `fake.py`, `contract.py` | `contract.run_all(backend)` is the shared gate every adapter test runs |
| Ollama chat (§12) | `ollama.py` | Native `/api/chat` NDJSON; `num_predict`/`num_ctx` mappings; errors via `map_status_error`/`map_text_error` |
| OpenRouter chat (§12) | `openrouter.py` | OpenAI-compatible SSE; namespaced IDs live only in `ModelInfo` metadata; wire names per the S208 OpenAI profile |
| Embeddings (§9) | `embeddings.py` | `EmbeddingBackend` ABC + provenance; Ollama via native `POST /api/embed` (verified against official Ollama docs 2026-10-12); `embed_or_fallback()` returns the documented `FtsFallbackResult` — never a crash |
| Model listing / health / token counting (§5) | `registry.py` | `BackendRegistry` aggregates backends; every count carries `TokenQuality` (exact/provider/estimated) |
| Profiles + secrets (§10–§11) | `profiles.py`, DB migration `0012` | Profiles store ONLY secret references; values live in the server-side `secrets` table and resolve only inside the server (INV-023, canary-tested) |
| Chat wiring (§2, §8) | `generation/service.py`, `generation/router.py` (S307) | `/api/v1/generate` resolves the chat's persisted profile and streams through the seam |

Decisions recorded (see also `docs/adr/0004-normalized-backend-events.md`):

- **Failures raise.** Inside `chat_stream`, failures RAISE `BackendError`
  subclasses; `ErrorEvent` is the serializable form the service/API layer
  produces from them. Cancellation raises `GenerationCancelled`.
- **Cancellation (§8).** One `asyncio.Event` per request is shared from the
  generation service into the backend; adapters check it per chunk/line and
  close their HTTP stream promptly. No background generation tasks exist,
  so disconnects cannot orphan work.
- **Seam bridge (S307).** Normalized events bridge to the UI's SSE dicts:
  `TextDelta` → `{"type": "token"}`, `Done` → `{"type": "done",
  "finish_reason"}`, `UsageUpdate` → `{"type": "usage"}`, errors →
  `{"type": "error", "code", "message", "retryable"}` then a terminal
  `done`/`error`. Raw provider bytes never cross (§3).
- **Capability truth (§4–§5).** `ChatBackend.filter_params` clears
  unsupported samplers with structured warnings, driven by the model's
  declared `supported_samplers` — never by provider-name conditionals.
- **Token counting (§5).** Default `count_tokens` is the conservative
  estimator (`TokenQuality.ESTIMATED`); provider-reported usage surfaces
  as `PROVIDER`. The registry never upgrades a quality silently.