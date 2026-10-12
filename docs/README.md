# Rúnmál Documentation Map

This directory is the technical memory of Rúnmál. The root `README.md` is public-facing and protected from routine AI edits; this index is the working map for builders.

## Start here

- `STATUS.md` — present implementation state, active campaign/slice, blockers.
- `INVARIANTS.md` — system laws that implementation must preserve.
- `DESIGN.md` — current architecture and subsystem boundaries.
- `ROADMAP.md` — atomic build slices and acceptance contracts.
- `RESEARCH.md` — clean-room research, source trail, dependency/license findings.

## Core subsystem documents

- `DATA_MODEL.md` — conceptual ownership, relationships, canonical vs derived state and migration rules.
- `PROMPT_COMPOSER.md` — typed prompt slots, budgeting, overflow and Prompt Trace contract.
- `MEMORY_ARCHITECTURE.md` — temporal memory, provenance, consolidation, witness scope, retrieval.
- `BACKEND_CONTRACT.md` — chat/embedding backend interfaces, capabilities, errors and cancellation.
- `VOICE_ARCHITECTURE.md` — VAD/STT/TTS state machine, barge-in, playback truth and routing.
- `VOICE_LICENSE_MATRIX.md` — voice runtime/model/dependency license gate.
- `BRIDGE_PROTOCOL.md` — versioned external companion/game bridge contract.
- `SECURITY_MODEL.md` — local-first threat model, secrets, tokens, extensions and network exposure.
- `COMPATIBILITY.md` — card/provider/OS compatibility targets and round-trip rules.

## Engineering and release documents

- `TESTING.md` — unit/contract/integration/E2E strategy and deterministic evidence rules.
- `BENCHMARKS.md` — local benchmark ledger/templates; measured facts live here, not internet guesses.
- `BACKUP_AND_RECOVERY.md` — sovereign export, SQLite backup, restore and disaster recovery.
- `README_SUGGESTIONS.md` — public README improvement proposals that do **not** authorize editing it.
- `adr/` — Architecture Decision Records for durable decisions that should not live only in Git history.

## Side quests

- `SIDEQUEST_SAMTAL.md` — Samtal (*together-talk*), the separate communication-system side quest. It is related to the Fellowship's communication future but is not part of Rúnmál core scope unless a roadmap decision explicitly integrates it.

## Fellowship

- `fellowship/FORGE-LOG.md` — append-only asynchronous thread between Yrsa and ChatGPT.

## Repository-level operating context

- `../AGENTS.md` — AI builder entry point and load order.
- `../05_VOLMARR_COLLABORATION_PROTOCOL.md` — how AI collaborators work with Volmarr.
- `../02_VOLMARR_ENGINEERING_METHOD.md` — Mythic Engineering method.
- `../AI.FOLLOW.THIS.NUMBER.ONE.RULE.md` — root README protection rule.

## Documentation discipline

A document is not "finished" because it exists. When runtime evidence, a dependency change or a roadmap decision invalidates it, update the owning document in the same slice that changes the system.

Prefer one canonical owner for each fact. Other docs should link to that owner rather than duplicating implementation-sensitive detail.

When a side quest grows into its own project, prefer moving/copying its canonical documentation into that project rather than letting the Rúnmál repo become a permanent attic of unrelated systems.