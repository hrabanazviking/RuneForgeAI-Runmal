"""Desktop shell entry point (R-04).

``python -m runmal.desktop`` starts the in-process engine and opens
the Rúnmál main window; closing the window (or File → Quit) stops
the engine — the Qt app *is* the control centre for the desktop road
(plan §2.4), replacing the Tk Control Center's job.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from runmal.desktop.engine import EngineHandle
from runmal.desktop.window import MainWindow


def create_window(engine: EngineHandle | None = None) -> MainWindow:
    """Build the main window over ``engine`` (a fresh handle if none).

    The app entry is the auto-wizard road (R-05): when the first
    refresh finds a first run, the setup wizard opens unasked."""
    return MainWindow(engine or EngineHandle(), auto_wizard=True)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Rúnmál")
    window = create_window()
    window.show()
    window.start_engine_async()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
