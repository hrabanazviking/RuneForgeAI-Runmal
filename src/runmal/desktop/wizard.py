"""First-Run Setup wizard (R-05) — the Qt dialog over wizard_logic.

Shown when first-run state is true (no backend profile and no
character — R-04's detection), and reachable any time from
File → First-Run Setup…. Four pages, one per plan §2.3 step:

1. Connect a mind (backend kinds in plain words; Ollama detection;
   API keys go to the R-02 secret store, write-only, password-masked
   here and never displayed back).
2. Prove it (health probe reported in words, never raw JSON).
3. Meet someone (create a first character, or import a card file;
   finishing the step opens a greeted chat pinned to the profile).
4. Your name (the persisted ``{{user}}`` name, R-03 road).

All network work runs off the GUI thread through
``runmal.desktop.workers``; the widgets talk only through
``WizardFlow`` → ``RunmalClient`` — no engine imports, no SQL.
Each page does its network step behind an explicit action button
and only then reports itself complete, so Next/Finish never block
the GUI thread on a request.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from runmal.desktop.client import RunmalClient
from runmal.desktop.wizard_logic import BACKEND_OPTIONS, WizardFlow
from runmal.desktop.workers import run_async

PAGE_CONNECT = 0
PAGE_PROVE = 1
PAGE_MEET = 2
PAGE_NAME = 3


def _words_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class _FlowPage(QWizardPage):
    """Base page: a completion flag + access to the wizard's flow."""

    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setTitle(title)
        self.setSubTitle(subtitle)
        self._complete = False

    def flow(self) -> WizardFlow:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        return wizard.flow

    def set_complete(self, complete: bool) -> None:
        if complete != self._complete:
            self._complete = complete
            self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 (Qt naming)
        return self._complete


