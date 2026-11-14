"""R-04 acceptance (window skeleton): QMainWindow structure, menus,
docks, snapshot rendering, first-run banner, clean-quit engine stop.

Skips cleanly when PySide6 is absent (the VM venv has none — the
client/engine tests carry the headless gate there; these run on the
fleet devices' R-01 environments, offscreen).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client.models import (  # noqa: E402
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    EngineSnapshot,
    HealthStatus,
    detect_first_run,
)
from runmal.desktop.engine import EngineHandle, EngineState  # noqa: E402
from runmal.desktop.window import MENU_TITLES, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    handle = EngineHandle()
    win = MainWindow(handle)
    # Shown, not just built: banner/dock visibility assertions read
    # *effective* visibility, which is always False inside a
    # never-shown top-level. (R-05 fix: this test failed identically
    # at base e3d4467 on a real Qt host for exactly that reason; the
    # launch proof always showed the window, the test never did.)
    win.show()
    qapp.processEvents()
    yield win, handle
    win.close()


def test_window_structure_and_menus(window) -> None:
    win, _ = window
    assert win.windowTitle() == "Rúnmál"
    titles = [a.text() for a in win.menuBar().actions()]
    assert titles == MENU_TITLES
    # Central region is the Chat Stage; both docks exist.
    assert win.centralWidget().objectName() == "chatStage"
    assert win.library_dock.objectName() == "libraryDock"
    assert win.session_dock.objectName() == "sessionDock"
    tab_titles = [win.left_tabs.tabText(i) for i in range(win.left_tabs.count())]
    assert tab_titles == ["Chats", "Characters"]
    # Real lifecycle actions exist; placeholders are honest about it.
    assert win.action_start_engine.text() == "Start Engine"
    assert win.action_quit.text() == "Quit"
    assert "R-09" in win.placeholder_actions["Connections…"].statusTip()


def test_initial_chrome_shows_stopped_engine(window) -> None:
    win, _ = window
    assert win.engine_status_label.text() == "Engine: stopped"
    assert win.action_start_engine.isEnabled() is True
    assert win.action_stop_engine.isEnabled() is False
    assert win.streaming_status_label.text() == "Streaming: idle"


def test_apply_snapshot_renders_lists_and_first_run(window) -> None:
    win, _ = window
    profile = BackendProfile.from_dict(
        {"id": "p1", "name": "hearth", "chat_backend": "fake",
         "chat_model": "fake-1"}
    )
    snapshot = EngineSnapshot(
        health=HealthStatus(ok=True, status="ok", version="0.1.0"),
        profiles=[profile],
        chats=[ChatSummary(id="c1", title="Gate chat")],
        characters=[CharacterSummary(id="k1", name="Gate Keeper")],
        first_run=detect_first_run([profile], []),
    )
    win.apply_snapshot(snapshot)
    assert win.chats_list.item(0).text() == "Gate chat"
    assert win.characters_list.item(0).text() == "Gate Keeper"
    assert "hearth" in win.session_backend_label.text()
    assert win.first_run_banner.isVisible() is False

    empty = EngineSnapshot(
        health=HealthStatus(ok=True, status="ok"),
        first_run=detect_first_run([], []),
    )
    win.apply_snapshot(empty)
    assert win.first_run_banner.isVisible() is True
    assert "First run" in win.session_first_run_label.text()
    assert win.backend_status_label.text() == "Backend: none configured"


def test_close_stops_engine(window) -> None:
    win, handle = window
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    win.close()
    assert handle.status().state is EngineState.STOPPED
