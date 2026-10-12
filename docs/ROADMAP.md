# ROADMAP.md — Sovereign AI Chat App (clean-room)

*Slice-based build plan in Volmarr's Mythic Engineering style. Each slice is a build+test+commit unit with a crisp acceptance contract — written so Yrsa and ChatGPT can ALTERNATE pick them up cold. ChatGPT: add your slices/ideas with the same contract shape; design changes update DESIGN.md first.*

## How a slice works
1. Read this roadmap + DESIGN.md + the slice contract below. Nothing else needed.
2. Build it. Tests are part of the slice, not a later slice.
3. Acceptance contract must pass fully before commit. Partial credit is not a slice.
4. Commit with message `S###: <title>`. Push per Volmarr's standing git discipline (fetch, diff, never force-push, verify remote HEAD).
5. If a slice's contract turns out wrong, update the contract in this file and note why — don't silently reinterpret it.

**Slice ID scheme:** `S` + campaign number + two-digit sequence (`S101` = Campaign I, slice 01). ChatGPT's added slices take the next free number in their campaign.

## Honest sizing
**68 slices across 7 campaigns.** Verdict on "easy vs my other builds": directionally right, precisely wrong. HugrGate was 500 slices, Mímisbrunnr 200, the kiosk 50. This is the *smallest* of Volmarr's builds — but it is a real multi-week project, not a weekend. The voice loop (Campaign V) and memory subsystem (Campaign IV) are where the dragons live; everything else is honest plumbing.

| Campaign | Slices | Theme |
|---|---|---|
| I | 12 | Foundation, text chat, personas, TavernCard import |
| II | 13 | Lorebooks, sampling presets, prompt template, group chats |
| III | 8 | Inference seam: Ollama + OpenRouter |
| IV | 10 | RAG / memory subsystem |
| V | 11 | Real-time voice loop |
| VI | 8 | Bridge APIs: VRChat + games |
| VII | 6 | Aesir-native cutover |
| **Total** | **68** | |

---

## CAMPAIGN I — Foundation, text chat, personas

*Goal: a running local app where Volmarr can chat in text with an imported character.*

- **S101 Repo scaffold** — Builds: Python project layout (`src/`, `tests/`), ruff/black, pytest, README skeleton, license placeholder, .gitignore. Acceptance: `pytest` green on empty suite; `python -m app --help` works.
- **S102 App shell + auth** — Builds: FastAPI app, `/healthz`, bearer-token auth (generated on first run, `secrets.compare_digest`), bind 127.0.0.1 default. Acceptance: unauthenticated requests 401; token persisted in local config; healthz 200.
- **S103 Storage core** — Builds: SQLAlchemy async + SQLite; `users`, `characters`, `chats`, `messages` tables, `user_id` columns from day one. Acceptance: CRUD round-trip tests green; single `.db` file created on first run.
- **S104 TavernCard import** — Builds: PNG `chara`/`ccv3` chunk extraction, JSON validation against v2/v3 field set, unknown fields logged never dropped. Acceptance: fixture cards (v1/v2/v3, PNG + JSON) import losslessly.
- **S105 TavernCard export** — Builds: card JSON → PNG/JSON, `extensions` opaque round-trip, CRC32 recomputed. Acceptance: import→export→import is byte-identical on card data.
- **S106 Character service + API** — Builds: `/api/characters` CRUD, avatar handling. Acceptance: API tests for full CRUD + avatar upload.
- **S107 Chat service + API** — Builds: `/api/chats` CRUD, message edit/delete. Acceptance: API tests; edits/deletes reflected in history queries.
- **S108 Generation stub + SSE** — Builds: `POST /api/generate` streams SSE events from a stub backend (canned tokens); client-disconnect cancels. Acceptance: SSE stream parses as events; disconnect stops the stub (no orphan task).
- **S109 Chat UI** — Builds: Jinja + htmx chat page, SSE token rendering, send box. Acceptance: scripted walkthrough passes; tokens render incrementally.
- **S110 Persona prompt assembly** — Builds: card fields → ordered slots, `{{char}}`/`{{user}}`/`{{original}}` macros, `creator_notes` excluded from prompts. Acceptance: unit tests on fixture cards assert slot contents and exclusions.
- **S111 Chat management UI** — Builds: list/rename/delete/export chats. Acceptance: UI flows covered by tests.
- **S112 Campaign hardening** — Builds: full suite green, README quickstart, systemd unit file. Acceptance: fresh-machine install doc works end to end; service starts via systemd.

## CAMPAIGN II — Lorebooks, presets, prompt template, groups

*Goal: the prompt engine — world info, sampling control, group conversations.*

