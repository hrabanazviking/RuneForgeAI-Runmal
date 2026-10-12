# RESEARCH.md — Sovereign AI Chat App (clean-room)

*Drafted 2026-10-12 by Yrsa's research coordination. All prose is original synthesis from public documentation and analyses. No SillyTavern (or any other project's) source code was read or reproduced. Brief fair-use field-name references only. Every load-bearing claim carries its source URL. Items marked **UNVERIFIED** need a docs check before build.*

**Clean-room statement:** This document studies *ideas* — data formats, interaction patterns, interface shapes — at the concept level. It contains no copied code, no copied config files, and no copied prose from the studied projects. Design shapes derived here are original.

---

## 1. SillyTavern feature anatomy (ideas studied, verdicts per area)

### 1.1 TavernCard v2/v3 — the character-card standard
The card is an open JSON schema. v1 was six flat fields (name, description, personality, scenario, first message, message examples). v2 wraps them in a `data` envelope marked `spec: "chara_card_v2"` and adds alternate greetings, a system-prompt override slot, post-history instructions, creator notes, an embedded lorebook, tags, creator attribution, a character version string, and an opaque `extensions` object that hosts must round-trip without destroying. v3 adds an `assets` array (alternate icons, backgrounds, emotion sprites) and multilingual fields, with a new `ccv3` PNG chunk label and an XCHAR archive container — classic `chara` embedding still supported.
Sources: https://github.com/malfoyslastname/character-card-spec-v2, https://github.com/kwaroran/character-card-spec-v3/blob/HEAD/concepts.md

Instructive field roles: description / personality / scenario / message-examples are *distinct prompt ingredients*, not redundant buckets. `creator_notes` is never injected into prompts. The `system_prompt` field supports an `{{original}}` macro so a card can pass through or replace the host default. Message examples are delimited by a `<START>` marker between exchanges. Template macros (`{{char}}`, `{{user}}`) are case-insensitive.
Source: https://github.com/peterpeet/claude-taverncard-skill/blob/HEAD/taverncard/SKILL.md

PNG embedding (concept): the avatar PNG doubles as the container — card JSON is base64-encoded into a PNG textual metadata chunk labeled `chara` (v2) or `ccv3` (v3); importers also accept iTXt/zTXt variants. Exporters must recompute chunk CRC32 or strict parsers flag corruption.
Sources: https://github.com/dhtadeo/airi/blob/HEAD/.agents/skills/airi-card-schema/SKILL.md

**Verdict: LEARN.** Import/export compatibility is table stakes. Preserve field roles exactly (creator_notes/tags/creator stay out of prompts), read v2+v3 with `chara`/`ccv3` chunk labels, honor `{{original}}`, keep `extensions` opaque-but-lossless, treat regex keys as preserved-but-inert.

### 1.2 Lorebooks / World Info
A lorebook is an entry list plus book-level activation knobs (scan depth, token budget, recursive scanning). Each entry: primary keys, secondary keys, content, enabled flag, ordering, placement (before/after character definitions, near example messages, top/bottom of author's note, in-chat at a depth), role, probability. Conditional machinery: `constant` (always inject), `selective` (requires keys from both sets, several logic modes), `sticky` / `cooldown` / `delay` (timed: persist N turns, suppress N turns, activate N turns in), recursion (one entry's content triggers others), weighted groups. Per-entry overrides fall back through book-level to global defaults via null-means-inherit tri-state. Scanning runs against a configurable depth of recent messages; whole-word and case-sensitivity toggles exist. Matched entries inject *content only* — keys are activation metadata, never injected. A token budget caps lore spend; per-entry priority decides discards.
Sources: https://github.com/yhhccl/opencode--airp-sillytavern/blob/HEAD/airp-sillytavern/references/sillytavern-structure.md, https://github.com/patcireamo/chungushub/blob/HEAD/architecture/lorebook.md

**Verdict: LEARN the entry model and activation semantics; ADAPT the resolution layer.** Adopt the field set for import compatibility (constant/selective/secondary-keys/timed effects are the genuinely good ideas). Simplify the fallback chain — entry→book→global null-inheritance is debugging hell; prefer explicit resolved values at write time.

### 1.3 Sampling presets
Presets are named bags of generation parameters. Portable set: temperature, top_p, frequency/presence penalties, repetition_penalty + range, max tokens, context length, stop sequences, seed. Local-only exotics (top_k, min_p, typical_p, mirostat, XTC, DRY, TFS, dynamic temp, beam search) are mostly llama.cpp-class; strict cloud endpoints choke on unknown fields, so adapters must filter params per backend.
Source: https://github.com/shenmintao/openclaw/blob/HEAD/extensions/sillytavern/skills/preset/SKILL.md

