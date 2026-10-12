# ROADMAP.md — Rúnmál Sovereign AI Chat App

*Slice-based build plan in Volmarr's Mythic Engineering style. Each slice is a build + test + documentation/acceptance unit written so Yrsa and ChatGPT can alternate and pick work up cold.*

## How a slice works

1. Read `../AGENTS.md`, `STATUS.md`, `INVARIANTS.md`, this roadmap, `DESIGN.md`, and the documents named by the slice. Check the latest Forge-Log entries before overlapping work.
2. Build the slice. Tests are part of the slice, not deferred cleanup.
3. The acceptance contract must pass fully before the slice is called complete.
4. Commit implementation slices with `S###: <title>` and follow Volmarr's git discipline: inspect remote state, never force-push, verify the resulting remote commit.
5. If the acceptance contract proves wrong, update the contract deliberately and record why. Never silently reinterpret it after seeing results.
6. If architecture must change, update `DESIGN.md`/owning subsystem doc first and add an ADR when the decision is durable enough to deserve one.

**Slice ID scheme:** `S` + campaign number + two-digit sequence (`S101` = Campaign I, slice 01).

## Honest sizing

**94 slices across 8 campaigns.** This is still compact beside larger RuneForgeAI builds, but it is a serious multi-week system. The hardest domains are living memory, real-time voice/audio routing and durable cross-system bridges. Campaign VIII exists because "sovereign" must include migration, backup and resurrection, not merely local inference.

| Campaign | Slices | Theme |
|---|---:|---|
| I | 14 | Foundation, text chat, personas, card compatibility |
| II | 15 | Lorebooks, sampling, prompt engine, group chats |
| III | 11 | Backend seams: Ollama + OpenRouter + independent embeddings |
| IV | 15 | Living memory / RAG / temporal truth |
| V | 14 | Real-time voice loop and audio routing |
| VI | 11 | Versioned bridge APIs: VRChat + games |
| VII | 6 | Aesir-native cutover |
| VIII | 8 | Sovereignty, durability, release and resurrection |
| **Total** | **94** | |

---

## CAMPAIGN I — Foundation, text chat, personas

*Goal: a running local app where Volmarr can chat in text with an imported character, on a schema that can safely evolve.*

