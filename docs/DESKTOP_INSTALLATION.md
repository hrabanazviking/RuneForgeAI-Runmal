# Desktop Installation and Launcher

This document covers the Rúnmál desktop application: native local
package builds, what the installed entry does, and the headless
server lifecycle that remains for bridge/automation use.

Since R-16 the Qt desktop shell is the only shipped front end. The
browser UI and the Tk Control Center were removed (ADR-0011); the
desktop app itself is the control centre — engine start/stop/restart
lives in its File menu, toolbar, and status bar.

## Normal installation

Ordinary users should install a prebuilt native package rather than
install Python manually.

### Windows 10 / 11

Download `Runmal-Setup.exe`, double-click it, follow the normal
installer, and leave **Create a desktop shortcut** selected if
desired.

The installer adds one Start-menu entry, **Rúnmál**, which opens the
desktop app. The application installs for the current user under
`%LOCALAPPDATA%\Programs\Runmal`. Personal Rúnmál data is stored
separately and is not removed merely by uninstalling the
application.

Development/unsigned builds may trigger Windows SmartScreen because
the project does not yet have a Windows code-signing certificate.
Public release signing should be added when signing credentials are
available.

### macOS — UNPROVEN

No Mac exists in the fleet, so macOS packaging is **UNPROVEN**
(plan §2.5): the build script is kept current, but nothing claims
the result works until it has actually run on a Mac.

When a Mac is available: run `scripts/build-macos-local.sh` on it to
produce `Runmal-macOS-Apple-Silicon.dmg` or
`Runmal-macOS-Intel.dmg`, open the DMG, and move `Runmal.app` into
Applications. Development/unsigned builds may be blocked by
Gatekeeper until the project has Apple Developer
signing/notarization credentials.

### Linux

On Debian/Ubuntu/Kubuntu-class systems, install the `.deb` matching
the machine architecture using the normal graphical package
installer:

- `runmal_<version>_amd64.deb`
- `runmal_<version>_arm64.deb`

Rúnmál then appears in the desktop application menu with
`Terminal=false`; its entry runs `/opt/runmal/runmal open`.

The launcher core is distribution-neutral. Additional package
formats can wrap the same binary without creating another Rúnmál
implementation.

## What happens when the Rúnmál icon is clicked

1. The launcher's `open` road dispatches to the desktop shell
   (source installs: `python -m runmal.desktop`; frozen packages:
   the same binary re-entered with the hidden `_desktop` command).
2. The desktop app starts its engine in-process on an ephemeral
   loopback port and shows the main window; the status bar reports
   the real engine state from `/healthz`.
3. Closing the window quits the app and stops the engine cleanly.

There is no browser step and no bootstrap nonce on this road. The
old `/launcher/bootstrap` path redirects to `/api/v1/status` for
anything that still asks for it.

## Headless server lifecycle

The launcher keeps its headless server commands for bridge and
automation use: `runmal start|stop|restart|status|doctor` manage a
hidden server process on port 8098, and the frozen binary's hidden
`_serve` command runs it in the foreground. The desktop app does not
use this server; it hosts its own engine in-process.

Autostart, where offered by the source installers, is opt-in and
current-user-only.

## Sovereign package builds

Rúnmál desktop packages are built locally on owner-controlled
machines. Hosted GitHub Actions runners are not part of the
packaging or release process.

Every builder installs the `desktop` extra and collects PySide6
into the bundle: since R-16 the frozen entry's `open` road launches
the Qt desktop shell, so a bundle without Qt ships an app whose
only front end cannot start.

### Windows local build

