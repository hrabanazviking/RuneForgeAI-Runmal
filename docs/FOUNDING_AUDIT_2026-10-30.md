# P-001 — The Founding Audit (2026-10-30)

*Rúnmál's feature inventory, taken from its own tree — the founding
94 slices plus the extra UI campaign — each feature stated as
behaviour, with the test that proves it named. This is the "HAVE"
baseline the Two Mirrors delta table (P-004) is measured against:
nothing here is remembered; every row traces to `docs/ROADMAP.md`'s
slice definition and to a test file present in `tests/` on this tree
(`yrsa/two-mirrors-build`, audit run at the P-007 baseline commit).*

## Method and evidence

- Slice definitions (behaviour column) are quoted/paraphrased from
  `docs/ROADMAP.md` — the founding roadmap's own Builds text.
- Proving tests were matched mechanically by slice number against
  `tests/test_*.py` (111 test files on this tree) and spot-checked.
  The whole inventory stands under the P-007 fresh baseline:
  **685 passed, 6 skipped, 0 failed (691 collected)** on this VM,
  reproduced twice; the 6 skips are named host absences (no Ollama /
  voice extras on the VM). The founding purplelongship evidence run
  read 686 passed / 3 skipped (`538c918`).
- **Number-collision warning (inherited, documented in ROADMAP +
  STATUS):** the extra UI campaign (2026-10-12) landed under commit
  labels S209–S215 / S301–S311 that collide with roadmap slice
  numbers. Where two test files share a slice prefix (e.g.
  `test_s209_modes.py` and `test_s209_lorebook_editor_ui.py`), both
  are listed; the extra campaign's own inventory is separate below.
- Only two founding slices have no dedicated test file: S101 (its
  proving test is the smoke test, `tests/test_smoke.py`) and S112
  (campaign hardening — proven at suite level and by the documented
  fresh-install walk, not by a single file). Both are named as such
  in the table rather than papered over.

## The founding 94 — feature inventory

### Campaign I — Foundation, text chat, personas

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S101 | **Repo scaffold** — Python `src/` + `tests/`, Ruff lint/format policy, pytest, package metadata, `.gitignore`, CLI entrypoint, one real smoke test. **Do not modify root README.** | `tests/test_smoke.py` |
| S102 | **App shell + local auth boundary** — FastAPI app, `/healthz`, generated high-entropy local credential, constant-time comparison where appropriate, bind `127.0.0.1` default, initial browser-origin/session decision recorded | `tests/test_s102_auth.py` |
| S103 | **Storage core + migrations** — SQLAlchemy async + SQLite, first versioned migration system, `users/owners`, `characters`, `chats`, `messages`, `user_id` ownership fields; foreign keys/WAL/busy-timeout policy | `tests/test_s103_storage.py` |
| S104 | **Character Card import** — v1/v2/current-v3 JSON/PNG parsing, `chara`/`ccv3` metadata handling, unknown fields preserved, input size/path validation | `tests/test_s104_cards.py` |
| S105 | **Character Card export** — deliberate supported JSON/PNG export versions, opaque extensions preserved, PNG metadata CRC handling | `tests/test_s105_export.py` |
| S106 | **Character service + `/api/v1/characters`** — CRUD, avatar/asset references | `tests/test_s106_characters.py` |
| S107 | **Chat service + `/api/v1/chats`** — CRUD, message append/edit/delete, stable IDs/mutation timestamps | `tests/test_s107_chats.py` |
| S108 | **Generation stub + normalized SSE** — `POST /api/v1/generate` streaming normalized events from a fake backend; cancellation token | `tests/test_s108_generate.py` |
| S109 | **Chat UI** — Jinja + htmx/Alpine chat page, incremental token rendering, stop button, error state | `tests/test_s109_ui.py` |
| S110 | **Persona prompt assembly** — card prompt fields → structured slots; `{{char}}`/`{{user}}`/`{{original}}`; creator notes/tags/creator excluded unless spec says otherwise | `tests/test_s110_persona.py` |
| S111 | **Chat management UI** — list/rename/delete/export chats | `tests/test_s111_chat_management.py` |
| S112 | **Campaign hardening + install docs** — full suite, `docs/QUICKSTART.md`, Linux/systemd reference unit without making systemd an architecture dependency | No dedicated test file — proven at suite level (full suite green; see P-007 baseline) and by the documented fresh-install walk in `docs/QUICKSTART.md` |
| S113 | **CHARX + asset compatibility** — current v3 CHARX archive import/export, safe asset extraction/storage, supported asset round trip | `tests/test_s113_charx.py` |
| S114 | **Backup foundation** — safe SQLite online-backup command/API + restore-to-staging check | `tests/test_s114_backup.py` |

