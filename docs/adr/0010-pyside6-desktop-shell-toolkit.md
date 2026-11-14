# ADR-0010 — PySide6 is the desktop-shell toolkit, pinned at 6.8.0.2

Status: Accepted
Date: 2026-11-14

## Context

Volmarr's ruling of 2026-11-14: the shipped web shell is scrapped and
Rúnmál's interface is rebuilt from scratch as **a full, proper native
windowed application — not in a web browser — with every engine function
surfaced**. The shell must work on Windows, Linux x86-64, and Linux ARM
(aarch64), each proven on real fleet machines; macOS stays Mac-ready but
**UNPROVEN** (no Mac exists in the fleet); Android/iPad are a later phase
that the architecture must not block.

The Python engine is reused in-process behind an HTTP client boundary
(the shell never imports engine services directly), so the toolkit
decision is about the window layer only.

The one hard technical risk was ARM: PySide6 6.12.0's aarch64 wheel is
`manylinux_2_39` (glibc >= 2.39), while Mimir (Raspberry Pi 5, Debian
bookworm) carries glibc 2.36. Debian bookworm ships no PySide6 packages,
so the fallback ladder was: (1) an older PySide6 pin whose aarch64 wheel
targets an older manylinux; (2) distro packages (unavailable); (3) a
newer-glibc userland on the Pi (last resort).

## Decision

**PySide6 (Qt for Python), `PySide6-Essentials==6.8.0.2`, pinned
uniformly on every platform** as the `desktop` optional-dependencies
extra in `pyproject.toml`. Qt WebEngine is not used for UI rendering
anywhere in the shell. Addons modules are added only when a slice
actually needs one.

The pin is deliberately *not* the newest release: one Qt version on all
platforms means one widget/QSS behaviour surface to design and test
against. 6.8 is Qt's LTS line.

## Consequences

- Every platform installs the shell the same way:
  `pip install "runmal[desktop]"` (dev) or via the frozen installers.
- Installer size grows by the Qt runtime (~85 MB class per platform);
  accepted and recorded here so R-17 is not surprised by it.
- If a future Qt release restores an aarch64 wheel at manylinux <= 2_36,
  the pin may be raised — by a new spike in the R-01 shape, on Mimir
  first, never by assumption.
- Known cosmetic note: the bare-venv Windows spike prints Qt's
  "Cannot find font directory" notice because Qt ships no fonts; a real
  desktop's system fonts apply. No action.

## Alternatives considered

- **PySide6 6.12.0 (newest) on x86/Windows, older pin on ARM only:**
  rejected — splits the behaviour surface across platforms for no user
  gain; version skew is exactly the failure this campaign exists to end.
- **PyQt6:** same Qt, GPL/commercial licensing, no technical gain.
- **wxPython:** no official aarch64 wheels; makes the hard platform harder.
- **Tkinter:** runs everywhere (the old launcher's Control Center proves
  it) but has no rich chat rendering, docks, or model/view — a ceiling,
  not a shell. Retained only as the emergency fallback if Qt ever fails
  on ARM entirely.
- **Electron / Tauri / any HTML shell:** rejected by the owner's ruling
  itself, and neither reuses the Python engine in-process.
- **Toga / Flet / Kivy:** widget sets/runtimes too immature for a dense
  desktop workbench, with their own ARM risk and none of Qt's payoff.

## Evidence / references

R-01 spike, 2026-11-14 — `scripts/desktop_spike.py` (QMainWindow shown +
engine in-process in a worker thread + `GET /healthz` -> {"status": "ok"}),
run against fresh environments built from main @ 1d66572:

| Platform | Machine | glibc | Python | PySide6 / Qt | Result |
|---|---|---|---|---|---|
| Windows x86-64 | F15 `PURPLEWIZARD` | — | 3.12.10 | 6.8.0.2 / 6.8.0 | PASS (offscreen) |
| Linux x86-64 | purpleraider (Kubuntu 26.10) | 2.44 | 3.12.13 | 6.8.0.2 / 6.8.0 | PASS (offscreen **and** real Wayland display) |
| Linux ARM aarch64 | Mimir (Pi 5, Debian bookworm) | 2.36 | 3.12.15 | 6.8.0.2 / 6.8.0 | PASS (offscreen) |

ARM resolver evidence: an unpinned install on Mimir backtracks from
6.12.0 to **6.8.0.2** (the newest aarch64 wheel compatible with
glibc 2.36); unpinned on x86-64 resolves 6.12.0. Ladder step (1) — the
older pin — is therefore the ARM answer; steps (2) and (3) were not
needed.

## Supersession

None. This ADR records the toolkit foundation for the R-series desktop
roadmap (`RUNMAL_INTERFACE_REDO_PLAN_2026-11-14`, goal workspace); the
shell architecture itself lands in `docs/DESIGN.md` with slice R-04.