The more transferable idea is the *prompt template*: a preset is also an ordered list of prompt blocks (main instruction, persona, character description/personality, scenario, example dialogue, lorebook-before/after, chat history, post-history instructions), each with role and position — plus depth injection (Author's Note): re-injecting reinforcement text N messages from the end, since proximity to generation beats burying it in the system prompt.
Sources: https://github.com/maurovideosmr-wq/sillytavern-mcp/blob/HEAD/docs/JS-Slash-Runner-Distilled/presets.md, https://github.com/pslava/ai-character-chat/blob/HEAD/PROMPT_BUILD.md

**Verdict: ADAPT.** Keep the portable sampler set plus per-provider parameter filtering (never send unknown params to strict endpoints). Adopt the ordered prompt-block template with slot positions and depth injection — implemented as first-class structured slots, not string-macro assembly. Store presets as variable-shape param bags, not one column per knob.

### 1.4 Group chats
A room of member cards sharing one transcript; each message records its speaker; exactly one member generates per turn. Speaker strategies: Manual (you pick), Natural (name mentions whole-word from last message → per-character talkativeness probability → random fallback), List (round-robin), Pooled (random among members silent since last user message). Members can be muted; cards store a per-character talkativeness factor.
Source: https://github.com/sillytavern/sillytavern-docs/blob/HEAD/Usage/Characters/groupchats.md

Community pain: unmoderated groups produce all-at-once replies, spotlight-hogging, narrative drift — hence third-party "director" extensions (an extra pass picking speakers and injecting staging context).
Sources: https://github.com/windy-sora/sillytavern-groupdirector/blob/HEAD/README_EN.md

**Verdict: LEARN the four strategies; ADAPT with a director slot.** Ship Manual/Natural/List/Pooled with mute + talkativeness, but design speaker selection as a pluggable policy interface so an LLM "director" slots in natively later.

### 1.5 Extensions API
Three layers: (a) a ~103-event bus covering app lifecycle, message lifecycle (sent/received/edited/deleted/streaming), generation lifecycle (prompt-ready, before/after assembly, started/stopped), and chat/character/world-info/settings/connection/preset changes; (b) named prompt-injection slots for extensions; (c) server-side plugins with their own REST endpoints, plus a slash-command macro language. Extensions live in a user data folder with namespaced settings storage.
Sources: https://github.com/pavdig/sillytavern-docs-rag/blob/HEAD/docs/SillyTavern_For_Contributors_Writing-Extensions.md, https://docs.sillytavern.app/for-contributors/writing-extensions/

Key note: it's a *two-runtime* plugin model (browser JS + Node server) — powerful but heavy, and prompt slots are stringly-typed by convention. One analysis maps every built-in extension to plain API primitives (e.g., the Memory extension is just "read messages → summarize → write a constant lore entry"), suggesting much of the value needs no plugin system at all.

**Verdict: ADAPT.** Take the event taxonomy as a design checklist (message lifecycle, generation lifecycle, chat/character/world-info/preset/setting changes) but implement server-side Python hooks with typed payloads, not a browser event bus. A clean HTTP API with webhook-style callbacks covers the same ground. Namespaced per-extension settings storage — LEARN verbatim.

### 1.6 STT / TTS / image-generation wiring
Provider-multiplexed extensions: speech-recognition sources, image-generation sources (incl. local ComfyUI/Automatic1111), and 20+ TTS providers. Flow: mic → STT → transcript into input box; AI reply → per-character voice assignment → TTS → playback; image gen triggered by message actions, rendered inline. A "visual novel mode" adds sprites/emotion expressions driven by chat state.
Sources: https://github.com/SillyTavern/SillyTavern/releases/tag/1.15.0

**Verdict: LEARN the wiring pattern, ADAPT the abstraction.** Per-character voice assignment and provider-swappable STT/TTS are exactly what VRChat companions need. Make each modality a provider registry (name → adapter) behind a stable internal interface, so cloud-vs-local is a config choice, not a code branch. LEAVE visual-novel sprite machinery — presentation chrome, not core.

### 1.7 RAG / long-term memory (where we beat SillyTavern)
ST's built-in answer is modest (vector-storage extension + chat auto-summarization). Third-party extensions converge on the winning pattern: (1) extract events/facts from chat turns (LLM-assisted), (2) embed in a real vector DB, (3) hybrid semantic+keyword retrieval at generation time, injected as a prompt slot. Advanced systems add: knowledge graphs of (subject, predicate, object) facts; salience scoring with decay and recall-strengthening; per-character "memory nucleus" core biography always injected; **witness-scoped recall** (a character only remembers conversations they were present for — fixes "accidental omniscience"); shared lorebooks learned once across characters; edit/delete/rename sync so memories track chat mutations.
Sources: https://github.com/KritBlade/VectFox, https://github.com/arthur4002/openvault, https://github.com/icsli/sillytavern-uwu-memory

**Verdict: LEARN aggressively — our clearest differentiator.** Adopt the full stack: extracted-event memory with embeddings, per-character memory nuclei, witness-scoped recall (critical for group chats and honesty), chat-mutation sync. Implement natively in Python (sqlite-vec, no Docker requirement) rather than extension-shaped.

### 1.8 Server API surface
ST's internal structure is the clearest conceptual blueprint: `/api/characters` (card CRUD), `/api/chats` (logs), `/api/groups`, `/api/worldinfo` (lorebooks), `/api/settings`, `/api/secrets` (server-only, never to the browser), `/api/users` (multi-user auth). Generation via backend routers (chat-completions, text-completions, provider-specific). Media: `/api/sd`, `/api/speech`, `/api/vector`, `/api/translate`. The frontend never holds secrets; the server proxies with auth headers injected server-side.
Source: https://github.com/delfianto/the-bannered-mare/blob/HEAD/docs/sillytavern/analysis/code-structure.md

**Verdict: LEARN the domain split, ADAPT the transport.** Resource boundaries are exactly right for our REST API — adopt nearly verbatim. Two changes: (1) unify generation behind one `/generate` dispatching to provider adapters with per-provider param filtering, instead of parallel backend routers; (2) secrets stay server-side, obviously.

---

## 2. Real-time voice loop

Target: CPU-only Ryzen 9 laptop, ~2-second conversational turns, barge-in supported, permissive licenses only (MIT/Apache-2.0/BSD). All prose original synthesis; license statuses as reported in sources — **re-verify at distribution time.**

### 2.1 Voice Activity Detection — Silero VAD
A small recurrent network (~2 MB ONNX) ingests 16 kHz mono audio in 512-sample (32 ms) chunks with LSTM state carried between chunks, outputting per-chunk speech probability. A segment opens when probability crosses an upper threshold and closes only after staying below a lower threshold for a minimum silence — **hysteresis** (e.g., open 0.5 / close 0.35) stops jitter flicker. Parameters: minimum speech duration (~250 ms, rejects coughs/door slams), minimum silence (~100 ms), padding (~30 ms) both ends. Inference ~1 ms/frame on CPU — effectively free. A 300–500 ms **pre-roll buffer** before the VAD trigger prevents clipping the first word; a volume gate before the neural VAD is a common cheap first filter.
Sources: https://github.com/elite588/ai-engineering-from-scratch/blob/HEAD/phases/06-speech-and-audio/14-voice-activity-detection-turn-taking/docs/en.md, https://dev.to/kiarina/extracting-speech-segments-with-silero-vad-and-onnx-runtime-3h8a

What makes a VAD good for live conversation: low false-negatives on speech onset (missing speech kills barge-in), strong rejection of non-speech transients (where old WebRTC energy VAD fails), sub-frame latency, statefulness. One 2026 comparison: Silero ~87.7% true-positive @ 5% false-positive, ~1 ms latency vs WebRTC VAD's ~50% — "Silero is the right default." Alternatives: WebRTC VAD (BSD, fast but dumb), pyannote segmentation (more accurate, ~10 ms), Cobra (commercial). License reported MIT by multiple sources — re-verify.

**Endpointing is distinct from VAD:** after VAD drops, wait a silence hangover before declaring end-of-turn — Pipecat ~200 ms, LiveKit ~550 ms, OpenAI Realtime ~200 ms. Too short interrupts the user; too long feels sluggish. Kyutai "flush trick": on VAD end-of-speech, signal STT to emit immediately instead of waiting its internal look-ahead — shaves hundreds of ms.
Sources: https://github.com/emilwareus/addcommitpush.io/blob/HEAD/presentations/voice-agents/VAD-DEEP-DIVE.md

### 2.2 STT — faster-whisper `small` (chunked), Moonshine (streaming)
Whisper via faster-whisper (CTranslate2, MIT) is the chunked workhorse. Real CPU numbers: i7-12700K, int8, 8 threads — `small` ran ~7.6× real-time; isolated per-model CPU/int8 factors: tiny 25×, base 15×, small 5.6×, medium 2.0×, large-v3 0.57× (slower than real-time). A Ryzen 9 (more/faster cores) should run **`small` well over 5–10× real-time and `medium` at ~2–3×**. Memory: small ~1.5 GB, medium ~2.7 GB resident. For live conversation: `small`, int8, beam_size=1, VAD filter on, word timestamps on.
Sources: https://vdf.ai/blog/whisper-on-premise-speech-to-text/, https://github.com/pbnz/watch-local/issues/36

Vanilla faster-whisper is chunked (30 s window) — fine paired with VAD-gated utterances, not a true streaming recognizer. True-streaming options: WhisperLive/whisper-streaming (LocalAgreement-2, MIT) wrap Whisper with partial-hypothesis policies; Vosk is genuinely streaming but lower accuracy. **Moonshine** (Useful Sensors, MIT for English tiny/base): purpose-built streaming ASR, tiny 27M / base 61M, variable-length encoder scaling compute to input length, v2 adds ergodic sliding-window attention for bounded-latency streaming; accuracy on par with models ~6× its size; 150–250 ms to first partial on CPU-friendly hardware.
Sources: https://arxiv.org/pdf/2602.12241, https://github.com/boona13/ghost/blob/HEAD/skills/moonshine-stt/SKILL.md

For barge-in: the trigger path is VAD → immediate interruption; STT needs fast accurate *finals*. Word timestamps are nice-to-have (faster-whisper has them natively). Moonshine's streaming partials additionally enable preemptive behavior (start thinking on a partial), but VAD-gated faster-whisper is the simpler proven route.

### 2.3 TTS — Kokoro is the pick (Apache 2.0)
**Piper: fast but a license trap.** VITS-based ONNX, tiny voices (15–75 MB), RTF ~0.3–0.7 on desktop CPUs, per-sentence latency in the low hundreds of ms. But the maintained `piper-tts` package (OHF-Voice/piper1-gpl, after rhasspy/piper was archived in 2025) is **GPL-3.0-or-later** — copyleft taint for a permissive-only project. The *voices* are MIT/CC0, so a clean-room self-built ONNX runner is theoretically possible, but that's real work. **Do not use the piper-tts package.**
Sources: https://github.com/OHF-Voice/piper1-gpl, https://github.com/baptistecristo/ai-agents-for-dumbphones/issues/26

**XTTS v2 (Coqui): capable but out.** Zero-shot cloning from ~6 s of reference audio, 17 languages, native chunked streaming (~200 ms time-to-first-audio on GPU). Two disqualifiers: CPU inference is 10–20× slower than GPU ("several seconds per line") — breaks the latency budget on a CPU-only laptop — and weights are under the **Coqui Public Model License (non-commercial)** — a non-starter if the app ever ships commercially.
Sources: https://github.com/subtitld/addon-coqui-xtts, https://github.com/alh477/oligarchy/blob/HEAD/modules/demod-voice/docs/faq.md

**Kokoro (hexgrad/kokoro): verified, permissive, the pick.** 82 M parameters, **Apache 2.0 weights and code**, 54 bundled voices across 8 languages, 24 kHz output, ranked #1 on TTS Spaces Arena at launch. CPU RTF ~0.47–0.57 (~2× real-time), UTMOS ~4.45, sub-0.3 s for short texts; the `kokoro-onnx` wrapper needs only ONNX Runtime (no PyTorch). No voice cloning (fixed voice bank — audition and pick one); acceptable for a defined companion persona. **Future watch:** Qwen3-TTS (Apache 2.0, 0.6B/1.7B, streaming-first, zero-shot cloning) is promising but GPU-oriented (~5 GB VRAM) — revisit when GPU hardware enters the picture.
Sources: https://www.qwe.edu.pl/tutorial/kokoro-tts-local-cpu-tutorial/, https://heyneo.com/blog/kokoro-tts-vs-supertonic-3-tts

**Streaming synthesis pattern:** sentence-chunked streaming — dispatch each LLM sentence to TTS as it arrives, play audio while the rest generates. Perceived latency equals the *first chunk's* latency, not total synthesis time.

### 2.4 Full-duplex orchestration
Canonical cascade: mic → VAD (gates everything downstream) → STT partials/finals → turn detector → LLM (streaming tokens) → TTS (sentence chunks, streaming) → playback. VAD is also the barge-in sensor.
Sources: https://dev.to/stalwartcoder/build-a-low-latency-voice-agent-in-python-with-pipecat-3plb

Turn-taking is a **preemptive state machine**, not a turn-based chatbot:
- **Barge-in:** while the agent speaks, STT keeps listening; VAD-confirmed user speech (short confirmation window, ~250–500 ms, to reject transients) → interruption event → cancel LLM stream → cancel TTS playback → flush partial audio → new utterance becomes priority input.
- **The context-rewind bug (critical):** history must record only what was actually *played*, not what was generated. Cut off mid-sentence → transcript reflects the truncated sentence, or the agent "believes things the user never heard."
- **Backchannel tolerance:** brief sounds ("mm-hm") must not trigger barge-in; sustained speech must. Configurable duration gate on the interruption path.
- **Preemptive generation:** biggest latency lever — when VAD fires end-of-speech *and* a final transcript exists, trigger the LLM immediately (skip turn-analysis ML); the interruption path covers the user-resuming case.
Sources: https://medium.com/@wasifullahdev/from-call-flows-to-autonomous-agents-building-real-time-voice-ai-with-twilio-livekit-6a34dcfcb6d6, https://medium.com/@kollaikalrupesh/how-i-reduced-voice-ai-response-latency-by-fixing-turn-detection-in-pipecat-eda1d8743386

**Echo cancellation (load-bearing for VRChat):** when the mic hears the speakers (game audio, the agent's own voice), VAD self-triggers and the agent interrupts itself. Web contexts get browser WebRTC AEC for free; desktop/PCVR with virtual audio cables needs a real AEC subsystem (Speex AEC, or LiveKit's transport-level cancellation) — otherwise develop with headphones. Alternative: speech-to-speech cloud models handle barge-in internally, but they're opaque and off-brand for a sovereign build.
Sources: https://dev.to/quintana/roomkit-pipecat-ten-framework-livekit-agents-choosing-the-right-conversational-ai-framework-2h80

### 2.5 Latency budgets (tuned, fully streaming cascade)

| Stage | Typical budget | Notes |
|---|---|---|
| VAD frame decision | 10–50 ms | Continuous; ~1 ms/frame Silero |
| Endpointing / turn decision | 200–300 ms | Silence-hangover config; the usual leak |
| STT final transcript | 50–150 ms after speech ends | Partials streamed during speech |
| LLM time-to-first-token | 150–400 ms | Usually the long pole; local small model fastest |
| TTS time-to-first-audio | 75–360 ms | First chunk only; Kokoro sub-0.3 s short text |
| Transport (one way) | 30–80 ms | Local loopback negligible |
| **End to end (first audio)** | **~0.8–1.1 s tuned; 1.1–2 s typical** | < ~700 ms feels human; > ~2 s feels broken |

Pipecat's illustrative round trip totals ~1.29 s: turn decision 300 ms + LLM first token 650 ms + TTS first audio 120 ms + audio path/sentence assembly 223 ms.
Sources: https://zoice.ai/blog/ai-voice-agent-latency-pipeline-stages/, https://github.com/ombharatiya/ai-system-design-guide/blob/HEAD/18-voice-and-audio-agents/01-realtime-voice-agents.md

For the Ryzen 9 target: the LLM is the long pole — a local 1–3B quantized model gives first-token in the low hundreds of ms, leaving the ~2 s target reachable with everything else streaming.

### 2.6 Python frameworks (license posture)
- **LiveKit Agents — Apache 2.0.** Session-managed pipeline, Silero VAD, built-in barge-in, semantic turn detection, preemptive generation. LiveKit server also Apache 2.0 and self-hostable. Most polished end-to-end; price is buying into their session/transport model. Sources: https://github.com/livekit/livekit
- **Pipecat — BSD-2-Clause.** Frame-based pipeline: VAD on transport, STT/LLM/TTS as processors, interruption frames propagate cancellation, per-stage latency metrics built in. 40+ integrations. **Caution:** its `piper` extra pulls GPL-3.0 `piper-tts` — use the framework without that extra.
- **Vocode — MIT but dormant** (last commit ~Nov 2024), phone-centric. Not a new foundation.
- **TEN Framework** — worth a look for real-time media; license UNVERIFIED.

**Verdict:** Pipecat (BSD-2) is the natural hand-hold — its frame/pipeline model is the exact architecture you'd hand-roll, with production-hardened interruption + metrics. Hand-rolling an asyncio frame pipeline (studying Pipecat's *ideas* — interruption frames, spoken-only history, stage metrics — without copying code) is fully defensible for maximum control and Aesir seam cleanliness. LiveKit Agents is the strongest alternative if a transport/SFU ever becomes useful.

