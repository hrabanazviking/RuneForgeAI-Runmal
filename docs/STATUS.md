# Rúnmál Forge Status

**Last documentation pass:** 2026-10-13

## Current phase

**Implementation — Campaign VIII (sovereignty, durability and release) substantially landed, from 2026-10-13; ONE slice held on a credential blocker (see below).** Campaigns I (S101–S114), II (S201–S215), III (S301–S311, backend seams), IV (S401–S415, living memory), V (S501–S514, real-time voice loop), VI (S601–S611, bridge APIs) and VII (S701–S706, Aesir cutover) are complete and verified on the forge laptop (purplelongship). An inserted **extra UI campaign** (see `docs/ROADMAP.md`, "Extra campaign (inserted, complete)") was also landed on 2026-10-12 under historical commit labels `S209`–`S215` / `S301`–`S311` that collide with roadmap numbers but are **not** roadmap slices (287 tests green at that wave's close, commit `5bd28cd`). A numbering divergence between the landed labels and this roadmap was found, reported, and resolved by Volmarr's ruling of 2026-10-12: the UI wave is kept as an extra campaign in the docs, the roadmap keeps its numbering, and the surge resumed at the true roadmap S209, completed Campaign II the same day, and then forged the true Campaigns III and IV. True roadmap progress: **93/94** (S101–S114 + S201–S215 + S301–S311 + S401–S415 + S501–S514 + S601–S611 + S701–S706 + S801–S804 + S806–S808) plus the extra UI campaign. Full suite on purplelongship at `42ec952`: **681 passed, 3 skipped**.

**⛔ BLOCKER — S805 (CI platform matrix) cannot land with the current GitHub credentials.** The slice is written and validated (`.github/workflows/ci.yml`: Linux + Windows core-test matrix), but GitHub refuses the push: the gh OAuth credential lacks the `workflow` scope ("refusing to allow an OAuth App to create or update workflow `.github/workflows/ci.yml` without `workflow` scope"), and the backup fine-grained PAT answers 403 (no Workflows permission). Retried twice (2026-10-13 ~05:47 EDT), same refusal. The commit is preserved on the local branch `s805-ci-workflow` (554bdca, on top of current main) and lands with a single push once Volmarr either runs `gh auth refresh -h github.com -s workflow` and enters the device code, adds the Workflows permission to the PAT, or commits the file via the GitHub web UI. The roadmap therefore stands at 93/94, NOT complete: no completion announcement and no completion email until S805 lands and the full close-out verifies.

## Current campaign

**Campaign VIII — Sovereignty, durability and release (roadmap definitions)** — 🔶 **7 of 8 slices landed and laptop-verified (2026-10-13); S805 held on the credential blocker above.** Landed: the portable `.runmal` archive — checksummed, deterministic, secrets excluded by policy with a defense-in-depth canary scan (S801); full backup bundles + staged restore that validates before touching anything, and archive import into a fresh staging install with referential proof (S802); the migration upgrade harness — real era fixtures at schema 0001/0009/0016 upgraded to HEAD with data intact (S803); `runmal doctor` — structured, actionable diagnostics that degrade to findings on a damaged install and never print a secret (S804); the SBOM + license manifest + release gate over the real installed set, reusing the S504 classifier (S806 — over the dev venv it flags 7 *unknown* license spellings for human review, zero forbidden); the release consistency dry-run (pyproject == package version == CHANGELOG entry, archive format, schema HEAD) plus the 0.1.0 CHANGELOG (S807); and the sovereign resurrection test (S808) — a full world exported from state dir A, imported into clean B, re-embedded under a different profile with statement + source provenance intact, and holding a new conversation. S805's workflow file is written and YAML-validated but unpushable until the credential gains workflow scope.

Active slice: **S805 — CI platform matrix** (blocked on credential scope; see Current phase). Last completed roadmap slice on `main`: **S808 — Sovereign resurrection test**. Campaign VIII landed so far: portable archive (S801), full backup + staged restore + import (S802), migration upgrade harness (S803), `runmal doctor` (S804), SBOM + license manifest/gate (S806), release/versioning + CHANGELOG (S807), sovereign resurrection (S808).

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