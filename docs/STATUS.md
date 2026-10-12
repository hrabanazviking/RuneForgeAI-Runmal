# Rúnmál Forge Status

**Last documentation pass:** 2026-10-12

## Current phase

**Implementation — Campaign V (roadmap definitions), from 2026-10-12.** Campaigns I (S101–S114), II (S201–S215), III (S301–S311, backend seams) and IV (S401–S415, living memory) are complete and verified on the forge laptop (purplelongship); the full suite stands at **429 tests green** at Campaign IV's close (commit `0d924da`; 2 skips are the tagged real-Ollama tests — no Ollama server on the laptop). An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices (287 tests green at that wave's close, commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumed at the true roadmap S209, completed Campaign II the same day, and then forged the true Campaigns III and IV. True roadmap progress: **55/94** (S101–S114 + S201–S215 + S301–S311 + S401–S415) plus the extra UI campaign.

## Current campaign

**Campaign V — Real-time voice loop (roadmap definitions)** — ⚠️ **IMPLEMENTED on branch `surge-c5`, NOT landed.** All 14 slices (S501–S514, commits `867b261`–`59be0b7`) are implemented and VM-verified, but purplelongship went offline 2026-10-12 ~18:54 UTC during the voice-dependency install, so laptop evidence, the tagged real-model runs (S502 VAD, S503 STT, S514 `--real` benchmark) and the S504 real-tree license audit are still owed. `main` remains at the Campaign IV close (`1494cbf`, 429 tests green on the laptop). **Blocking issue: purplelongship offline — likely needs Volmarr's hands.** Resume: on the laptop, finish the voice-deps pip install, check out `surge-c5`, run the full suite + tagged real-model tests + S514 `--real`, complete the S504 license audit on the real installed tree (if the real tree fails the gate, that is a STOP for Volmarr's licensing call), then fast-forward `main` to `surge-c5`.

Active slice: **S501 — Audio plumbing** (implemented on `surge-c5`, pending laptop verification). Last completed roadmap slice on `main`: **S415 — Full rebuild/reindex**. Campaign IV closed with: vector-store interface + sqlite-vec adapter (S401), embedding ingestion (S402), hybrid retrieval (S403), chat auto-summarization (S404), event/fact extraction (S405), salience + decay (S406), witness-scoped recall (S407), memory nucleus (S408), mutation sync (S409), memory browser UI (S410), provenance graph (S411), deduplication + consolidation (S412), contradiction + supersession engine (S413), recall trace + memory evaluator (S414), full rebuild/reindex (S415).

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