**Biggest latency wins in order:** (1) stream everything so stages overlap, (2) preemptive generation on VAD-end + transcript, (3) aggressive-but-safe endpointing (~400 ms), (4) small fast LLM first token, (5) sentence-chunked TTS. **Biggest risks:** echo-induced self-interruption and the spoken-history bookkeeping bug — both correctness issues, both must be tested explicitly.

---

## 3. Python stack

### 3.1 Backend — FastAPI + SSE for chat, WebSocket reserved for voice
FastAPI is the default Python ASGI framework for AI workloads: async-native, Pydantic validation, automatic OpenAPI docs, largest LLM-integration ecosystem. (One 2026 comparison scored FastAPI 82/100 vs Litestar 73/100 — FastAPI wins on ecosystem maturity, not raw capability; Litestar has stronger DI and native DTOs but a smaller community. For a solo/AI-assisted team, FastAPI's "Google-ability" matters more than benchmark margins never touched at personal scale.)
Sources: https://github.com/byte-ish/litestar-vs-fastapi, https://medium.com/@atharvjswal56/i-tested-5-python-web-frameworks-in-2026-heres-what-actually-works-a3e412d523e8

Correction to the original brief: for token streaming, **SSE is the 2026 best practice, not WebSocket** — the flow is one-directional (server → client). Proven FastAPI pattern: async generator yielding chunks as `StreamingResponse(media_type="text/event-stream")`, `X-Accel-Buffering: no` so proxies don't batch, error handling *inside* the generator (status can't change mid-stream), and a client-disconnect check that cancels the upstream LLM call so tokens aren't burned after the tab closes. **WebSocket stays for the voice loop** — genuinely bidirectional (mic audio up, speech down) — so keep FastAPI's native WebSocket support available for that future endpoint rather than forcing chat onto it.
Sources: https://jetbi.com/blog/streaming-architecture-2026-beyond-websockets, https://github.com/mamta352/ailearnings/blob/HEAD/source/blog/posts/llm-streaming.md

