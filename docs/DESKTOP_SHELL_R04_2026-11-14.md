# Desktop Shell Skeleton — R-04 (2026-11-14)

The windowed-shell redo's first UI slice. Before R-04, the only
desktop-shaped code was the R-01 toolkit spike and the Tk "Control
Center" (`launcher/gui.py`), whose whole job was subprocess
start/stop/status for a browser-served shell that no longer exists as
the product's face. R-04 lands the real skeleton the remaining
R-slices build screens into: a `QMainWindow`, the client layer every
widget must talk through, the in-process engine lifecycle, and
first-run detection. It adds **no engine routes** (route census
unchanged at 365 paths / 455 operations).

## Definition (before implementation, per repo law)

- **Owning subsystem:** `src/runmal/desktop/` — a new top-level
  package beside the engine. The engine (`runmal.app` and everything
  under it) is unchanged in kind and untouched by this slice.
- **Inputs:** the engine's existing HTTP contract (`/healthz`,
  `/api/v1/status`, the R-02 backend-profile routes, `/api/v1/chats`,
  `/api/v1/characters`) and the local auth material in `runmal.auth`.
- **Outputs:** a launchable window (`python -m runmal.desktop`), a
  typed client API for widgets, an engine status/lifecycle API, and
  a `FirstRunState` the R-05 wizard will consume.