### Campaign II — Lorebooks, presets, prompt engine, groups

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S201 | **Lorebook model + API** — `lorebooks`/`lore_entries`, `/api/v1/lorebooks` CRUD | `tests/test_s201_lorebooks.py` |
| S202 | **Keyword scanning** — primary/secondary keys, whole-word/case toggles, scan depth | `tests/test_s202_scan.py` |
| S203 | **Activation semantics** — constant/selective/sticky/cooldown/delay/recursion, cycle detection, hard recursion depth | `tests/test_s203_activation.py` |
| S204 | **Budget + priority** — token budget, priority, deterministic stable tie-break for equal priority, seeded probability where used | `tests/test_s204_budget.py` |
| S205 | **Prompt template engine** — typed ordered slots, roles/positions/priorities/budgets; reserve response budget first; deterministic overflow policy | `tests/test_s205_composer.py` |
| S206 | **Author's Note depth injection** — reinforcement slot N messages from end | `tests/test_s206_depth.py` |
| S207 | **Sampling presets** — named variable-shape canonical parameter bag + prompt-template reference | `tests/test_s207_presets.py` |
| S208 | **Backend parameter filtering** — capability-driven unsupported-control filtering/warnings | `tests/test_s208_compat.py` |
| S209 | **Lorebook editor UI** — htmx editor + activation preview | `tests/test_s209_lorebook_editor_ui.py`<br>`tests/test_s209_modes.py` |
| S210 | **Group chats** — room/members/per-message speaker | `tests/test_s210_group_chats.py`<br>`tests/test_s210_groupchat.py` |
| S211 | **Speaker policies** — Manual/Natural/List/Pooled, mute/talkativeness; seeded deterministic tests | `tests/test_s211_connections.py`<br>`tests/test_s211_speaker_policies.py` |
| S212 | **Pluggable director interface** — speaker-policy interface + deterministic fake LLM director seam | `tests/test_s212_director.py`<br>`tests/test_s212_editor.py` |
| S213 | **Campaign hardening + prompt docs** —  | `tests/test_s213_hardening.py`<br>`tests/test_s213_tools.py` |
| S214 | **Prompt Trace + token ledger** — safe trace manifest: included/discarded slots, token counts/estimates, lore triggers, memory placeholders, backend metadata, discard reasons | `tests/test_s214_prompt_trace.py`<br>`tests/test_s214_tokens.py` |
| S215 | **Prompt inspector UI** — human-readable trace view with slot/lore budget explanations | `tests/test_s215_e2e.py`<br>`tests/test_s215_prompt_inspector.py` |

### Campaign III — Backend seams: Ollama + OpenRouter + embeddings

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S301 | **Backend interfaces** — `ChatBackend`, normalized events, `SamplingParams`, `ModelInfo`, capability metadata, cancellation and error types per `BACKEND_CONTRACT.md` | `tests/test_s301_backends.py`<br>`tests/test_s301_tokens.py` |
| S302 | **Ollama chat adapter** — native `/api/chat` NDJSON → normalized events | `tests/test_s302_ollama.py`<br>`tests/test_s302_renderer.py` |
| S303 | **OpenRouter adapter** — OpenAI-compatible SSE normalization, namespaced model IDs contained behind metadata | `tests/test_s303_gallery.py`<br>`tests/test_s303_openrouter.py` |
| S304 | **Embedding backend seam** — independent `EmbeddingBackend`, FTS fallback contract, vector provenance. Ollama implementation uses current official native embed endpoint after re-verification | `tests/test_s304_embeddings.py`<br>`tests/test_s304_lorebook_editor.py` |
| S305 | **Model listing + health + token counting** — Builds normalized health/model metadata and exact/provider/estimated token-count quality | `tests/test_s305_group_ui.py`<br>`tests/test_s305_registry.py` |
| S306 | **Backend profiles + secrets** — Builds named modality profiles; secret references server-side; threat model implementation | `tests/test_s306_completion.py`<br>`tests/test_s306_profiles.py` |
| S307 | **Wire chat through seam** — replace stub; per-chat profile selection | `tests/test_s307_seam.py`<br>`tests/test_s307_variables.py` |
| S308 | **Campaign hardening + docs** —  | `tests/test_s308_contract_suite.py`<br>`tests/test_s308_palette.py` |
| S309 | **Error taxonomy + retry contract** — Builds normalized auth/rate-limit/context/timeout/cancel/provider errors and bounded retries | `tests/test_s309_a11y.py`<br>`tests/test_s309_retry.py` |
| S310 | **Capability negotiation** — Builds model/backend feature discovery consumed by UI/prompt/sampler layers | `tests/test_s310_negotiation.py`<br>`tests/test_s310_responsive.py` |
| S311 | **Independent embedding profiles + migration hook** — Builds switching active embedding profile without switching chat model; schedules re-embedding while FTS remains available | `tests/test_s311_embedding_profiles.py`<br>`tests/test_s311_ui_regression.py` |