- **S201 Lorebook model + API** — Builds: `lorebooks`/`lore_entries` tables, `/api/lorebooks` CRUD. Acceptance: CRUD tests.
- **S202 Keyword scanning** — Builds: primary/secondary keys, whole-word + case toggles, scan depth. Acceptance: fixture chats trigger expected entries; non-matches stay silent.
- **S203 Activation semantics** — Builds: constant/selective/sticky/cooldown/delay/recursion. Acceptance: one scenario test per semantic, all green.
- **S204 Budget + priority** — Builds: token budget, per-entry priority, deterministic discard order. Acceptance: over-budget fixtures resolve identically every run.
- **S205 Prompt template engine** — Builds: ordered slots with roles/positions/token budgets; overflow trims oldest history first. Acceptance: golden-prompt tests on fixtures.
- **S206 Author's Note depth injection** — Builds: re-inject reinforcement text N messages from end. Acceptance: prompt tests show the note at the configured depth.
- **S207 Sampling presets** — Builds: preset model (variable-shape param bag), CRUD. Acceptance: CRUD + param round-trip tests.
- **S208 Per-provider param filtering** — Builds: unknown params dropped with logged warning per backend. Acceptance: strict-mock backend receives only allowed params; warning logged.
- **S209 Lorebook editor UI** — Builds: htmx editor for books/entries. Acceptance: UI flow tests.
- **S210 Group chats** — Builds: room model, members, per-message speaker field. Acceptance: API tests.
- **S211 Speaker policies** — Builds: Manual/Natural/List/Pooled + mute + talkativeness. Acceptance: deterministic policy tests incl. fallbacks.
- **S212 Pluggable director interface** — Builds: speaker-policy interface; stub LLM-director seam. Acceptance: a custom policy plugs in via the interface in tests.
- **S213 Campaign hardening + docs** — Acceptance: suite green; prompt-engine documented.

## CAMPAIGN III — Inference seam: Ollama + OpenRouter

*Goal: real models behind the chat, swappable without touching app code.*

- **S301 Seam interfaces** — Builds: `InferenceBackend` ABC, `ChatEvent`, `SamplingParams`, `ModelInfo`, `EmbeddingsUnsupported`. Acceptance: interface tests with a fake backend.
- **S302 Ollama adapter** — Builds: native `/api/chat` NDJSON streaming → `ChatEvent`s. Acceptance: streams correctly against real Ollama (or recorded fixture).
- **S303 OpenRouter adapter** — Builds: OpenAI-compat SSE → `ChatEvent`s; model-id namespacing hidden behind `ModelInfo.id`. Acceptance: fixture SSE → events; `[DONE]` handled; no namespaced ids leak.
- **S304 Embeddings** — Builds: `embed()` per adapter; typed `EmbeddingsUnsupported`. Acceptance: vectors returned with (provider, model, dims) provenance; unsupported raises the typed error.
- **S305 Model listing + health + token counting** — Builds: `list_models`, `health_check`, `count_tokens`. Acceptance: Ollama + OpenRouter fixtures.
- **S306 Backend config + secrets** — Builds: `/api/backends` CRUD; secrets server-side only. Acceptance: a secret appears in NO API response (negative test).
- **S307 Wire chat through the seam** — Builds: replace stub; per-chat backend + preset selection. Acceptance: end-to-end chat against Ollama streams real tokens.
- **S308 Campaign hardening + docs** — Acceptance: suite green; backend docs.

## CAMPAIGN IV — RAG / memory subsystem

*Goal: the app remembers — our clearest edge over SillyTavern.*

- **S401 Vector store interface + sqlite-vec adapter** — Builds: store interface; `vec0` adapter. Acceptance: insert/search round-trip; fake-store swap test.
- **S402 Embedding ingestion** — Builds: chunking pipeline; provenance recorded per vector. Acceptance: fixture docs → vectors with (provider, model, dims).
- **S403 Hybrid retrieval** — Builds: vector + FTS5 keyword, score fusion. Acceptance: fixture queries hit from both paths.
- **S404 Chat auto-summarization** — Builds: rolling summaries of old history. Acceptance: long fixture chat summarizes; token budget respected.
- **S405 Event/fact extraction** — Builds: LLM-assisted extraction, async, never blocks replies. Acceptance: fixture chat → expected event set.
- **S406 Salience + decay** — Builds: scoring, recall-strengthening, forgetting. Acceptance: time-decay simulation tests.
- **S407 Witness-scoped recall** — Builds: memories tagged with chat/character witnesses; retrieval filters. Acceptance: character A cannot recall character B's private chat (negative test).
- **S408 Memory nucleus** — Builds: per-character core biography, always injected. Acceptance: prompt tests show nucleus present.
- **S409 Mutation sync** — Builds: message edit/delete/rename updates linked memories. Acceptance: sync tests.
- **S410 Memory browser UI + hardening** — Acceptance: UI tests; suite green.

## CAMPAIGN V — Real-time voice loop

*Goal: talk to the app — ~2 s turns, barge-in, on the CPU-only Ryzen 9. The dragons live here.*