Strict line: the *provider SSE seam* (FastAPI consumes Ollama/OpenRouter SSE) and the *UI SSE endpoint* (FastAPI re-emits normalized UI events to the browser) are separate — never proxy provider SSE bytes straight to the browser; the seam normalizes first.

### 3.2 Frontend — Jinja + htmx + Alpine.js
For a tiny team building streaming chat plus a later voice UI, server-rendered wins on iteration speed: htmx needs no build step (single script tag) and handles the token stream via its SSE extension; the developer who built the data model builds the UI; React/Vue/Svelte become the right call only for genuinely complex client-side state (real-time collaboration, offline-first) — not chat + CRUD + settings.
Sources: https://dev.to/ai_made_tools/htmx-vs-react-do-you-really-need-a-javascript-framework-1p3i, https://medium.com/codetodeploy/i-tried-htmx-after-years-of-react-heres-my-honest-take-cc00045f8ede

The voice UI later needs genuine client-side JS anyway (mic capture, audio playback, WebSocket audio transport) — htmx coexists fine with a small vanilla-JS island for that. Keep the backend API-first so a full SPA could attach later without a rewrite.

### 3.3 Storage — SQLite core, sqlite-vec for vectors
At personal scale SQLite is simply right: zero ops, single file, trivial backup, ACID. Postgres is operational weight with zero payoff for a single user on a laptop. Use SQLAlchemy (async) so Postgres remains a one-config-change option later; add an FTS5 virtual table for keyword fallback at no license cost.

