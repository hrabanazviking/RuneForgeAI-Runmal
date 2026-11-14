"""R-06 acceptance (Chat Stage widgets): the real QMainWindow's
stage — open a chat and see its greeting, create through the New
Chat dialog's character picker, send a composed turn from the
composer and watch it land, rename through its dialog, delete
through its confirmation box, export to a file — plus the Session
dock's real values and the R-07 placeholder honesty.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on the
fleet devices' R-01 environments, offscreen. The engine behind the
window is a MockTransport stand-in; the live engine in the real
window is scripts/desktop_r06_proof.py.
"""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client import DesktopSession, RunmalClient  # noqa: E402
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.window import MainWindow  # noqa: E402

TOKEN = "R06-WINDOW-CREDENTIAL"
GREETING = "Well met, traveller. The pass is open."


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
    """Just the roads the stage drives, in-memory."""

    def __init__(self):
        self.profiles = {
            "p1": {"id": "p1", "name": "Demo mode", "chat_backend": "fake",
                   "chat_model": "fake-1", "embedding_backend": "",
                   "embedding_model": "", "has_chat_secret": False,
                   "has_embedding_secret": False, "config": {}}
        }
        self.characters = {
            "k1": {"id": "k1", "name": "Gate Keeper", "has_avatar": False}
        }
        self.presets = {
            "s1": {"id": "s1", "name": "Storyteller", "params": {}}
        }
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self._seq = 100

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        if path == "/api/v1/backend-profiles":
            return httpx.Response(200, json=list(self.profiles.values()))
        if path == "/api/v1/characters":
            return httpx.Response(200, json=list(self.characters.values()))
        if path.startswith("/api/v1/characters/"):
            character = self.characters.get(path.rsplit("/", 1)[1])
            if character is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=character)
        if path == "/api/v1/presets":
            return httpx.Response(200, json=list(self.presets.values()))
        if path.startswith("/api/v1/presets/"):
            preset = self.presets.get(path.rsplit("/", 1)[1])
            if preset is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=preset)
        if path == "/api/v1/chats" and request.method == "POST":
            cid = self._id("c")
            chat = {"id": cid, "title": body.get("title", ""),
                    "character_id": body.get("character_id"),
                    "backend_profile_id": None, "preset_id": None,
                    "message_count": 0}
            self.chats[cid] = chat
            self.messages[cid] = []
            if chat["character_id"] in self.characters:
                self.messages[cid].append({
                    "id": self._id("m"), "role": "assistant",
                    "content": GREETING, "speaker_name": "Gate Keeper",
                })
            return httpx.Response(201, json=chat)
        if path == "/api/v1/chats" and request.method == "GET":
            return httpx.Response(200, json=list(self.chats.values()))
        if path.startswith("/api/v1/chats/"):
            rest = path[len("/api/v1/chats/"):]
            cid, _, tail = rest.partition("/")
            chat = self.chats.get(cid)
            if chat is None:
                return httpx.Response(404, json={"detail": "chat not found"})
            if tail == "" and request.method == "GET":
                return httpx.Response(200, json=chat)
            if tail == "" and request.method == "PATCH":
                chat["title"] = body.get("title", chat["title"])
                return httpx.Response(200, json=chat)
            if tail == "" and request.method == "DELETE":
                del self.chats[cid]
                return httpx.Response(200, json={"deleted": True, "id": cid})
            if tail == "messages" and request.method == "GET":
                return httpx.Response(200, json=self.messages[cid])
            if tail == "messages" and request.method == "POST":
                message = {"id": self._id("m"), "role": body.get("role", ""),
                           "content": body.get("content", ""),
                           "speaker_name": None}
                self.messages[cid].append(message)
                return httpx.Response(201, json=message)
            if tail == "export":
                return httpx.Response(200, json={
                    "format": "runmal-chat", "version": 1,
                    "chat": {"id": chat["id"], "title": chat["title"],
                             "character_id": chat["character_id"]},
                    "messages": list(self.messages[cid]),
                })
            if tail == "persona":
                persona = None
                if chat["character_id"] in self.characters:
                    persona = {"character_id": chat["character_id"],
                               "name": "Gate Keeper"}
                return httpx.Response(
                    200, json={"chat_id": cid, "persona": persona})
            if tail == "backend-profile":
                chat["backend_profile_id"] = body.get("profile_id")
                return httpx.Response(200, json=chat)
            if tail == "preset":
                chat["preset_id"] = body.get("preset_id")
                return httpx.Response(200, json=chat)
        if path == "/api/v1/generate" and request.method == "POST":
            sse = (
                'data: {"type": "token", "text": "Rúnmál "}\n\n'
                'data: {"type": "token", "text": "hears you."}\n\n'
                'data: {"type": "done", "finish_reason": "stop"}\n\n'
            )
            return httpx.Response(
                200, content=sse.encode(),
                headers={"content-type": "text/event-stream",
                         "x-backend-key": "fake",
                         "x-generation-mode": "composed"},
            )
        if path == "/api/v1/generate/cancel":
            return httpx.Response(200, json={"cancelled": True})
        return httpx.Response(404, json={"detail": "not found"})


