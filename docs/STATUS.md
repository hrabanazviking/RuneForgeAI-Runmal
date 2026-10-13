# Rúnmál Forge Status

**Last documentation pass:** 2026-10-13

## Current phase

**Implementation — COMPLETE: 94/94 roadmap slices landed, from 2026-10-13.** Campaigns I (S101–S114), II (S201–S215), III (S301–S311, backend seams), IV (S401–S415, living memory), V (S501–S514, real-time voice loop), VI (S601–S611, bridge APIs), VII (S701–S706, Aesir cutover) and VIII (S801–S808, sovereignty) are complete and verified on the forge laptop (purplelongship). An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices (287 tests green at that wave's close, commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumed at the true roadmap S209, completed Campaign II the same day, and then forged the true Campaigns III and IV. True roadmap progress: **94/94** (S101–S114 + S201–S215 + S301–S311 + S401–S415 + S501–S514 + S601–S611 + S701–S706 + S801–S808) plus the extra UI campaign. Full suite on purplelongship at the S805 evidence run (`538c918`): **686 passed, 3 skipped**.

**S805 substitution (owner's ruling, 2026-10-13):** S805's hosted-CI shape (a GitHub Actions Linux+Windows workflow) is **abandoned by Volmarr's ruling** — *"don't rely on Microsoft's AIs. Test it yourself and don't worry about them"*; *"just push without the need for Microsoft's CI crap."* S805 is implemented instead as a **self-hosted platform matrix** (ADR-0007): the `runmal release matrix` harness runs the core suite on project-owned hardware and records structured evidence legs in `docs/platform-matrix/`, summarised in `docs/PLATFORM_MATRIX.md`. The Linux leg ran for real on purplelongship and passed (686 passed, 3 skipped — the skips named in the matrix doc). The Windows leg is recorded **not run**: no Windows machine exists in the fleet and none will be rented. The roadmap definition in `docs/ROADMAP.md` is untouched; the mechanism substitution is recorded here and in the Forge-Log. The abandoned Actions commit's local branch (`s805-ci-workflow`) was deleted once the replacement landed and verified.

## Current campaign

**Campaign VIII — Sovereignty, durability and release (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)**. All 8 slices (S801–S808) implemented and laptop-verified; full suite on purplelongship at the campaign's close: **681 passed, 3 skipped** (686 with the S805 harness tests added). Landed: the portable `.runmal` archive — checksummed, deterministic, secrets excluded by policy with a defense-in-depth canary scan (S801); full backup bundles + staged restore that validates before touching anything, and archive import into a fresh staging install with referential proof (S802); the migration upgrade harness — real era fixtures at schema 0001/0009/0016 upgraded to HEAD with data intact (S803); `runmal doctor` — structured, actionable diagnostics that degrade to findings on a damaged install and never print a secret (S804); the **self-hosted platform matrix** (S805 — substituted by Volmarr's ruling for the hosted-CI design; harness `runmal release matrix`, Linux leg passed on purplelongship, Windows leg recorded not run; ADR-0007, `docs/PLATFORM_MATRIX.md`); the SBOM + license manifest + release gate over the real installed set, reusing the S504 classifier (S806 — over the dev venv it flags 7 *unknown* license spellings for human review, zero forbidden); the release consistency dry-run (pyproject == package version == CHANGELOG entry, archive format, schema HEAD) plus the 0.1.0 CHANGELOG (S807); and the sovereign resurrection test (S808) — a full world exported from state dir A, imported into clean B, re-embedded under a different profile with statement + source provenance intact, and holding a new conversation.

Active slice: **none — the 94-slice roadmap is complete.** Last completed roadmap slice: **S805 — platform matrix (self-hosted form)**. Post-roadmap items already ruled and sequenced after this close-out: the Chatterbox user-installed reclassification (Volmarr, 2026-10-13 05:45 EDT).

## Previous campaign

**Campaign VII — Aesir cutover (roadmap definitions)** — ✅ **COMPLETE and landed (2026-10-13)**. All 6 slices (S701–S706) implemented and laptop-verified; full suite at the close: **645 passed, 3 skipped**. Aesir chat adapter passing the shared contract suite (S701); public sampling mapping with a declared unsupported set (S702); Aesir embeddings with provenance + FTS fallback (S703); profile migration tooling with byte-identical chat history and no cross-provider secret references (S704); the predeclared-bar benchmark passed on purplelongship — Aesir/Ollama ratio 1.209 ≤ 1.5, TTFT delta +0.001 ms (S705); cutover hardening + provider-identity isolation scan (S706). Rúnmál-side only — nothing on Mimir/the Pi was touched, no Hailo work (paused by Volmarr's order). Chatterbox remained **HELD fail-closed** throughout, untouched by this campaign.

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
- `docs/PLATFORM_MATRIX.md` — self-hosted S805 matrix + evidence legs
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