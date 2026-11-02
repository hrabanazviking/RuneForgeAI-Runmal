# ADR-0009 — Hosted CI is authorized for the desktop distribution campaign

**Status:** accepted by owner directive (2026-11-01)

## Context

Rúnmál's historical S805 record contains an owner ruling from 2026-10-13 that rejected the then-proposed GitHub-hosted Linux/Windows matrix. S805 was completed instead with the project-owned self-hosted matrix, and that historical acceptance record remains true.

On 2026-11-01 Volmarr issued a newer and materially different directive: build the zero-technical-skills Rúnmál installer/launcher for Windows, macOS, Linux, and other practical desktop targets, with Windows 11 as the first field-test machine before the incoming Kubuntu Z13. Producing and verifying native packages across operating systems requires platform-native builders that the local forge does not currently contain.

## Decision

GitHub-hosted runners are explicitly permitted for the post-roadmap **Distribution / Desktop UX campaign D001-D010** to:

- run the launcher/auth acceptance suite on Windows, macOS, and Linux;
- run the full Rúnmál regression suite on the Linux package branch gate;
- build Windows installer, macOS application/DMG, and Linux package artifacts;
- smoke-test frozen launcher executables;
- expose those artifacts for owner field testing.

This decision does **not** retroactively change S805, its self-hosted evidence, or ADR-0007. It supersedes the old no-hosted-CI restriction only where it would otherwise block the newer cross-platform desktop-distribution directive.

## Boundaries

- Hosted CI is build/test infrastructure, not a runtime dependency.
- Rúnmál remains local-first and does not gain telemetry or cloud runtime requirements.
- No user chats, characters, credentials, memories, or other private Rúnmál state are uploaded to CI.
- CI uses synthetic/test data only.
- Release signing credentials, if added later, must be handled through repository secrets and must never be committed.
- Owner field testing remains the final D010 acceptance gate.

## Consequence

The repository may contain `.github/workflows/desktop-packages.yml` for this campaign even though the older S805 hosted-matrix approach remains recorded as abandoned in its own historical context.
