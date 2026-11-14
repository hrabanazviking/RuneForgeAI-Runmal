"""The Rúnmál main window — desktop shell (R-04 skeleton, R-05
wizard, R-06 Chat Stage I, R-07 Chat Stage II).

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

R-07 completes the stage: a message list under the transcript
carries the per-message actions (edit, delete, swipe ◀ ▶ with a
list/select/delete dialog, branch, pin/unpin, copy), the chat
actions Regenerate / Continue / Impersonate, an Author's Note
editor, chat search, and checkpoints + undo surfacing — every
one over the engine's existing chats roads through the same
client layer and ChatFlow, off the GUI thread.

Honesty rule (carried from R-04): an action is REAL only where
its machinery exists. Later-slice screens stay placeholder
actions labelled with their slice, never dressed up.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from runmal.desktop.chat_logic import (
    ChatFlow,
    ImpersonateDraft,
    OpenChat,
    SessionView,
    StreamDraft,
    export_filename,
    message_list_label,
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


class EditMessageDialog(QDialog):
    """Edit one message's text (R-07)."""

    def __init__(
        self, current_text: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Message")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Message text:"))
        self.text_edit = QPlainTextEdit(current_text)
        layout.addWidget(self.text_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.text_edit.toPlainText()


class SwipeListDialog(QDialog):
    """One message's swipe deck (R-07): list every alternate,
    select one as active, or delete one. The buttons act through
    callbacks the window supplies (they run the real roads and
    then refresh this list from the returned message)."""

    def __init__(
        self,
        message: MessageView,
        *,
        on_select,
        on_delete,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Swipes")
        self._message = message
        self._on_select = on_select
        self._on_delete = on_delete
        layout = QVBoxLayout(self)
        self.deck_label = QLabel("")
        layout.addWidget(self.deck_label)
        self.swipe_list = QListWidget()
        layout.addWidget(self.swipe_list)
        row = QHBoxLayout()
        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(
            lambda _c=False: self._act(self._on_select)
        )
        row.addWidget(self.select_button)
        self.delete_button = QPushButton("Delete Swipe")
        self.delete_button.clicked.connect(
            lambda _c=False: self._act(self._on_delete)
        )
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.refresh(message)

    def refresh(self, message: MessageView) -> None:
        self._message = message
        deck = list(message.swipes) or [message.content]
        self.deck_label.setText(
            f"{len(deck)} alternate(s) — active is "
            f"{message.swipe_id + 1} of {len(deck)}."
        )
        self.swipe_list.clear()
        for index, text in enumerate(deck):
            excerpt = " ".join(text.split())
            if len(excerpt) > 70:
                excerpt = excerpt[:67] + "…"
            item = QListWidgetItem(f"{index + 1}. {excerpt}")
            item.setData(_CHAT_ID_ROLE, index)
            self.swipe_list.addItem(item)
            if index == message.swipe_id:
                self.swipe_list.setCurrentItem(item)

    def selected_index(self) -> int | None:
        item = self.swipe_list.currentItem()
        if item is None:
            return None
        index = item.data(_CHAT_ID_ROLE)
        return index if isinstance(index, int) else None

    def _act(self, callback) -> None:
        index = self.selected_index()
        if index is None:
            return
        # The callback runs the road OFF the GUI thread and calls
        # back with the updated message when it lands.
        callback(self._message.id, index, self.refresh)


class AuthorsNoteDialog(QDialog):
    """The chat's Author's Note editor (R-07, P-056 shape)."""

    def __init__(
        self, note, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Author's Note")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Note text (steers every reply):"))
        self.text_edit = QPlainTextEdit(note.text)
        layout.addWidget(self.text_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("Depth:"))
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(0, 100)
        self.depth_spin.setValue(note.depth)
        row.addWidget(self.depth_spin)
        row.addWidget(QLabel("Frequency:"))
        self.frequency_spin = QSpinBox()
        self.frequency_spin.setRange(1, 100)
        self.frequency_spin.setValue(note.frequency)
        row.addWidget(self.frequency_spin)
        row.addWidget(QLabel("Role:"))
        self.role_combo = QComboBox()
        self.role_combo.addItems(["system", "user", "assistant"])
        self.role_combo.setCurrentText(note.role or "system")
        row.addWidget(self.role_combo)
        layout.addLayout(row)
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(note.enabled)
        layout.addWidget(self.enabled_check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "text": self.text_edit.toPlainText(),
            "depth": self.depth_spin.value(),
            "frequency": self.frequency_spin.value(),
            "enabled": self.enabled_check.isChecked(),
            "role": self.role_combo.currentText(),
        }


class ImpersonateDialog(QDialog):
    """An impersonate draft (R-07): the model's suggestion for
    YOUR next line, editable. Accept lands the final text as a
    real user message; Discard stores nothing."""

    def __init__(
        self, draft: ImpersonateDraft, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impersonate — Draft Your Next Line")
        self.draft = draft
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("A draft in your voice — edit it, accept it, or discard it:")
        )
        self.text_edit = QPlainTextEdit(draft.content)
        layout.addWidget(self.text_edit)
        row = QHBoxLayout()
        self.accept_button = QPushButton("Accept as My Message")
        self.accept_button.clicked.connect(self.accept)
        row.addWidget(self.accept_button)
        self.discard_button = QPushButton("Discard Draft")
        self.discard_button.clicked.connect(self.reject)
        row.addWidget(self.discard_button)
        layout.addLayout(row)

    def text(self) -> str:
        return self.text_edit.toPlainText()


class ChatSearchDialog(QDialog):
    """Chat search (R-07, P-072): query across chats (or only the
    open one), results as chat + snippet rows; opening a result
    goes through the window callback."""

    def __init__(
        self,
        *,
        on_search,
        on_open,
        current_chat_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Search Chats")
        self._on_search = on_search
        self._on_open = on_open
        self._current_chat_id = current_chat_id
        self.hits: list = []
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Words to find…")
        self.query_edit.returnPressed.connect(
            lambda: self.run_search()
        )
        row.addWidget(self.query_edit, 1)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(lambda _c=False: self.run_search())
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.scope_check = QCheckBox("Only this chat")
        self.scope_check.setEnabled(current_chat_id is not None)
        layout.addWidget(self.scope_check)
        self.results_label = QLabel("No search yet.")
        self.results_label.setWordWrap(True)
        layout.addWidget(self.results_label)
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(
            lambda item: self._open_item(item)
        )
        layout.addWidget(self.results_list)
        open_row = QHBoxLayout()
        self.open_button = QPushButton("Open Chat")
        self.open_button.clicked.connect(
            lambda _c=False: self._open_current()
        )
        open_row.addWidget(self.open_button)
        layout.addLayout(open_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def run_search(self) -> None:
        query = self.query_edit.text().strip()
        if not query:
            self.results_label.setText("Write something to search for first.")
            return
        scope = (
            self._current_chat_id
            if (self.scope_check.isChecked() and self._current_chat_id)
            else None
        )
        self.results_label.setText("Searching…")
        # The callback runs the search OFF the GUI thread and
        # calls back into apply_outcome() when it lands.
        self._on_search(query, scope, self.apply_outcome)

    def apply_outcome(self, outcome) -> None:
        if outcome is None:
            self.results_label.setText("That search failed — see the status bar.")
            return
        self.hits = list(outcome.hits)
        self.results_label.setText(outcome.status_words)
        self.results_list.clear()
        for hit in self.hits:
            excerpt = " ".join(hit.snippet.split())
            if len(excerpt) > 80:
                excerpt = excerpt[:77] + "…"
            item = QListWidgetItem(
                f"{hit.chat_title or hit.chat_id} — {excerpt}"
            )
            item.setData(_CHAT_ID_ROLE, hit.chat_id)
            self.results_list.addItem(item)

    def _open_current(self) -> None:
        item = self.results_list.currentItem()
        if item is not None:
            self._open_item(item)

    def _open_item(self, item: QListWidgetItem) -> None:
        chat_id = item.data(_CHAT_ID_ROLE)
        if chat_id:
            self._on_open(chat_id)


class CheckpointsDialog(QDialog):
    """Checkpoints + undo surfacing (R-07): list the open chat's
    checkpoints (create / restore-as-new-chat / delete) and its
    undo journal (top first), with an Undo Last button. All roads
    run through the window-supplied callbacks."""

    def __init__(
        self,
        *,
        checkpoints: list,
        undo_entries: list,
        on_create,
        on_restore,
        on_delete,
        on_undo,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Checkpoints & Undo")
        self._on_create = on_create
        self._on_restore = on_restore
        self._on_delete = on_delete
        self._on_undo = on_undo
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Checkpoints (snapshots of this chat):"))
        self.checkpoint_list = QListWidget()
        layout.addWidget(self.checkpoint_list)
        row = QHBoxLayout()
        self.create_button = QPushButton("Create Checkpoint")
        self.create_button.clicked.connect(lambda _c=False: self._create())
        row.addWidget(self.create_button)
        self.restore_button = QPushButton("Restore as New Chat")
        self.restore_button.clicked.connect(lambda _c=False: self._restore())
        row.addWidget(self.restore_button)
        self.delete_button = QPushButton("Delete Checkpoint")
        self.delete_button.clicked.connect(lambda _c=False: self._delete())
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        layout.addWidget(QLabel("Undo journal (newest first):"))
        self.undo_list = QListWidget()
        layout.addWidget(self.undo_list)
        undo_row = QHBoxLayout()
        self.undo_button = QPushButton("Undo Last Action")
        self.undo_button.clicked.connect(lambda _c=False: self._undo())
        undo_row.addWidget(self.undo_button)
        layout.addLayout(undo_row)
        self.state_label = QLabel("")
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.refresh(checkpoints, undo_entries)

    def refresh(self, checkpoints: list, undo_entries: list) -> None:
        self.checkpoint_list.clear()
        for checkpoint in checkpoints:
            item = QListWidgetItem(
                f"{checkpoint.name} · {checkpoint.message_count} "
                f"message(s) · {checkpoint.created_at}"
            )
            item.setData(_CHAT_ID_ROLE, checkpoint.id)
            self.checkpoint_list.addItem(item)
        if checkpoints:
            self.checkpoint_list.setCurrentRow(0)
        self.undo_list.clear()
        for entry in undo_entries:
            item = QListWidgetItem(entry.label)
            item.setData(_CHAT_ID_ROLE, entry.id)
            self.undo_list.addItem(item)
        self.undo_button.setEnabled(bool(undo_entries))
        self.state_label.setText(
            f"{len(checkpoints)} checkpoint(s) · "
            f"{len(undo_entries)} undoable action(s)."
        )

    def selected_checkpoint_id(self) -> str | None:
        item = self.checkpoint_list.currentItem()
        if item is None:
            return None
        value = item.data(_CHAT_ID_ROLE)
        return value if isinstance(value, str) else None

    def _create(self) -> None:
        # Callbacks run their roads OFF the GUI thread and call
        # back into refresh() with the new state when they land.
        self._on_create(self)

    def _restore(self) -> None:
        checkpoint_id = self.selected_checkpoint_id()
        if checkpoint_id:
            self._on_restore(checkpoint_id)

    def _delete(self) -> None:
        checkpoint_id = self.selected_checkpoint_id()
        if checkpoint_id:
            self._on_delete(self, checkpoint_id)

    def _undo(self) -> None:
        self._on_undo(self)


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
        # Chat Stage II state (R-07).
        self._edit_dialog: EditMessageDialog | None = None
        self._swipe_dialog: SwipeListDialog | None = None
        self._note_dialog: AuthorsNoteDialog | None = None
        self._impersonate_dialog: ImpersonateDialog | None = None
        self._search_dialog: ChatSearchDialog | None = None
        self._checkpoints_dialog: CheckpointsDialog | None = None
        self._delete_message_box: QMessageBox | None = None
        self._branch_name_dialog: RenameChatDialog | None = None
        self.last_impersonate_draft: ImpersonateDraft | None = None
        self.last_search_outcome = None

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

        # R-07: the message list + per-message action bar. The
        # transcript above is the reading view; this list is how a
        # message is PICKED for an action (edit/delete/swipes/
        # branch/pin/copy), one row per stored message.
        self.message_list = QListWidget()
        self.message_list.setObjectName("messageList")
        self.message_list.setMaximumHeight(130)
        layout.addWidget(self.message_list)
        message_row = QHBoxLayout()
        self.edit_message_button = QPushButton("Edit…")
        self.edit_message_button.clicked.connect(
            lambda _c=False: self.open_edit_message_dialog()
        )
        message_row.addWidget(self.edit_message_button)
        self.delete_message_button = QPushButton("Delete Message")
        self.delete_message_button.clicked.connect(
            lambda _c=False: self.confirm_delete_selected_message()
        )
        message_row.addWidget(self.delete_message_button)
        self.swipe_prev_button = QPushButton("◀ Swipe")
        self.swipe_prev_button.clicked.connect(
            lambda _c=False: self.swipe_selected(-1)
        )
        message_row.addWidget(self.swipe_prev_button)
        self.swipe_next_button = QPushButton("Swipe ▶")
        self.swipe_next_button.clicked.connect(
            lambda _c=False: self.swipe_selected(1)
        )
        message_row.addWidget(self.swipe_next_button)
        self.swipes_button = QPushButton("Swipes…")
        self.swipes_button.clicked.connect(
            lambda _c=False: self.open_swipe_dialog()
        )
        message_row.addWidget(self.swipes_button)
        self.branch_button = QPushButton("Branch…")
        self.branch_button.clicked.connect(
            lambda _c=False: self.open_branch_dialog()
        )
        message_row.addWidget(self.branch_button)
        self.pin_button = QPushButton("Pin")
        self.pin_button.clicked.connect(
            lambda _c=False: self.toggle_pin_selected()
        )
        message_row.addWidget(self.pin_button)
        self.copy_message_button = QPushButton("Copy")
        self.copy_message_button.clicked.connect(
            lambda _c=False: self.copy_selected_message()
        )
        message_row.addWidget(self.copy_message_button)
        layout.addLayout(message_row)

        # R-07: the chat-level action row.
        chat_row = QHBoxLayout()
        self.regenerate_button = QPushButton("Regenerate")
        self.regenerate_button.clicked.connect(
            lambda _c=False: self.regenerate_last()
        )
        chat_row.addWidget(self.regenerate_button)
        self.continue_button = QPushButton("Continue")
        self.continue_button.clicked.connect(
            lambda _c=False: self.continue_current()
        )
        chat_row.addWidget(self.continue_button)
        self.impersonate_button = QPushButton("Impersonate…")
        self.impersonate_button.clicked.connect(
            lambda _c=False: self.open_impersonate()
        )
        chat_row.addWidget(self.impersonate_button)
        self.authors_note_button = QPushButton("Author's Note…")
        self.authors_note_button.clicked.connect(
            lambda _c=False: self.open_authors_note_dialog()
        )
        chat_row.addWidget(self.authors_note_button)
        self.search_button = QPushButton("Search Chats…")
        self.search_button.clicked.connect(
            lambda _c=False: self.open_search_dialog()
        )
        chat_row.addWidget(self.search_button)
        self.checkpoints_button = QPushButton("Checkpoints & Undo…")
        self.checkpoints_button.clicked.connect(
            lambda _c=False: self.open_checkpoints_dialog()
        )
        chat_row.addWidget(self.checkpoints_button)
        layout.addLayout(chat_row)

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
            "Per-message actions, search and checkpoints live in "
            "the Chat Stage (R-07)."
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
        self.action_undo = QAction("Undo", self)
        self.action_undo.setStatusTip(
            "Undo the open chat's most recent journaled action (R-07)"
        )
        self.action_undo.triggered.connect(
            lambda _c=False: self.undo_last_action()
        )
        edit_menu.addAction(self.action_undo)
        self.action_find = QAction("Find in Chat…", self)
        self.action_find.triggered.connect(
            lambda _c=False: self.open_search_dialog()
        )
        edit_menu.addAction(self.action_find)

        view_menu = bar.addMenu("View")
        view_menu.addAction(self.library_dock.toggleViewAction())
        view_menu.addAction(self.session_dock.toggleViewAction())
        view_menu.addSeparator()
        self._placeholder(view_menu, "Theme…", "R-15")
        self._placeholder(view_menu, "Text Size…", "R-15")
        self._placeholder(view_menu, "Ornament Density…", "R-15")

        chat_menu = bar.addMenu("Chat")
        self.action_regenerate = QAction("Regenerate", self)
        self.action_regenerate.triggered.connect(
            lambda _c=False: self.regenerate_last()
        )
        chat_menu.addAction(self.action_regenerate)
        self.action_continue = QAction("Continue", self)
        self.action_continue.triggered.connect(
            lambda _c=False: self.continue_current()
        )
        chat_menu.addAction(self.action_continue)
        self.action_impersonate = QAction("Impersonate…", self)
        self.action_impersonate.triggered.connect(
            lambda _c=False: self.open_impersonate()
        )
        chat_menu.addAction(self.action_impersonate)
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
        status.showMessage("Rúnmál — Chat Stage (R-07)")

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
        # R-07: keep the actionable message list in step with the
        # stored history (the pending user line and the draft are
        # display-only — actions land on stored messages only).
        selected_id = self.selected_message_id()
        self.message_list.clear()
        for message in self.current_messages:
            item = QListWidgetItem(
                message_list_label(
                    message,
                    character_name=character_name,
                    user_name=self._user_name,
                )
            )
            item.setData(_CHAT_ID_ROLE, message.id)
            self.message_list.addItem(item)
            if message.id == selected_id:
                self.message_list.setCurrentItem(item)
        if (
            self.message_list.currentItem() is None
            and self.message_list.count() > 0
        ):
            self.message_list.setCurrentRow(self.message_list.count() - 1)
        self._update_message_chrome()

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
            self.message_list.clear()
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
                    self.message_list.clear()
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

    # ------------------------------------------- R-07 message actions

    def selected_message_id(self) -> str | None:
        item = self.message_list.currentItem()
        if item is None:
            return None
        value = item.data(_CHAT_ID_ROLE)
        return value if isinstance(value, str) and value else None

    def selected_message(self) -> MessageView | None:
        message_id = self.selected_message_id()
        if not message_id:
            return None
        for message in self.current_messages:
            if message.id == message_id:
                return message
        return None

    def _update_message_chrome(self) -> None:
        has_chat = self.current_chat_id is not None and not self._streaming
        message = self.selected_message()
        has_message = has_chat and message is not None
        for button in (
            self.edit_message_button,
            self.delete_message_button,
            self.swipes_button,
            self.branch_button,
            self.copy_message_button,
        ):
            button.setEnabled(has_message)
        deck = message.swipe_count if message is not None else 1
        self.swipe_prev_button.setEnabled(
            has_message and message is not None and message.swipe_id > 0
        )
        self.swipe_next_button.setEnabled(
            has_message and message is not None and message.swipe_id < deck - 1
        )
        self.pin_button.setEnabled(has_message)
        if message is not None:
            self.pin_button.setText("Unpin" if message.pinned else "Pin")
        for button in (
            self.regenerate_button,
            self.continue_button,
            self.impersonate_button,
            self.authors_note_button,
            self.checkpoints_button,
        ):
            button.setEnabled(has_chat)
        self.search_button.setEnabled(self._engine.is_running)
        self.action_regenerate.setEnabled(has_chat)
        self.action_continue.setEnabled(has_chat)
        self.action_impersonate.setEnabled(has_chat)
        self.action_undo.setEnabled(has_chat)

    def _reload_open_chat(self, words: str = "") -> None:
        """Re-read the open chat after an action landed, keeping
        the action's words in the stage status afterwards."""
        chat_id = self.current_chat_id
        if chat_id is None:
            return
        try:
            self.open_chat_blocking(chat_id)
        except Exception as exc:  # the action's words already landed
            self._apply_error(str(exc))
            return
        if words:
            self.chat_stage_status.setText(words)
            self.statusBar().showMessage(words, 8000)
        self.refresh_async()

    def _run_action(self, fn, words_of) -> None:
        """Run one ChatFlow action off-thread; on success reload
        the open chat and show ``words_of(result)``."""

        def done(result) -> None:
            self._reload_open_chat(words_of(result))

        worker = run_async(fn, done, self._apply_error)
        self._workers.append(worker)

    # -- edit / delete --

    def edit_message_blocking(
        self, message_id: str, content: str
    ) -> MessageView:
        updated = self.flow().edit_message(
            self.current_chat_id or "", message_id, content
        )
        self._reload_open_chat(f"Message edited — “{updated.content[:40]}”.")
        return updated

    def open_edit_message_dialog(self) -> EditMessageDialog | None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            self.statusBar().showMessage("Pick a message to edit first.", 5000)
            return None
        dialog = EditMessageDialog(message.content, self)
        dialog.accepted.connect(
            lambda d=dialog, mid=message.id: self._edit_accepted(mid, d)
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_edit_dialog", None)
        )
        self._edit_dialog = dialog
        dialog.show()
        return dialog

    def _edit_accepted(self, message_id: str, dialog: EditMessageDialog) -> None:
        self._edit_dialog = None
        chat_id = self.current_chat_id
        if chat_id is None:
            return
        text = dialog.text()
        flow = self.flow()
        self._run_action(
            lambda: flow.edit_message(chat_id, message_id, text),
            lambda _m: "Message edited and saved.",
        )

    def delete_message_blocking(self, message_id: str) -> bool:
        deleted = self.flow().delete_message(
            self.current_chat_id or "", message_id
        )
        self._reload_open_chat(
            "Message deleted — Undo can bring it back."
            if deleted
            else "That message was already gone."
        )
        return deleted

    def confirm_delete_selected_message(self) -> QMessageBox | None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            self.statusBar().showMessage(
                "Pick a message to delete first.", 5000
            )
            return None
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete Message")
        excerpt = " ".join(message.content.split())[:80]
        box.setText(f"Delete this message?\n“{excerpt}”")
        box.setInformativeText(
            "The message leaves the chat history. The deletion is "
            "journaled, so Checkpoints & Undo can restore it."
        )
        delete_button = box.addButton(
            "Delete", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.buttonClicked.connect(
            lambda button, mid=message.id, db=delete_button: (
                self._delete_message_confirmed(mid) if button is db else None
            )
        )
        box.destroyed.connect(
            lambda _obj=None: setattr(self, "_delete_message_box", None)
        )
        self._delete_message_box = box
        box.show()
        return box

    def _delete_message_confirmed(self, message_id: str) -> None:
        self._delete_message_box = None
        chat_id = self.current_chat_id
        if chat_id is None:
            return
        flow = self.flow()
        self._run_action(
            lambda: flow.delete_message(chat_id, message_id),
            lambda deleted: (
                "Message deleted — Undo can bring it back."
                if deleted
                else "That message was already gone."
            ),
        )

    # -- swipes --

    def swipe_selected_blocking(self, step: int) -> MessageView | None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            return None
        flow = self.flow()
        updated = (
            flow.swipe_next(self.current_chat_id, message.id)
            if step > 0
            else flow.swipe_prev(self.current_chat_id, message.id)
        )
        self._reload_open_chat(
            f"Swipe {updated.swipe_id + 1} of {updated.swipe_count} shown."
        )
        return updated

    def swipe_selected(self, step: int) -> None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            self.statusBar().showMessage("Pick a message first.", 5000)
            return
        chat_id = self.current_chat_id
        flow = self.flow()
        fn = flow.swipe_next if step > 0 else flow.swipe_prev
        self._run_action(
            lambda: fn(chat_id, message.id),
            lambda m: f"Swipe {m.swipe_id + 1} of {m.swipe_count} shown.",
        )

    def select_swipe_blocking(
        self, message_id: str, index: int
    ) -> MessageView:
        updated = self.flow().select_swipe(
            self.current_chat_id or "", message_id, index
        )
        self._reload_open_chat(
            f"Swipe {updated.swipe_id + 1} of {updated.swipe_count} shown."
        )
        return updated

    def delete_swipe_blocking(
        self, message_id: str, index: int
    ) -> MessageView:
        updated = self.flow().delete_swipe(
            self.current_chat_id or "", message_id, index
        )
        self._reload_open_chat(
            f"Swipe deleted — {updated.swipe_count} alternate(s) remain."
        )
        return updated

    def open_swipe_dialog(self) -> SwipeListDialog | None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            self.statusBar().showMessage(
                "Pick a message to see its swipes.", 5000
            )
            return None
        chat_id = self.current_chat_id
        flow = self.flow()

        def _async_swipe(fn):
            def start(message_id: str, index: int, done) -> None:
                worker = run_async(
                    lambda: fn(chat_id, message_id, index),
                    done,
                    self._apply_error,
                )
                self._workers.append(worker)

            return start

        dialog = SwipeListDialog(
            message,
            on_select=_async_swipe(flow.select_swipe),
            on_delete=_async_swipe(flow.delete_swipe),
            parent=self,
        )
        dialog.finished.connect(
            lambda _r=0: self._reload_open_chat("Swipes updated.")
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_swipe_dialog", None)
        )
        self._swipe_dialog = dialog
        dialog.show()
        return dialog

    # -- branch / pin / copy --

    def branch_blocking(
        self, *, message_id: str | None = None, name: str = ""
    ) -> ChatSummary:
        branch = self.flow().branch_from(
            self.current_chat_id or "", message_id=message_id, name=name
        )
        self.refresh_blocking()
        self.open_chat_blocking(branch.id)
        self.chat_stage_status.setText(
            f"Branched — now in the new chat “{branch.title or branch.id}”; "
            "the original chat is unchanged."
        )
        return branch

    def open_branch_dialog(self) -> RenameChatDialog | None:
        message = self.selected_message()
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return None
        dialog = RenameChatDialog("", self)
        dialog.setWindowTitle("Branch Chat")
        dialog.accepted.connect(
            lambda d=dialog, mid=(message.id if message else None):
            self._branch_accepted(mid, d)
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_branch_name_dialog", None)
        )
        self._branch_name_dialog = dialog
        dialog.show()
        return dialog

    def _branch_accepted(
        self, message_id: str | None, dialog: RenameChatDialog
    ) -> None:
        self._branch_name_dialog = None
        chat_id = self.current_chat_id
        if chat_id is None:
            return
        name = dialog.title()
        flow = self.flow()

        def branch() -> ChatSummary:
            return flow.branch_from(chat_id, message_id=message_id, name=name)

        def done(new_chat: ChatSummary) -> None:
            self.refresh_async()
            self.open_chat_async(new_chat.id)
            self.statusBar().showMessage(
                f"Branched — now in “{new_chat.title or new_chat.id}”; "
                "the original chat is unchanged.",
                8000,
            )

        worker = run_async(branch, done, self._apply_error)
        self._workers.append(worker)

    def toggle_pin_blocking(self) -> bool | None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            return None
        now_pinned = self.flow().set_pinned(
            self.current_chat_id, message, not message.pinned
        )
        self._reload_open_chat(
            "Message pinned to memory."
            if now_pinned
            else "Message unpinned."
        )
        return now_pinned

    def toggle_pin_selected(self) -> None:
        message = self.selected_message()
        if message is None or self.current_chat_id is None:
            self.statusBar().showMessage("Pick a message first.", 5000)
            return
        chat_id = self.current_chat_id
        target = not message.pinned
        flow = self.flow()
        self._run_action(
            lambda: flow.set_pinned(chat_id, message, target),
            lambda now: (
                "Message pinned to memory." if now else "Message unpinned."
            ),
        )

    def copy_selected_message(self) -> str:
        message = self.selected_message()
        if message is None:
            self.statusBar().showMessage("Pick a message to copy first.", 5000)
            return ""
        QApplication.clipboard().setText(message.content)
        self.statusBar().showMessage("Message copied.", 4000)
        return message.content

    # -- regenerate / continue / impersonate --

    def regenerate_blocking(self):
        """Regenerate the last reply synchronously (proof/tests)."""
        chat_id = self.current_chat_id or ""
        flow = self.flow()
        request_id = self.client().new_request_id()
        self._active_request_id = request_id
        self._streaming = True
        self._draft = StreamDraft()
        try:
            result = flow.regenerate(
                chat_id,
                on_event=lambda event: (
                    self._draft.apply(event) if self._draft else None
                ),
                request_id=request_id,
            )
        finally:
            self._streaming = False
            self._active_request_id = None
            self._draft = None
        self._reload_open_chat(result.status_words)
        return result

    def regenerate_last(self) -> None:
        if self._streaming or self.current_chat_id is None:
            if self.current_chat_id is None:
                self.statusBar().showMessage("Open a chat first.", 5000)
            return
        chat_id = self.current_chat_id
        self._draft = StreamDraft()
        self._streaming = True
        self._active_request_id = self.client().new_request_id()
        self._set_streaming_words("regenerating…")
        self._update_composer_chrome()
        self.stop_button.setEnabled(True)
        self.action_stop_generating.setEnabled(True)
        flow = self.flow()
        request_id = self._active_request_id

        def run(emit) -> object:
            return flow.regenerate(chat_id, on_event=emit, request_id=request_id)

        worker = run_stream(
            run, self._on_stream_event, self._on_regen_done, self._on_turn_failed
        )
        self._workers.append(worker)

    def _on_regen_done(self, result) -> None:
        self._streaming = False
        self._active_request_id = None
        self._draft = None
        self._update_composer_chrome()
        self._set_streaming_words("idle")
        self._reload_open_chat(result.status_words)

    def continue_blocking(self):
        outcome = self.flow().continue_turn(self.current_chat_id or "")
        self._reload_open_chat(outcome.status_words)
        return outcome

    def continue_current(self) -> None:
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return
        chat_id = self.current_chat_id
        flow = self.flow()
        self._run_action(
            lambda: flow.continue_turn(chat_id),
            lambda outcome: outcome.status_words,
        )

    def impersonate_blocking(self) -> ImpersonateDraft:
        draft = self.flow().impersonate(self.current_chat_id or "")
        self.last_impersonate_draft = draft
        return draft

    def accept_impersonate_blocking(self, content: str) -> MessageView:
        draft = self.last_impersonate_draft
        if draft is None:
            raise ValueError("no impersonate draft to accept")
        message = self.flow().accept_impersonate(
            self.current_chat_id or "", draft, content
        )
        self.last_impersonate_draft = None
        self._reload_open_chat("Impersonated line accepted as your message.")
        return message

    def discard_impersonate_blocking(self) -> bool:
        draft = self.last_impersonate_draft
        if draft is None:
            return False
        discarded = self.flow().discard_impersonate(
            self.current_chat_id or "", draft
        )
        self.last_impersonate_draft = None
        self._reload_open_chat("Impersonate draft discarded — nothing was stored.")
        return discarded

    def open_impersonate(self) -> None:
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return
        chat_id = self.current_chat_id
        flow = self.flow()

        def drafted(draft: ImpersonateDraft) -> None:
            self.last_impersonate_draft = draft
            dialog = ImpersonateDialog(draft, self)
            dialog.accepted.connect(
                lambda d=dialog: self._impersonate_accepted(d)
            )
            dialog.rejected.connect(
                lambda d=dialog: self._impersonate_discarded(d)
            )
            dialog.destroyed.connect(
                lambda _obj=None: setattr(self, "_impersonate_dialog", None)
            )
            self._impersonate_dialog = dialog
            dialog.show()

        worker = run_async(
            lambda: flow.impersonate(chat_id), drafted, self._apply_error
        )
        self._workers.append(worker)

    def _impersonate_accepted(self, dialog: ImpersonateDialog) -> None:
        self._impersonate_dialog = None
        draft = self.last_impersonate_draft
        chat_id = self.current_chat_id
        if draft is None or chat_id is None:
            return
        text = dialog.text()
        flow = self.flow()
        self._run_action(
            lambda: flow.accept_impersonate(chat_id, draft, text),
            lambda _m: "Impersonated line accepted as your message.",
        )
        self.last_impersonate_draft = None

    def _impersonate_discarded(self, dialog: ImpersonateDialog) -> None:
        self._impersonate_dialog = None
        draft = self.last_impersonate_draft
        chat_id = self.current_chat_id
        if draft is None or chat_id is None:
            return
        flow = self.flow()
        self._run_action(
            lambda: flow.discard_impersonate(chat_id, draft),
            lambda _d: "Impersonate draft discarded — nothing was stored.",
        )
        self.last_impersonate_draft = None

    # -- author's note --

    def authors_note_blocking(self):
        return self.flow().authors_note(self.current_chat_id or "")

    def save_authors_note_blocking(self, **values):
        note = self.flow().save_authors_note(
            self.current_chat_id or "", **values
        )
        self._reload_open_chat(
            "Author's Note saved."
            if note.enabled and note.text.strip()
            else "Author's Note saved (currently not steering: "
            "empty or disabled)."
        )
        return note

    def open_authors_note_dialog(self) -> None:
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return
        chat_id = self.current_chat_id
        flow = self.flow()

        def got(note) -> None:
            dialog = AuthorsNoteDialog(note, self)
            dialog.accepted.connect(
                lambda d=dialog: self._note_accepted(chat_id, d)
            )
            dialog.destroyed.connect(
                lambda _obj=None: setattr(self, "_note_dialog", None)
            )
            self._note_dialog = dialog
            dialog.show()

        worker = run_async(
            lambda: flow.authors_note(chat_id), got, self._apply_error
        )
        self._workers.append(worker)

    def _note_accepted(self, chat_id: str, dialog: AuthorsNoteDialog) -> None:
        self._note_dialog = None
        values = dialog.values()
        flow = self.flow()
        self._run_action(
            lambda: flow.save_authors_note(chat_id, **values),
            lambda _n: "Author's Note saved.",
        )

    # -- search --

    def search_blocking(self, query: str, chat_id: str | None = None):
        outcome = self.flow().search(query, chat_id=chat_id)
        self.last_search_outcome = outcome
        return outcome

    def open_search_dialog(self) -> ChatSearchDialog:
        flow = self.flow()

        def on_search(query: str, scope_chat_id: str | None, done) -> None:
            def found(outcome) -> None:
                self.last_search_outcome = outcome
                done(outcome)

            worker = run_async(
                lambda: flow.search(query, chat_id=scope_chat_id),
                found,
                lambda message: (self._apply_error(message), done(None)),
            )
            self._workers.append(worker)

        def on_open(chat_id: str) -> None:
            if chat_id != self.current_chat_id and not self._streaming:
                self.open_chat_async(chat_id)

        dialog = ChatSearchDialog(
            on_search=on_search,
            on_open=on_open,
            current_chat_id=self.current_chat_id,
            parent=self,
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_search_dialog", None)
        )
        self._search_dialog = dialog
        dialog.show()
        return dialog

    # -- checkpoints / undo --

    def checkpoints_state_blocking(self):
        chat_id = self.current_chat_id or ""
        flow = self.flow()
        return flow.checkpoints(chat_id), flow.undo_journal(chat_id)

    def create_checkpoint_blocking(self, name: str = ""):
        checkpoint = self.flow().create_checkpoint(
            self.current_chat_id or "", name=name
        )
        self._reload_open_chat(
            f"Checkpoint “{checkpoint.name}” created "
            f"({checkpoint.message_count} message(s))."
        )
        return checkpoint

    def restore_checkpoint_blocking(self, checkpoint_id: str) -> ChatSummary:
        restored = self.flow().restore_checkpoint(
            self.current_chat_id or "", checkpoint_id
        )
        self.refresh_blocking()
        self.open_chat_blocking(restored.id)
        self.chat_stage_status.setText(
            f"Checkpoint restored as the new chat "
            f"“{restored.title or restored.id}” — the original chat "
            "is unchanged."
        )
        return restored

    def delete_checkpoint_blocking(self, checkpoint_id: str) -> bool:
        deleted = self.flow().delete_checkpoint(
            self.current_chat_id or "", checkpoint_id
        )
        self._reload_open_chat(
            "Checkpoint deleted." if deleted else "That checkpoint was gone."
        )
        return deleted

    def undo_blocking(self) -> dict:
        result = self.flow().undo_last(self.current_chat_id or "")
        undone = result.get("undone", "the last action")
        self._reload_open_chat(f"Undid: {undone}.")
        return result

    def undo_last_action(self) -> None:
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return
        chat_id = self.current_chat_id
        flow = self.flow()

        def words(result: dict) -> str:
            return f"Undid: {result.get('undone', 'the last action')}."

        self._run_action(lambda: flow.undo_last(chat_id), words)

    def open_checkpoints_dialog(self) -> CheckpointsDialog | None:
        if self.current_chat_id is None:
            self.statusBar().showMessage("Open a chat first.", 5000)
            return None
        chat_id = self.current_chat_id
        flow = self.flow()

        def state():
            return flow.checkpoints(chat_id), flow.undo_journal(chat_id)

        def _async_state(fn):
            """Run ``fn`` + a state re-read off-thread; refresh the
            dialog with the new state when it lands."""

            def start(dialog, *args) -> None:
                def work():
                    fn(*args)
                    return state()

                worker = run_async(
                    work,
                    lambda result: dialog.refresh(*result),
                    self._apply_error,
                )
                self._workers.append(worker)

            return start

        def on_restore(checkpoint_id: str) -> None:
            def done(restored: ChatSummary) -> None:
                self.refresh_async()
                self.open_chat_async(restored.id)
                self.statusBar().showMessage(
                    f"Checkpoint restored as “{restored.title or restored.id}”.",
                    8000,
                )

            worker = run_async(
                lambda: flow.restore_checkpoint(chat_id, checkpoint_id),
                done,
                self._apply_error,
            )
            self._workers.append(worker)

        def on_undo(dialog) -> None:
            def work():
                flow.undo_last(chat_id)
                return state()

            def done(result) -> None:
                dialog.refresh(*result)
                self._reload_open_chat("Undid the last journaled action.")

            worker = run_async(work, done, self._apply_error)
            self._workers.append(worker)

        # The dialog opens empty and fills from an off-thread
        # state read — no network on the GUI thread, ever.
        dialog = CheckpointsDialog(
            checkpoints=[],
            undo_entries=[],
            on_create=_async_state(lambda: flow.create_checkpoint(chat_id)),
            on_restore=on_restore,
            on_delete=_async_state(
                lambda cid: flow.delete_checkpoint(chat_id, cid)
            ),
            on_undo=on_undo,
            parent=self,
        )
        dialog.destroyed.connect(
            lambda _obj=None: setattr(self, "_checkpoints_dialog", None)
        )
        self._checkpoints_dialog = dialog
        dialog.show()
        worker = run_async(
            state,
            lambda result: dialog.refresh(*result),
            self._apply_error,
        )
        self._workers.append(worker)
        return dialog

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
        self._update_message_chrome()

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
                "first-run wizard, R-06/R-07 Chat Stage) over the "
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