### Campaign IV — Living memory / RAG

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S401 | **Vector-store interface + sqlite-vec adapter** — Builds isolated store abstraction | `tests/test_s401_vectorstore.py` |
| S402 | **Embedding ingestion** — Builds chunking/embedding pipeline and complete provenance | `tests/test_s402_ingestion.py` |
| S403 | **Hybrid retrieval** — Builds vector + FTS5 + structured filtering and deterministic score fusion | `tests/test_s403_hybrid.py` |
| S404 | **Chat auto-summarization** — Builds rolling summaries of old history with provenance/version metadata | `tests/test_s404_summarize.py` |
| S405 | **Event/fact extraction** — Builds asynchronous LLM-assisted candidate extraction using a deterministic fake in tests | `tests/test_s405_extraction.py` |
| S406 | **Salience + decay** — Builds retrieval strength/stability/recall reinforcement using injected clock | `tests/test_s406_salience.py` |
| S407 | **Witness-scoped recall** — Builds explicit witness/scope model and pre-score eligibility filter | `tests/test_s407_witness.py` |
| S408 | **Memory nucleus** — Builds curated per-character/user core memory slot | `tests/test_s408_nucleus.py` |
| S409 | **Mutation sync** — Builds edit/delete/rename maintenance events against memory provenance | `tests/test_s409_sync.py` |
| S410 | **Memory browser UI** — Builds inspect/search plus provenance/witness/status display | `tests/test_s410_browser.py` |
| S411 | **Provenance graph** — Builds many-to-many source evidence and extractor/user-edit provenance | `tests/test_s411_graph.py` |
| S412 | **Deduplication + consolidation** — Builds duplicate/refinement detection and provenance-preserving merge | `tests/test_s412_consolidation.py` |
| S413 | **Contradiction + supersession engine** — Builds active/historical/disputed/superseded states and temporal replacement | `tests/test_s413_supersession.py` |
| S414 | **Recall trace + memory evaluator** — Builds per-memory eligibility/score/discard explanation and deterministic evaluation corpus | `tests/test_s414_evaluator.py` |
| S415 | **Full rebuild/reindex** — Builds rebuild derived memory/vector/index state from canonical messages/provenance, including embedding-profile change | `tests/test_s415_rebuild.py` |

