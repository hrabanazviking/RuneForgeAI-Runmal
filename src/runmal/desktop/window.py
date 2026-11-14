"""The Rúnmál main window — desktop shell (R-04 skeleton, R-05
wizard, R-06 Chat Stage I).

One ``QMainWindow`` titled "Rúnmál": the plan §2.3 menu bar, a
toolbar, a left Library dock (Chats / Characters), a collapsible
right Session dock, the central Chat Stage, and a status bar
carrying engine + streaming state in words.

R-06 makes the centre real: the stage renders the open chat's
stored history, the composer sends a composed turn through the
client layer (``chat_logic.ChatFlow``: user line persisted, reply
streamed in live, landed only on a clean finish — the bridge's
discipline), and Stop cancels the stream by request id. The Chats
dock opens / creates (with a character picker; the engine seeds
the greeting) / renames / deletes (confirmed) / exports chats.
The Session dock shows the open chat's character, persona,
backend profile, model, and preset from real API data.

Honesty rule (carried from R-04): an action is REAL only where
its machinery exists. Later-slice screens stay placeholder
actions labelled with their slice — per-message actions,
regenerate/continue/impersonate, Author's Note, chat search and
checkpoints/undo are R-07 and are labelled so, never dressed up.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from runmal.desktop.chat_logic import (
    ChatFlow,
    OpenChat,
    SessionView,
    StreamDraft,
    export_filename,
    transcript_html,
)
from runmal.desktop.client import RunmalClient, fetch_snapshot
from runmal.desktop.client.models import (
    ChatSummary,
    EngineSnapshot,
    MessageView,
)
from runmal.desktop.client.session import DesktopSession
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.workers import run_async, run_stream

MENU_TITLES = [
    "File", "Edit", "View", "Chat", "Characters",
    "World", "Tools", "Window", "Help",
]

_CHAT_ID_ROLE = Qt.ItemDataRole.UserRole


class NewChatDialog(QDialog):
    """New Chat (R-06): pick a character (or none) + optional title.

    The engine seeds the picked character's greeting as the new
    chat's first message; "(No character)" is an honest choice —
    the chat is then bound to nobody, as the API allows."""

    def __init__(
        self, characters: list, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Chat")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Talk with:"))
        self.character_combo = QComboBox()
        self.character_combo.addItem("(No character)", None)
        for character in characters:
            self.character_combo.addItem(
                character.name or character.id, character.id
            )
        layout.addWidget(self.character_combo)
        layout.addWidget(QLabel("Title (optional):"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Let Rúnmál name it from the character")
        layout.addWidget(self.title_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def character_id(self) -> str | None:
        return self.character_combo.currentData()

    def title(self) -> str:
        return self.title_edit.text().strip()

    def select_character(self, character_id: str | None) -> None:
        for index in range(self.character_combo.count()):
            if self.character_combo.itemData(index) == character_id:
                self.character_combo.setCurrentIndex(index)
                return


class RenameChatDialog(QDialog):
    """Rename one chat (R-06 chats dock)."""

    def __init__(
        self, current_title: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rename Chat")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Chat title:"))
        self.title_edit = QLineEdit(current_title)
        self.title_edit.selectAll()
        layout.addWidget(self.title_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def title(self) -> str:
        return self.title_edit.text().strip()


class MainWindow(QMainWindow):
    """Rúnmál shell window (engine + client injected)."""

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
        self._flow_instance: ChatFlow | None = None
        self._workers: list = []
        self.placeholder_actions: dict[str, QAction] = {}
        # Auto-wizard (R-05): the real app entry enables this so a
        # first run opens the setup wizard unasked; tests and proof
        # drivers construct the window without it and drive the
        # wizard explicitly.
        self._auto_wizard = auto_wizard
        self._wizard = None
        self._wizard_shown = False
        self.setup_result: dict = {}
        self.setup_chat_id: str | None = None
        # Chat Stage state (R-06).
        self.current_chat_id: str | None = None
        self.current_chat: ChatSummary | None = None
        self.current_messages: list[MessageView] = []
        self.current_session: SessionView | None = None
        self._characters_cache: list = []
        self._profiles_cache: list = []
        self._user_name = ""
        self._streaming = False
        self._draft: StreamDraft | None = None
        self._pending_user_text = ""
        self._active_request_id: str | None = None
        self._new_chat_dialog: NewChatDialog | None = None
        self._rename_dialog: RenameChatDialog | None = None
        self._delete_box: QMessageBox | None = None

        self.setWindowTitle("Rúnmál")
        self.resize(1200, 800)
        self._build_central()
        self._build_left_dock()
        self._build_session_dock()
        self._build_menus_and_toolbar()
        self._build_status_bar()
        self.update_engine_chrome()
        self._update_composer_chrome()

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
            "Open a chat from the Chats dock, or start a new one — "
            "the conversation lives here."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(body)
        self.stage_body = body

        self.message_view = QTextBrowser()
        self.message_view.setObjectName("messageView")
        self.message_view.setOpenExternalLinks(False)
        self.message_view.setHtml(
            "<p><i>No chat open yet — pick one in the Chats dock, "
            "or press New Chat.</i></p>"
        )
        layout.addWidget(self.message_view, 1)

        self.chat_stage_status = QLabel("Streaming: idle")
        self.chat_stage_status.setWordWrap(True)
        layout.addWidget(self.chat_stage_status)

        composer_row = QHBoxLayout()
        self.composer_edit = QPlainTextEdit()
        self.composer_edit.setObjectName("composerEdit")
        self.composer_edit.setPlaceholderText(
            "Write a message… (Enter sends, Shift+Enter adds a line)"
        )
        self.composer_edit.setMaximumHeight(90)
        self.composer_edit.installEventFilter(self)
        composer_row.addWidget(self.composer_edit, 1)
        buttons = QVBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(
            lambda _c=False: self.send_current_message()
        )
        buttons.addWidget(self.send_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(lambda _c=False: self.request_stop())
        buttons.addWidget(self.stop_button)
        buttons.addStretch(1)
        composer_row.addLayout(buttons)
        layout.addLayout(composer_row)
        self.setCentralWidget(stage)

    def _build_left_dock(self) -> None:
        tabs = QTabWidget()

        chats_tab = QWidget()
        chats_layout = QVBoxLayout(chats_tab)
        self.chats_list = QListWidget()
        self.chats_list.itemClicked.connect(
            lambda item: self._chat_item_activated(item)
        )
        self.chats_list.itemDoubleClicked.connect(
            lambda item: self._chat_item_activated(item)
        )
        chats_layout.addWidget(self.chats_list)
        chat_buttons = QHBoxLayout()
        self.new_chat_button = QPushButton("New…")
        self.new_chat_button.clicked.connect(
            lambda _c=False: self.open_new_chat_dialog()
        )
        chat_buttons.addWidget(self.new_chat_button)
        self.rename_chat_button = QPushButton("Rename…")
        self.rename_chat_button.clicked.connect(
            lambda _c=False: self.open_rename_dialog()
        )
        chat_buttons.addWidget(self.rename_chat_button)
        self.delete_chat_button = QPushButton("Delete")
        self.delete_chat_button.clicked.connect(
            lambda _c=False: self.confirm_delete_selected_chat()
        )
        chat_buttons.addWidget(self.delete_chat_button)
        self.export_chat_button = QPushButton("Export…")
        self.export_chat_button.clicked.connect(
            lambda _c=False: self.export_selected_chat()
        )
        chat_buttons.addWidget(self.export_chat_button)
        chats_layout.addLayout(chat_buttons)
        chats_note = QLabel(
            "Per-message actions, search and checkpoints land in R-07."
        )
        chats_note.setWordWrap(True)
        chats_layout.addWidget(chats_note)
        tabs.addTab(chats_tab, "Chats")

        characters_tab = QWidget()
        characters_layout = QVBoxLayout(characters_tab)
        self.characters_list = QListWidget()
        self.characters_list.itemDoubleClicked.connect(
            lambda item: self._character_item_activated(item)
        )
        characters_layout.addWidget(self.characters_list)
        self.new_chat_with_button = QPushButton("New Chat with Character")
        self.new_chat_with_button.clicked.connect(
            lambda _c=False: self._new_chat_with_selected_character()
        )
        characters_layout.addWidget(self.new_chat_with_button)
        characters_note = QLabel(
            "The full character library and editor land in R-08."
        )
        characters_note.setWordWrap(True)
        characters_layout.addWidget(characters_note)
        tabs.addTab(characters_tab, "Characters")

        self.left_tabs = tabs
        self.library_dock = QDockWidget("Library", self)
        self.library_dock.setObjectName("libraryDock")
        self.library_dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.library_dock)

    def _build_session_dock(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.session_chat_label = QLabel("Chat: none open")
        self.session_character_label = QLabel("Character: —")
        self.session_persona_label = QLabel("Persona: —")
        self.session_engine_label = QLabel("Engine: —")
        self.session_backend_label = QLabel("Backend: —")
        self.session_profile_label = QLabel("Profile: —")
        self.session_model_label = QLabel("Model: —")
        self.session_preset_label = QLabel("Preset: —")
        self.session_first_run_label = QLabel("Setup: —")
        self.session_counts_label = QLabel("Chats: — · Characters: —")
        for label in (
            self.session_chat_label,
            self.session_character_label,
            self.session_persona_label,
            self.session_engine_label,
            self.session_backend_label,
            self.session_profile_label,
            self.session_model_label,
            self.session_preset_label,
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
                f"{t} lands in {s} — not built yet in this shell.", 5000
            )
        )
        menu.addAction(action)
        self.placeholder_actions[text] = action
        return action

    def _build_menus_and_toolbar(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("File")
        self.action_new_chat = QAction("New Chat", self)
        self.action_new_chat.triggered.connect(
            lambda _c=False: self.open_new_chat_dialog()
        )
        file_menu.addAction(self.action_new_chat)
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
        self._placeholder(chat_menu, "Regenerate", "R-07")
        self._placeholder(chat_menu, "Continue", "R-07")
        self.action_stop_generating = QAction("Stop Generating", self)
        self.action_stop_generating.triggered.connect(
            lambda _c=False: self.request_stop()
        )
        chat_menu.addAction(self.action_stop_generating)
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
        self._placeholder(window_menu, "Quick Switcher…", "a later slice")

        help_menu = bar.addMenu("Help")
        self.action_about = QAction("About Rúnmál", self)
        self.action_about.triggered.connect(lambda _c=False: self.show_about())
        help_menu.addAction(self.action_about)

        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.addAction(self.action_new_chat)
        toolbar.addAction(self.action_start_engine)
        toolbar.addAction(self.action_stop_engine)
        self.action_refresh = QAction("Refresh Status", self)
        self.action_refresh.triggered.connect(
            lambda _c=False: self.refresh_async()
        )
        toolbar.addAction(self.action_refresh)
        toolbar.addAction(self.action_stop_generating)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        self.engine_status_label = QLabel("Engine: stopped")
        self.backend_status_label = QLabel("Backend: —")
        self.streaming_status_label = QLabel("Streaming: idle")
        status.addPermanentWidget(self.engine_status_label)
        status.addPermanentWidget(self.backend_status_label)
        status.addPermanentWidget(self.streaming_status_label)
        status.showMessage("Rúnmál — Chat Stage (R-06)")

    # ------------------------------------------------------------ client

    def client(self) -> RunmalClient:
        """The window's client (created lazily over the local
        credential road; the credential never leaves the client)."""
        if self._client is None:
            self._client = RunmalClient(
                DesktopSession.from_local_credential(self._engine.base_url)
            )
        return self._client

    def flow(self) -> ChatFlow:
        """The window's Chat Stage flow (over the same client)."""
        if self._flow_instance is None:
            self._flow_instance = ChatFlow(self.client())
        return self._flow_instance

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
        """Render one fetched snapshot into the docks/status bar.

        The chats/characters lists always refresh (keeping the
        open chat selected); the Session dock's backend/model
        lines follow the snapshot only while no chat is open —
        with a chat open they carry that chat's resolved values
        (see :meth:`_show_session_view`)."""
        self._characters_cache = list(snapshot.characters)
        self._profiles_cache = list(snapshot.profiles)
        self.chats_list.clear()
        for chat in snapshot.chats:
            item = QListWidgetItem(chat.title or chat.id)
            item.setData(_CHAT_ID_ROLE, chat.id)
            self.chats_list.addItem(item)
            if chat.id == self.current_chat_id:
                self.chats_list.setCurrentItem(item)
        self.characters_list.clear()
        for character in snapshot.characters:
            item = QListWidgetItem(character.name or character.id)
            item.setData(_CHAT_ID_ROLE, character.id)
            self.characters_list.addItem(item)

        if self.current_chat_id is None:
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

    # ------------------------------------------------------- chat stage

    def _character_name(self, character_id: str | None) -> str:
        if not character_id:
            return ""
        for character in self._characters_cache:
            if character.id == character_id:
                return character.name or ""
        if self.current_session is not None and self.current_chat is not None:
            if self.current_chat.character_id == character_id:
                return self.current_session.character_label
        return ""

    def _stage_header(self, opened: OpenChat) -> tuple[str, str]:
        chat = opened.chat
        name = self._character_name(chat.character_id)
        title = f"Chat with {name}" if name else (chat.title or "Chat")
        count = len(opened.messages)
        body = f"{chat.title or '(untitled chat)'} · {count} message(s)"
        if name:
            body += f" · with {name}"
        return title, body

    def _show_session_view(self, view: SessionView) -> None:
        self.session_chat_label.setText(f"Chat: {view.chat_title}")
        self.session_character_label.setText(f"Character: {view.character_label}")
        self.session_persona_label.setText(f"Persona: {view.persona_label}")
        self.session_profile_label.setText(f"Profile: {view.profile_label}")
        self.session_backend_label.setText(f"Backend: {view.profile_label}")
        self.session_model_label.setText(f"Model: {view.model_label}")
        self.session_preset_label.setText(f"Preset: {view.preset_label}")
        self.backend_status_label.setText(f"Backend: {view.profile_label}")

    def _clear_session_view(self) -> None:
        self.session_chat_label.setText("Chat: none open")
        self.session_character_label.setText("Character: —")
        self.session_persona_label.setText("Persona: —")
        self.session_profile_label.setText("Profile: —")
        self.session_preset_label.setText("Preset: —")
        self.current_session = None

    def _render_transcript(self) -> None:
        messages = list(self.current_messages)
        if self._pending_user_text:
            messages.append(
                MessageView(
                    id="", role="user", content=self._pending_user_text,
                    speaker_name=self._user_name or None,
                )
            )
        character_name = ""
        if self.current_chat is not None:
            character_name = self._character_name(self.current_chat.character_id)
        draft_speaker = character_name or "Assistant"
        self.message_view.setHtml(
            transcript_html(
                messages,
                character_name=character_name,
                user_name=self._user_name,
                draft=self._draft,
                draft_speaker=draft_speaker,
            )
        )
        bar = self.message_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _apply_open_chat(self, opened: OpenChat) -> None:
        self.current_chat = opened.chat
        self.current_chat_id = opened.chat.id
        self.current_messages = list(opened.messages)
        self.current_session = opened.session
        self._draft = None
        self._pending_user_text = ""
        title, body = self._stage_header(opened)
        self.stage_title.setText(title)
        self.stage_body.setText(body)
        if opened.session is not None:
            self._show_session_view(opened.session)
        self._render_transcript()
        for index in range(self.chats_list.count()):
            item = self.chats_list.item(index)
            if item.data(_CHAT_ID_ROLE) == opened.chat.id:
                self.chats_list.setCurrentItem(item)
                break
        self._update_composer_chrome()

    def open_chat_blocking(self, chat_id: str) -> OpenChat:
        """Open one chat in the stage (proof drivers/tests; the GUI
        path is :meth:`open_chat_async`)."""
        opened = self.flow().open_chat(chat_id)
        self._apply_open_chat(opened)
        return opened

    def open_chat_async(self, chat_id: str) -> None:
        flow = self.flow()
        worker = run_async(
            lambda: flow.open_chat(chat_id),
            self._apply_open_chat,
            self._apply_error,
        )
        self._workers.append(worker)

    def _chat_item_activated(self, item: QListWidgetItem) -> None:
        chat_id = item.data(_CHAT_ID_ROLE)
        if chat_id and chat_id != self.current_chat_id:
            if self._streaming:
                self.statusBar().showMessage(
                    "Finish or stop the current reply before switching chats.",
                    5000,
                )
                return
            self.open_chat_async(chat_id)

    def _character_item_activated(self, item: QListWidgetItem) -> None:
        character_id = item.data(_CHAT_ID_ROLE)
        if character_id:
            self.open_new_chat_dialog(character_id=character_id)

    # ------------------------------------------------------- chats dock

    def create_chat_blocking(
        self, *, character_id: str | None = None, title: str = ""
    ) -> OpenChat:
        """Create + open a chat (proof drivers/tests)."""
        opened = self.flow().create_chat(character_id=character_id, title=title)
        self._apply_open_chat(opened)
        self.refresh_blocking()
        return opened

    def open_new_chat_dialog(
        self, *, character_id: str | None = None
    ) -> NewChatDialog:
        """Open (or raise) the New Chat dialog with its character
        picker fed by the roster the window last fetched."""
        if self._new_chat_dialog is not None and self._new_chat_dialog.isVisible():
            self._new_chat_dialog.raise_()
            self._new_chat_dialog.activateWindow()
            return self._new_chat_dialog
        dialog = NewChatDialog(list(self._characters_cache), self)
        if character_id:
            dialog.select_character(character_id)
        dialog.accepted.connect(
            lambda d=dialog: self._new_chat_accepted(d)
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_new_chat_dialog", None)
        )
        self._new_chat_dialog = dialog
        dialog.show()
        return dialog

    def _new_chat_accepted(self, dialog: NewChatDialog) -> None:
        character_id = dialog.character_id()
        title = dialog.title()
        self._new_chat_dialog = None
        flow = self.flow()

        def create() -> OpenChat:
            return flow.create_chat(character_id=character_id, title=title)

        def done(opened: OpenChat) -> None:
            self._apply_open_chat(opened)
            self.statusBar().showMessage(
                f"New chat open: {opened.chat.title or opened.chat.id}", 5000
            )
            self.refresh_async()

        worker = run_async(create, done, self._apply_error)
        self._workers.append(worker)

    def _new_chat_with_selected_character(self) -> None:
        item = self.characters_list.currentItem()
        if item is None:
            self.statusBar().showMessage(
                "Pick a character in the list first.", 5000
            )
            return
        self.open_new_chat_dialog(character_id=item.data(_CHAT_ID_ROLE))

    def selected_chat_id(self) -> str | None:
        """The chats-dock selection, falling back to the open chat."""
        item = self.chats_list.currentItem()
        if item is not None:
            chat_id = item.data(_CHAT_ID_ROLE)
            if chat_id:
                return chat_id
        return self.current_chat_id

    def _chat_title_for(self, chat_id: str) -> str:
        # The dock list is the freshest title the user can see (a
        # rename lands there before the open chat is re-read), so
        # it wins over the open chat's cached row.
        for index in range(self.chats_list.count()):
            item = self.chats_list.item(index)
            if item.data(_CHAT_ID_ROLE) == chat_id:
                return item.text()
        if self.current_chat is not None and self.current_chat.id == chat_id:
            return self.current_chat.title or chat_id
        return chat_id

    def rename_chat_blocking(self, chat_id: str, title: str) -> ChatSummary:
        """Rename one chat and refresh the dock (proof/tests)."""
        renamed = self.flow().rename_chat(chat_id, title)
        self.refresh_blocking()
        if self.current_chat_id == chat_id:
            self.open_chat_blocking(chat_id)
        return renamed

    def open_rename_dialog(
        self, chat_id: str | None = None
    ) -> RenameChatDialog | None:
        target = chat_id or self.selected_chat_id()
        if not target:
            self.statusBar().showMessage("Pick a chat to rename first.", 5000)
            return None
        dialog = RenameChatDialog(self._chat_title_for(target), self)
        dialog.accepted.connect(
            lambda d=dialog, cid=target: self._rename_accepted(cid, d)
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_rename_dialog", None)
        )
        self._rename_dialog = dialog
        dialog.show()
        return dialog

    def _rename_accepted(self, chat_id: str, dialog: RenameChatDialog) -> None:
        title = dialog.title()
        self._rename_dialog = None
        if not title:
            self.statusBar().showMessage("A chat title cannot be empty.", 5000)
            return
        flow = self.flow()

        def rename() -> ChatSummary:
            return flow.rename_chat(chat_id, title)

        def done(renamed: ChatSummary) -> None:
            self.statusBar().showMessage(
                f"Chat renamed to “{renamed.title}”.", 5000
            )
            self.refresh_async()
            if self.current_chat_id == chat_id:
                self.open_chat_async(chat_id)

        worker = run_async(rename, done, self._apply_error)
        self._workers.append(worker)

    def delete_chat_blocking(self, chat_id: str) -> bool:
        """Delete one chat (already confirmed by the caller) and
        refresh; deleting the open chat clears the stage."""
        deleted = self.flow().delete_chat(chat_id)
        if deleted and self.current_chat_id == chat_id:
            self.current_chat = None
            self.current_chat_id = None
            self.current_messages = []
            self._clear_session_view()
            self.stage_title.setText("Chat Stage")
            self.stage_body.setText(
                "That chat was deleted. Open another, or start a new one."
            )
            self.message_view.setHtml(
                "<p><i>No chat open — pick one in the Chats dock, "
                "or press New Chat.</i></p>"
            )
            self._update_composer_chrome()
        self.refresh_blocking()
        return deleted

    def confirm_delete_selected_chat(self) -> QMessageBox | None:
        """Two-step delete (S111 semantics): a confirmation box
        stating the action is irreversible; only its Delete
        button performs it."""
        target = self.selected_chat_id()
        if not target:
            self.statusBar().showMessage("Pick a chat to delete first.", 5000)
            return None
        if self._streaming and target == self.current_chat_id:
            self.statusBar().showMessage(
                "Stop the current reply before deleting its chat.", 5000
            )
            return None
        title = self._chat_title_for(target)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete Chat")
        box.setText(f"Delete “{title}” and its whole history?")
        box.setInformativeText(
            "This is irreversible — the chat and its messages are "
            "removed. Export first if you want a copy."
        )
        delete_button = box.addButton(
            "Delete", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.buttonClicked.connect(
            lambda button, cid=target, db=delete_button: (
                self._delete_confirmed(cid) if button is db else None
            )
        )
        box.destroyed.connect(
            lambda _obj=None: setattr(self, "_delete_box", None)
        )
        self._delete_box = box
        box.show()
        return box

    def _delete_confirmed(self, chat_id: str) -> None:
        self._delete_box = None
        flow = self.flow()

        def delete() -> bool:
            return flow.delete_chat(chat_id)

        def done(deleted: bool) -> None:
            if deleted:
                self.statusBar().showMessage("Chat deleted.", 5000)
                if self.current_chat_id == chat_id:
                    self.current_chat = None
                    self.current_chat_id = None
                    self.current_messages = []
                    self._clear_session_view()
                    self.stage_title.setText("Chat Stage")
                    self.stage_body.setText(
                        "That chat was deleted. Open another, or start a new one."
                    )
                    self.message_view.setHtml(
                        "<p><i>No chat open — pick one in the Chats dock, "
                        "or press New Chat.</i></p>"
                    )
                    self._update_composer_chrome()
            self.refresh_async()

        worker = run_async(delete, done, self._apply_error)
        self._workers.append(worker)

    def export_chat_to_path(self, chat_id: str, path: str) -> str:
        """Write one chat's portable export JSON to ``path``
        (the road the Export button's file dialog lands on)."""
        text = self.flow().export_text(chat_id)
        Path(path).write_text(text, encoding="utf-8")
        return path

    def export_selected_chat(self) -> None:
        target = self.selected_chat_id()
        if not target:
            self.statusBar().showMessage("Pick a chat to export first.", 5000)
            return
        chat = ChatSummary(id=target, title=self._chat_title_for(target))
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export Chat", export_filename(chat),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        flow = self.flow()
        worker = run_async(
            lambda: flow.export_text(target),
            lambda text: self._export_write(path, text),
            self._apply_error,
        )
        self._workers.append(worker)

    def _export_write(self, path: str, text: str) -> None:
        Path(path).write_text(text, encoding="utf-8")
        self.statusBar().showMessage(f"Chat exported to {path}.", 8000)

    # ------------------------------------------------------------ sending

    def _update_composer_chrome(self) -> None:
        has_chat = self.current_chat_id is not None
        self.send_button.setEnabled(has_chat and not self._streaming)
        self.composer_edit.setEnabled(has_chat and not self._streaming)
        self.stop_button.setEnabled(self._streaming)
        self.action_stop_generating.setEnabled(self._streaming)
        if not has_chat:
            self.chat_stage_status.setText(
                "No chat open — the composer wakes when a chat is open."
            )
        elif not self._streaming:
            self.chat_stage_status.setText("Streaming: idle")

    def _set_streaming_words(self, words: str) -> None:
        self.streaming_status_label.setText(f"Streaming: {words}")
        self.chat_stage_status.setText(f"Streaming: {words}")

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        """Enter sends from the composer; Shift+Enter adds a line."""
        if obj is self.composer_edit and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.send_current_message()
                    return True
        return super().eventFilter(obj, event)

    def send_current_message(self) -> None:
        """Send the composer's text as one composed turn (R-06)."""
        if self._streaming:
            return
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat before sending.", 5000)
            return
        text = self.composer_edit.toPlainText().strip()
        if not text:
            self.statusBar().showMessage("Write a message first.", 5000)
            return
        chat_id = self.current_chat_id
        self.composer_edit.clear()
        self._pending_user_text = text
        self._draft = StreamDraft()
        self._streaming = True
        self._active_request_id = self.client().new_request_id()
        self._set_streaming_words("starting…")
        self._update_composer_chrome()
        self.stop_button.setEnabled(True)
        self.action_stop_generating.setEnabled(True)
        self._render_transcript()
        flow = self.flow()
        request_id = self._active_request_id

        def run(emit) -> object:
            return flow.send_turn(
                chat_id, text, on_event=emit, request_id=request_id
            )

        worker = run_stream(
            run, self._on_stream_event, self._on_turn_done, self._on_turn_failed
        )
        self._workers.append(worker)

    def _on_stream_event(self, event) -> None:
        if self._draft is None:
            self._draft = StreamDraft()
        self._draft.apply(event)
        if event.kind == "started":
            who = event.backend_key or "the backend"
            self._set_streaming_words(f"streaming — {who} is answering…")
        elif event.kind == "token":
            self._set_streaming_words("streaming — reply arriving…")
            self._render_transcript()
        elif event.kind == "error":
            self._set_streaming_words(f"failed — {event.message}")

    def _on_turn_done(self, result) -> None:
        chat_id = self.current_chat_id
        self._streaming = False
        self._active_request_id = None
        words = result.status_words
        draft = result.draft
        self._pending_user_text = ""
        self._draft = None
        self._update_composer_chrome()
        self._set_streaming_words(
            "stopped — partial reply not saved"
            if draft.stopped
            else ("failed" if draft.error else "idle")
        )
        self.chat_stage_status.setText(words)
        self.statusBar().showMessage(words, 10000)
        if chat_id is not None:
            # Reload the authoritative history: the saved user line
            # (always) and the reply (only when it landed cleanly).
            try:
                self.open_chat_blocking(chat_id)
            except Exception as exc:  # the words above already landed
                self._apply_error(str(exc))
            self.chat_stage_status.setText(words)
            if draft.stopped and draft.text:
                # Keep the unsaved partial visible, honestly marked,
                # below the reloaded history.
                self._draft = draft
                self._render_transcript()
                self.chat_stage_status.setText(words)
            self.refresh_async()

    def _on_turn_failed(self, message: str) -> None:
        chat_id = self.current_chat_id
        self._streaming = False
        self._active_request_id = None
        self._pending_user_text = ""
        self._draft = None
        self._update_composer_chrome()
        self._set_streaming_words("failed")
        words = f"That send failed: {message} — reload the chat to see what was saved."
        self.chat_stage_status.setText(words)
        self.statusBar().showMessage(words, 10000)
        if chat_id is not None:
            try:
                self.open_chat_blocking(chat_id)
            except Exception:
                pass
            self.chat_stage_status.setText(words)

    def request_stop(self) -> None:
        """Stop control (R-06): cancel the in-flight stream by its
        request id, through the engine's cancel road (INV-003)."""
        if not self._streaming:
            self.statusBar().showMessage("Nothing is streaming right now.", 4000)
            return
        self._set_streaming_words("stopping — asking the engine to cancel…")
        flow = self.flow()
        worker = run_async(
            flow.cancel_active,
            lambda cancelled: self.statusBar().showMessage(
                "Stop sent — the engine is cancelling the reply."
                if cancelled
                else "Stop sent — the stream may already have finished.",
                5000,
            ),
            self._apply_error,
        )
        self._workers.append(worker)

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
        window so the greeted chat it opened is what the user sees —
        opened in the real Chat Stage (R-06), greeting rendered."""
        self.setup_result = dict(result)
        self.setup_chat_id = result.get("chat_id") or None
        # The finished wizard is spent (its flow state is the old
        # run); the next open builds a fresh one. The hidden wizard
        # stays parented to this window and is not deleted while its
        # workers may still be landing — dropping only our reference.
        self._wizard = None
        name = result.get("character_name") or "your character"
        greeting = result.get("greeting") or ""
        if self.setup_chat_id:
            try:
                self.open_chat_blocking(self.setup_chat_id)
            except Exception:
                pass  # the title/greeting landing below still holds
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
                "first-run wizard, R-06 Chat Stage) over the "
                "in-process engine.\n"
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