- **Invariants honoured:** INV-023 (the credential is held only in
  memory by the client session object; it never appears in reprs,
  errors, logs, or any response-shaped object — the client tests
  assert this), INV-024 (everything is loopback/local), INV-031
  (this slice's evidence is the launch proof, not optimism).
- **Failure behaviour:** engine unreachable → `TransportError`;
  401/403 → `AuthError`; 404 → `NotFoundError`; other ≥400 →
  `ApiError` with the engine's plain `detail`. In the window, a
  failed refresh becomes status-bar words; the GUI thread never
  blocks on the network and never freezes on a dead engine.
- **Compatibility:** additive only. No existing route, behaviour, or
  file contract changes. The Tk Control Center and the subprocess
  launcher road stay as they are until R-16 retires them.

## Architecture (plan §2.2, made concrete)

```
widgets (desktop/window.py)          — Qt; no engine imports, no SQL
  │  holds an EngineHandle + a RunmalClient; calls go through…
client layer (desktop/client/)       — Qt-FREE typed HTTP clients,
  │                                    session, error taxonomy,
  │                                    first-run rule, snapshots
  ▼  HTTP (loopback, bearer session)
engine (runmal.app, in-process)      — unchanged FastAPI app
host seam (desktop/engine.py)        — Qt-free; uvicorn in a worker
                                       thread (the R-01 spike road)
```

- **Widgets never import engine services or touch SQL.** Their only
  engine roads are `RunmalClient` (data) and `EngineHandle`
  (lifecycle). The one module allowed to import `runmal.app` is the
  host seam `desktop/engine.py`, which is not a widget.
- **All network work runs off the GUI thread.** The client core is
  synchronous httpx; `desktop/workers.py` runs callables in Qt's
  thread pool and returns results via signals. The window exposes a
  synchronous `refresh_blocking()` used only by tests/proof drivers.
- **The client core is importable without Qt.** `runmal.desktop`'s
  package `__init__` imports nothing; Qt lives only in
  `window.py` / `workers.py` / `app.py`. A subprocess test asserts
  importing the client + engine modules pulls in no PySide6 — this
  is what lets the VM's Qt-less venv gate the client layer.

## Session contract (the auth road, chosen)

Two roads into `require_local_auth` already exist and both are
implemented in `client/session.py` (`DesktopSession`):

1. **Local credential — the desktop default.** The shell runs
   in-process as the same OS user as the engine, so it reads the
   owner-only credential via `runmal.auth.get_or_create_credential()`
   and sends `Authorization: Bearer …`. Chosen because it is the
   simplest proven road inside one trusted local process: no nonce
   file exchange, no redirect handling, and no cookie same-origin
   machinery (which exists to protect *browsers*).
2. **Bootstrap nonce → session cookie — the browser road.**
   `DesktopSession.from_bootstrap()` mints a nonce with
   `create_bootstrap_nonce()` and exchanges it at
   `/launcher/bootstrap` for the signed `runmal_session` cookie,
   exactly as `launcher.core.bootstrap_url()` sets up for a browser.
   Kept for future out-of-process shells that cannot read the
   credential file; tested against a simulated engine here and by
   construction against the same `auth.py` primitives the launcher
   road already proves in production use.

## Engine lifecycle contract

`EngineHandle` (one per window): `start()` builds the app via
`create_app(default_session_factory())` on an ephemeral loopback
port (or a caller-fixed port), runs uvicorn in a daemon thread, and
blocks until `/healthz` answers `{"status": "ok"}` or the attempt
fails; `stop()` sets `should_exit` and joins (idempotent);
`status()` never trusts internal flags alone — a RUNNING claim
requires a fresh real `/healthz` ok, a live-but-unhealthy thread
reads STARTING, a dead thread with a recorded failure reads FAILED.
The window drives it from File → Start/Stop/Restart Engine, the
toolbar, and the status bar; closing the window stops the engine
(clean quit). This replaces the Tk Control Center's job for the
desktop road.

## First-run contract

`detect_first_run(profiles, characters)` is a pure rule:
**first run ⟺ zero backend profiles AND zero characters** — the
empty state every fresh install starts in (plan §1.3.4). Chats do
not count (the old shell auto-created character-less chats).
`RunmalClient.first_run_state()` fetches both lists through the
client layer; the window renders the result in the Session dock,
the status area, and a central banner, and File → First-Run Setup…
re-checks and reports it. The wizard itself is R-05 and is **not**
built here — R-04 ships detection + indication only.

## The window (skeleton scope, honestly labelled)

`MainWindow` ("Rúnmál"): the §2.3 menus (File/Edit/View/Chat/
Characters/World/Tools/Window/Help), a toolbar, a left **Library**
dock with Chats/Characters tabs, a right **Session** dock (engine,
backend, model, setup, counts — words, never colour alone), a
central **Chat Stage** placeholder region, and a status bar
(engine state, backend, streaming-idle placeholder).

REAL in R-04: engine start/stop/restart, dock toggles, status
refresh, first-run status, About, Quit (stops the engine).
Placeholder actions (New Chat, Connections, editor screens, …) are
labelled with the slice that lands them and say so in the status
bar when triggered — the §1.6 lesson: no dead control dressed as a
feature, and no substring test standing in for behaviour.

## Verification

- `tests/test_r04_desktop_client.py` — MockTransport session roads
  (bearer + bootstrap cookie), typed parsing + drift tolerance,
  error taxonomy, credential-hygiene reprs, pure + client first-run,
  and the no-Qt import proof.
- `tests/test_r04_desktop_engine.py` — live in-process engine:
  STOPPED → RUNNING → STOPPED transitions against a real `/healthz`,
  the typed client against that engine, first-run true on a fresh
  data dir and false after creating one profile + one character
  through the real API, profile health/models through the client.
- `tests/test_r04_desktop_window.py` — window structure (menu order,
  docks, tabs), initial stopped chrome, snapshot rendering incl. the
  first-run banner, close-stops-engine. Skips cleanly without
  PySide6.
- **Launch proof** — `scripts/desktop_r04_proof.py` drives the real
  window (offscreen Qt on headless venues; the window is really
  shown and its actions really triggered): menus, dock toggle,
  About, placeholder honesty, engine start via the window, status
  bar vs real `/healthz`, first-run true → configure → false,
  clean quit stops the engine. Required venues: F15 (Windows) and
  purpleraider (Linux x86-64); Mimir (ARM) as the same driver allows.
  Logs live in the campaign's evidence folder, not the repo.
