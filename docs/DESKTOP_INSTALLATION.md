# Desktop Installation and Launcher

This document covers the Distribution campaign desktop experience and native local package builds.

## Normal installation

Ordinary users should install a prebuilt native package rather than install Python manually.

### Windows 10 / 11

Download `Runmal-Setup.exe`, double-click it, follow the normal installer, and leave **Create a desktop shortcut** selected if desired.

The installer adds:

- **Rúnmál** - starts the local service if necessary and opens the browser UI;
- **Rúnmál Control Center** - Start, Stop, Restart, diagnostics, and sign-in autostart control.

The application installs for the current user under `%LOCALAPPDATA%\Programs\Runmal`. Personal Rúnmál data is stored separately and is not removed merely by uninstalling the application.

Development/unsigned builds may trigger Windows SmartScreen because the project does not yet have a Windows code-signing certificate. Public release signing should be added when signing credentials are available.

### macOS

Download the DMG matching the Mac:

- `Runmal-macOS-Apple-Silicon.dmg`
- `Runmal-macOS-Intel.dmg`

Open it and move `Runmal.app` into Applications.

Development/unsigned builds may be blocked by Gatekeeper until the project has Apple Developer signing/notarization credentials. The application architecture itself does not require administrator privileges for normal Rúnmál data.

### Linux

On Debian/Ubuntu/Kubuntu-class systems, install the `.deb` matching the machine architecture using the normal graphical package installer:

- `runmal_<version>_amd64.deb`
- `runmal_<version>_arm64.deb`

Rúnmál then appears in the desktop application menu with `Terminal=false`.

The launcher core is distribution-neutral. Additional package formats can wrap the same binary without creating another Rúnmál implementation.

## What happens when the Rúnmál icon is clicked

1. The launcher checks `http://127.0.0.1:8098/healthz`.
2. If Rúnmál is already healthy, it reuses it.
3. Otherwise it starts a hidden launcher-managed server process.
4. It waits for the health endpoint rather than guessing a sleep duration.
5. It creates a 90-second, one-use browser-bootstrap nonce.
6. The browser exchanges that nonce for a signed HttpOnly session cookie.
7. The nonce is consumed and cannot be replayed.
8. The browser redirects to `/chat`.

The permanent bearer credential never appears in the bootstrap URL.

## Control Center

Run **Rúnmál Control Center** to access:

- Open Rúnmál
- Start
- Stop
- Restart
- Diagnostics
- Start Rúnmál automatically when I sign in

Autostart is opt-in and current-user-only.

## Sovereign package builds

Rúnmál desktop packages are built locally on owner-controlled machines. Hosted GitHub Actions runners are not part of the packaging or release process.

### Windows local build

Run on Windows from the repository checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-local.ps1
```

The builder:

- creates an isolated build environment;
- installs the Rúnmál build dependencies locally;
- freezes the application with PyInstaller;
- smoke-tests the launcher;
- starts the frozen local server and verifies `/healthz`;
- creates the installer with Inno Setup;
- writes `Runmal-Setup.exe` directly into the repository root;
- prints its SHA-256 digest.

Inno Setup 6 must be installed on the Windows build machine.

### Linux local build

Run on the target Linux architecture:

```bash
./scripts/build-linux-local.sh
```

The builder creates and smoke-tests the native frozen app and writes one of these directly into the repository root:

- `runmal_<version>_amd64.deb`
- `runmal_<version>_arm64.deb`

### macOS local build

Run on the target Mac:

```bash
./scripts/build-macos-local.sh
```

The builder creates and smoke-tests the `.app`, builds the native DMG with `hdiutil`, and writes one of these directly into the repository root:

- `Runmal-macOS-Apple-Silicon.dmg`
- `Runmal-macOS-Intel.dmg`

A package is considered a real distributable only after the native builder has actually produced and smoke-tested the file on its target operating system.

## Source/bootstrap installers

The readable bootstrap scripts remain useful for testing, repair, or platforms where a prebuilt package is not available:

- Windows: `scripts/install-windows.ps1`
- Linux: `scripts/install-linux.sh`
- macOS: `scripts/install-macos.sh`

These scripts install Rúnmál into an isolated private environment. They are not the recommended front door for nontechnical users once native packages are published.

### Testing an unmerged branch

Developers may point the bootstrap installer at another Git ref while testing. Normal users should stay on packaged releases/main and never need to know what a Git ref is.

## Diagnostics

The launcher writes server startup output to:

`~/.local/share/runmal/launcher-server.log`

The Control Center's **Show Diagnostics** button produces a copyable report containing platform/runtime paths, launcher status, and the existing `runmal doctor` findings. Credentials are not intentionally included.

## Uninstall/data safety

Application binaries and personal data are separate. Removing or upgrading the desktop package must not silently delete chats, characters, lorebooks, memories, settings, credentials, voices, or backups.

A future explicit **Remove Rúnmál and all personal data** flow must require separate confirmation rather than being folded into ordinary uninstall.
