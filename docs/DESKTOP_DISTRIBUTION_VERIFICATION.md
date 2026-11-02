# Desktop Distribution Verification

**Campaign:** Distribution / Desktop UX D001-D010  
**Verification date:** 2026-11-01 / 2026-11-02 UTC  
**Feature branch:** `feature/cross-platform-launcher`  
**Pull request:** #1  
**Status:** D001-D009 implemented and CI-verified; D010 owner field test pending

## Automated acceptance status

The desktop launcher/distribution branch has passed the following gates:

- launcher/auth acceptance tests on Windows;
- launcher/auth acceptance tests on macOS;
- launcher/auth acceptance tests on Linux;
- complete Rúnmál regression suite on Linux;
- Ruff checks for launcher/security changes;
- source launcher CLI smoke tests;
- frozen launcher startup tests;
- frozen local-server `/healthz` tests;
- native package construction and artifact upload.

A stricter frozen-server smoke test initially exposed a PyInstaller-only failure: SQLAlchemy selects `aiosqlite` dynamically from the `sqlite+aiosqlite://` URL, so static import analysis did not bundle the driver. The packaging definition was corrected to include `aiosqlite` explicitly and to collect the `sqlite_vec` native payload. The frozen server then passed its health check across the package matrix.

## Verified package matrix

| Target | Package | Frozen launcher | Frozen server | Package build |
| --- | --- | --- | --- | --- |
| Windows x64-compatible | `Runmal-Setup.exe` | PASS | PASS | PASS |
| macOS Apple Silicon | DMG / `.app` | PASS | PASS | PASS |
| macOS Intel | DMG / `.app` | PASS | PASS | PASS |
| Linux AMD64 | `.deb` | PASS | PASS | PASS |
| Linux ARM64 | `.deb` | PASS | PASS | PASS |

The Windows package uses the x64-compatible dependency path. On Windows ARM64, the source/bootstrap path intentionally uses the x64 Python/dependency stack under Windows compatibility because the stable upstream `sqlite-vec` release does not currently provide a native Windows ARM64 wheel. No third-party replacement vector wheel is silently substituted.

## Security acceptance preserved

Automated tests verify that:

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

## Artifact behavior

The normal desktop path is now:

1. Install the native package.
2. Click **Rúnmál** from the desktop/application menu.
3. The launcher checks whether the loopback server is already healthy.
4. If necessary, it starts a hidden local server and waits for readiness.
5. The launcher creates a short-lived, one-use bootstrap nonce.
6. The default browser exchanges that nonce for an HttpOnly local browser session.
7. The user is redirected to `/chat` without copying or seeing the permanent credential.

A separate **Rúnmál Control Center** provides Start, Stop, Restart, status, diagnostics, and opt-in sign-in autostart.

## Remaining D010 gate

The automated matrix cannot replace the human zero-technical-skills acceptance test.

D010 remains pending until the owner performs the Windows 11 field test using the generated installer and confirms the practical flow:

> install -> find/click Rúnmál -> browser opens -> Rúnmál is usable without terminal commands or credential copying

PR #1 should remain unmerged until this field test is complete or the owner explicitly orders it merged earlier.

## Release-signing note

The current CI artifacts are development/test builds and are not code-signed/notarized. Windows SmartScreen and macOS Gatekeeper may therefore identify them as an unknown publisher. Runtime/package correctness and release-signing trust are separate gates. Public release signing should be added when project signing credentials are available.

## Scope still intentionally separate

This distribution campaign establishes the zero-terminal installer/launcher foundation. Full automatic in-app updating and a richer first-run backend/model wizard can build on this layer without changing the launcher/auth architecture. They are not falsely marked complete by this verification record.
