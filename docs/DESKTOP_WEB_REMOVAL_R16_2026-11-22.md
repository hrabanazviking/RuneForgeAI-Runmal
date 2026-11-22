# R-16 — Scrap the web shell (2026-11-22)

Slice contract: plan Part 3 R-16 + §2.4 + §1.6. ADR-0011 records the
architecture decision.

## Removed

- `src/runmal/web/` — 8 templates, 13 static files, page router
  (9 page routes: `/`, `/chat`, `/connections`, `/editor`, `/tools`,
  `/gallery`, `/lorebooks`, `/group`, `/inspector`) + the `/static` mount.
- `voice_page` + its `_PAGE`/`_backends_panel` HTML builders
  (`GET /voice`); the voice JSON API is untouched.
- `memories_browser_page` (`GET /memories` and
  `GET /api/v1/memories-browser`); the memories JSON API is untouched.
- `launcher/gui.py` (Tk Control Center, retired per §2.4) and the
  launcher CLI's `control` command.
- Web-only tests/fixtures: `test_s109_ui`, `test_s301_tokens`,
  `test_s308_palette`, `test_s309_a11y`, `test_s310_responsive`,
  `test_s311_ui_regression`, `tests/fixtures/ui/*.golden.txt`,
  `tests/js/*.cjs` (Node tests of the removed web scripts), the
  `*_ui_page` legs in S211/S212/S213/S303/S304/S305/S209/S302, the page
  legs in S410/S511, the web legs in P-011/P-042/P-107/P-117, and
  `scripts/walkthrough_s109.py` / `scripts/walkthrough_s111.py`.
  Engine API legs in every mixed file are kept.
- Historical gate batteries P-206/P-212…P-218/P-232: their web
  source-contract legs (group.js/group.html/renderer.js pins, the
  S311 golden watch, citizen counts of removed page tests) are
  amended in-slice to the R-16 truth — the substrate/API legs stand
  unchanged and the amended fences assert the web files' absence at
  full strength (e.g. P-232 H2 now pins that no UI goldens ship;
  the per-swipe-browsing absence fences assert the files themselves
  are gone). P-232's H1 footprint failure is the documented
  pre-existing one, unchanged in kind.
- The `jinja2` dependency (pyproject) — only the web router used it.

## Repointed

- Launcher: `core.open_runmal` launches the desktop app
  (`desktop_command`/`launch_desktop`, frozen builds re-enter with
  `_desktop`); no browser is opened and no server is started for the
  desktop road (it hosts its engine in-process). The headless server
  lifecycle (start/stop/status/doctor/`_serve`, bootstrap nonce)
  stays for bridge/headless use. The frozen entry
  (`launcher/frozen_entry.py`) repoints directly at
  `runmal.desktop.app:main`.
- `/launcher/bootstrap` redirect: `/chat` → `/api/v1/status`.
- `packaging/linux/runmal.desktop` + install scripts: launch the
  desktop entry; the Control Center desktop action is gone.
- `packaging/windows/runmal.iss`: shortcuts launch the app with no
  `open`/`control` parameters.
- `scripts/build-windows-local.ps1` (+ linux/macos builders): the
  Tk/web assumptions are dropped; PySide6 is collected for the
  frozen desktop build. Full installer proof is R-17.

## Census

Route census measured from `/openapi.json` after removal:
11 OpenAPI page routes gone (8 web pages — the `/` redirect was
schema-excluded — + `/voice` + `/memories` +
`/api/v1/memories-browser`), each a single GET operation.
365 paths / 455 operations → **354 paths / 444 operations**, healed
in all 14 Part XIII census-pin files + the P-218 derived remainders
(363/453 → 352/442).

## Standing gate (§1.6, mechanical)

`tests/test_r16_desktop_smoke.py`: `runmal.web` is not importable
and its tree is absent; the built app serves no old page path while
the API answers; every shipped desktop front-end file parses and
the desktop client layer imports with no PySide6; the launcher's
open road targets the desktop module. `scripts/desktop_r16_proof.py`
is the launch proof: the desktop entry launches headless-clean on a
fresh data dir, the real engine 404s every removed route, and a
clean quit stops the engine.

## Verification (speed law)

Swift standard per Volmarr's 2026-11-22 speed law — own tests +
neighbour batches + census + clean full-suite COLLECTION + the real
launch proof; no full-suite execution gate (the plan's "full suite
green" wording is superseded by the speed law; deviation recorded
here and in the campaign state file).

Results (VM, Linux x86-64, offscreen Qt 6.8.0): standing gate +
launcher + census family — 73 passed (p218 33/33 within its batch;
the wider census/neighbour sweep ran 185 + 113 passed in crew
verification); P-232 — 34 passed + only the known pre-existing
`test_h1_tree_law_footprint` failure; full-suite COLLECTION clean
at 6,604 tests (baseline 6,722 at R-15, net −118); ruff clean on
all newly-touched files (app.py keeps its baseline I001/E501
classes, reduced 9 → 5 in the touched sources, none new). Launch
proof `scripts/desktop_r16_proof.py`: **20/20 PASS** — launcher
open road names `runmal.desktop` and spawns nothing under
`--no-launch`, `control` rejected, `runmal.web` not importable,
the real window launches themed on a fresh data dir, every removed
page path answers 404 JSON while `/api/v1/status` + `/healthz`
answer 200, and a clean quit stops the engine. Proof-hygiene note:
a data dir left half-initialised by killed runs stalls engine boot
— the proof now wipes its dedicated data dir and proves a fresh
install on every run. Venue: fleet proofs (purplelongship, Mimir)
deferred to the keeper road as throughout the campaign;
purpleraider deferred under Volmarr's pause; the Windows installer
proof is R-17's.
