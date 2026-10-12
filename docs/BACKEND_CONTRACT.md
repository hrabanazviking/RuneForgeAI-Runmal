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