class ConnectPage(_FlowPage):
    """Step 1 — Connect a mind."""

    def __init__(self) -> None:
        super().__init__(
            "Connect a mind",
            "Choose how Rúnmál will think. You can change this "
            "later in Connections — nothing here is final.",
        )
        layout = QVBoxLayout(self)

        self.kind_group = QButtonGroup(self)
        self.kind_buttons: dict[str, QRadioButton] = {}
        for option in BACKEND_OPTIONS:
            button = QRadioButton(option.title)
            button.toggled.connect(
                lambda checked, k=option.kind: checked
                and self._kind_selected(k)
            )
            self.kind_group.addButton(button)
            self.kind_buttons[option.kind] = button
            layout.addWidget(button)
        self.blurb_label = _words_label()
        layout.addWidget(self.blurb_label)

        self.panels = QStackedWidget()
        self._panel_by_kind: dict[str, QWidget] = {}
        self._build_ollama_panel()
        self._build_key_model_panel(
            "openrouter",
            key_placeholder="Paste your OpenRouter API key",
            model_placeholder="Model name, exactly as OpenRouter lists it",
        )
        self._build_openai_panel()
        self._build_aesir_panel()
        self._build_demo_panel()
        layout.addWidget(self.panels)

        self.connect_button = QPushButton("Connect this mind")
        self.connect_button.clicked.connect(lambda _c=False: self._connect())
        layout.addWidget(self.connect_button)
        self.connect_status = _words_label()
        layout.addWidget(self.connect_status)
        layout.addStretch(1)

        self._connected_kind: str | None = None
        self.kind_buttons["ollama"].setChecked(True)
        self._kind_selected("ollama")

    # ------------------------------------------------------------- panels

    def _panel(self, kind: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 4, 4, 4)
        self.panels.addWidget(panel)
        self._panel_by_kind[kind] = panel
        return panel, panel_layout

    def _build_ollama_panel(self) -> None:
        panel, layout = self._panel("ollama")
        layout.addWidget(QLabel("Ollama address:"))
        self.ollama_url_edit = QLineEdit("http://127.0.0.1:11434")
        layout.addWidget(self.ollama_url_edit)
        row = QHBoxLayout()
        self.detect_button = QPushButton("Look for Ollama")
        self.detect_button.clicked.connect(lambda _c=False: self._detect())
        row.addWidget(self.detect_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.detect_status = _words_label(
            "Not checked yet — Rúnmál can look for Ollama now."
        )
        layout.addWidget(self.detect_status)
        layout.addWidget(QLabel("Model to talk with:"))
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        layout.addWidget(self.ollama_model_combo)

    def _build_key_model_panel(
        self, kind: str, *, key_placeholder: str, model_placeholder: str
    ) -> None:
        panel, layout = self._panel(kind)
        layout.addWidget(QLabel("API key (stored in the secret store, "
                                "never shown back):"))
        key_edit = QLineEdit()
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setPlaceholderText(key_placeholder)
        layout.addWidget(key_edit)
        layout.addWidget(QLabel("Model:"))
        model_edit = QLineEdit()
        model_edit.setPlaceholderText(model_placeholder)
        layout.addWidget(model_edit)
        if kind == "openrouter":
            self.openrouter_key_edit = key_edit
            self.openrouter_model_edit = model_edit

    def _build_openai_panel(self) -> None:
        panel, layout = self._panel("openai")
        layout.addWidget(QLabel("Server address (base URL):"))
        self.openai_url_edit = QLineEdit()
        self.openai_url_edit.setPlaceholderText("e.g. http://127.0.0.1:1234/v1")
        layout.addWidget(self.openai_url_edit)
        layout.addWidget(QLabel("API key (if the server has one):"))
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.openai_key_edit)
        layout.addWidget(QLabel("Model:"))
        self.openai_model_edit = QLineEdit()
        layout.addWidget(self.openai_model_edit)

    def _build_aesir_panel(self) -> None:
        panel, layout = self._panel("aesir")
        layout.addWidget(_words_label(
            "Aesir runs on this machine as part of the Rúnmál "
            "project. No key and no address are needed; if it is "
            "not running, the next step will say so in plain words."
        ))
        layout.addWidget(QLabel("Model (optional):"))
        self.aesir_model_edit = QLineEdit()
        layout.addWidget(self.aesir_model_edit)

    def _build_demo_panel(self) -> None:
        panel, layout = self._panel("fake")
        demo = next(o for o in BACKEND_OPTIONS if o.kind == "fake")
        layout.addWidget(_words_label(demo.blurb))

    # ----------------------------------------------------------- behaviour

    def selected_kind(self) -> str:
        for kind, button in self.kind_buttons.items():
            if button.isChecked():
                return kind
        return "fake"

    def _kind_selected(self, kind: str) -> None:
        option = next(o for o in BACKEND_OPTIONS if o.kind == kind)
        self.blurb_label.setText(option.blurb)
        self.panels.setCurrentWidget(self._panel_by_kind[kind])
        if kind != self._connected_kind:
            self.set_complete(False)
            self.connect_status.setText("")

    def _fields(self, kind: str) -> dict[str, str]:
        if kind == "ollama":
            return {
                "chat_model": self.ollama_model_combo.currentText().strip(),
                "base_url": self.ollama_url_edit.text().strip(),
                "api_key": "",
            }
        if kind == "openrouter":
            return {
                "chat_model": self.openrouter_model_edit.text().strip(),
                "base_url": "",
                "api_key": self.openrouter_key_edit.text().strip(),
            }
        if kind == "openai":
            return {
                "chat_model": self.openai_model_edit.text().strip(),
                "base_url": self.openai_url_edit.text().strip(),
                "api_key": self.openai_key_edit.text().strip(),
            }
        if kind == "aesir":
            return {
                "chat_model": self.aesir_model_edit.text().strip(),
                "base_url": "",
                "api_key": "",
            }
        return {"chat_model": "", "base_url": "", "api_key": ""}

    def _detect(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        self.detect_button.setEnabled(False)
        self.detect_status.setText("Looking for Ollama…")
        url = self.ollama_url_edit.text().strip()
        wizard.run_flow(
            lambda: self.flow().detect_ollama(url),
            self._detect_done,
            self._detect_failed,
        )

    def _detect_done(self, result) -> None:
        self.detect_button.setEnabled(True)
        self.detect_status.setText(result.words)
        if result.reachable and result.models:
            self.ollama_model_combo.clear()
            self.ollama_model_combo.addItems(result.models)

    def _detect_failed(self, message: str) -> None:
        self.detect_button.setEnabled(True)
        self.detect_status.setText(
            f"The check itself failed: {message}. You can type the "
            "address and model by hand, or pick another mind."
        )

    def _connect(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        kind = self.selected_kind()
        fields = self._fields(kind)
        if kind in ("openrouter", "openai") and not fields["chat_model"]:
            self.connect_status.setText(
                "Name the model to talk with first — the field "
                "above the Connect button."
            )
            return
        if kind == "openrouter" and not fields["api_key"]:
            self.connect_status.setText(
                "OpenRouter needs its API key — paste it above. "
                "It goes to the secret store and is never shown back."
            )
            return
        if kind == "openai" and not fields["base_url"]:
            self.connect_status.setText(
                "Name the server address first — the base URL above."
            )
            return
        self.connect_button.setEnabled(False)
        self.connect_status.setText("Connecting…")
        wizard.run_flow(
            lambda: self.flow().create_chosen_profile(kind, **fields),
            lambda profile: self._connect_done(kind, profile),
            self._connect_failed,
        )

    def _connect_done(self, kind: str, profile) -> None:
        self.connect_button.setEnabled(True)
        self._connected_kind = kind
        if kind == "fake":
            words = (
                "Demo mode is connected. Remember: it is a canned "
                "responder, not a real model. Choose Next to prove it."
            )
        else:
            words = (
                f"Connected: {profile.label}. Choose Next to prove it."
            )
        self.connect_status.setText(words)
        self.set_complete(True)

    def _connect_failed(self, message: str) -> None:
        self.connect_button.setEnabled(True)
        self.connect_status.setText(
            f"That did not connect: {message}. Check the details "
            "above and try again, or pick another mind."
        )
        self.set_complete(False)


class ProvePage(_FlowPage):
    """Step 2 — Prove it, in words."""

    def __init__(self) -> None:
        super().__init__(
            "Prove it",
            "Rúnmál checks the connection you just made and says "
            "what it found, in plain words.",
        )
        layout = QVBoxLayout(self)
        self.prove_status = _words_label("Not checked yet.")
        layout.addWidget(self.prove_status)
        self.retry_button = QPushButton("Check again")
        self.retry_button.clicked.connect(lambda _c=False: self._prove())
        layout.addWidget(self.retry_button)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 (Qt naming)
        self._prove()

    def _prove(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        self.set_complete(False)
        self.retry_button.setEnabled(False)
        self.prove_status.setText("Checking the connection…")
        wizard.run_flow(
            self.flow().prove,
            self._prove_done,
            self._prove_failed,
        )

    def _prove_done(self, result) -> None:
        self.retry_button.setEnabled(True)
        self.prove_status.setText(result.words)
        # Even a failed probe completes the step: the user has seen
        # the honest verdict and may go back to fix it or continue.
        self.set_complete(True)

    def _prove_failed(self, message: str) -> None:
        self.retry_button.setEnabled(True)
        self.prove_status.setText(
            f"The check itself failed: {message}. You can check "
            "again, go back and change the connection, or continue "
            "and fix it later in Connections."
        )
        self.set_complete(True)


class MeetPage(_FlowPage):
    """Step 3 — Meet someone; finishes into a greeted chat."""

    def __init__(self) -> None:
        super().__init__(
            "Meet someone",
            "Every chat in Rúnmál is with someone. Create your "
            "first character, or import a card you already have — "
            "the wizard then opens your first chat with their "
            "greeting already in it.",
        )
        layout = QVBoxLayout(self)
        self.mode_group = QButtonGroup(self)
        self.create_radio = QRadioButton("Create someone new")
        self.import_radio = QRadioButton(
            "Import a character card (JSON or PNG)"
        )
        self.mode_group.addButton(self.create_radio)
        self.mode_group.addButton(self.import_radio)
        self.create_radio.setChecked(True)
        self.create_radio.toggled.connect(
            lambda checked: checked and self._mode_changed(False)
        )
        self.import_radio.toggled.connect(
            lambda checked: checked and self._mode_changed(True)
        )
        layout.addWidget(self.create_radio)
        layout.addWidget(self.import_radio)

        self.panels = QStackedWidget()
        create_panel = QWidget()
        create_layout = QVBoxLayout(create_panel)
        create_layout.setContentsMargins(12, 4, 4, 4)
        create_layout.addWidget(QLabel("Name:"))
        self.char_name_edit = QLineEdit()
        create_layout.addWidget(self.char_name_edit)
        create_layout.addWidget(QLabel("A few lines about them:"))
        self.char_description_edit = QPlainTextEdit()
        self.char_description_edit.setMaximumHeight(64)
        create_layout.addWidget(self.char_description_edit)
        create_layout.addWidget(QLabel("Personality:"))
        self.char_personality_edit = QLineEdit()
        create_layout.addWidget(self.char_personality_edit)
        create_layout.addWidget(QLabel("Their first greeting:"))
        self.char_greeting_edit = QPlainTextEdit()
        self.char_greeting_edit.setMaximumHeight(64)
        create_layout.addWidget(self.char_greeting_edit)
        self.panels.addWidget(create_panel)
        self.create_panel = create_panel

        import_panel = QWidget()
        import_layout = QVBoxLayout(import_panel)
        import_layout.setContentsMargins(12, 4, 4, 4)
        import_layout.addWidget(QLabel("Card file:"))
        row = QHBoxLayout()
        self.import_path_edit = QLineEdit()
        row.addWidget(self.import_path_edit)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(lambda _c=False: self._browse())
        row.addWidget(self.browse_button)
        import_layout.addLayout(row)
        self.panels.addWidget(import_panel)
        self.import_panel = import_panel
        layout.addWidget(self.panels)

        self.meet_button = QPushButton("Create my first character")
        self.meet_button.clicked.connect(lambda _c=False: self._meet())
        layout.addWidget(self.meet_button)
        self.meet_status = _words_label()
        layout.addWidget(self.meet_status)
        self.greeting_preview = _words_label()
        layout.addWidget(self.greeting_preview)
        layout.addStretch(1)

    def _mode_changed(self, importing: bool) -> None:
        self.panels.setCurrentWidget(
            self.import_panel if importing else self.create_panel
        )
        self.meet_button.setText(
            "Import this card" if importing else "Create my first character"
        )
        self.set_complete(False)
        self.meet_status.setText("")
        self.greeting_preview.setText("")

    def _browse(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose a character card",
            "",
            "Character cards (*.json *.png);;All files (*)",
        )
        if path:
            self.import_path_edit.setText(path)

    def _meet(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        if self.import_radio.isChecked():
            path = self.import_path_edit.text().strip()
            if not path:
                self.meet_status.setText(
                    "Choose a card file first — Browse… finds it."
                )
                return
            filename = Path(path).name

            def import_and_greet():
                data = Path(path).read_bytes()
                character = self.flow().import_character(filename, data)
                return self.flow().open_greeted_chat(character.id)

            job = import_and_greet
        else:
            name = self.char_name_edit.text().strip()
            if not name:
                self.meet_status.setText(
                    "Give your character a name first."
                )
                return
            fields = {
                "name": name,
                "description": self.char_description_edit.toPlainText(),
                "personality": self.char_personality_edit.text(),
                "first_greeting": self.char_greeting_edit.toPlainText(),
            }

            def create_and_greet():
                self.flow().create_character(**fields)
                return self.flow().open_greeted_chat()

            job = create_and_greet
        self.meet_button.setEnabled(False)
        self.meet_status.setText("Setting up your first chat…")
        wizard.run_flow(job, self._meet_done, self._meet_failed)

    def _meet_done(self, greeted) -> None:
        self.meet_button.setEnabled(True)
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.setup_result.update({
            "profile_id": (
                wizard.flow.profile.id if wizard.flow.profile else ""
            ),
            "character_id": greeted.character.id,
            "character_name": greeted.character.name,
            "chat_id": greeted.chat.id,
            "chat_title": greeted.chat.title,
            "greeting": greeted.greeting,
        })
        self.meet_status.setText(
            f"Your first chat with {greeted.character.name} is open "
            "and waiting behind this wizard."
        )
        if greeted.greeting:
            self.greeting_preview.setText(
                f"They say first: “{greeted.greeting}”"
            )
        self.set_complete(True)

    def _meet_failed(self, message: str) -> None:
        self.meet_button.setEnabled(True)
        self.meet_status.setText(
            f"That did not work: {message}. Check the details and "
            "try again."
        )
        self.set_complete(False)


class NamePage(_FlowPage):
    """Step 4 — Your name (the persisted ``{{user}}`` name)."""

    def __init__(self) -> None:
        super().__init__(
            "Your name",
            "One last thing: the name the cast uses for you. It "
            "fills the {{user}} place in their prompts, and you can "
            "change it later any time.",
        )
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Your name:"))
        self.user_name_edit = QLineEdit()
        self.user_name_edit.setPlaceholderText("User")
        layout.addWidget(self.user_name_edit)
        self.save_name_button = QPushButton("Save my name")
        self.save_name_button.clicked.connect(lambda _c=False: self._save())
        layout.addWidget(self.save_name_button)
        self.name_status = _words_label()
        layout.addWidget(self.name_status)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 (Qt naming)
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.run_flow(
            self.flow().get_user_name,
            lambda name: self.user_name_edit.setText(name),
            lambda _msg: None,
        )

    def _save(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        name = self.user_name_edit.text()
        self.save_name_button.setEnabled(False)
        self.name_status.setText("Saving…")
        wizard.run_flow(
            lambda: self.flow().set_user_name(name),
            self._save_done,
            self._save_failed,
        )

    def _save_done(self, stored: str) -> None:
        self.save_name_button.setEnabled(True)
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.setup_result["user_name"] = stored
        self.name_status.setText(
            f"Saved — the cast will call you {stored}. Choose "
            "Finish to step into your first chat."
        )
        self.set_complete(True)

    def _save_failed(self, message: str) -> None:
        self.save_name_button.setEnabled(True)
        self.name_status.setText(
            f"That name did not save: {message}. Try a shorter, "
            "single-line name."
        )
        self.set_complete(False)


class SetupWizard(QWizard):
    """The R-05 First-Run Setup wizard dialog."""

    setup_completed = Signal(dict)

    def __init__(self, client: RunmalClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flow = WizardFlow(client)
        self._client = client
        self._workers: list = []
        self.setup_result: dict = {}
        self.setWindowTitle("Rúnmál — First-Run Setup")
        self.resize(560, 520)
        self.connect_page = ConnectPage()
        self.prove_page = ProvePage()
        self.meet_page = MeetPage()
        self.name_page = NamePage()
        self.setPage(PAGE_CONNECT, self.connect_page)
        self.setPage(PAGE_PROVE, self.prove_page)
        self.setPage(PAGE_MEET, self.meet_page)
        self.setPage(PAGE_NAME, self.name_page)
        self.setStartId(PAGE_CONNECT)

    def run_flow(self, fn, on_result, on_error) -> None:
        """Run one flow call off the GUI thread (workers pattern)."""
        worker = run_async(fn, on_result, on_error)
        self._workers.append(worker)

    def accept(self) -> None:  # noqa: D102 (Qt override)
        super().accept()
        self.setup_completed.emit(dict(self.setup_result))
