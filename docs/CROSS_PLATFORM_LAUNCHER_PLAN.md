# Cross-Platform Installer and Desktop Launcher Campaign

**Campaign:** Distribution / Desktop UX (D001-D010)  
**Defined:** 2026-11-01  
**Status:** implementation in progress  
**Owner:** Volmarr / Rúnmál fellowship

## Goal

Rúnmál must behave like an ordinary desktop application. A nontechnical user should be able to download Rúnmál, install it, find a Rúnmál icon in the normal application menu, click it, and begin using the existing browser UI without learning Python, Git, virtual environments, localhost ports, bearer tokens, or terminal commands.

The command-line interface remains available for expert users. It is no longer the front door.

## Supported desktop targets

The launcher core is intentionally platform-neutral and standard-library-first.

| Platform | Friendly package | Bootstrap/source installer | Desktop integration |
| --- | --- | --- | --- |
| Windows 10/11 | `Runmal-Setup.exe` | PowerShell bootstrap | Start Menu + optional Desktop shortcut |
| macOS Intel / Apple Silicon | `Runmal.dmg` / `.app` | shell bootstrap | Applications bundle |
| Linux | `.deb` first; portable bundle thereafter | shell bootstrap | freedesktop application menu entry |
| Other Python 3.12+ POSIX systems | source install | manual/bootstrap-compatible | launcher CLI; native package may vary |

Mobile operating systems are a separate application-distribution problem and are not silently treated as desktop platforms. The HTTP/UI architecture leaves room for a future Android/iOS client, but this campaign does not pretend a desktop Python package is a native mobile app.

## Non-negotiable UX

A normal user must not have to:

- open a terminal;
- install or understand Git;
- create or activate a Python virtual environment;
- type `runmal serve`;
- know that port 8098 exists;
- locate `local_credential`;
- copy or paste bearer tokens;
- understand FastAPI, uvicorn, systemd, launchd, or Windows services.

The happy path is:

1. Download the platform package.
2. Install it with the platform's normal installer flow.
3. Click **Rúnmál**.
4. The launcher starts the local server if needed.
5. The launcher waits for `/healthz`.
6. The launcher performs a one-time local browser bootstrap without exposing the permanent credential.
7. The default browser opens Rúnmál.

## Architecture

### D001 - Launcher lifecycle core

Add a `runmal-launcher` entry point that can:

- `open` Rúnmál;
- `start` the managed local server;
- `stop` a server process started by the launcher;
- `restart` it;
- report `status`;
- show a graphical `control` center;
- surface diagnostics.

The launcher must detect an already-running Rúnmál instance and must not create duplicate servers.

### D002 - Safe browser bootstrap

The permanent local bearer credential remains private and must never be placed in a URL, HTML body, log, trace, or diagnostic output.

The launcher creates a high-entropy, short-lived, one-use bootstrap nonce in the owner-only Rúnmál data directory. It opens a loopback bootstrap URL containing only that disposable nonce. The server consumes it once, issues a signed HttpOnly browser-session cookie, deletes the nonce record, and redirects to `/chat`.

Browser cookie authentication must use SameSite protection and an explicit same-origin check for state-changing requests. Bearer authentication remains supported for scripts and bridges.

### D003 - Process ownership and recovery

The launcher stores only nonsecret lifecycle state such as the managed process ID and port. It may terminate only a process it recorded as launcher-managed. Stale state is cleaned safely. Startup failures are written to a launcher log and surfaced as human-readable errors.

### D004 - Cross-platform Control Center

Provide a small graphical control surface using standard-library Tk where available/bundled:

- Open Rúnmál
- Start
- Stop
- Restart
- Status
- Diagnostics
- Start automatically when I sign in

The main Rúnmál application shortcut should open Rúnmál directly. The Control Center is a separate management surface, not an extra mandatory click.

### D005 - Native desktop integration

- **Windows:** Start Menu entry, optional Desktop shortcut, current-user install by default, no administrator rights for normal app files.
- **macOS:** `.app` bundle distributed in a DMG; normal Applications-folder workflow.
- **Linux:** freedesktop `.desktop` entry with `Terminal=false`, application icon, native package metadata.

Autostart is opt-in and uses current-user mechanisms only:

- Windows HKCU Run key;
- macOS user LaunchAgent;
- Linux XDG autostart desktop entry.

### D006 - Bootstrap installers

Keep readable platform bootstrap scripts for repair, development, unsupported architectures, and users who prefer source installs:

- `scripts/install-windows.ps1`
- `scripts/install-linux.sh`
- `scripts/install-macos.sh`

They must create an isolated Rúnmál environment and desktop entry rather than polluting arbitrary system Python environments.

### D007 - Prebuilt packages

CI produces self-contained artifacts so ordinary users do not need Python installed:

- Windows installer executable;
- macOS application/DMG;
- Linux `.deb` initially.

Additional Linux package formats and architectures can be added without changing launcher behavior.

Unsigned CI artifacts are development/test builds. Public releases should be code-signed/notarized when project signing credentials become available.

### D008 - Update-safe layout

Application code and personal data stay separate. Updates must never silently remove chats, characters, lorebooks, memories, voices, settings, backups, or credentials.

The existing `RUNMAL_DATA_DIR` contract remains authoritative. This campaign does not migrate the user data directory simply to make paths look more native.

### D009 - Tests and platform CI

Acceptance coverage must include:

- bootstrap nonce is one-use and expires;
- permanent bearer credential never appears in bootstrap responses;
- signed browser sessions authenticate APIs;
- unsafe cookie-authenticated requests reject unexpected/missing Origin;
- existing bearer auth continues to work;
- launcher detects an already-running server;
- launcher bootstrap URL contains only the disposable nonce;
- stale launcher state does not cause arbitrary process termination;
- Windows, macOS, and Linux package builds execute in CI.

### D010 - Human acceptance test

Give the package to a person who has never used Python, Git, a terminal, localhost, or an AI backend and tell them only:

> Install this and open Rúnmál.

The campaign passes when they can install it, launch it from the normal application menu, reach the UI, and use it without being asked to copy a credential or type a command.

## Security invariants preserved

This campaign must preserve the existing local-first and auth boundaries:

- default bind remains `127.0.0.1`;
- `/healthz` remains liveness-only;
- the permanent local credential remains owner-only;
- bearer auth remains valid for scripts/bridges;
- launcher convenience does not imply LAN/WAN exposure;
- browser convenience must not weaken secret-handling rules;
- no telemetry is introduced.

## Windows-first field test

The first real-world field test is Windows 11. The package and source bootstrap should therefore expose clear errors, never require a terminal for normal launching, and produce a copyable diagnostic report if startup fails.

The same launcher code is used on Linux/Kubuntu and macOS rather than creating three unrelated application implementations.
