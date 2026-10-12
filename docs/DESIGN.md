# DESIGN.md — Sovereign AI Chat App (clean-room)

*Architecture for Volmarr's sovereign Python chat app. Derived from RESEARCH.md. All component shapes are original design; SillyTavern's ideas were studied, never its code.*

> **Name:** placeholder until Volmarr names it (his call, his joy).
> **Language:** Python. **License:** Volmarr's own (permissive, no copyleft taint — see License taint register in RESEARCH.md).

## 1. Component map

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                   │
│  Web UI (Jinja + htmx + Alpine; SSE token stream)                │
│  Voice island (vanilla JS: mic capture, audio playback, WS audio)│
│  Bridge clients: VRChat OSC bridge · Conan RCON bridge ·         │
│                  Skyrim-style HTTP bridge (scoped tokens)        │
└──────────────┬──────────────────────────────────────────────────┘
               │  HTTP REST + SSE (chat) · WebSocket (voice audio)
┌──────────────▼──────────────────────────────────────────────────┐
│                     FASTAPI APP (single service)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐    │
│  │ Chat     │ │ Persona  │ │ Lorebook │ │ Prompt Composer   │    │
│  │ Service  │ │ Service  │ │ Service  │ │ (ordered slots)   │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────────┬─────────┘    │
│  ┌────▼────────────▼────────────▼─────────────────▼─────────┐    │
│  │              INFERENCE SEAM (abstract)                    │    │
│  │  OllamaBackend (native /api) · OpenRouterBackend         │    │
│  │  (OpenAI-compat) · AesirBackend (Campaign VII)           │    │
│  └──────────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────────▼───────────────────────────────┐    │
│  │  MEMORY SUBSYSTEM: event extraction → sqlite-vec + FTS5   │    │
│  │  (hybrid retrieval, salience/decay, witness scoping)      │    │
│  └──────────────────────────┬───────────────────────────────┘    │
│  ┌──────────────────────────▼───────────────────────────────┐    │
│  │  VOICE PIPELINE (Campaign V): VAD → STT → LLM → TTS       │    │
│  │  (Silero VAD · faster-whisper small · Kokoro-82M ·        │    │
│  │   asyncio frame pipeline or Pipecat BSD-2)                │    │
│  └──────────────────────────────────────────────────────────┘    │
│  Hooks (typed server-side events) · Extension registry          │
│  (namespaced settings) · Secrets vault (server-side only)       │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│  STORAGE: single SQLite file (+ sqlite-vec) — chats, messages,  │
│  characters, lorebooks, presets, memories, vectors, settings    │
│  user_id columns from day one (multi-user later)                │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Data flow — text path

1. Client POSTs a message → Chat Service appends it to the chat's message rows.
2. Prompt Composer assembles the prompt from **ordered slots**: system/main instruction → persona (character card fields: description, personality, scenario) → memory nucleus → retrieved lorebook entries (before/after positions) → RAG memory events → example dialogue → chat history (token-budgeted, oldest summarized/trimmed) → Author's Note (depth-injected N messages from end) → post-history instructions.
3. Sampling preset resolves to `SamplingParams`; the Inference Seam's adapter filters params per backend.
4. `chat_stream` yields normalized `ChatEvent`s; FastAPI re-emits them as UI SSE events (never raw provider bytes).
5. Completed reply is persisted; memory subsystem extracts events/facts asynchronously (never blocks the reply).
6. Client disconnect cancels the upstream generation (no burned tokens).

## 3. Data flow — voice path

```
mic (16 kHz mono, ring buffer)
 → Silero VAD (512-sample frames, hysteresis 0.5/0.35, pre-roll 300–500 ms)
 → utterance segments → faster-whisper small int8 (beam 1, word timestamps)
 → turn detector (silence hangover ~400 ms; preemptive trigger on VAD-end + final transcript)
 → Prompt Composer (same slots as text; voice persona may set shorter-reply instructions)
 → Inference Seam chat_stream → sentence chunker
 → Kokoro-82M TTS per sentence (streaming; play while rest generates)
 → audio out (headset/speakers; virtual-cable route into VRChat)
BARGE-IN (parallel): VAD confirms user speech (~300 ms) → interruption event
 → cancel LLM stream + TTS playback → flush partial audio
 → HISTORY RECORDS ONLY AUDIO ACTUALLY PLAYED (the context-rewind rule)
 → new utterance becomes priority input
Backchannel tolerance: brief sounds ("mm-hm") don't interrupt; sustained speech does.
Per-stage latency metrics logged from day one.
```

