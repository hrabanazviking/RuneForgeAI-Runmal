"""R-17 launch proof: platform packaging & the installed entry.

Run on the build seat after `scripts/build-linux-local.sh`:

    ~/workspace/runmal-venv/bin/python scripts/desktop_r17_proof.py

Checks: (1) all three platform builders install the `desktop` extra
and collect PySide6 (a frozen app missing either cannot open its
only front end), and the macOS builder still says UNPROVEN;
(2) the Linux .deb in the repo root is a real package for this
machine's architecture; (3) the package's installed entry — the
extracted /opt/runmal/runmal — answers `status`, its `open` road
names the desktop dispatch, and the desktop shell itself launches
offscreen from the installed tree and stays up clean; (4) the
source-tree launcher road still names runmal.desktop and rejects
the retired `control` command.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kwargs)


def main() -> int:
    # (1) Builders carry the desktop bundle.
    linux = (REPO / "scripts/build-linux-local.sh").read_text(encoding="utf-8")
    macos = (REPO / "scripts/build-macos-local.sh").read_text(encoding="utf-8")
    windows = (REPO / "scripts/build-windows-local.ps1").read_text(encoding="utf-8")
    check(
        "linux builder installs desktop extra + collects PySide6",
        '".[desktop]"' in linux and "--collect-all PySide6" in linux,
    )
    check(
        "windows builder installs desktop extra + collects PySide6",
        '".[desktop]"' in windows and "--collect-all PySide6" in windows,
    )
    check(
        "macos builder refreshed and still marked UNPROVEN",
        '".[desktop]"' in macos
        and "--collect-all PySide6" in macos
        and "UNPROVEN" in macos,
    )
    check(
        "linux builder smoke-tests the desktop entry offscreen",
        "QT_QPA_PLATFORM=offscreen" in linux and '"$RUNMAL_BIN" _desktop' in linux,
    )

    # (2) The built .deb is real and for this architecture.
    arch = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine(), platform.machine()
    )
    debs = sorted(REPO.glob(f"runmal_*_{arch}.deb"))
    deb = debs[-1] if debs else None
    check("linux deb present for this architecture", deb is not None, str(deb))
    if deb is None:
        return 1
    check("deb is a full package (>10 MB)", deb.stat().st_size > 10_000_000,
          f"{deb.stat().st_size} bytes")
    info = _run(["dpkg-deb", "-I", str(deb)]).stdout
    check("deb control names runmal + this arch",
          "Package: runmal" in info and f"Architecture: {arch}" in info)

    # (3) The installed entry from the package launches the desktop.
    # Extract on the workspace disk: /tmp may be a small noexec tmpfs,
    # which cannot run the frozen binary (and barely holds it).
    scratch = Path.home() / "workspace" / ".r17-tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="r17-install-", dir=scratch))
    try:
        _run(["dpkg-deb", "-x", str(deb), str(root)])
        binary = root / "opt/runmal/runmal"
        check("package carries /opt/runmal/runmal", binary.is_file())
        status = _run([str(binary), "status"])
        check("installed entry answers status",
              status.returncode == 0 and '"running"' in status.stdout,
              status.stdout.strip().replace("\n", " ")[:80])
        opened = _run([str(binary), "open", "--no-launch"])
        check("installed open road dispatches to _desktop",
              opened.returncode == 0 and "_desktop" in opened.stdout,
              opened.stdout.strip())
        desk_log = root / "desktop.log"
        data_dir = root / "data"
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "RUNMAL_DATA_DIR": str(data_dir),
        }
        with desk_log.open("w") as log:
            proc = subprocess.Popen(
                [str(binary), "_desktop"], stdout=log, stderr=log, env=env
            )
            time.sleep(12)
            alive = proc.poll() is None
            if alive:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log_text = desk_log.read_text(encoding="utf-8", errors="replace")
        check(
            "installed desktop launches offscreen and stays up clean",
            alive and "Traceback" not in log_text,
            "alive after 12s" if alive else f"exited early: {log_text[-200:]}",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # (4) Source-tree launcher road.
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    opened = _run(
        [sys.executable, "-m", "runmal.launcher", "open", "--no-launch"],
        cwd=REPO, env=env,
    )
    check("source launcher open names runmal.desktop",
          opened.returncode == 0 and "runmal.desktop" in opened.stdout)
    control = _run(
        [sys.executable, "-m", "runmal.launcher", "control"],
        cwd=REPO, env=env,
    )
    check("retired control command rejected", control.returncode != 0)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
