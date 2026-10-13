# Rúnmál Forge Status

**Last documentation pass:** 2026-10-13

## Current phase

**Implementation — Campaign VII (Aesir cutover) next, from 2026-10-13.** Campaigns I (S101–S114), II (S201–S215), III (S301–S311, backend seams), IV (S401–S415, living memory), V (S501–S514, real-time voice loop) and VI (S601–S611, bridge APIs) are complete and verified on the forge laptop (purplelongship); the full suite stands at **616 tests green** at Campaign VI's close (2026-10-13; 3 skips). An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices (287 tests green at that wave's close, commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumed at the true roadmap S209, completed Campaign II the same day, and then forged the true Campaigns III and IV. True roadmap progress: **80/94** (S101–S114 + S201–S215 + S301–S311 + S401–S415 + S501–S514 + S601–S611) plus the extra UI campaign.

## Current campaign

**Campaign VI — Bridge APIs (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)**. All 11 slices (S601–S611) are implemented and laptop-verified; full suite on purplelongship at the close: **616 passed, 3 skipped**. The bridge surface (BRIDGE_PROTOCOL §§1–17): paired-credential auth with exact capability+resource scopes (S601, migration 0016); versioned conversation-state/turn/generate API with speaker provenance (S602); future-only persona switching (S603); a TTS job hook whose playback reports deliberately never feed the S508 heard-text ledger (S604); three reference bridges outside the core — VRChat OSC (S605), Conan Exiles RCON skeleton (S606), Skyrim-style hosted HTTP (S607) — sharing one HTTP client core; builder docs + §14 contract-test mapping (S608); the durable event outbox with per-credential checkpoints and bounded retention (S609, migration 0017); idempotency with conflict detection and capability discovery (S610, migration 0018); and PC-host room-audio ingress with ledger-exact self-output exclusion, standalone-Quest honestly unsupported (S611). Chatterbox remains **HELD fail-closed** pending Volmarr's ruling, untouched by this campaign.

Active slice: **Campaign VII — S701** (next). Last completed roadmap slice on `main`: **S611 — VRChat room-audio ingress**. Campaign VI closed with: bridge auth/scopes (S601), conversation-state API (S602), persona switching (S603), TTS hook (S604), VRChat OSC reference bridge (S605), Conan RCON reference (S606), Skyrim HTTP reference bridge (S607), builder documentation + hardening (S608), durable event outbox (S609), idempotency + capability discovery (S610), room-audio ingress (S611).

## Previous campaign

**Campaign V — Real-time voice loop (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)** under Volmarr's multi-backend rulings of 2026-10-13 (Forge-Log 02:16–02:27 EDT; ADR-0005/0006). All 14 slices (S501–S514) are implemented and laptop-verified; the original wave (`surge-c5`, commits `867b261`–`59be0b7`) was reworked at the S504 gate after Volmarr dismissed Kokoro and ruled TTS/STT multi-backend (successor branch `surge-c5-tts`, fast-forwarded to `main` at this landing). The S504 per-backend gate: **CosyVoice ADMITTED** — its real installed tree audits green (**70 distributions, 0 violations**, binding audit through `backend_status`), installs in one pass through the one-button machinery, and synthesizes the fixed corpus for real on purplelongship. **Chatterbox HELD fail-closed** — chatterbox-tts 0.1.7 hard-pins librosa + transformers==5.2.0, and transformers 5.x hard-imports LGPL `soxr` whenever librosa is present; its install plan is disabled and the machinery refuses it, **awaiting Volmarr's ruling** (reclassify as user-installed / ship a patched fork / drop) — full evidence in `docs/VOICE_LICENSE_MATRIX.md`. The predeclared TTS performance thresholds were **not met on the shipped CPU build** (declared for the GPU reference; NVIDIA's wheels declare no license metadata, so the lawful tree is CPU torch) and were **not adjusted** — measured results in `docs/BENCHMARKS.md` (2026-10-13). STT: faster-whisper default verified again in the final environment (WER 0.1111 ≤ 0.25; RTF p50 0.7095 ≤ 1.0); the distil-whisper one-button proof completed (install via the machinery + real transcription, WER 0.1). Full suite on purplelongship: **549 passed, 3 skipped**.

## Documentation foundation now present

### Builder / architecture core

- `AGENTS.md` — builder entry point and protected-file/load-order rules
- `docs/README.md` — technical documentation map
- `docs/INVARIANTS.md` — system laws
- `docs/DESIGN.md` — top-level architecture
- `docs/RESEARCH.md` — corrected source-driven clean-room findings
- `docs/ROADMAP.md` — 94-slice build plan
- `docs/DATA_MODEL.md` — conceptual data ownership and migration semantics
- `docs/PROMPT_COMPOSER.md` — structured prompt and Prompt Trace contract

### Subsystems

- `docs/MEMORY_ARCHITECTURE.md`
- `docs/BACKEND_CONTRACT.md`
- `docs/VOICE_ARCHITECTURE.md`
- `docs/VOICE_LICENSE_MATRIX.md`
- `docs/BRIDGE_PROTOCOL.md`
- `docs/SECURITY_MODEL.md`
- `docs/COMPATIBILITY.md`

### Verification / durability

- `docs/TESTING.md`
- `docs/BENCHMARKS.md`
- `docs/BACKUP_AND_RECOVERY.md`
- `docs/adr/` — durable architecture decisions
- `docs/README_SUGGESTIONS.md` — protected README improvement proposals only

### Fellowship

- `docs/fellowship/FORGE-LOG.md` — direct append-only Yrsa ↔ ChatGPT coordination

## Important pre-code corrections now encoded

- Character Card v3 archive terminology is **CHARX**, not XCHAR; normative current spec is authority.
- Ollama native embedding endpoint is currently `POST /api/embed`; re-verify official docs at S304.
- Voice-license review covers the complete runtime/model/phonemization dependency tree and occurs before S504 acceptance.
- Pytest exit code 5 on no collected tests means S101 includes a real smoke test and requires exit 0.
- Database migrations are part of S103 storage foundation.
- Chat and embedding backends are independent modality seams composed through profiles.
- External bridge APIs are versioned from their first public contract and gain idempotency/durable event replay.
- Memory is provenance-backed temporal truth with witness scope, consolidation and supersession.
- Voice history is derived from playback evidence, not assumed equal to generated text.
- A release is not "sovereign" until backup/export/migration and clean-machine resurrection work.

## Builder coordination

Yrsa and ChatGPT coordinate directly through `docs/fellowship/FORGE-LOG.md`. The log is append-only. Always re-read its latest entries and remote commits before starting overlapping work.

Samtal remains a separate side quest unless an explicit architecture/roadmap decision integrates it.

## Known open pre-S101 review

ChatGPT has requested Yrsa audit the expanded architecture/roadmap before implementation, especially changes to the original backend, memory, voice-license and bridge assumptions. Disagreement is cheapest while it still costs prose instead of refactors.

## How to update this file

When a slice changes status, update:

- current campaign;
- active/last completed slice;
- blocking issue(s);
- latest decisive benchmark/migration/compatibility result when relevant.

Do not turn this into a second roadmap. Keep it as the fast answer to: **What is true about the forge right now?**