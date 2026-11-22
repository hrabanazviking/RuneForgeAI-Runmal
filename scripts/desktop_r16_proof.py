"""R-16 launch proof: the web shell is gone and the desktop is the app.

Run with the VM Qt proof environment:

    QT_QPA_PLATFORM=offscreen \
    LD_LIBRARY_PATH=$HOME/workspace/.qtlibs/root/usr/lib/x86_64-linux-gnu \
    PYTHONPATH=/tmp/pyside \
    ~/workspace/runmal-venv/bin/python scripts/desktop_r16_proof.py

Checks: (1) the launcher's open road names the desktop module and
spawns nothing with --no-launch, and the retired `control` command is
rejected; (2) runmal.web is not importable; (3) the REAL desktop
window launches offscreen on the R-16 tree, themed (R-15), engine up;
(4) the served engine answers 404 (JSON, never HTML) on every removed
page path while /api/v1/status and /healthz answer; (5) clean quit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

DATA = Path.home() / "workspace" / ".r16-proof-data"
shutil.rmtree(DATA, ignore_errors=True)  # every run proves a fresh install
DATA.mkdir(parents=True, exist_ok=True)
os.environ["RUNMAL_DATA_DIR"] = str(DATA)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def main() -> int:
    # (1) Launcher open road: names the desktop, spawns nothing.
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "runmal.launcher", "open", "--no-launch"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )
    out = proc.stdout + proc.stderr
    check(
        "launcher open --no-launch names runmal.desktop",
        proc.returncode == 0 and "runmal.desktop" in out,
        out.strip().splitlines()[-1] if out.strip() else "",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "runmal.launcher", "control"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )
    check("launcher control command is gone", proc.returncode != 0)

    # (2) The web package is not importable.
    proc = subprocess.run(
        [sys.executable, "-c", "import runmal.web"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )
    check("runmal.web not importable", proc.returncode != 0)

    # (3) The real desktop window on the R-16 tree.
    from PySide6.QtWidgets import QApplication

    from runmal.desktop.app import create_window
    from runmal.desktop.theme import build_qss

    app = QApplication([])
    window = create_window()
    window.show()
    window.start_engine_async()
    for _ in range(300):
        app.processEvents()
        if window._client is not None:
            break
        time.sleep(0.1)
    check("desktop window launched, engine hosted", window._client is not None)
    prefs = window.appearance_prefs
    check(
        "app themed by the desktop theme (R-15 intact)",
        app.styleSheet() == build_qss(prefs.variant, prefs.ornament, prefs.text_scale),
        f"({prefs.variant}/{prefs.ornament}/{prefs.text_scale})",
    )
    base = window._client.base_url

    from runmal.auth import get_or_create_credential

    def get(path: str) -> tuple[int, str]:
        try:
            req = urllib.request.Request(
                base + path,
                headers={"Authorization": f"Bearer {get_or_create_credential()}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                return resp.status, resp.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            exc.read()
            return exc.code, exc.headers.get_content_type()

    # (4) Removed pages are dead; the API lives.
    for path in (
        "/",
        "/chat",
        "/connections",
        "/editor",
        "/tools",
        "/gallery",
        "/lorebooks",
        "/group",
        "/inspector",
        "/voice",
        "/memories",
        "/static/app.js",
    ):
        status, ctype = get(path)
        check(
            f"removed page {path} answers 404 non-HTML",
            status == 404 and ctype != "text/html",
            f"({status}, {ctype})",
        )
    for path in ("/api/v1/status", "/healthz"):
        status, _ctype = get(path)
        check(f"live road {path} answers 200", status == 200, f"({status})")

    # (5) Clean quit: close the window; the engine stops with it.
    window.close()
    gone = False
    deadline = time.time() + 15
    while time.time() < deadline:
        app.processEvents()
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1).read()
        except Exception:
            gone = True
            break
        time.sleep(0.2)
    check("clean quit stops the engine", gone)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
