"""The Rúnmál main window — desktop shell skeleton (R-04).

One ``QMainWindow`` titled "Rúnmál": the plan §2.3 menu bar, a
toolbar, a left dock (Chats / Characters tabs), a collapsible right
Session dock, a central Chat Stage placeholder region, and a status
bar carrying engine state in words.

Honesty rule for this skeleton slice: an action is REAL only where
its machinery exists in R-04 (engine lifecycle, dock toggles, status
refresh, first-run status, About, Quit). Everything whose screen
lands in a later slice is a placeholder action that says so in the
status bar when triggered — never a dead button dressed as a feature.

R-05 adds: File → First-Run Setup… opens the real setup wizard
(``runmal.desktop.wizard``), the first-run banner points at it, and
when the app entry enables ``auto_wizard`` a detected first run
opens the wizard unasked. Wizard completion refreshes the window
into the greeted chat the wizard opened.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QLabel,
    QListWidget,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runmal.desktop.client import RunmalClient, fetch_snapshot
from runmal.desktop.client.models import EngineSnapshot
from runmal.desktop.client.session import DesktopSession
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.workers import run_async

MENU_TITLES = [
    "File", "Edit", "View", "Chat", "Characters",
    "World", "Tools", "Window", "Help",
]


class MainWindow(QMainWindow):
    """Rúnmál shell skeleton window (engine + client injected)."""

    def __init__(
        self,
        engine: EngineHandle,
        client: RunmalClient | None = None,
        *,
        auto_wizard: bool = False,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._client = client
        self._workers: list = []
        self.placeholder_actions: dict[str, QAction] = {}
        # Auto-wizard (R-05): the real app entry enables this so a
        # first run opens the setup wizard unasked; tests and proof
        # drivers construct the window without it and drive the
        # wizard explicitly (the F15/purpleraider app entry is the
        # auto road — see desktop/app.py).
        self._auto_wizard = auto_wizard
        self._wizard = None
        self._wizard_shown = False
        self.setup_result: dict = {}
        self.setup_chat_id: str | None = None

        self.setWindowTitle("Rúnmál")
        self.resize(1200, 800)
        self._build_central()
        self._build_left_dock()
        self._build_session_dock()
        self._build_menus_and_toolbar()
        self._build_status_bar()
        self.update_engine_chrome()

    # ------------------------------------------------------------ build

    def _build_central(self) -> None:
        stage = QWidget()
        stage.setObjectName("chatStage")
        layout = QVBoxLayout(stage)
        title = QLabel("Chat Stage")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        self.stage_title = title
        self.first_run_banner = QLabel("")
        self.first_run_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.first_run_banner.setWordWrap(True)
        self.first_run_banner.setVisible(False)
        layout.addWidget(self.first_run_banner)
        body = QLabel(
            "The conversation lives here. Streaming chat arrives in "
            "R-06; this skeleton proves the window, the engine "
            "lifecycle, and the client boundary it will stand on."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(body)
        self.stage_body = body
        layout.addStretch(1)
        self.setCentralWidget(stage)

    def _build_left_dock(self) -> None:
        tabs = QTabWidget()
        self.chats_list = QListWidget()
        self.characters_list = QListWidget()
        tabs.addTab(self.chats_list, "Chats")
        tabs.addTab(self.characters_list, "Characters")
        self.left_tabs = tabs
        self.library_dock = QDockWidget("Library", self)
        self.library_dock.setObjectName("libraryDock")
        self.library_dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.library_dock)

    def _build_session_dock(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.session_engine_label = QLabel("Engine: —")
        self.session_backend_label = QLabel("Backend: —")
        self.session_model_label = QLabel("Model: —")
        self.session_first_run_label = QLabel("Setup: —")
        self.session_counts_label = QLabel("Chats: — · Characters: —")
        for label in (
            self.session_engine_label,
            self.session_backend_label,
            self.session_model_label,
            self.session_first_run_label,
            self.session_counts_label,
        ):
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)
        self.session_dock = QDockWidget("Session", self)
        self.session_dock.setObjectName("sessionDock")
        self.session_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.session_dock)

    def _placeholder(self, menu, text: str, slice_label: str) -> QAction:
        action = QAction(text, self)
        action.setStatusTip(f"{text} — lands in {slice_label}")
        action.triggered.connect(
            lambda _checked=False, t=text, s=slice_label: self.statusBar().showMessage(
                f"{t} lands in {s} — not part of the R-04 skeleton.", 5000
            )
        )
        menu.addAction(action)
        self.placeholder_actions[text] = action
        return action

    def _build_menus_and_toolbar(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("File")
        self._placeholder(file_menu, "New Chat", "R-06")
        file_menu.addSeparator()
        self.action_start_engine = QAction("Start Engine", self)
        self.action_start_engine.triggered.connect(
            lambda _c=False: self.start_engine_async()
        )
        file_menu.addAction(self.action_start_engine)
        self.action_stop_engine = QAction("Stop Engine", self)
        self.action_stop_engine.triggered.connect(
            lambda _c=False: self.stop_engine_async()
        )
        file_menu.addAction(self.action_stop_engine)
        self.action_restart_engine = QAction("Restart Engine", self)
        self.action_restart_engine.triggered.connect(
            lambda _c=False: self.restart_engine_async()
        )
        file_menu.addAction(self.action_restart_engine)
        file_menu.addSeparator()
        self.action_first_run = QAction("First-Run Setup…", self)
        self.action_first_run.triggered.connect(
            lambda _c=False: self.show_first_run_status()
        )
        file_menu.addAction(self.action_first_run)
        self._placeholder(file_menu, "Import / Export…", "R-14")
        self._placeholder(file_menu, "Backups…", "R-14")
        file_menu.addSeparator()
        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(lambda _c=False: self.close())
        file_menu.addAction(self.action_quit)

        edit_menu = bar.addMenu("Edit")
        self._placeholder(edit_menu, "Undo", "R-07")
        self._placeholder(edit_menu, "Find in Chat…", "R-07")

        view_menu = bar.addMenu("View")
        view_menu.addAction(self.library_dock.toggleViewAction())
        view_menu.addAction(self.session_dock.toggleViewAction())
        view_menu.addSeparator()
        self._placeholder(view_menu, "Theme…", "R-15")
        self._placeholder(view_menu, "Text Size…", "R-15")
        self._placeholder(view_menu, "Ornament Density…", "R-15")

        chat_menu = bar.addMenu("Chat")
        self._placeholder(chat_menu, "Regenerate", "R-06")
        self._placeholder(chat_menu, "Continue", "R-07")
        self._placeholder(chat_menu, "Stop Generating", "R-06")
        self._placeholder(chat_menu, "Prompt Inspector", "R-12")

        characters_menu = bar.addMenu("Characters")
        self._placeholder(characters_menu, "New Character…", "R-08")
        self._placeholder(characters_menu, "Character Editor…", "R-08")

        world_menu = bar.addMenu("World")
        self._placeholder(world_menu, "Lorebooks…", "R-10")
        self._placeholder(world_menu, "Scenarios…", "R-12")
        self._placeholder(world_menu, "Memory…", "R-12")

        tools_menu = bar.addMenu("Tools")
        self._placeholder(tools_menu, "Connections…", "R-09")
        self._placeholder(tools_menu, "Presets…", "R-09")
        self._placeholder(tools_menu, "Plugins…", "R-14")

        window_menu = bar.addMenu("Window")
        self._placeholder(window_menu, "Quick Switcher…", "R-06")

        help_menu = bar.addMenu("Help")
        self.action_about = QAction("About Rúnmál", self)
        self.action_about.triggered.connect(lambda _c=False: self.show_about())
        help_menu.addAction(self.action_about)

        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.addAction(self.action_start_engine)
        toolbar.addAction(self.action_stop_engine)
        self.action_refresh = QAction("Refresh Status", self)
        self.action_refresh.triggered.connect(
            lambda _c=False: self.refresh_async()
        )
        toolbar.addAction(self.action_refresh)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        self.engine_status_label = QLabel("Engine: stopped")
        self.backend_status_label = QLabel("Backend: —")
        self.streaming_status_label = QLabel("Streaming: idle")
        status.addPermanentWidget(self.engine_status_label)
        status.addPermanentWidget(self.backend_status_label)
        status.addPermanentWidget(self.streaming_status_label)
        status.showMessage("Rúnmál shell skeleton (R-04)")

    # ------------------------------------------------------------ client

    def client(self) -> RunmalClient:
        """The window's client (created lazily over the local
        credential road; the credential never leaves the client)."""
        if self._client is None:
            self._client = RunmalClient(
                DesktopSession.from_local_credential(self._engine.base_url)
            )
        return self._client

    # ------------------------------------------------------- engine chrome

    def update_engine_chrome(self) -> EngineSnapshot | None:
        status = self._engine.status()
        self.engine_status_label.setText(status.label)
        self.session_engine_label.setText(status.label)
        running = status.state in (EngineState.RUNNING, EngineState.STARTING)
        self.action_start_engine.setEnabled(not running)
        self.action_stop_engine.setEnabled(running)
        self.action_restart_engine.setEnabled(True)
        return None

    # ----------------------------------------------------- snapshot apply

    def apply_snapshot(self, snapshot: EngineSnapshot) -> None:
        """Render one fetched snapshot into the docks/status bar."""
        self.chats_list.clear()
        for chat in snapshot.chats:
            self.chats_list.addItem(chat.title or chat.id)
        self.characters_list.clear()
        for character in snapshot.characters:
            self.characters_list.addItem(character.name or character.id)

        if snapshot.profiles:
            first = snapshot.profiles[0]
            self.session_backend_label.setText(f"Backend: {first.label}")
            self.session_model_label.setText(
                f"Model: {first.chat_model or '—'}"
            )
            self.backend_status_label.setText(f"Backend: {first.label}")
        else:
            self.session_backend_label.setText("Backend: none configured")
            self.session_model_label.setText("Model: —")
            self.backend_status_label.setText("Backend: none configured")

        self.session_counts_label.setText(
            f"Chats: {len(snapshot.chats)} · Characters: {len(snapshot.characters)}"
        )
        self.session_first_run_label.setText(
            f"Setup: {snapshot.first_run.label}"
        )
        if snapshot.first_run.is_first_run:
            self.first_run_banner.setText(
                "First run: no backend profile and no character yet. "
                "File → First-Run Setup… opens the setup wizard: "
                "connect a mind, meet your first character."
            )
            self.first_run_banner.setVisible(True)
            if self._auto_wizard and not self._wizard_shown:
                self._wizard_shown = True
                QTimer.singleShot(0, self.open_setup_wizard)
        else:
            self.first_run_banner.setVisible(False)
        self.update_engine_chrome()

    def _apply_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Status refresh failed: {message}", 8000)
        self.update_engine_chrome()

    # ---------------------------------------------------------- refresh

    def refresh_blocking(self) -> EngineSnapshot:
        """Synchronous refresh (proof drivers/tests; the GUI paths
        use :meth:`refresh_async` so the window never freezes)."""
        snapshot = fetch_snapshot(self.client())
        self.apply_snapshot(snapshot)
        return snapshot

    def refresh_async(self) -> None:
        client = self.client()
        worker = run_async(
            lambda: fetch_snapshot(client),
            self.apply_snapshot,
            self._apply_error,
        )
        self._workers.append(worker)

    # --------------------------------------------------- engine lifecycle

    def start_engine_blocking(self) -> EngineSnapshot | None:
        """Start the engine and refresh (proof drivers/tests)."""
        status = self._engine.start()
        self.update_engine_chrome()
        if status.state is EngineState.RUNNING:
            return self.refresh_blocking()
        return None

    def stop_engine_blocking(self) -> None:
        self._engine.stop()
        self.update_engine_chrome()
        self.engine_status_label.setText("Engine: stopped")
        self.session_engine_label.setText("Engine: stopped")

    def start_engine_async(self) -> None:
        worker = run_async(
            self._engine.start,
            lambda _status: self.refresh_async()
            if self._engine.is_running
            else self.update_engine_chrome(),
            self._apply_error,
        )
        self._workers.append(worker)

    def stop_engine_async(self) -> None:
        worker = run_async(
            self._engine.stop,
            lambda _status: self.stop_engine_blocking_chrome(),
            self._apply_error,
        )
        self._workers.append(worker)

    def restart_engine_async(self) -> None:
        worker = run_async(
            self._engine.restart,
            lambda _status: self.refresh_async()
            if self._engine.is_running
            else self.update_engine_chrome(),
            self._apply_error,
        )
        self._workers.append(worker)

    def stop_engine_blocking_chrome(self) -> None:
        self.update_engine_chrome()
        self.engine_status_label.setText(self._engine.status().label)
        self.session_engine_label.setText(self._engine.status().label)

    # ------------------------------------------------------------ dialogs

    def show_first_run_status(self) -> None:
        """File → First-Run Setup… (R-05): re-check first-run state,
        then open the setup wizard either way — it is also how a
        configured install adds another mind or character."""
        if not self._engine.is_running:
            self.statusBar().showMessage(
                "First-run check needs the engine — start it first.", 5000
            )
            return
        try:
            snapshot = self.refresh_blocking()
        except Exception as exc:
            self._apply_error(str(exc))
            return
        if snapshot.first_run.is_first_run:
            self.statusBar().showMessage(
                "First run detected: no backend profile, no character. "
                "Opening the setup wizard.",
                8000,
            )
        else:
            self.statusBar().showMessage(
                snapshot.first_run.label
                + " Opening the setup wizard.",
                8000,
            )
        self.open_setup_wizard()

    def open_setup_wizard(self):
        """Open (or raise) the R-05 First-Run Setup wizard.

        Returns the wizard. Completion lands in
        :meth:`_on_setup_completed`, which refreshes the window into
        the greeted chat the wizard opened."""
        from runmal.desktop.wizard import SetupWizard

        if self._wizard is not None and self._wizard.isVisible():
            self._wizard.raise_()
            self._wizard.activateWindow()
            return self._wizard
        wizard = SetupWizard(self.client(), self)
        wizard.setup_completed.connect(self._on_setup_completed)
        wizard.destroyed.connect(lambda _obj=None: setattr(self, "_wizard", None))
        self._wizard = wizard
        self._wizard_shown = True
        wizard.show()
        return wizard

    def _on_setup_completed(self, result: dict) -> None:
        """The wizard finished: remember the landing and refresh the
        window so the greeted chat it opened is what the user sees."""
        self.setup_result = dict(result)
        self.setup_chat_id = result.get("chat_id") or None
        # The finished wizard is spent (its flow state is the old
        # run); the next open builds a fresh one. The hidden wizard
        # stays parented to this window and is not deleted while its
        # workers may still be landing — dropping only our reference.
        self._wizard = None
        name = result.get("character_name") or "your character"
        greeting = result.get("greeting") or ""
        self.stage_title.setText(f"Chat with {name}")
        if greeting:
            self.stage_body.setText(f"“{greeting}”")
        self.first_run_banner.setVisible(False)
        self.statusBar().showMessage(
            f"Setup complete — your first chat with {name} is open.",
            10000,
        )
        if self._engine.is_running:
            self.refresh_async()

    def show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About Rúnmál")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Rúnmál — sovereign AI chat app.\n"
                "Native windowed shell (R-04 skeleton, R-05 "
                "first-run wizard) over the in-process engine.\n"
                "Toolkit: PySide6 6.8.0.2 (ADR-0010)."
            )
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        self._about_dialog = dialog

    # -------------------------------------------------------------- close

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Clean quit stops the in-process engine."""
        try:
            self._engine.stop()
        finally:
            super().closeEvent(event)