- **S501 Audio plumbing** — Builds: capture/playback (sounddevice), 16 kHz mono ring buffer. Acceptance: loopback test records and plays.
- **S502 Silero VAD** — Builds: 512-sample frames, hysteresis, pre-roll, tunable params. Acceptance: fixture audio (speech/noise/silence) segments correctly.
- **S503 STT service** — Builds: faster-whisper `small` int8, beam 1, word timestamps. Acceptance: fixture audio transcribes within the accuracy bar; RTF measured and recorded.
- **S504 TTS service** — Builds: Kokoro-82M via kokoro-onnx, sentence-chunked streaming. Acceptance: first-audio latency measured; voice-audition doc written.
- **S505 Orchestrator skeleton** — Builds: asyncio frame pipeline, stage wiring. Acceptance: text-in/text-out dry run through the pipeline.
- **S506 Turn-taking** — Builds: endpointing (~400 ms hangover), preemptive trigger on VAD-end + final transcript. Acceptance: simulated conversation turns take correctly.
- **S507 Barge-in** — Builds: interruption event, LLM/TTS cancellation, backchannel tolerance (~300 ms confirmation). Acceptance: simulated interruption cancels cleanly; "mm-hm" does not interrupt.
- **S508 Spoken-only history** — Builds: history records audio actually played. Acceptance: cut-off-mid-sentence test → history shows the truncated sentence (the context-rewind rule).
- **S509 Echo / self-interruption** — Builds: AEC notes, headset path, self-trigger test. Acceptance: agent speaking + room noise → no self-interruption.
- **S510 Latency metrics** — Builds: per-stage logging, p50/p95. Acceptance: metrics emitted for every turn; budget table in docs.
- **S511 Voice UI island + hardening** — Builds: mic button, status, waveform. Acceptance: UI tests; suite green. **License check:** no GPL (piper-tts) or CPML (XTTS v2) anywhere in the voice stack — add a CI license scan here.

## CAMPAIGN VI — Bridge APIs (VRChat + games)

*Goal: the app becomes the brain behind companions.*

- **S601 Bridge auth** — Builds: scoped, revocable per-bridge tokens. Acceptance: scope-enforcement tests (a bridge can't touch another bridge's chats).
- **S602 Conversation-state API** — Builds: bridges read/write turns on named chats. Acceptance: API tests.
- **S603 Persona switching API** — Builds: switch persona mid-chat via API. Acceptance: prompt reflects the switch.
- **S604 TTS hook API** — Builds: request speech of a text; playback-completion events. Acceptance: hook round-trip test.
- **S605 VRChat OSC bridge (reference)** — Builds: Python script, second-account desktop-follower pattern, private-instance-first defaults. Acceptance: OSC messages verified in a documented manual test; disclosure/consent notes in docs.
- **S606 Conan Exiles RCON bridge** — Builds: design doc + reference skeleton (Source RCON handshake, Talk-event relay to chat API). Acceptance: RCON handshake test against fixture; design reviewed.
- **S607 Skyrim-style HTTP bridge contract** — Builds: prompt-in/utterance-out contract. Acceptance: contract tests with a mock game client.
- **S608 Bridge builder docs + hardening** — Acceptance: docs let a third party build a bridge; suite green.

## CAMPAIGN VII — Aesir-native cutover

*Goal: Volmarr's own silicon becomes the inference heart. Cheapest path: Aesir ships OpenAI-compatible `/v1`-style endpoints (see RESEARCH.md §4.3, §7 Q6).*

- **S701 AesirBackend adapter** — Builds: adapter against Aesir's API (streaming deltas, done/error). Acceptance: fixture streams → `ChatEvent`s.
- **S702 Sampling mapping** — Builds: `SamplingParams` ↔ Aesir controls; unsupported controls declared in `ModelInfo`. Acceptance: mapping tests; declared-unsupported never sent.
- **S703 Embeddings via Aesir** — Builds: Aesir embeddings or explicit `EmbeddingsUnsupported` → FTS5 fallback. Acceptance: fallback path test.
- **S704 Per-chat migration tooling** — Builds: migrate a chat's backend Ollama→Aesir, history intact. Acceptance: migration test.
- **S705 Performance validation** — Builds: streaming-latency benchmark vs Ollama baseline. Acceptance: latency report; no regression beyond the agreed bar.
- **S706 Cutover docs + final hardening** — Acceptance: docs; full suite green; the app runs end-to-end on Aesir.

---

## For ChatGPT (her additions)
- Add slices with the next free number in their campaign, same contract shape (Builds / Acceptance).
- If an addition changes architecture, update DESIGN.md first, then the slice.
- Suggested areas she may own: frontend polish passes, the voice-audition tooling (S504), bridge consent/ToS docs (S605), Aesir API shaping (Campaign VII needs Aesir's server surface defined — whoever builds Aesir's HTTP layer should read RESEARCH.md §4.3 first).
- Alternation rule: never start a slice another builder has touched without reading their commit; slices are atomic — don't split them, add new ones.