Echo/self-interruption is treated as a first-class bug: verify with the agent speaking while room/game audio plays; headset separation or OS-level AEC.

## 4. Prompt composition (the durable idea, structured)

Slots are first-class (not string macros): each slot has a role, position, and token budget. Order: system → persona → memory nucleus → lorebook (before) → RAG events → examples → history → lorebook (after) → author's note (depth-injected) → post-history instructions. Lorebook scanning runs against recent messages (configurable depth); matched entries inject content only. Token budget enforced with per-slot priority; overflow trims oldest history first, then summarizes.

## 5. Storage schema sketch

Tables (SQLite, SQLAlchemy async; `user_id` on everything from day one):
- `users` (later), `characters` (card fields as columns + raw JSON for lossless round-trip + `extensions` opaque), `chats` (id, character/group refs, backend, preset, created), `messages` (chat_id, role, speaker, content, tokens, timestamps, *played_text* for voice), `lorebooks`, `lore_entries` (keys, secondary keys, constant/selective/sticky/cooldown/delay, order, position, priority, enabled), `presets` (name, param bag JSON, prompt-block order), `groups` (members, speaker policy, talkativeness, muted), `memories` (events/facts, salience, decay, witness chat/character refs), `vectors` (sqlite-vec `vec0` + (provider, model, dims) provenance), `settings` (namespaced), `secrets` (server-side only, never serialized to clients), `bridge_tokens` (scoped, revocable).

## 6. API sketch

REST domains (adopted from the studied shape, original implementation): `/api/characters`, `/api/chats`, `/api/groups`, `/api/lorebooks`, `/api/presets`, `/api/settings`, `/api/secrets` (server-only), `/api/backends` (list/configure/test), `/api/memory`, `/api/vector`. Generation: single `POST /api/generate` (SSE stream of normalized events) dispatching to provider adapters. Voice: WebSocket `/api/voice/session` (audio frames up, events + audio down). Bridges: `/api/bridge/*` (conversation state, persona switching, TTS hooks) behind scoped tokens. Frontend never holds secrets — the server injects auth headers.

## 7. Inference seam (recap from RESEARCH.md §4)

Abstract `InferenceBackend`: `chat_stream` (only streaming is implemented per backend; `chat` accumulates), `embed` (raises `EmbeddingsUnsupported` → RAG falls back to FTS5), `list_models`, `health_check`, `count_tokens`. Normalized `ChatEvent` (`TextDelta`/`Done`/`Error`), `SamplingParams` value object, `ModelInfo`. Adapters: Ollama via **native `/api/*`** (never the lossy `/v1` shim), OpenRouter via OpenAI-compat client, Aesir later (cheapest if it ships `/v1`-style endpoints). The seam absorbs all wire-format, param-name, auth-shape, and default-value divergence.

## 8. Extension model

Server-side Python hooks with typed payloads, keyed to the studied event taxonomy: message lifecycle (created/received/edited/deleted/streaming), generation lifecycle (prompt-ready, before/after assembly, started/stopped), chat/character/lorebook/preset/setting/backend changes. Extensions register prompt slots by name and get namespaced settings storage. No browser/Node dual runtime — a clean HTTP API with webhook-style callbacks covers the ground. Group-chat speaker selection is a pluggable policy (Manual/Natural/List/Pooled built in; LLM "director" later).

## 9. Non-goals (phase one)

Multi-user accounts, visual-novel sprite machinery, image generation UI, cloud hosting, mobile apps, plugin marketplace. The backend stays API-first so all of these can attach later without rewrites.
