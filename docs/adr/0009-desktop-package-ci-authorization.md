# ADR-0009 — Hosted desktop-package CI authorization revoked

**Status:** superseded by owner directive (2026-11-01)

## Context

An earlier draft of the desktop-distribution campaign briefly authorized GitHub-hosted runners to build and test Windows, macOS, and Linux packages. That decision was made while trying to obtain native package coverage quickly.

Volmarr subsequently issued an explicit owner directive: Rúnmál must not use GitHub Actions to build or produce these packages. The project will not depend on chargeable Microsoft-hosted CI for desktop distribution.

This newer owner ruling supersedes the earlier authorization in this ADR.

## Decision

Hosted GitHub Actions runners are **not authorized** for Rúnmál desktop packaging or release builds.

Native desktop packages are built on project-owned or owner-controlled machines using local build scripts:

- Windows: `scripts/build-windows-local.ps1`
- Linux: `scripts/build-linux-local.sh`
- macOS: `scripts/build-macos-local.sh`

The native build must run on the target operating system and perform its own smoke tests before producing the distributable.

Expected distributables are written into the repository root:

- `Runmal-Setup.exe`
- `runmal_<version>_amd64.deb`
- `runmal_<version>_arm64.deb`
- `Runmal-macOS-Apple-Silicon.dmg`
- `Runmal-macOS-Intel.dmg`

Project-owned self-hosted automation remains possible if Volmarr later chooses it, because that does not create a dependency on GitHub-hosted compute.

## Boundaries

- Rúnmál remains local-first and gains no cloud runtime dependency.
- No user chats, characters, credentials, memories, or private state are sent to a hosted CI service for packaging.
- Package verification must reflect a real native build, not merely the existence of packaging source files.
- Release signing remains a separate concern and must never place signing secrets in the repository.
- Owner field testing remains the final D010 acceptance gate.

## Consequence

The desktop distribution feature must not contain an active `.github/workflows/desktop-packages.yml` workflow.

Windows packages are built on Windows, macOS packages on Macs, and Linux packages on Linux. This requires access to the target platform, but keeps build sovereignty with the project owner and avoids hosted-runner billing or dependency.