### Campaign V — Real-time voice loop

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S501 | **Audio plumbing** — Builds device enumeration, explicit role selection, capture/playback, 16 kHz mono ring buffer/pre-roll | `tests/test_s501_audio.py` |
| S502 | **Silero VAD** — Builds frame/state/hysteresis/pre-roll/tunable parameters | `tests/test_s502_vad.py` |
| S503 | **STT service** — Builds faster-whisper `small` int8 baseline with word timestamps; benchmark harness hook | `tests/test_s503_stt.py` |
| S504 | **TTS service + license gate** — Builds selected Kokoro-compatible/permissive TTS path, sentence/chunk streaming, voice audition. **Before implementation acceptance, verify full runtime/model/phonemization dependency licenses.** | `tests/test_s504_tts.py` |
| S505 | **Voice orchestrator state machine** — Builds explicit LISTENING/USER_SPEAKING/FINALIZING/THINKING/SYNTHESIZING/SPEAKING/INTERRUPTING states | `tests/test_s505_orchestrator.py` |
| S506 | **Turn-taking** — Builds endpoint hangover/preemptive trigger/resume cancellation | `tests/test_s506_turntaking.py` |
| S507 | **Barge-in** — Builds one interruption event propagating through LLM, TTS queue and playback; backchannel tolerance | `tests/test_s507_bargein.py` |
| S508 | **Playback truth ledger** — Builds text-span/audio-chunk playback records and conservative heard-text reconstruction | `tests/test_s508_ledger.py` |
| S509 | **Echo/self-interruption support contract** — Builds headset-first supported path and/or verified AEC/routing path; self-output separation where possible | `tests/test_s509_support.py` |
| S510 | **Latency metrics** — Builds monotonic per-stage metrics, p50/p95 report | `tests/test_s510_metrics.py` |
| S511 | **Voice UI island + campaign hardening** — Builds mic/status/waveform/device selector | `tests/test_s511_voice_ui.py` |
| S512 | **Per-character voice profiles** — Builds TTS backend/voice/params references on personas with fallback | `tests/test_s512_voice_profiles.py` |
| S513 | **Virtual-cable/device routing** — Builds persisted logical routes for companion output and optional room/game ingress | `tests/test_s513_routing.py` |
| S514 | **Voice benchmark harness** — Builds reproducible benchmark command/corpus/report for STT, TTS, end-to-end and interruption latency | `tests/test_s514_benchmark.py` |

### Campaign VI — Bridge APIs (VRChat + games)

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S601 | **Bridge auth** — Builds scoped/revocable per-bridge credentials | `tests/test_s601_bridge_auth.py` |
| S602 | **Versioned conversation-state API** — Builds `/api/v1/bridge/...` read/write turns with ownership/scope checks | `tests/test_s602_bridge_conversation.py` |
| S603 | **Persona switching API** — Builds explicit future-turn persona selection | `tests/test_s603_bridge_persona.py` |
| S604 | **TTS hook API** — Builds scoped request and lifecycle events | `tests/test_s604_bridge_tts.py` |
| S605 | **VRChat OSC reference bridge** — Builds Python OSC/control reference bridge, second-account follower pattern where desired | `tests/test_s605_vrchat_osc.py` |
| S606 | **Conan Exiles RCON reference** — Builds design + clean-room skeleton translating Source RCON/game events to stable bridge API | `tests/test_s606_conan_rcon.py` |
| S607 | **Skyrim-style HTTP bridge** — Builds prompt/event translation adapter against stable Rúnmál contract | `tests/test_s607_skyrim_http.py` |
| S608 | **Bridge builder docs + hardening** —  | `tests/test_s608_bridge_conformance.py` |
| S609 | **Durable bridge event outbox** — Builds ordered event IDs, checkpoint/ack/replay/retention for proactive companion speech | `tests/test_s609_bridge_outbox.py` |
| S610 | **Idempotency + protocol capability discovery** — Builds write idempotency keys and bridge capability endpoint/version metadata | `tests/test_s610_bridge_idempotency.py` |
| S611 | **VRChat room-audio ingress** — Builds explicit PC-host audio capture/routing integration feeding voice ingress while excluding/marking known self-output | `tests/test_s611_room_ingress.py` |

### Campaign VII — Aesir cutover

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S701 | **Aesir ChatBackend adapter** — Builds adapter to Aesir server surface | `tests/test_s701_aesir.py` |
| S702 | **Sampling/capability mapping** — Builds canonical controls ↔ Aesir; unsupported controls declared | `tests/test_s702_aesir_mapping.py` |
| S703 | **Aesir embeddings** — Builds Aesir `EmbeddingBackend` or explicit unsupported capability with FTS fallback | `tests/test_s703_aesir_embeddings.py` |
| S704 | **Profile migration tooling** — Builds chat/profile migration Ollama/OpenRouter → Aesir with history/state intact | `tests/test_s704_profile_migration.py` |
| S705 | **Performance validation** — Builds benchmark vs declared Ollama baseline | `tests/test_s705_benchmark.py` |
| S706 | **Cutover docs + hardening** —  | `tests/test_s706_cutover.py` |

### Campaign VIII — Sovereignty, durability, release

