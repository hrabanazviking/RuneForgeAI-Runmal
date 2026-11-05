# Rúnmál: Companion Lorebooks and Second Brain

**Repository:** hrabanazviking/RuneForgeAI-Runmal  
**Date:** 2026-11-04  
**State:** Planned, not implemented.

## Shared roadmap and operating boundaries

- Canonical full roadmap: https://github.com/hrabanazviking/bifrost-viewer/blob/main/docs/roadmaps/BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md
- Local copy: [BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md](BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md)
- This document is a **proposal**, not a report of implemented features.
- Keep this application independent. All Second Brain access must be optional, versioned, permission-scoped and disabled by default.
- Never store private documents, account identities, OAuth configuration, access tokens, API keys, secrets, live logs, or database contents in public GitHub.
- Bifröst Viewer is the knowledge-service coordinator; Skein and Skry expose their own stable public functions. Consumers must not query private PostgreSQL directly.

## Objective

Make Bifröst an optional source of books, approved lore, citations and research for Rúnmál companions without overriding character boundaries or private memories.

## Implementation responsibilities

1. Connect to the versioned read/search API with one individually scoped capability per client or persona where appropriate.
2. Offer opt-in library selection for a persona and per-session source restrictions.
3. Expose provenance-aware lorebook retrieval and query-time Skein/Skry entity neighborhoods.
4. Keep character cards, autobiographical companion memory, and public research corpora distinct.
5. Allow optional manual publication of user-approved original notes through restricted Ingest, never silent harvesting of chat.
6. Respect cloud provider settings and the original document sharing permissions when generating remote prompts.
7. Present source failures or stale Skein results transparently rather than improvising apparently sourced knowledge.

## Acceptance tests

- [ ] Personas operate without Bifröst by default.
- [ ] No private chat text auto-uploaded.
- [ ] Read-only source lookup provides real citation and per-persona scope.

## Suggested implementation process

1. Audit installed source and actual local changes first, particularly unpublished agent work.
2. Map the existing public extension points, resource budgets and security boundary.
3. Add a small, independently testable optional adapter and sanitized fixtures.
4. Exercise permission denial, network loss, stale output, retry/idempotence and recovery.
5. Document new stable contracts and record the limitation before deployment.
6. Confirm the core application's tests and offline operation remain intact.

The canonical Bifröst roadmap sets the shared protocol vision; this repository retains ownership of its own integration implementation.