Vector store comparison (zero-ops deploy / personal-scale perf / license):

| Store | Deploy | Perf | License |
|---|---|---|---|
| **sqlite-vec** | Best — pure-C extension, same SQLite file, `pip install sqlite-vec` | "Fast enough" KNN at personal scale | **MIT OR Apache-2.0** (dual) |
| Postgres + pgvector | Worst — needs a Postgres server | Strong (~1M+ vectors) | Permissive — but ops cost disqualifies phase one |
| Chroma (embedded) | Good, Apache-2.0 | Fine < ~1M docs; poor concurrent-query behavior, prototype-grade durability reputation | Apache-2.0 |
| Qdrant | Moderate — single binary, second service | Best-in-class filtering/quantization | Apache-2.0 |

**Recommendation: sqlite-vec primary** — the only option living inside the same single-file deploy. Dual MIT/Apache-2.0, pure C, zero dependencies, `vec0` virtual tables. Caveats: pre-v1 (isolate behind our own vector-store interface for swap-ability). **Fallback:** LanceDB (Apache-2.0, embedded, native hybrid search) if sqlite-vec's pre-v1 status bites.
Sources: https://github.com/asg017/sqlite-vec, https://aifoss.dev/blog/pgvector-vs-chroma-vs-qdrant-local-rag-2026/

