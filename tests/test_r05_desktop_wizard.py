"""R-05 acceptance (wizard dialog + window wiring): the QWizard's
four pages, the honest Demo labelling, and a full programmatic
drive — connect Demo, prove, create a character, save a name,
finish — against a MockTransport engine, plus the main window's
wizard opening and completion landing.

Skips cleanly when PySide6 is absent (R-04 pattern). The live
end-to-end in the real window is scripts/desktop_r05_proof.py.
"""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWizard  # noqa: E402

from runmal.desktop.client import DesktopSession, RunmalClient  # noqa: E402
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.window import MainWindow  # noqa: E402
from runmal.desktop.wizard import (  # noqa: E402
    PAGE_CONNECT,
    PAGE_MEET,
    PAGE_NAME,
    PAGE_PROVE,
    SetupWizard,
)

TOKEN = "R05-WIZARD-TEST"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_for(qapp, predicate, timeout=10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


class MiniEngine:
    """Just the roads the wizard drives, in-memory."""

    def __init__(self):
        self.profiles = {}
        self.user_name = ""
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        if path == "/api/v1/backend-profiles" and request.method == "POST":
            pid = self._id("p")
            profile = {
                "id": pid, "name": body.get("name", ""),
                "chat_backend": body.get("chat_backend", ""),
                "chat_model": body.get("chat_model", ""),
                "has_chat_secret": False, "has_embedding_secret": False,
                "config": body.get("config") or {},
            }
            self.profiles[pid] = profile
            return httpx.Response(201, json=profile)
        if path.startswith("/api/v1/backend-profiles/"):
            rest = path[len("/api/v1/backend-profiles/"):]
            pid, _, tail = rest.partition("/")
            profile = self.profiles.get(pid)
            if profile is None:
                return httpx.Response(404, json={"detail": "not found"})
            if tail == "health":
                return httpx.Response(200, json={
                    "profile_id": pid, "backend": "fake", "ok": True,
                    "detail": "fake backend healthy", "latency_ms": 0.0,
                })
            if tail == "models":
                return httpx.Response(200, json={
                    "profile_id": pid, "backend": "fake",
                    "models": [{"model_id": "fake-1"}],
                })
            if request.method == "PATCH":
                profile.update(body)
                return httpx.Response(200, json=profile)
            return httpx.Response(200, json=profile)
        if path == "/api/v1/characters" and request.method == "POST":
            card = body.get("card") or {}
            return httpx.Response(201, json={
                "id": "k1", "name": card.get("name", ""),
            })
        if path == "/api/v1/characters":
            return httpx.Response(200, json=[{"id": "k1", "name": "Gate Keeper"}])
        if path == "/api/v1/chats" and request.method == "POST":
            return httpx.Response(201, json={
                "id": "c1", "title": body.get("title", ""),
                "character_id": body.get("character_id"),
                "backend_profile_id": None, "message_count": 1,
            })
        if path == "/api/v1/chats/c1/backend-profile":
            return httpx.Response(200, json={
                "id": "c1", "title": "First chat with Gate Keeper",
                "character_id": "k1", "backend_profile_id": body.get("profile_id"),
                "message_count": 1,
            })
        if path == "/api/v1/chats/c1/messages":
            return httpx.Response(200, json=[{
                "id": "m1", "role": "assistant",
                "content": "Well met, traveller.", "speaker_name": None,
            }])
        if path == "/api/v1/user-name":
            if request.method == "PUT":
                self.user_name = body.get("user_name", "")
            return httpx.Response(200, json={
                "user_name": self.user_name or "User",
                "is_set": bool(self.user_name),
            })
        return httpx.Response(404, json={"detail": "not found"})


def make_client(engine=None) -> RunmalClient:
    engine = engine or MiniEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http)


def test_wizard_structure_and_demo_honesty(qapp) -> None:
    wizard = SetupWizard(make_client())
    wizard.show()
    try:
        assert wizard.windowTitle() == "Rúnmál — First-Run Setup"
        assert wizard.pageIds() == [PAGE_CONNECT, PAGE_PROVE, PAGE_MEET, PAGE_NAME]
        assert wizard.startId() == PAGE_CONNECT
        assert wait_for(qapp, lambda: wizard.currentId() == PAGE_CONNECT)
        demo = wizard.connect_page.kind_buttons["fake"]
        assert "not a real model" in demo.text().lower()
        assert wizard.connect_page.isComplete() is False
        assert wizard.meet_page.create_radio.isChecked() is True
    finally:
        wizard.close()


def test_wizard_full_drive_demo_to_greeted_chat(qapp) -> None:
    wizard = SetupWizard(make_client())
    completed: list[dict] = []
    wizard.setup_completed.connect(completed.append)
    wizard.show()
    try:
        # Step 1: Demo, honestly labelled, connects.
        wizard.connect_page.kind_buttons["fake"].setChecked(True)
        wizard.connect_page.connect_button.click()
        assert wait_for(qapp, wizard.connect_page.isComplete)
        assert "canned responder" in wizard.connect_page.connect_status.text()

        wizard.button(QWizard.WizardButton.NextButton).click()
        assert wizard.currentId() == PAGE_PROVE
        # Step 2 auto-proves on entry.
        assert wait_for(qapp, wizard.prove_page.isComplete)
        assert wizard.prove_page.prove_status.text().startswith("Reachable")

        wizard.button(QWizard.WizardButton.NextButton).click()
        assert wizard.currentId() == PAGE_MEET
        # Step 3: create the character; the greeted chat lands.
        wizard.meet_page.char_name_edit.setText("Gate Keeper")
        wizard.meet_page.char_description_edit.setPlainText("Guards the pass.")
        wizard.meet_page.char_personality_edit.setText("Calm.")
        wizard.meet_page.char_greeting_edit.setPlainText("Well met, traveller.")
        wizard.meet_page.meet_button.click()
        assert wait_for(qapp, wizard.meet_page.isComplete)
        assert wizard.setup_result["chat_id"] == "c1"
        assert wizard.setup_result["character_name"] == "Gate Keeper"
        assert "Well met, traveller." in wizard.meet_page.greeting_preview.text()

        wizard.button(QWizard.WizardButton.NextButton).click()
        assert wizard.currentId() == PAGE_NAME
        # Step 4: save the name, then Finish.
        assert wait_for(
            qapp, lambda: wizard.name_page.user_name_edit.text() == "User"
        )
        wizard.name_page.user_name_edit.setText("Volmarr")
        wizard.name_page.save_name_button.click()
        assert wait_for(qapp, wizard.name_page.isComplete)
        wizard.button(QWizard.WizardButton.FinishButton).click()
        assert wait_for(qapp, lambda: bool(completed))
        assert completed[0]["user_name"] == "Volmarr"
        assert completed[0]["chat_id"] == "c1"
    finally:
        wizard.close()


def test_window_opens_wizard_and_lands_completion(qapp) -> None:
    handle = EngineHandle()
    window = MainWindow(handle, client=make_client())
    try:
        wizard = window.open_setup_wizard()
        assert wizard.isVisible()
        assert window.open_setup_wizard() is wizard  # raises, not dupes
        wizard.close()

        window._on_setup_completed({
            "chat_id": "c1",
            "character_name": "Gate Keeper",
            "greeting": "Well met, traveller.",
        })
        assert window.setup_chat_id == "c1"
        assert window.stage_title.text() == "Chat with Gate Keeper"
        assert "Well met" in window.stage_body.text()
        assert window.first_run_banner.isVisible() is False
    finally:
        window.close()
