# Rúnmál Forge Status

**Last documentation pass:** 2026-10-12

## Current phase

**Implementation — Campaign II (roadmap definitions), resumed 2026-10-12.** Campaign I (S101–S114) is complete and verified on the forge laptop (purplelongship). In roadmap Campaign II, slices S201–S208 are complete. An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices; the full suite stands at 287 tests green at that wave's close (commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumes at the true roadmap S209. True roadmap progress: **22/94** (S101–S114 + S201–S208) plus the extra UI campaign.

## Current campaign

**Campaign II — Lorebooks, presets, prompt template, groups (roadmap definitions)**

Active slice: **S209 — Lorebook editor UI** (roadmap definition: htmx editor + activation preview; preview matches server activation engine). Last completed roadmap slice: **S208 — Backend parameter filtering**. Next after S209–S215: Campaign III — Backend seams (S301–S311, roadmap definitions).

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