def make_window(qapp):
    engine = MiniEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    window = MainWindow(EngineHandle(), client=client)
    window.show()
    qapp.processEvents()
    return window, client, engine


def test_stage_structure_and_honest_placeholders(qapp) -> None:
    window, _client, _engine = make_window(qapp)
    try:
        assert window.message_view.objectName() == "messageView"
        assert window.composer_edit.objectName() == "composerEdit"
        assert window.send_button.text() == "Send"
        assert window.stop_button.text() == "Stop"
        # No chat open: composer asleep, stop disabled.
        assert window.send_button.isEnabled() is False
        assert window.stop_button.isEnabled() is False
        assert "No chat open" in window.chat_stage_status.text()
        # R-07 has since LANDED: Regenerate/Continue are real
        # actions now, no longer placeholders (R-07 slice note).
        assert "Regenerate" not in window.placeholder_actions
        assert "Continue" not in window.placeholder_actions
        assert window.action_regenerate.text() == "Regenerate"
        # Stop Generating is REAL now (not a placeholder).
        assert "Stop Generating" not in window.placeholder_actions
        assert window.action_stop_generating.text() == "Stop Generating"
        assert window.action_new_chat.text() == "New Chat"
    finally:
        window.close()


def test_create_open_send_rename_export_delete(qapp, tmp_path) -> None:
    window, client, engine = make_window(qapp)
    try:
        window.refresh_blocking()

        # --- New Chat through the dialog's character picker.
        dialog = window.open_new_chat_dialog()
        assert dialog.isVisible()
        dialog.select_character("k1")
        dialog.title_edit.setText("Gate chat")
        dialog.accept()
        assert wait_for(qapp, lambda: window.current_chat_id is not None)
        chat_id = window.current_chat_id
        assert GREETING in window.message_view.toPlainText()
        assert window.stage_title.text() == "Chat with Gate Keeper"
        # Session dock: real values from the mock engine's data.
        assert "Gate Keeper" in window.session_character_label.text()
        assert "Gate Keeper" in window.session_persona_label.text()
        assert "engine default" in window.session_profile_label.text()
        assert window.session_preset_label.text() == "Preset: No preset applied"
        assert window.send_button.isEnabled() is True

        # Pin the Demo profile + preset; the dock follows real data.
        client.set_chat_backend_profile(chat_id, "p1")
        client.set_chat_preset(chat_id, "s1")
        window.open_chat_blocking(chat_id)
        assert "Demo mode" in window.session_profile_label.text()
        assert window.session_model_label.text() == "Model: fake-1"
        assert window.session_preset_label.text() == "Preset: Storyteller"

        # --- Send from the composer; the composed reply lands.
        window.composer_edit.setPlainText("I seek passage.")
        window.send_button.click()
        assert wait_for(
            qapp,
            lambda: "Rúnmál hears you." in window.message_view.toPlainText()
            and not window._streaming,
        )
        history = client.list_chat_messages(chat_id)
        assert [m.role for m in history] == ["assistant", "user", "assistant"]
        assert "saved" in window.chat_stage_status.text()

        # --- Rename through its dialog.
        rename = window.open_rename_dialog()
        assert rename is not None and rename.isVisible()
        rename.title_edit.setText("The Pass Chat")
        rename.accept()
        assert wait_for(
            qapp,
            lambda: any(
                window.chats_list.item(i).text() == "The Pass Chat"
                for i in range(window.chats_list.count())
            ),
        )

        # --- Export to a real file.
        target = tmp_path / "pass-chat.json"
        window.export_chat_to_path(chat_id, str(target))
        document = json.loads(target.read_text(encoding="utf-8"))
        assert document["chat"]["title"] == "The Pass Chat"
        assert len(document["messages"]) == 3

        # --- Delete through the confirmation box.
        box = window.confirm_delete_selected_chat()
        assert box is not None and box.isVisible()
        delete_button = next(
            b for b in box.buttons() if b.text() == "Delete"
        )
        box.buttonClicked.emit(delete_button)
        assert wait_for(
            qapp,
            lambda: window.current_chat_id is None
            and window.chats_list.count() == 0,
        )
        assert "none open" in window.session_chat_label.text()
        assert client.list_chats() == []
    finally:
        window.close()


def test_open_existing_chat_from_dock_list(qapp) -> None:
    window, client, _engine = make_window(qapp)
    try:
        first = window.create_chat_blocking(character_id="k1", title="One")
        second = window.create_chat_blocking(character_id=None, title="Two")
        assert window.current_chat_id == second.chat.id
        # Clicking the first chat's dock row opens it again.
        for index in range(window.chats_list.count()):
            item = window.chats_list.item(index)
            if item.text() == "One":
                window.chats_list.itemClicked.emit(item)
                break
        assert wait_for(qapp, lambda: window.current_chat_id == first.chat.id)
        assert GREETING in window.message_view.toPlainText()
        assert isinstance(window, MainWindow)
    finally:
        window.close()