| Slice | Feature (behaviour) | Proving test(s) |
|---|---|---|
| S801 | **Portable `.runmal` archive** — Builds versioned manifest + characters/chats/lorebooks/memories/provenance/presets/assets export; excludes secrets and rebuildable caches by policy | `tests/test_s801_archive.py` |
| S802 | **Full backup + restore UI/CLI** — Builds safe online SQLite backup, asset snapshot, staging restore and restore report | `tests/test_s802_restore.py` |
| S803 | **Migration/upgrade harness** — Builds released old-schema fixtures and CI upgrade-to-HEAD path | `tests/test_s803_upgrade_harness.py` |
| S804 | **`runmal doctor`** — Builds diagnostics for DB integrity/migration, sqlite-vec, models/providers, audio devices, broken provenance, ports, assets and configuration | `tests/test_s804_doctor.py` |
| S805 | **CI platform matrix** — Builds at least Linux + Windows core matrix; tagged hardware/provider jobs separate | `tests/test_s805_platform_matrix.py` |
| S806 | **SBOM + license manifest/gate** — Builds dependency/model/asset inventory and forbidden-license policy check for distributed release set | `tests/test_s806_sbom.py` |
| S807 | **Release/versioning machinery** — Builds semantic app versioning, archive/schema versions, CHANGELOG/release notes/migration notes, reproducible release checklist | `tests/test_s807_release.py` |
| S808 | **Sovereign resurrection test** — Builds clean-install restore acceptance | `tests/test_s808_resurrection.py` |

## Extra UI campaign (inserted 2026-10-12, complete — NOT part of the 94)

Evidence for the wave as a whole: 287 tests green on purplelongship
at the wave's close (commit `5bd28cd`), recorded in `docs/ROADMAP.md`
("Extra campaign") and `docs/STATUS.md`. Behaviour inventory
(historical commit label → what it built):

| Label | Feature (behaviour) |
|---|---|
| S209x | Impersonation controls |
| S210x | Group chat core |
| S211x | Connection profiles UI + health |
| S212x | Persona/scenario/greeting UI |
| S213x | Impersonation/depth tools UI |
| S214x | Token counting |
| S215x | Lorebook/group/prompt integration test + hardening |
| S301x | Hearth design tokens + layout shell |
| S302x | Chat thread + streaming renderer |
| S303x | Character gallery + editor shell |
| S304x | Lorebook editor |
| S305x | Group chat UI |
| S306x | Connection + preset UI completion |
| S307x | Macro/variable helper UI |
| S308x | Command palette + keyboard map |
| S309x | Accessibility pass |
| S310x | Mobile/responsive pass |
| S311x | UI regression + visual fixtures |

(The `x` suffix is this audit's disambiguation only; the repo's own
reading rule is: labels in 2026-10-12 history/docs refer to this
campaign unless explicitly tied to the roadmap.)

## Post-founding additions standing on this tree

- **Chatterbox user-installed reclassification** (Volmarr's ruling,
  2026-10-13): Chatterbox is `default_shipped=false` with a stock-tree
  one-button install recipe; the S504 licence gate guards only the
  default shipped tree. CosyVoice remains the sole admitted default
  voice. Record: `docs/VOICE_LICENSE_MATRIX.md` + ADR-0005 addenda.
- **S805 self-hosted platform matrix** (owner's ruling replacing the
  hosted-CI shape, ADR-0007): Linux leg passed on purplelongship;
  Windows leg recorded NOT RUN — no Windows machine in the fleet and
  none will be rented. This is a ruled state, not a hidden gap.

## Honest caveats the delta table must carry forward

1. **CosyVoice CPU performance:** the predeclared GPU-reference
   thresholds (first-audio p50 ≤ 1.5 s, RTF ≤ 1.0) were NOT met by
   the shipped CPU build (measured p50 23.15 s / RTF 6.73) and were
   NOT adjusted. The voice feature is HAVE; its CPU speed is
   HAVE-THIN. (Carried from P-006; feeds P-009/P-010.)
2. **Host-absence skips:** voice-device, Ollama-live, and UDP tests
   skip on hosts without that hardware/service (named in P-007);
   "proven" for those rows means proven on the hosts named in their
   evidence (chiefly purplelongship), not on every host.
3. **Windows:** no feature in this inventory is Windows-proven; the
   matrix's Windows leg is recorded not run (see above).

## What P-001 hands onward

- To P-002/P-003: the behaviour language used above (feature =
  observable behaviour + named proof) is the language the two mirror
  censuses must use, so P-004's delta table compares like with like.
- To P-004: every HAVE claim in the delta table must cite a row of
  this audit; anything not in this inventory is MISSING or THIN
  until proven otherwise.
