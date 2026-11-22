# ADR-0011 — Web shell removed; desktop is the only shipped front end (R-16)

Date: 2026-11-22 · Slice: R-16 (interface redo plan §2.4, Part 3)

## Decision

- `src/runmal/web/` (Jinja templates, static JS/CSS, page router) is removed.
- The two stray server-rendered pages are removed with it: `voice_page`
  (`GET /voice`, in `voice/router.py`) and `memories_browser_page`
  (`GET /memories` + `GET /api/v1/memories-browser`, in `memory/router.py`).
  Their JSON API routes stay untouched.
- The PySide6 desktop shell (`src/runmal/desktop/`) is the only shipped
  front end. The launcher is repointed: `launcher/core.py`'s open road
  now launches the desktop app (`desktop_command` / `launch_desktop`;
  frozen builds re-enter the executable with the `_desktop` command,
  dispatched by `launcher/__main__`), and the Tk Control Center
  (`launcher/gui.py`) is retired — the Qt app is the control centre
  (engine start/stop/status live in its window). The headless server
  lifecycle in `launcher/core.py` (start/stop/status/bootstrap nonce)
  remains as its own feature for bridge/headless use.
- `/launcher/bootstrap` now redirects to `/api/v1/status` (the session
  cookie it mints still authenticates API roads for out-of-process
  clients); there is no browser page left to land on.
- The engine, HTTP API, bridge, and CLI stay (`runmal serve`, backups, …).

## Why

The web shell was rated 0/10 and ordered scrapped (plan Part 1 audit:
three page scripts did not parse, four pages were permanently
auth-broken, no navigation, no first-run flow). The desktop shell
(R-04…R-15) now covers every surface that ever worked. Keeping the web
package shipped dead code and the exact rot class §1.6 diagnosed.

## Standing gate (the §1.6 lesson, made mechanical)

`tests/test_r16_desktop_smoke.py` + `scripts/desktop_r16_proof.py`:
every shipped front-end file (the whole `desktop/` package) parses,
no template/static remnants ship anywhere in the package, the removed
page routes answer 404 while `/healthz` and the API stay up, and the
installed entry (`python -m runmal.desktop`) launches headless-clean.