Embeddings: Ollama serves `/api/embeddings` plus OpenAI-shaped `/v1/embeddings` natively. The seam must record `(provider, model, dimensions)` with every vector — embedding spaces are not interchangeable across models.
Sources: https://github.com/hardgraph/skills/blob/HEAD/skills/ollama/SKILL.md

### 3.4 Auth — single local token now, real users later
Single-user phase: **one long random bearer token**, generated on first run, stored in local config (or env), compared with `secrets.compare_digest`, `Authorization: Bearer`, plus bind to `127.0.0.1` by default. Bind-localhost-first is the actual security boundary; the token defends the LAN case. Multi-user later: Argon2-hashed passwords, short-lived JWT access tokens (5–15 min) with refresh tokens in httpOnly cookies (never localStorage), roles field, and per-user data scoping in every query — keep user-id columns in the schema from day one as cheap insurance. **UNVERIFIED:** no single canonical doc for this exact progression; synthesized from standard guidance.

### 3.5 Packaging/ops — systemd primary, Docker optional
- **systemd unit (primary):** `ExecStart` on a venv/uv-managed Python, `Restart=always`, pinned working dir, env file for token + backend config. Simplest "service on a Kubuntu laptop" story — no container runtime.
- **Docker (optional):** Compose with app + Ollama is the portable story. **UNVERIFIED:** current Ollama Docker GPU flag syntax — docs-check before writing any Compose file.
- **Ollama coexistence:** trivial — Ollama on :11434, app on its own port, localhost HTTP. `OLLAMA_KEEP_ALIVE` tuning avoids model reload latency between turns.
- **Deploy shape, phase one:** `pip`/`uv` app + systemd unit + Ollama + one SQLite(+sqlite-vec) file. Zero containers, zero extra services, one backup file.

