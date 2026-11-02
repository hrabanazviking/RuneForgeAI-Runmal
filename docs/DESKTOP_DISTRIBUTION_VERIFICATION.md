# Desktop Distribution Verification

**Campaign:** Distribution / Desktop UX D001-D010  
**Verification date:** 2026-11-01 / 2026-11-02 UTC  
**Feature branch:** `feature/cross-platform-launcher`  
**Pull request:** #1  
**Status:** launcher implementation complete; native local package re-verification and D010 owner field test pending

## Owner packaging ruling

Volmarr has explicitly ruled that Rúnmál must not use GitHub Actions to build or produce desktop packages. Hosted runner packaging is therefore not part of the accepted distribution mechanism.

The active packaging path is now local and sovereign:

- Windows: `scripts/build-windows-local.ps1`
- Linux: `scripts/build-linux-local.sh`
- macOS: `scripts/build-macos-local.sh`

Each builder performs native packaging and smoke tests on an owner-controlled machine and writes the finished distributable into the repository root.

## Historical hosted-run evidence

Before the owner's no-GitHub-Actions ruling, one hosted build run exercised the launcher and package definitions on Windows, macOS, and Linux. That run exposed a real PyInstaller issue: SQLAlchemy selects `aiosqlite` dynamically from the `sqlite+aiosqlite://` URL, so static import analysis did not initially bundle the driver. The package definition was corrected to include `aiosqlite` explicitly and collect the `sqlite_vec` native payload.

That historical run is useful engineering evidence, but it is **not** the continuing package-production mechanism and must not be used to justify reintroducing hosted GitHub Actions.

## Native local verification matrix

The authoritative release evidence is now a native local build on the target platform.

| Target | Root package | Local frozen launcher | Local frozen server | Local package build |
| --- | --- | --- | --- | --- |
| Windows x64-compatible | `Runmal-Setup.exe` | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN |
| macOS Apple Silicon | `Runmal-macOS-Apple-Silicon.dmg` | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN |
| macOS Intel | `Runmal-macOS-Intel.dmg` | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN |
| Linux AMD64 | `runmal_<version>_amd64.deb` | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN |
| Linux ARM64 | `runmal_<version>_arm64.deb` | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN | PENDING LOCAL RE-RUN |

A target row becomes PASS only when its local builder is run on that target and the resulting package is retained as the actual distributable.

The Windows package uses the x64-compatible dependency path. On Windows ARM64, the source/bootstrap path intentionally uses the x64 Python/dependency stack under Windows compatibility because the stable upstream `sqlite-vec` release does not currently provide a native Windows ARM64 wheel. No third-party replacement vector wheel is silently substituted.

## Security acceptance preserved

The launcher/auth test suite covers that:

- launcher bootstrap nonces are one-use;
- bootstrap nonces expire;
- the permanent bearer credential is not returned in the launcher bootstrap response;
- the permanent bearer credential is not placed in the launcher URL;
- browser sessions are signed and expire;
- the browser session cookie is HttpOnly and SameSite-protected;
- state-changing cookie-authenticated requests require same-origin browser context;
- bearer-authenticated API clients retain the existing contract;
- the launcher does not spawn a duplicate server when a healthy Rúnmál is already running;
- the launcher refuses to claim a port occupied by a foreign process;
- the launcher never kills a process without launcher-owned lifecycle state.

## Package behavior

The normal desktop path is:

1. Install the native package.
2. Click **Rúnmál** from the desktop/application menu.
3. The launcher checks whether the loopback server is already healthy.
4. If necessary, it starts a hidden local server and waits for readiness.
5. The launcher creates a short-lived, one-use bootstrap nonce.
6. The default browser exchanges that nonce for an HttpOnly local browser session.
7. The user is redirected to `/chat` without copying or seeing the permanent credential.

A separate **Rúnmál Control Center** provides Start, Stop, Restart, status, diagnostics, and opt-in sign-in autostart.

## Remaining D010 gate

D010 remains pending until the owner performs the Windows 11 field test using the locally built installer and confirms the practical flow:

> install -> find/click Rúnmál -> browser opens -> Rúnmál is usable without terminal commands or credential copying

The owner has already directed that the launcher feature be merged when ready; D010 remains a usability verification record rather than a justification for hosted CI.

## Release-signing note

Locally built development/test packages are not automatically code-signed/notarized. Windows SmartScreen and macOS Gatekeeper may therefore identify them as an unknown publisher. Runtime/package correctness and release-signing trust are separate gates. Public release signing should be added when project signing credentials are available.

## Scope still intentionally separate

This distribution campaign establishes the zero-terminal installer/launcher foundation. Full automatic in-app updating and a richer first-run backend/model wizard can build on this layer without changing the launcher/auth architecture. They are not falsely marked complete by this verification record.