- **S101 Repo scaffold** — Builds: Python `src/` + `tests/`, Ruff lint/format policy, pytest, package metadata, `.gitignore`, CLI entrypoint, one real smoke test. **Do not modify root README.** Acceptance: `pytest` exits 0 (not pytest's exit-5 empty-suite case); lint/format checks pass; `python -m app --help` or final package equivalent works.
- **S102 App shell + local auth boundary** — Builds: FastAPI app, `/healthz`, generated high-entropy local credential, constant-time comparison where appropriate, bind `127.0.0.1` default, initial browser-origin/session decision recorded. Acceptance: unauthenticated protected API 401; localhost binding default proven; healthz 200; secret absent from logs/responses.
- **S103 Storage core + migrations** — Builds: SQLAlchemy async + SQLite, first versioned migration system, `users/owners`, `characters`, `chats`, `messages`, `user_id` ownership fields; foreign keys/WAL/busy-timeout policy. Acceptance: fresh DB migrates to HEAD; CRUD round trip; migration version recorded; `PRAGMA foreign_keys` verified; representative prior fixture can be migrated once one exists.
- **S104 Character Card import** — Builds: v1/v2/current-v3 JSON/PNG parsing, `chara`/`ccv3` metadata handling, unknown fields preserved, input size/path validation. Acceptance: legal fixture corpus imports semantically losslessly; malformed/truncated fixtures fail with typed errors; no archive/path traversal.
- **S105 Character Card export** — Builds: deliberate supported JSON/PNG export versions, opaque extensions preserved, PNG metadata CRC handling. Acceptance: import→export→import preserves semantic card data and opaque supported metadata; creator metadata remains metadata.
- **S106 Character service + `/api/v1/characters`** — Builds: CRUD, avatar/asset references. Acceptance: API CRUD + asset tests; unsafe filename/path attempts rejected.
- **S107 Chat service + `/api/v1/chats`** — Builds: CRUD, message append/edit/delete, stable IDs/mutation timestamps. Acceptance: API tests; edits/deletes reflected in history and emit mutation events for future memory sync.
- **S108 Generation stub + normalized SSE** — Builds: `POST /api/v1/generate` streaming normalized events from a fake backend; cancellation token. Acceptance: stream parses; client disconnect/Stop cancels stub; no orphan task; raw fake-provider format does not leak.
- **S109 Chat UI** — Builds: Jinja + htmx/Alpine chat page, incremental token rendering, stop button, error state. Acceptance: scripted browser walkthrough; Stop propagates cancellation.
- **S110 Persona prompt assembly** — Builds: card prompt fields → structured slots; `{{char}}`/`{{user}}`/`{{original}}`; creator notes/tags/creator excluded unless spec says otherwise. Acceptance: golden slot-manifest tests on fixtures.
- **S111 Chat management UI** — Builds: list/rename/delete/export chats. Acceptance: UI flows tested; destructive action confirmation semantics defined.
- **S112 Campaign hardening + install docs** — Builds: full suite, `docs/QUICKSTART.md`, Linux/systemd reference unit without making systemd an architecture dependency. Acceptance: fresh-machine documented install succeeds; service starts; root README untouched.
- **S113 CHARX + asset compatibility** — Builds: current v3 CHARX archive import/export, safe asset extraction/storage, supported asset round trip. Acceptance: normative current-v3 fixtures round-trip; archive traversal/zip-bomb style bounds tested; unknown compatible metadata preserved.
- **S114 Backup foundation** — Builds: safe SQLite online-backup command/API + restore-to-staging check. Acceptance: backup taken while app can be active opens cleanly and passes integrity check; failed restore cannot replace working DB.

## CAMPAIGN II — Lorebooks, presets, prompt template, groups

*Goal: a prompt engine whose decisions are deterministic and inspectable.*

- **S201 Lorebook model + API** — Builds: `lorebooks`/`lore_entries`, `/api/v1/lorebooks` CRUD. Acceptance: CRUD + ownership tests.
- **S202 Keyword scanning** — Builds: primary/secondary keys, whole-word/case toggles, scan depth. Acceptance: fixture chats trigger exactly expected entries.
- **S203 Activation semantics** — Builds: constant/selective/sticky/cooldown/delay/recursion, cycle detection, hard recursion depth. Acceptance: scenario per semantic; cyclic lore terminates deterministically.
- **S204 Budget + priority** — Builds: token budget, priority, deterministic stable tie-break for equal priority, seeded probability where used. Acceptance: over-budget fixtures resolve identically under fixed state/seed.
- **S205 Prompt template engine** — Builds: typed ordered slots, roles/positions/priorities/budgets; reserve response budget first; deterministic overflow policy. Acceptance: golden prompt manifests never exceed effective context allowance after reservation.
- **S206 Author's Note depth injection** — Builds: reinforcement slot N messages from end. Acceptance: prompt tests verify exact position/depth behavior and boundary cases.
- **S207 Sampling presets** — Builds: named variable-shape canonical parameter bag + prompt-template reference. Acceptance: CRUD/round-trip tests.
- **S208 Backend parameter filtering** — Builds: capability-driven unsupported-control filtering/warnings. Acceptance: strict fake backend receives only declared controls; warning is structured and testable.
- **S209 Lorebook editor UI** — Builds: htmx editor + activation preview. Acceptance: UI flows; preview matches server activation engine.
- **S210 Group chats** — Builds: room/members/per-message speaker. Acceptance: API/data tests.
- **S211 Speaker policies** — Builds: Manual/Natural/List/Pooled, mute/talkativeness; seeded deterministic tests. Acceptance: policy fixtures incl. fallback behavior.
- **S212 Pluggable director interface** — Builds: speaker-policy interface + deterministic fake LLM director seam. Acceptance: custom policy plugs in without group-service changes.
- **S213 Campaign hardening + prompt docs** — Acceptance: suite green; prompt/lore behavior documented in owning docs.
- **S214 Prompt Trace + token ledger** — Builds: safe trace manifest: included/discarded slots, token counts/estimates, lore triggers, memory placeholders, backend metadata, discard reasons. Acceptance: golden trace fixtures; secrets provably absent.
- **S215 Prompt inspector UI** — Builds: human-readable trace view with slot/lore budget explanations. Acceptance: browser test can answer "why was this injected/discarded?" from trace data.

## CAMPAIGN III — Backend seams: Ollama + OpenRouter

*Goal: real models behind chat, independently selectable embeddings, and normalized failure behavior.*

- **S301 Backend interfaces** — Builds: `ChatBackend`, normalized events, `SamplingParams`, `ModelInfo`, capability metadata, cancellation and error types per `BACKEND_CONTRACT.md`. Acceptance: one fake backend passes common contract suite.
- **S302 Ollama chat adapter** — Builds: native `/api/chat` NDJSON → normalized events. Acceptance: recorded-fixture contract tests mandatory; tagged real-Ollama test optional; cancellation closes stream.
- **S303 OpenRouter adapter** — Builds: OpenAI-compatible SSE normalization, namespaced model IDs contained behind metadata. Acceptance: fixture SSE incl. `[DONE]`, errors/usage; no provider wire objects leak.
- **S304 Embedding backend seam** — Builds: independent `EmbeddingBackend`, FTS fallback contract, vector provenance. Ollama implementation uses current official native embed endpoint after re-verification. Acceptance: embedding fake/adapter returns provider/model/dims/version; unavailable embeddings degrade without crash.
- **S305 Model listing + health + token counting** — Builds normalized health/model metadata and exact/provider/estimated token-count quality. Acceptance: fixtures for Ollama/OpenRouter; UI/service can distinguish estimate from exact count.
- **S306 Backend profiles + secrets** — Builds named modality profiles; secret references server-side; threat model implementation. Acceptance: secret appears in no API response/log/trace/export capture; profile can pair cloud chat with local embeddings.
- **S307 Wire chat through seam** — Builds: replace stub; per-chat profile selection. Acceptance: tagged end-to-end Ollama chat streams real tokens; ordinary suite works without Ollama.
- **S308 Campaign hardening + docs** — Acceptance: full backend contract suite green; `BACKEND_CONTRACT.md` reflects implementation.
- **S309 Error taxonomy + retry contract** — Builds normalized auth/rate-limit/context/timeout/cancel/provider errors and bounded retries. Acceptance: fixtures prove no silent cross-provider continuation after visible output.
- **S310 Capability negotiation** — Builds model/backend feature discovery consumed by UI/prompt/sampler layers. Acceptance: unsupported controls/features are disabled/degraded from metadata, not provider-name conditionals.
- **S311 Independent embedding profiles + migration hook** — Builds switching active embedding profile without switching chat model; schedules re-embedding while FTS remains available. Acceptance: old/new incompatible spaces never mix in one similarity query.

## CAMPAIGN IV — Living memory / RAG

*Goal: Rúnmál remembers as temporal, provenance-backed knowledge rather than a bag of embeddings.*

- **S401 Vector-store interface + sqlite-vec adapter** — Builds isolated store abstraction. Acceptance: insert/search round trip + fake-store swap.
- **S402 Embedding ingestion** — Builds chunking/embedding pipeline and complete provenance. Acceptance: fixture documents produce vectors with profile/model/dim/version metadata.
- **S403 Hybrid retrieval** — Builds vector + FTS5 + structured filtering and deterministic score fusion. Acceptance: fixture queries exercise both paths and deterministic ranking.
- **S404 Chat auto-summarization** — Builds rolling summaries of old history with provenance/version metadata. Acceptance: long fixture chat remains under prompt budget; summary source range recorded.
- **S405 Event/fact extraction** — Builds asynchronous LLM-assisted candidate extraction using a deterministic fake in tests. Acceptance: fixture transcript → expected candidates/provenance; reply path never waits on extraction.
- **S406 Salience + decay** — Builds retrieval strength/stability/recall reinforcement using injected clock. Acceptance: fake-clock scenarios prove decay and pinned/stable behavior.
- **S407 Witness-scoped recall** — Builds explicit witness/scope model and pre-score eligibility filter. Acceptance: character A cannot retrieve character B's private-chat memory, including through vector hits.
- **S408 Memory nucleus** — Builds curated per-character/user core memory slot. Acceptance: prompt trace shows nucleus inclusion and budget behavior.
- **S409 Mutation sync** — Builds edit/delete/rename maintenance events against memory provenance. Acceptance: removing one of several sources preserves supported fact; removing all support invalidates derived memory.
- **S410 Memory browser UI** — Builds inspect/search plus provenance/witness/status display. Acceptance: UI tests.
- **S411 Provenance graph** — Builds many-to-many source evidence and extractor/user-edit provenance. Acceptance: every derived fixture memory can trace to canonical evidence.
- **S412 Deduplication + consolidation** — Builds duplicate/refinement detection and provenance-preserving merge. Acceptance: repeated paraphrases consolidate idempotently without losing evidence.
- **S413 Contradiction + supersession engine** — Builds active/historical/disputed/superseded states and temporal replacement. Acceptance: "old residence → new residence" fixture keeps history while current-state query prefers new truth.
- **S414 Recall trace + memory evaluator** — Builds per-memory eligibility/score/discard explanation and deterministic evaluation corpus. Acceptance: evaluator covers witness, temporal, duplicate, deletion, decay and re-embedding scenarios.
- **S415 Full rebuild/reindex** — Builds rebuild derived memory/vector/index state from canonical messages/provenance, including embedding-profile change. Acceptance: destroy derived indexes → rebuild → evaluation corpus remains semantically correct.

## CAMPAIGN V — Real-time voice loop

*Goal: natural live conversation on target hardware with truthful interruption bookkeeping.*

- **S501 Audio plumbing** — Builds device enumeration, explicit role selection, capture/playback, 16 kHz mono ring buffer/pre-roll. Acceptance: loopback fixture/manual tagged test; missing saved device produces remap state rather than silent OS-default switch.
- **S502 Silero VAD** — Builds frame/state/hysteresis/pre-roll/tunable parameters. Acceptance: fixture speech/noise/silence segmentation meets a threshold defined in the slice before results are run.
- **S503 STT service** — Builds faster-whisper `small` int8 baseline with word timestamps; benchmark harness hook. Acceptance: fixed fixture corpus meets predeclared transcript-quality/RTF thresholds on reference hardware or records a deliberate contract revision.
- **S504 TTS service + license gate** — Builds selected Kokoro-compatible/permissive TTS path, sentence/chunk streaming, voice audition. **Before implementation acceptance, verify full runtime/model/phonemization dependency licenses.** Acceptance: dependency audit passes policy; fixed text corpus synthesizes; first-audio threshold defined before benchmark and reported.
- **S505 Voice orchestrator state machine** — Builds explicit LISTENING/USER_SPEAKING/FINALIZING/THINKING/SYNTHESIZING/SPEAKING/INTERRUPTING states. Acceptance: deterministic simulated state transitions.
- **S506 Turn-taking** — Builds endpoint hangover/preemptive trigger/resume cancellation. Acceptance: fixture turn scenarios cover pauses/resumed speech.
- **S507 Barge-in** — Builds one interruption event propagating through LLM, TTS queue and playback; backchannel tolerance. Acceptance: sustained interruption stops playback within predeclared threshold; backchannel fixture does not falsely interrupt.
- **S508 Playback truth ledger** — Builds text-span/audio-chunk playback records and conservative heard-text reconstruction. Acceptance: mid-chunk interruption never records known-unplayed suffix as certainly heard; uncertainty represented when alignment is insufficient.
- **S509 Echo/self-interruption support contract** — Builds headset-first supported path and/or verified AEC/routing path; self-output separation where possible. Acceptance: supported mode passes companion-speaking + room-noise fixture/manual hardware test; documentation states unsupported modes honestly.
- **S510 Latency metrics** — Builds monotonic per-stage metrics, p50/p95 report. Acceptance: every complete turn produces coherent timing chain; no negative/impossible stage ordering.
- **S511 Voice UI island + campaign hardening** — Builds mic/status/waveform/device selector. Acceptance: UI tests + full voice suite; license scan remains green.
- **S512 Per-character voice profiles** — Builds TTS backend/voice/params references on personas with fallback. Acceptance: persona switch selects correct voice without changing chat backend.
- **S513 Virtual-cable/device routing** — Builds persisted logical routes for companion output and optional room/game ingress. Acceptance: routing survives restart when devices remain; missing device is explicit.
- **S514 Voice benchmark harness** — Builds reproducible benchmark command/corpus/report for STT, TTS, end-to-end and interruption latency. Acceptance: report records hardware, versions, models and p50/p95; thresholds are not rewritten after results merely to pass.

## CAMPAIGN VI — Versioned bridge APIs (VRChat + games)

*Goal: Rúnmál becomes a stable brain service for external companions without game-specific code infecting core domains.*

- **S601 Bridge auth** — Builds scoped/revocable per-bridge credentials. Acceptance: wrong-scope/revoked-token negative tests.
- **S602 Versioned conversation-state API** — Builds `/api/v1/bridge/...` read/write turns with ownership/scope checks. Acceptance: contract tests.
- **S603 Persona switching API** — Builds explicit future-turn persona selection. Acceptance: prompt trace reflects switch; old messages retain original speakers.
- **S604 TTS hook API** — Builds scoped request and lifecycle events. Acceptance: hook round trip + cancellation.
- **S605 VRChat OSC reference bridge** — Builds Python OSC/control reference bridge, second-account follower pattern where desired. Acceptance: OSC behavior documented/tested manually or with fixture; docs explicitly state OSC is not room-voice capture.
- **S606 Conan Exiles RCON reference** — Builds design + clean-room skeleton translating Source RCON/game events to stable bridge API. Acceptance: protocol fixture handshake; core contains no Conan-specific branches.
- **S607 Skyrim-style HTTP bridge** — Builds prompt/event translation adapter against stable Rúnmál contract. Acceptance: mock game client contract tests.
- **S608 Bridge builder docs + hardening** — Acceptance: third party can implement a bridge from `BRIDGE_PROTOCOL.md`; suite green.
- **S609 Durable bridge event outbox** — Builds ordered event IDs, checkpoint/ack/replay/retention for proactive companion speech. Acceptance: disconnect/reconnect resumes without lost/duplicated acknowledged events.
- **S610 Idempotency + protocol capability discovery** — Builds write idempotency keys and bridge capability endpoint/version metadata. Acceptance: transport retry never duplicates a turn; conflicting key reuse errors.
- **S611 VRChat room-audio ingress** — Builds explicit PC-host audio capture/routing integration feeding voice ingress while excluding/marking known self-output. Acceptance: documented PCVR test demonstrates participant/game audio reaches STT independently from OSC; unsupported standalone-Quest path stated honestly.

## CAMPAIGN VII — Aesir-native cutover

*Goal: Project Aesir becomes a first-class local inference heart without changing Rúnmál domain code.*

- **S701 Aesir ChatBackend adapter** — Builds adapter to Aesir server surface. Acceptance: fixture stream passes the same ChatBackend contract suite.
- **S702 Sampling/capability mapping** — Builds canonical controls ↔ Aesir; unsupported controls declared. Acceptance: unsupported never sent/pretended honored.
- **S703 Aesir embeddings** — Builds Aesir `EmbeddingBackend` or explicit unsupported capability with FTS fallback. Acceptance: correct provenance/fallback.
- **S704 Profile migration tooling** — Builds chat/profile migration Ollama/OpenRouter → Aesir with history/state intact. Acceptance: migration fixture.
- **S705 Performance validation** — Builds benchmark vs declared Ollama baseline. Acceptance: acceptable regression/performance bar is written before run; report records configuration and result.
- **S706 Cutover docs + hardening** — Acceptance: full suite green; end-to-end chat/memory works on Aesir profile; no domain code depends on provider identity.

## CAMPAIGN VIII — Sovereignty, durability and release

*Goal: prove Rúnmál survives upgrades, machines and providers. Burn the hall down; restore the hearthstone.*

- **S801 Portable `.runmal` archive** — Builds versioned manifest + characters/chats/lorebooks/memories/provenance/presets/assets export; excludes secrets and rebuildable caches by policy. Acceptance: export schema validated; secret canary absent from archive bytes/text entries.
- **S802 Full backup + restore UI/CLI** — Builds safe online SQLite backup, asset snapshot, staging restore and restore report. Acceptance: backup under active app restores cleanly without corrupting current install on failed validation.
- **S803 Migration/upgrade harness** — Builds released old-schema fixtures and CI upgrade-to-HEAD path. Acceptance: every supported fixture migrates and preserves invariant checks.
- **S804 `runmal doctor`** — Builds diagnostics for DB integrity/migration, sqlite-vec, models/providers, audio devices, broken provenance, ports, assets and configuration. Acceptance: injected faults produce specific actionable findings without leaking secrets.
- **S805 CI platform matrix** — Builds at least Linux + Windows core matrix; tagged hardware/provider jobs separate. Acceptance: core tests pass on both; platform-specific unsupported voice cases are explicit, not hidden skips.
- **S806 SBOM + license manifest/gate** — Builds dependency/model/asset inventory and forbidden-license policy check for distributed release set. Acceptance: deliberately injected forbidden fixture/dependency is detected; release artifact has SBOM/license report.
- **S807 Release/versioning machinery** — Builds semantic app versioning, archive/schema versions, CHANGELOG/release notes/migration notes, reproducible release checklist. Acceptance: dry-run release artifact/version metadata mutually consistent.
- **S808 Sovereign resurrection test** — Builds clean-install restore acceptance. Acceptance: on a fresh state directory, restore prior supported Rúnmál data, rebuild derived indexes under a compatible possibly different embedding profile, open the same persona/chat/memory/lore/assets, and successfully generate a new turn. **The provider is replaceable; the persistent relationship state survives.**

---

## Forge-Fellowship coordination

- Yrsa and ChatGPT use `fellowship/FORGE-LOG.md` as the append-only asynchronous thread for design, roadmap, slice claims and reviews.
- Before starting a slice, read the latest relevant commit/log entry and do not duplicate work already claimed.
- A builder may add a new slice with the next free number in the correct campaign, preserving Builds/Acceptance shape and updating campaign totals.
- Volmarr resolves product-direction disputes.
- The root `README.md` remains untouched unless Volmarr explicitly orders that specific edit.

## Suggested ownership by cognitive pass

Either forge-mate may implement any slice. For high-risk slices, separate passes even when one model performs all of them:

1. Cartographer — map existing state.
2. Architect — confirm domain/contract/invariants.
3. Forge Worker — implement.
4. Auditor — attack assumptions/edge cases.
5. Verifier — run decisive tests/benchmarks.
6. Scribe — update persistent project memory.