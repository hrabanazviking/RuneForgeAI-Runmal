"""R-17 packaging gates (Qt-free, text-level).

Since R-16 the frozen entry's `open` road launches the Qt desktop
shell, so every platform builder must (a) install the `desktop`
extra and (b) collect PySide6 into the bundle — a builder missing
either ships a frozen app whose only front end cannot start. The
Linux builder additionally smoke-tests the desktop entry offscreen.
macOS stays explicitly UNPROVEN (plan §2.5): its builder must carry
that word, never a silent implication that it works.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_linux_builder_installs_desktop_extra_and_collects_pyside6() -> None:
    script = _read("scripts/build-linux-local.sh")
    assert '".[desktop]"' in script
    assert "--collect-all PySide6" in script


def test_linux_builder_smoke_tests_the_desktop_entry() -> None:
    script = _read("scripts/build-linux-local.sh")
    assert "QT_QPA_PLATFORM=offscreen" in script
    assert '"$RUNMAL_BIN" _desktop' in script


def test_windows_builder_installs_desktop_extra_and_collects_pyside6() -> None:
    script = _read("scripts/build-windows-local.ps1")
    assert '".[desktop]"' in script
    assert "--collect-all PySide6" in script


def test_macos_builder_refreshed_and_still_marked_unproven() -> None:
    script = _read("scripts/build-macos-local.sh")
    assert '".[desktop]"' in script
    assert "--collect-all PySide6" in script
    assert "UNPROVEN" in script


def test_linux_desktop_file_opens_the_desktop_app_only() -> None:
    entry = _read("packaging/linux/runmal.desktop")
    assert "Exec=/opt/runmal/runmal open" in entry
    # The Tk Control Center is gone (R-16); no second action remains.
    assert "ControlCenter" not in entry


def test_installation_doc_describes_the_desktop_app() -> None:
    doc = _read("docs/DESKTOP_INSTALLATION.md")
    assert "desktop app" in doc
    # Stale web-shell instructions must not survive the R-17 refresh.
    assert "opens the browser UI" not in doc
    assert "browser-bootstrap nonce" not in doc


def test_frozen_entry_dispatches_to_the_desktop_shell() -> None:
    launcher_main = _read("src/runmal/launcher/__main__.py")
    assert "from runmal.desktop.app import main as desktop_main" in launcher_main
    core = _read("src/runmal/launcher/core.py")
    assert "runmal.desktop" in core
