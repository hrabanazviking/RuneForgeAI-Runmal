# R-17 — Platform proof & installers (2026-11-22)

Final slice of the windowed-shell redo. Everything was rebuilt on
the R-16 tree (595811b, the desktop-only front end) and the
packaging story was proven end to end where the fleet allows.

## The packaging defect R-17 found and fixed

The platform builders installed only the base project
(`pip install -e .`) and collected only `runmal`/`sqlite_vec` into
the PyInstaller bundle. Since R-16 the frozen entry's `open` road
launches the Qt desktop shell — so a package built by those scripts
would have shipped a front end that cannot start (no PySide6 in the
bundle). All three builders now:

- install the `desktop` extra (`pip install -e ".[desktop]"`), and
- pass `--collect-all PySide6` to PyInstaller.

The Linux builder additionally smoke-tests the desktop entry: after
the launcher `status` and frozen-server `/healthz` smokes, it
launches the frozen binary's `_desktop` offscreen on a throwaway
data dir and fails the build unless the shell reaches its event
loop, stays up 10 s, and leaves no traceback. The macOS builder was
refreshed identically and carries an explicit UNPROVEN header
(plan §2.5). The Windows builder received the same two changes by
inspection (it can only run on Windows).

Also refreshed: `packaging/linux/runmal.desktop` drops the retired
Control Center action (the desktop app is the control centre), and
`docs/DESKTOP_INSTALLATION.md` was rewritten for the desktop era —
it still described the browser UI, the bootstrap-nonce road, and
the Tk Control Center, all removed at R-16.

A standing text-level gate (`tests/test_r17_packaging.py`) pins the
builder contents, the .desktop entry, the installation doc, and
the frozen-entry desktop dispatch, so the packaging cannot quietly
rot back.

## Platform proof table (plan §2.5)

| Platform | Venue | Result |
|---|---|---|
| Linux x86-64 | Muse VM (build seat) | **PROVEN** — deb built (all smokes incl. desktop), `dpkg -i` installed, installed entry launched the desktop offscreen clean; R-17 proof 13/13; R-16 proof re-run 20/20 |
| Linux x86-64 | purplelongship | **PROVEN** — R-16 launch proof re-run on the R-16 tree: 20/20, offscreen |
| Linux ARM (aarch64) | Mimir (Pi 5) | **PROVEN** — arm64 deb built on-device with the R-17 builder (byte-identical script, sha256-verified before the run; all builder smokes incl. desktop passed); extracted install launched the desktop offscreen clean; R-16 proof re-run 20/20 (after removing an untracked `__pycache__`-only `src/runmal/web` leftover from an older checkout, which had made the deleted package importable as a namespace package on that dirty tree only) |
| Windows (x86-64) | F15 `PURPLEWIZARD` | **DEFERRED** — the F15's road runs through purpleraider, which is paused by Volmarr's order; the owed F15 proofs (R-09…R-16) and the `Runmal-Setup.exe` rebuild ride with it. The existing exe still dates from 2026-11-02 (web-shell code) and is labelled stale in the installation doc |
| macOS | — | **UNPROVEN** — no Mac in the fleet; packaging script refreshed, explicitly unproven |

## Packages built

- `runmal_0.1.0_amd64.deb` — 107,002,494 bytes, SHA-256
  `0164f40bdaa10fea14e73c770c7dbe573c89fb91b51fc16d34bcdb26b692127b`,
  built on the Muse VM from the R-17 tree. It cannot be committed
  to the repo: at 107 MB it exceeds GitHub's 100 MB file limit
  (the push was declined by the remote hook), so the Qt-era
  packages outgrow the repo's commit-the-deb convention — the
  tracked root copy remains the 2026-11-13 build, and this package
  lives on the VM at `~/workspace/runmal-refresh/`. Installed with
  `dpkg -i`; `/opt/runmal/runmal status` answered, `open
  --no-launch` dispatched to `_desktop`, and the installed desktop
  launched offscreen and stayed up with no traceback.
- `runmal_0.1.0_arm64.deb` — 150,630,328 bytes, SHA-256
  `1ca78c8a0499bdb4df7e1e3597c489d1ad56a1842319c8ac05ba40ed45b669ec`,
  built on Mimir from the R-16 tree plus the R-17 builder script
  (R-17 changes no application code, so the bundled app is the
  banked app). It lives on Mimir at
  `~/runmal-r01-src/runmal_0.1.0_arm64.deb`; the copy tracked at
  this repo's root is still the 2026-11-13 build (150 MB does not
  travel the device road). One incident, recorded honestly: the first
  `dpkg-deb` compression was killed mid-write when the device
  road's invoke timed out; the packaging step was re-run detached
  over the builder's own `dist/` (all builder smokes had already
  passed) and produced the package above. Extracted to
  `~/r17-install` on Mimir: `status` answered, `open` dispatched
  to `_desktop`, desktop launched offscreen clean.

Build-environment note (VM): the builder's staging uses `mktemp`,
which lands on the VM's 512 MB noexec `/tmp` tmpfs — the first VM
build failed at the copy step with "No space left on device". The
build was re-run with `TMPDIR` on the workspace disk and passed.
The R-17 proof script extracts packages onto the workspace disk
for the same reason.

## Rebuild proof sweep

The R-04…R-16 per-slice launch proofs stand as banked; for R-17 the
R-16 proof (the full-shell launch proof: window, theme, engine,
removed-web-path 404s, clean quit) was re-run as the rebuild
evidence on every reachable venue — VM 20/20, purplelongship
20/20, Mimir 20/20 — alongside the new R-17 packaging proof
(13/13 on the VM). The F15 legs of the sweep remain deferred with
the Windows row above.

## Gates (VM seat, swift standard)

- R-17 packaging tests 7/7; R-16 smoke gate 8/8; P-207 census
  16/16 (census unchanged 354 paths / 444 operations — R-17 adds
  no engine routes).
- Neighbour batch (R-13 + R-14 logic/live, launcher core/auth):
  52 passed.
- P-232 file: 34 passed + only the known pre-existing H1 footprint
  failure (identical at base; not a blocker per the speed law).
- Full suite collects 6,611 cleanly (Qt-less VM venv; R-16 banked
  tree measured 6,604 on the same basis, +7 R-17 tests).
- Ruff clean on the new files; both shell builders pass `bash -n`.
- README.md untouched.