Run on Windows from the repository checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-local.ps1
```

The builder:

- creates an isolated build environment;
- installs the Rúnmál build dependencies locally (including the
  `desktop` extra);
- freezes the application with PyInstaller (PySide6 collected);
- smoke-tests the launcher;
- starts the frozen local server and verifies `/healthz`;
- creates the installer with Inno Setup;
- writes `Runmal-Setup.exe` into `artifacts\`;
- prints its SHA-256 digest.

Inno Setup 6 must be installed on the Windows build machine.

### Linux local build

Run on the target Linux architecture:

```bash
./scripts/build-linux-local.sh
```

The builder creates and smoke-tests the native frozen app —
launcher `status`, the frozen server's `/healthz`, and the desktop
entry launched offscreen (it must reach its event loop and stay up
with no traceback) — and writes one of these directly into the
repository root:

- `runmal_<version>_amd64.deb`
- `runmal_<version>_arm64.deb`

### macOS local build — UNPROVEN

Run on the target Mac:

```bash
./scripts/build-macos-local.sh
```

The builder mirrors the Linux one (desktop extra installed,
PySide6 collected, launcher + server smokes) and builds the native
DMG with `hdiutil`. It has never run on a real Mac; see the UNPROVEN
note above.

A package is considered a real distributable only after the native
builder has actually produced and smoke-tested the file on its
target operating system.

### Package freshness (R-17, 2026-11-22)

Rebuilt on the R-16 tree (the desktop-only front end):

- `runmal_0.1.0_amd64.deb` — built on the Muse VM (Linux x86-64):
  all builder smokes passed, the package was installed with
  `dpkg -i`, and the installed `/opt/runmal/runmal` answered
  `status`, dispatched `open` to the desktop, and launched the
  desktop shell offscreen clean. SHA-256:
  `0164f40bdaa10fea14e73c770c7dbe573c89fb91b51fc16d34bcdb26b692127b`
  (107,002,494 bytes). At 107 MB it exceeds GitHub's 100 MB file
  limit, so it is not committed — it lives on the VM at
  `~/workspace/runmal-refresh/`; the copy at this repo's root is
  still the 2026-11-13 build.
- `runmal_0.1.0_arm64.deb` — built on Mimir (Raspberry Pi 5,
  aarch64) with the same builder and install/launch-proven there;
  it lives on Mimir at `~/runmal-r01-src/` (the copy at this
  repo's root is still the 2026-11-13 build). See
  `docs/DESKTOP_PLATFORM_PROOF_R17_2026-11-22.md` for its digest
  and evidence.
- `Runmal-Setup.exe` still dates from 2026-11-02 and contains the
  earlier (web-shell) code. The Windows rebuild runs
  `scripts/build-windows-local.ps1` on the F15; it is owed when
  that machine is next reachable (its road runs through
  purpleraider). Until then, the source/bootstrap installer below
  is the current-code path on Windows, because it always installs
  the current `main`.
- macOS DMGs: UNPROVEN — no Mac in the fleet (see above).

## Source/bootstrap installers

The readable bootstrap scripts remain useful for testing, repair,
or platforms where a prebuilt package is not available:

- Windows: `scripts/install-windows.ps1`
- Linux: `scripts/install-linux.sh`
- macOS: `scripts/install-macos.sh`

These scripts install Rúnmál into an isolated private environment.
They are not the recommended front door for nontechnical users once
native packages are published.

### Testing an unmerged branch

Developers may point the bootstrap installer at another Git ref
while testing. Normal users should stay on packaged releases/main
and never need to know what a Git ref is.

## Diagnostics

The launcher writes server startup output to:

`~/.local/share/runmal/launcher-server.log`

The desktop app's status bar and engine lifecycle controls are the
day-to-day diagnostics surface; `runmal doctor` (headless road)
produces the copyable report of platform/runtime paths and
findings. Credentials are not intentionally included in either.

## Uninstall/data safety

Application binaries and personal data are separate. Removing or
upgrading the desktop package must not silently delete chats,
characters, lorebooks, memories, settings, credentials, voices, or
backups.

A future explicit **Remove Rúnmál and all personal data** flow must
require separate confirmation rather than being folded into
ordinary uninstall.
