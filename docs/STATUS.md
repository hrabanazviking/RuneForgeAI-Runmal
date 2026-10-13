# Rúnmál Forge Status

**Last documentation pass:** 2026-10-13

## Current phase

**Implementation — Campaign VIII (sovereignty, durability and release) next, from 2026-10-13.** Campaigns I (S101–S114), II (S201–S215), III (S301–S311, backend seams), IV (S401–S415, living memory), V (S501–S514, real-time voice loop), VI (S601–S611, bridge APIs) and VII (S701–S706, Aesir cutover) are complete and verified on the forge laptop (purplelongship); the full suite stands at **645 tests green** at Campaign VII's close (2026-10-13; 3 skips). An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices (287 tests green at that wave's close, commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumed at the true roadmap S209, completed Campaign II the same day, and then forged the true Campaigns III and IV. True roadmap progress: **86/94** (S101–S114 + S201–S215 + S301–S311 + S401–S415 + S501–S514 + S601–S611 + S701–S706) plus the extra UI campaign.

## Current campaign

**Campaign VII — Aesir cutover (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)**. All 6 slices (S701–S706) are implemented and laptop-verified; full suite on purplelongship at the close: **645 passed, 3 skipped**. Rúnmál-side cutover only — nothing on Mimir/the Pi was touched, and no Hailo work was done (paused by Volmarr's order; the Aesir adapter is an HTTP client for the Aesir *server surface*, OpenAI-compatible per BACKEND_CONTRACT §12). The Aesir ChatBackend passes the shared S301 contract suite on recorded fixtures (S701); its sampling mapping is a public table with a declared unsupported set — presence/frequency penalty and requested context length are dropped with warnings, never sent (S702). Aesir embeddings are independently selectable with `aesir` provenance and the FTS fallback contract (S703). Profile migration tooling (`runmal profiles migrate-to-aesir`, S704) copies Ollama/OpenRouter profiles to Aesir with chats repointed and history byte-identical; namespaced cloud model IDs require an explicit Aesir model, and secret references never cross providers. The S705 adapter benchmark (bar predeclared in `docs/BENCHMARKS.md` before the run) passed all bars on purplelongship: Aesir/Ollama total-stream ratio 1.209 ≤ 1.5, TTFT delta +0.001 ms, both adapters > 275k tokens/sec on identical streams. Hardening (S706): end-to-end chat + memory on an Aesir profile, and a provider-identity isolation scan proving the domain packages carry no provider-key literals outside the S208 compat registry. Chatterbox remains **HELD fail-closed** pending Volmarr's ruling, untouched by this campaign.

Active slice: **Campaign VIII — S801** (next). Last completed roadmap slice on `main`: **S706 — Cutover docs + hardening**. Campaign VII closed with: Aesir chat adapter (S701), sampling/capability mapping (S702), Aesir embeddings (S703), profile migration tooling (S704), performance validation (S705), cutover docs + hardening (S706).

## Previous campaign

**Campaign VI — Bridge APIs (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)**. All 11 slices (S601–S611) implemented and laptop-verified; full suite at the close: **616 passed, 3 skipped**. Paired-credential bridge auth with exact capability+resource scopes (S601, migration 0016); versioned conversation-state/turn/generate API with speaker provenance (S602); future-only persona switching (S603); a TTS job hook whose playback reports never feed the S508 heard-text ledger (S604); three reference bridges outside the core — VRChat OSC (S605), Conan Exiles RCON skeleton (S606), Skyrim-style hosted HTTP (S607) — sharing one HTTP client core; builder docs + §14 contract-test mapping (S608); the durable event outbox with per-credential checkpoints and bounded retention (S609, migration 0017); idempotency with conflict detection and capability discovery (S610, migration 0018); and PC-host room-audio ingress with ledger-exact self-output exclusion, standalone-Quest honestly unsupported (S611).

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