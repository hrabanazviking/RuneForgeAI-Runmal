# Rúnmál Forge Status

**Last documentation pass:** 2026-10-12

## Current phase

**Architecture / pre-implementation.** The repository currently contains the public project definition, clean-room research, architecture, roadmap and builder protocol. Campaign I implementation has not yet been claimed complete by this status document.

## Current campaign

**Campaign I — Foundation, text chat, personas**

Expected first implementation slice: **S101 — Repo scaffold**.

## Documentation foundation now present

- `AGENTS.md` — builder entry point
- `docs/INVARIANTS.md` — system laws
- `docs/DESIGN.md` — architecture
- `docs/RESEARCH.md` — source-driven clean-room findings
- `docs/ROADMAP.md` — slice plan
- `docs/MEMORY_ARCHITECTURE.md`
- `docs/BACKEND_CONTRACT.md`
- `docs/VOICE_ARCHITECTURE.md`
- `docs/BRIDGE_PROTOCOL.md`
- `docs/SECURITY_MODEL.md`
- `docs/TESTING.md`
- `docs/BACKUP_AND_RECOVERY.md`
- `docs/COMPATIBILITY.md`
- `docs/fellowship/FORGE-LOG.md`

## Important pre-code corrections

These findings must be reflected in design/roadmap implementation before or during their owning slices:

- Current Character Card v3 archive terminology is **CHARX**, not XCHAR; use the normative current specification.
- Ollama native embedding endpoint is currently `POST /api/embed`; re-verify official docs at implementation time.
- Voice-license review must inspect the full runtime dependency tree; a permissive Kokoro wrapper/model does not by itself prove a permissive phonemization stack.
- Pytest exit code 5 on no collected tests means S101 needs a real smoke test, not an "empty green suite."
- Database migrations belong in the storage foundation, not as later cleanup.
- External bridge APIs are versioned from their first public contract.

## Builder coordination

Yrsa and ChatGPT coordinate through `docs/fellowship/FORGE-LOG.md`. The log is append-only. Always re-read its latest entries before starting overlapping work.

## How to update this file

When a slice changes status, update:

- current campaign;
- active/last completed slice;
- blocking issue(s);
- latest decisive benchmark/migration/compatibility result when relevant.

Do not turn this into a second roadmap. Keep it as the fast answer to: **What is true about the forge right now?**