---

## 4. Inference seam design

### 4.1 The OpenAI-compatible contract
The seam speaks OpenAI Chat Completions as its canonical contract (it's what Ollama's `/v1`, OpenRouter, vLLM, llama.cpp server, LM Studio all implement):
- `POST /chat/completions` with `stream=true` → SSE chunks (`choices[0].delta.content`), `[DONE]` terminator
- `POST /completions` (legacy text completions — needed for some prompt-template flows)
- `POST /embeddings` (RAG ingestion/retrieval)
- `GET /models` (id, context length where available)

Sampling parameters passing through the seam (union of what backends honor): `temperature`, `top_p`, `top_k`, `min_p`, repetition controls (`repeat_penalty` plus OpenAI-style `presence_penalty`/`frequency_penalty` mapped per backend), `max_tokens` (→ Ollama `num_predict`), `stop` sequences, `seed`, `num_ctx` where the backend allows per-request control.
Source: https://github.com/trillx/kiminola/blob/HEAD/.scratch/kiminola/research/03-llm-provider-landscape-byok-openrouter-oauth.md

### 4.2 Backend specifics
**Ollama — use the NATIVE `/api/*`, not the `/v1` shim, for the Ollama adapter.** Native: `POST /api/chat` (NDJSON stream, `stream` defaults true), `/api/generate`, `/api/embeddings`, `GET /api/tags`, `GET /api/show`; per-request `options` include temperature, top_p, top_k, min_p, repeat_penalty, seed, num_predict, num_ctx, stop. Streaming is newline-delimited JSON; final object carries `done:true` plus timing stats. The `/v1` OpenAI-compat shim is explicitly partial: silently ignores per-request `num_ctx` (models load at the 4096 default), has known streamed tool-call corruption, and its image handling differs. Official shim docs: https://docs.ollama.com/api/openai-compatibility
Sources: https://github.com/jayll1303/aiekit/blob/HEAD/.kiro/skills/ollama-local-llm/references/api-integration.md, https://github.com/corespeed-io/lore/blob/HEAD/docs/research/ollama-benchmark-reader.md

**OpenRouter — OpenAI-compatible cloud aggregator.** Base `https://openrouter.ai/api/v1`, `Authorization: Bearer <key>` (`sk-or-...`), `/chat/completions` and `/completions`, SSE streaming with `[DONE]`, public no-auth `GET /models` catalog (id, context_length, pricing). Differences from raw OpenAI: namespaced model ids (`provider/model:variant`), per-request provider routing (`provider.order`, `allow_fallbacks`), model-slug variants (`:free`, `:nitro`), optional attribution headers, cheap non-billable `GET /v1/key` health check. Posture: prepaid credits, pass-through pricing, prompts/completions not logged by default, training-on-data providers excluded unless opted in. **UNVERIFIED:** exact current fee percentages — check openrouter.ai/docs before Volmarr spends money.
Source: https://github.com/trillx/kiminola/blob/HEAD/.scratch/kiminola/research/03-llm-provider-landscape-byok-openrouter-oauth.md

### 4.3 The seam as a Python interface (design, not code)
An abstract `InferenceBackend` class; concrete adapters `OllamaBackend` (native `/api`), `OpenRouterBackend` (OpenAI-compat), later `AesirBackend`. All app code talks only to the abstract class.

- `chat_stream(messages, params)` → async iterator of normalized `ChatEvent`s (`TextDelta(text)`, `Done(usage)`, `Error(message)`) — adapters translate NDJSON (Ollama) or SSE (OpenRouter) into this shape. Backends implement *only* streaming.
- `chat(messages, params)` → non-streaming convenience, implemented by accumulating `chat_stream`.
- `embed(texts)` → vectors; adapters without embedding support raise `EmbeddingsUnsupported`, which the RAG layer catches to fall back to keyword/FTS5 search (graceful degradation, not a crash).
- `list_models()` → normalized `ModelInfo`: id, context_length (nullable), capability flags (chat/embeddings/vision/tools), max_output_tokens (nullable).
- `health_check()` → cheap liveness probe (Ollama: `GET /api/tags`; OpenRouter: `GET /v1/key`).
- `count_tokens(text, model)` → token counting for context-budget management; default implementation estimates conservatively and documents that it does.

