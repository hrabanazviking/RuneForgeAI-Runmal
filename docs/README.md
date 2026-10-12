# Rúnmál Documentation Map

This directory is the technical memory of Rúnmál. The root `README.md` is public-facing and protected from routine AI edits; this index is the working map for builders.

## Start here

- `STATUS.md` — present implementation state, active campaign/slice, blockers.
- `INVARIANTS.md` — system laws that implementation must preserve.
- `DESIGN.md` — current architecture and subsystem boundaries.
- `ROADMAP.md` — atomic build slices and acceptance contracts.
- `RESEARCH.md` — clean-room research, source trail, dependency/license findings.

## Core subsystem documents

- `MEMORY_ARCHITECTURE.md` — temporal memory, provenance, consolidation, witness scope, retrieval.
- `BACKEND_CONTRACT.md` — LLM/embedding backend interfaces, capabilities, errors, cancellation.
- `VOICE_ARCHITECTURE.md` — VAD/STT/TTS state machine, barge-in, playback truth, routing.
- `BRIDGE_PROTOCOL.md` — versioned external companion/game bridge contract.
- `SECURITY_MODEL.md` — local-first threat model, secrets, tokens, extensions, LAN exposure.
- `COMPATIBILITY.md` — supported card/provider/OS compatibility targets and round-trip rules.

## Engineering and release documents

- `TESTING.md` — test classes, deterministic fixtures, live-provider tests, benchmark rules.
- `BACKUP_AND_RECOVERY.md` — sovereign export, SQLite backup, restore and disaster recovery.
- `adr/` — Architecture Decision Records for durable decisions that should not live only in Git history.

## Fellowship

- `fellowship/FORGE-LOG.md` — append-only asynchronous thread between Yrsa and ChatGPT.

## Repository-level operating context

- `../AGENTS.md` — AI builder entry point and load order.
- `../05_VOLMARR_COLLABORATION_PROTOCOL.md` — how AI collaborators work with Volmarr.
- `../02_VOLMARR_ENGINEERING_METHOD.md` — Mythic Engineering method.
- `../AI.FOLLOW.THIS.NUMBER.ONE.RULE.md` — root README protection rule.

## Documentation discipline

A document is not "finished" because it exists. When runtime evidence, a dependency change, or a roadmap decision invalidates it, update the owning document in the same slice that changes the system.

Prefer one canonical owner for each fact. Other docs should link to that owner rather than duplicating implementation-sensitive detail.