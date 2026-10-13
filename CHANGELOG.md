# Changelog

All notable changes to Rúnmál are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow the application version in `pyproject.toml` /
`runmal.__version__`, verified by `runmal release check` (S807).

## [0.1.0] — 2026-10-13

First complete roadmap build: 94 slices, 8 campaigns (plus an
inserted extra UI campaign), forged and verified on purplelongship.

### Added

- **Core (Campaign I, S101–S114):** local-first FastAPI application,
  SQLite storage with a versioned migration runner, characters and
  character cards, chats and messages, assets, local credential auth,
  backups, walkthroughs.
- **Conversation (Campaign II, S201–S215):** lorebooks and lore
  activation, group chats, speaker policies, a pluggable director,
  prompt tracing with a token ledger and inspector UI.
- **Backend seams (Campaign III, S301–S311):** Ollama and OpenRouter
  chat adapters behind one contract, the embedding seam, backend
  profiles with secret references, connection health, the shared
  adapter contract suite.
- **Living memory (Campaign IV, S401–S415):** memory statements with
  statement-level provenance (INV-019), sqlite-vec vector store, FTS
  degradation, retrieval and rebuild tooling.
- **Voice (Campaign V, S501–S514):** audio plumbing, Silero VAD,
  faster-whisper STT (verified default ear), a multi-backend TTS
  registry under per-backend license admission (S504) — CosyVoice
  admitted as the default shipped voice; user-installed backends are
  the user's own choice, audited and displayed, never blocked.
- **Bridge APIs (Campaign VI, S601–S611):** scoped bridge
  credentials, idempotent bridge endpoints for external tools.
- **Aesir cutover (Campaign VII, S701–S706):** Aesir chat and
  embedding adapters over the same seam, parameter/capability
  mapping, profile migration tooling, recorded-stream performance
  validation, cutover hardening.
- **Sovereignty (Campaign VIII, S801–S808):** portable `.runmal`
  archives with checksums and a no-secrets policy, full backup and
  staged restore, import into a clean state, the migration upgrade
  harness (fixtures at schema 0001/0009/0016), `runmal doctor`
  diagnostics, a Linux+Windows CI matrix, the SBOM + license
  manifest + release gate, this release check, and the sovereign
  resurrection test.

### Notes

- Schema revision at release: 0018 (18 migrations).
- Portable archive format: `runmal-archive` v1.
- Chatterbox TTS is HELD fail-closed in this release; it is not
  part of the default shipped tree.