`SamplingParams` value object (the app's only sampling vocabulary): temperature, top_p, top_k, min_p, repeat_penalty, presence_penalty, frequency_penalty, max_tokens, stop (list), seed, num_ctx. Each adapter maps these to backend-native fields; unsupported ones are dropped with a logged warning, never an exception.

**What the seam REQUIRES of a future Aesir backend:** (1) streaming token endpoint with terminal done/error signal; (2) server-side stop-sequence enforcement (or documented client-side post-filter contract); (3) the full `SamplingParams` surface — unhonorable controls declared unsupported in `ModelInfo` for predictable degradation; (4) embeddings, or explicit `EmbeddingsUnsupported` so RAG falls back to FTS5; (5) model metadata incl. context length. **Cheapest integration path: if Aesir ships `/v1`-style OpenAI-compatible endpoints, the OpenRouter adapter pattern (OpenAI-compat client + base URL + key) can be reused nearly verbatim.**

### 4.4 What the seam must NOT leak
Callers (chat service, RAG pipeline, persona renderer) must never see: wire-format differences (NDJSON vs SSE vs `[DONE]` vs `done:true`); parameter-name divergence (`num_predict` vs `max_tokens`, `options.stop` nesting); backend bugs/lossy mappings (Ollama `/v1` dropped streamed tool calls, ignored `num_ctx` — the adapter absorbs these by using native `/api/chat`); auth shapes (Ollama's ignored placeholder key vs OpenRouter's `sk-or-...`); model-id namespacing (`provider/model:variant`, `model:tag` — stay behind `ModelInfo.id`); image/vision encoding quirks; default-value divergence (the adapter applies the *app's* canonical defaults before calling, so switching backends never silently changes generation behavior).

---

## 5. Consumers — what the bridges need from the app's API

(From the earlier AI-companion research program; the VRChat/game bridge reports live in `~/workspace/your_files/ai-companion-mods/`.)

- **VRChat OSC bridge** (easiest gate): needs conversation-state API (read/write turns against a named chat), persona switching (which character is "wearing" the avatar), and TTS hooks (request speech of a text, receive audio or a playback-completion event). Architecture: second VRChat account + desktop follower; group voice capture requires PCVR (audio tap on the VRChat host machine; standalone Quest has no tap). Ryzen 9 CPU runs Whisper-small + Piper-class STT live; XTTS-class cloning does not fit CPU latency.
- **Conan Exiles bridge**: the existing "Conan Exiles meets ChatGPT" mod is a paused proof-of-concept with a closed OpenAI-only client — plan is to re-implement the RCON bridge ourselves (Source RCON protocol; game mod surfaces Talk-dialogue events; our bridge relays to the chat app's API).
- **Skyrim bridge**: Mantella-style — the game mod posts dialogue prompts to an HTTP endpoint and renders returned text/voice. Our app exposes the same shape: prompt-in/utterance-out plus persona context.
- Common requirement: **scoped bridge tokens** (per-bridge credentials, revocable, limited to named chats/personas), **webhook/callback or pollable outbox** for "companion wants to speak" events, and **latency SLAs** documented per consumer (voice ~2 s turns; text bridges tolerant to ~10 s).

---

## 6. License taint register — DO NOT USE

| Item | Problem | Replacement |
|---|---|---|
| SillyTavern code (any) | AGPL-3.0 — the entire reason for clean-room | Study ideas only |
| `piper-tts` package (OHF-Voice/piper1-gpl) | GPL-3.0-or-later | Kokoro-82M (Apache 2.0) via kokoro-onnx |
| XTTS v2 weights | Coqui Public Model License (non-commercial) | Kokoro (no cloning) / Qwen3-TTS later on GPU |
| Any AGPL service in the deploy chain | Network copyleft taint | Prefer MIT/Apache-2.0/BSD; verify at distribution |
| Vocode | MIT but dormant since ~Nov 2024 | Pipecat (BSD-2) / LiveKit Agents (Apache 2.0) / hand-rolled |

Re-verify every license at distribution time — projects relicense.

---

## 7. Open questions for Volmarr (biggest decisions)

1. **App name.** Everything ships under a placeholder until he names it (his joy, his call).
2. **First inference backend:** Ollama-local-first, or OpenRouter-first? (Affects Campaign III ordering; both get built, but one is the daily driver.)
3. **Persona seed material:** his saved Yrsa personality versions (Friends-and-Fables era) — which formats are they in? TavernCard JSON/PNG, plain text, or something custom? May need a custom import validator beyond v2/v3. **UNVERIFIED** until he shares one.
4. **Voice for Yrsa:** Kokoro has a fixed voice bank (no cloning) — audition and pick, or defer voice-clone ambitions to the GPU era (Qwen3-TTS)?
5. **Multi-user:** single-user now is the plan — confirm no one else needs accounts in phase one.
6. **Aesir's API shape:** when Aesir grows its server surface, prefer OpenAI-compatible `/v1`-style endpoints — it makes the Campaign VII cutover nearly free.
