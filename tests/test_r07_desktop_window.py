"""R-07 acceptance (Chat Stage II widgets): the real QMainWindow's
message actions — edit through its dialog, swipe ◀ ▶ + the swipes
dialog, pin toggle, branch through its dialog, Author's Note
editor, search dialog, checkpoints & undo dialog, regenerate and
continue and impersonate through the window's own roads.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on the
fleet devices' R-01 environments, offscreen. The engine behind the
window is a MockTransport stand-in; the live engine in the real
window is scripts/desktop_r07_proof.py.
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

TOKEN = "r07-window-token"
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
    """The R-06 roads plus the R-07 chats roads, in-memory."""

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
        self.notes: dict[str, dict] = {}
        self.pinned: dict[str, set] = {}
        self.checkpoints: dict[str, list[dict]] = {}
        self.journal: dict[str, list[dict]] = {}
        self._seq = 100

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _public(self, cid, message):
        message["content"] = message["swipes"][message["swipe_id"]]
        message["pinned"] = message["id"] in self.pinned.get(cid, set())
        return {
            "id": message["id"], "role": message["role"],
            "content": message["content"],
            "speaker_name": message["speaker_name"],
            "swipes": list(message["swipes"]),
            "swipe_id": message["swipe_id"],
            "swipe_count": len(message["swipes"]),
            "pinned": message["pinned"],
        }

    def _new_message(self, role, content, speaker_name=None):
        return {
            "id": self._id("m"), "role": role, "content": content,
            "speaker_name": speaker_name, "swipes": [content], "swipe_id": 0,
            "pinned": False,
        }

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
        if path == "/api/v1/chats/search":
            query = request.url.params.get("q", "")
            results = []
            for cid, messages in self.messages.items():
                for ordinal, message in enumerate(messages):
                    if query.lower() in message["content"].lower():
                        results.append({
                            "chat_id": cid,
                            "chat_title": self.chats[cid]["title"],
                            "message_id": message["id"],
                            "role": message["role"],
                            "snippet": message["content"],
                            "ordinal": ordinal,
                        })
            return httpx.Response(200, json={
                "query": query, "mode_used": "fulltext",
                "fallback_reason": None, "total": len(results),
                "results": results,
            })
        if path == "/api/v1/chats" and request.method == "POST":
            cid = self._id("c")
            chat = {"id": cid, "title": body.get("title", ""),
                    "character_id": body.get("character_id"),
                    "backend_profile_id": None, "preset_id": None,
                    "message_count": 0}
            self.chats[cid] = chat
            self.messages[cid] = []
            self.notes[cid] = {
                "text": "", "depth": 4, "frequency": 1,
                "enabled": True, "role": "system",
            }
            self.pinned[cid] = set()
            self.checkpoints[cid] = []
            self.journal[cid] = []
            if chat["character_id"] in self.characters:
                self.messages[cid].append(
                    self._new_message("assistant", GREETING, "Gate Keeper")
                )
                chat["message_count"] = 1
            return httpx.Response(201, json=chat)
        if path == "/api/v1/chats" and request.method == "GET":
            return httpx.Response(200, json=list(self.chats.values()))
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
        if path.startswith("/api/v1/chats/"):
            rest = path[len("/api/v1/chats/"):]
            cid, _, tail = rest.partition("/")
            chat = self.chats.get(cid)
            if chat is None:
                return httpx.Response(404, json={"detail": "chat not found"})
            return self._chat_road(request, cid, chat, tail, body)
        return httpx.Response(404, json={"detail": "not found"})

    def _chat_road(self, request, cid, chat, tail, body):
        messages = self.messages[cid]
        if tail == "" and request.method == "GET":
            return httpx.Response(200, json=chat)
        if tail == "" and request.method == "PATCH":
            chat["title"] = body.get("title", chat["title"])
            return httpx.Response(200, json=chat)
        if tail == "" and request.method == "DELETE":
            del self.chats[cid]
            return httpx.Response(200, json={"deleted": True, "id": cid})
        if tail == "messages" and request.method == "GET":
            return httpx.Response(
                200, json=[self._public(cid, m) for m in messages]
            )
        if tail == "messages" and request.method == "POST":
            message = self._new_message(body.get("role", ""), body.get("content", ""))
            messages.append(message)
            chat["message_count"] = len(messages)
            self.journal[cid].append({
                "id": self._id("u"), "operation": "message.append",
                "detail": "append", "_undo": ("append", message["id"]),
            })
            return httpx.Response(201, json=self._public(cid, message))
        if tail == "persona":
            persona = None
            if chat["character_id"] in self.characters:
                persona = {"character_id": chat["character_id"],
                           "name": "Gate Keeper"}
            return httpx.Response(200, json={"chat_id": cid, "persona": persona})
        if tail == "backend-profile":
            chat["backend_profile_id"] = body.get("profile_id")
            return httpx.Response(200, json=chat)
        if tail == "preset":
            chat["preset_id"] = body.get("preset_id")
            return httpx.Response(200, json=chat)
        if tail == "export":
            return httpx.Response(200, json={
                "format": "runmal-chat", "version": 1,
                "chat": {"id": chat["id"], "title": chat["title"],
                         "character_id": chat["character_id"]},
                "messages": [self._public(cid, m) for m in messages],
            })
        if tail == "authors-note":
            if request.method == "GET":
                return httpx.Response(200, json=self.notes[cid])
            self.notes[cid] = {
                "text": body.get("text", ""), "depth": body.get("depth", 4),
                "frequency": body.get("frequency", 1),
                "enabled": body.get("enabled", True),
                "role": body.get("role", "system"),
            }
            return httpx.Response(200, json=chat)
        if tail == "branches" and request.method == "POST":
            new_id = self._id("c")
            source = messages
            if body.get("message_id"):
                cut = next(
                    i for i, m in enumerate(source)
                    if m["id"] == body["message_id"]
                )
                source = source[: cut + 1]
            self.chats[new_id] = {
                "id": new_id, "title": body.get("name") or "Branch",
                "character_id": chat["character_id"],
                "backend_profile_id": None, "preset_id": None,
                "message_count": len(source),
            }
            self.messages[new_id] = [
                dict(m, swipes=list(m["swipes"])) for m in source
            ]
            self.notes[new_id] = dict(self.notes[cid])
            self.pinned[new_id] = set()
            self.checkpoints[new_id] = []
            self.journal[new_id] = []
            return httpx.Response(201, json=self.chats[new_id])
        if tail == "continue":
            last = messages[-1]
            if last["role"] == "assistant":
                last["swipes"][last["swipe_id"]] += " And onward."
                return httpx.Response(201, json={
                    "chat_id": cid, "kind": "continue", "mode": "extend",
                    "content": " And onward.", "backend": "fake",
                    "message": self._public(cid, last),
                })
            message = self._new_message("assistant", "A new step.")
            messages.append(message)
            return httpx.Response(201, json={
                "chat_id": cid, "kind": "continue", "mode": "next",
                "content": "A new step.", "backend": "fake",
                "message": self._public(cid, message),
            })
        if tail == "impersonate":
            return httpx.Response(201, json={
                "id": "draft1", "chat_id": cid, "kind": "impersonate",
                "status": "draft", "draft": True, "role": "user",
                "content": "I will go on, then.", "message_id": None,
                "backend": "fake",
            })
        if tail == "impersonate/accept":
            message = self._new_message("user", body.get("content", ""))
            messages.append(message)
            return httpx.Response(201, json=self._public(cid, message))
        if tail == "impersonate/discard":
            return httpx.Response(200, json={"discarded": True, "chat_id": cid})
        if tail == "pinned-messages":
            return httpx.Response(200, json=[
                self._public(cid, m) for m in messages
                if m["id"] in self.pinned[cid]
            ])
        if tail == "checkpoints":
            if request.method == "GET":
                return httpx.Response(200, json=[
                    {k: v for k, v in c.items() if k != "_snapshot"}
                    for c in self.checkpoints[cid]
                ])
            checkpoint = {
                "id": self._id("k"), "name": body.get("name") or "Checkpoint 1",
                "created_at": "2026-11-14T00:00:00+00:00",
                "message_count": len(messages),
                "chat_title": chat["title"],
                "_snapshot": [dict(m, swipes=list(m["swipes"])) for m in messages],
            }
            self.checkpoints[cid].append(checkpoint)
            public = {k: v for k, v in checkpoint.items() if k != "_snapshot"}
            return httpx.Response(201, json=public)
        if tail.startswith("checkpoints/"):
            parts = tail.split("/")
            checkpoint = next(
                (c for c in self.checkpoints[cid] if c["id"] == parts[1]), None
            )
            if checkpoint is None:
                return httpx.Response(404, json={"detail": "not found"})
            if len(parts) == 2 and request.method == "DELETE":
                self.checkpoints[cid].remove(checkpoint)
                return httpx.Response(
                    200, json={"deleted": True, "id": parts[1]}
                )
            if len(parts) == 3 and parts[2] == "restore":
                new_id = self._id("c")
                snapshot = checkpoint["_snapshot"]
                self.chats[new_id] = {
                    "id": new_id, "title": body.get("name") or checkpoint["name"],
                    "character_id": chat["character_id"],
                    "backend_profile_id": None, "preset_id": None,
                    "message_count": len(snapshot),
                }
                self.messages[new_id] = [
                    dict(m, swipes=list(m["swipes"])) for m in snapshot
                ]
                self.notes[new_id] = dict(self.notes[cid])
                self.pinned[new_id] = set()
                self.checkpoints[new_id] = []
                self.journal[new_id] = []
                return httpx.Response(201, json=self.chats[new_id])
        if tail == "undo":
            if request.method == "GET":
                entries = [
                    {"id": e["id"], "operation": e["operation"],
                     "detail": e["detail"], "created_at": "",
                     "message_count": 0}
                    for e in reversed(self.journal[cid])
                ]
                return httpx.Response(200, json={
                    "entries": entries, "count": len(entries),
                    "can_undo": bool(entries),
                })
            if not self.journal[cid]:
                return httpx.Response(404, json={"detail": "nothing to undo"})
            entry = self.journal[cid].pop()
            kind, payload = entry["_undo"]
            if kind == "delete":
                messages.insert(min(payload[0], len(messages)), payload[1])
            elif kind == "append":
                self.messages[cid] = [
                    m for m in messages if m["id"] != payload
                ]
            return httpx.Response(
                200, json={"undone": entry["operation"], "chat_id": cid}
            )
        if tail.startswith("messages/"):
            parts = tail.split("/")
            message = next(
                (m for m in messages if m["id"] == parts[1]), None
            )
            if message is None:
                return httpx.Response(404, json={"detail": "message not found"})
            if len(parts) == 2 and request.method == "PATCH":
                message["swipes"][message["swipe_id"]] = body.get("content", "")
                return httpx.Response(200, json=self._public(cid, message))
            if len(parts) == 2 and request.method == "DELETE":
                index = messages.index(message)
                removed = messages.pop(index)
                self.journal[cid].append({
                    "id": self._id("u"), "operation": "message.delete",
                    "detail": "delete", "_undo": ("delete", (index, removed)),
                })
                return httpx.Response(
                    200, json={"deleted": True, "id": parts[1]}
                )
            if parts[2:] == ["swipes"] and request.method == "POST":
                # P-065: the new alternate becomes the active one.
                message["swipes"].append(body.get("content", ""))
                message["swipe_id"] = len(message["swipes"]) - 1
                return httpx.Response(201, json=self._public(cid, message))
            if parts[2:] == ["swipes", "select"]:
                if body.get("index") is not None:
                    message["swipe_id"] = body["index"]
                elif body.get("action") == "next":
                    message["swipe_id"] = min(
                        message["swipe_id"] + 1, len(message["swipes"]) - 1
                    )
                elif body.get("action") == "prev":
                    message["swipe_id"] = max(message["swipe_id"] - 1, 0)
                return httpx.Response(200, json=self._public(cid, message))
            if len(parts) == 4 and parts[2] == "swipes" and request.method == "DELETE":
                message["swipes"].pop(int(parts[3]))
                message["swipe_id"] = min(
                    message["swipe_id"], len(message["swipes"]) - 1
                )
                return httpx.Response(200, json=self._public(cid, message))
            if parts[2:] == ["pin"]:
                if request.method == "POST":
                    self.pinned[cid].add(parts[1])
                    return httpx.Response(201, json={"id": "mem1"})
                self.pinned[cid].discard(parts[1])
                return httpx.Response(
                    200, json={"unpinned": True, "id": parts[1]}
                )
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


def open_seeded_chat(qapp, window):
    """Create a greeted chat through the dialog and send one turn."""
    window.refresh_blocking()
    dialog = window.open_new_chat_dialog()
    dialog.select_character("k1")
    dialog.accept()
    assert wait_for(qapp, lambda: window.current_chat_id is not None)
    window.composer_edit.setPlainText("I seek passage.")
    window.send_button.click()
    assert wait_for(
        qapp,
        lambda: "Rúnmál hears you." in window.message_view.toPlainText()
        and not window._streaming,
    )
    return window.current_chat_id


def select_message(window, index: int) -> None:
    window.message_list.setCurrentRow(index)
    window._update_message_chrome()


def test_stage_ii_structure_is_real(qapp) -> None:
    window, _client, _engine = make_window(qapp)
    try:
        # R-07 controls exist and are NOT placeholders any more.
        assert "Regenerate" not in window.placeholder_actions
        assert "Continue" not in window.placeholder_actions
        assert "Undo" not in window.placeholder_actions
        assert window.action_regenerate.text() == "Regenerate"
        assert window.action_continue.text() == "Continue"
        assert window.message_list.objectName() == "messageList"
        assert window.edit_message_button.text() == "Edit…"
        assert window.pin_button.text() in ("Pin", "Unpin")
        # Nothing open: the R-07 chat actions sleep.
        assert window.regenerate_button.isEnabled() is False
        assert window.edit_message_button.isEnabled() is False
    finally:
        window.close()


def test_message_actions_drive_the_window(qapp) -> None:
    window, client, _engine = make_window(qapp)
    try:
        chat_id = open_seeded_chat(qapp, window)
        assert window.message_list.count() == 3

        # Edit the user line through its dialog.
        select_message(window, 1)
        dialog = window.open_edit_message_dialog()
        assert dialog is not None and dialog.isVisible()
        dialog.text_edit.setPlainText("I seek the high pass.")
        dialog.accept()
        assert wait_for(
            qapp,
            lambda: "high pass" in window.message_view.toPlainText(),
        )
        history = client.list_chat_messages(chat_id)
        assert history[1].content == "I seek the high pass."

        # Give the greeting a second swipe (client road; P-065:
        # the new alternate becomes active), then walk back with
        # the window's own ◀ button and work the swipes dialog.
        greeting = history[0]
        client.add_swipe(chat_id, greeting.id, "Well met. State your name.")
        window.open_chat_blocking(chat_id)
        assert "State your name" in window.message_view.toPlainText()
        select_message(window, 0)
        assert window.swipe_prev_button.isEnabled()
        window.swipe_prev_button.click()
        assert wait_for(
            qapp,
            lambda: client.list_chat_messages(chat_id)[0].content == GREETING,
        )
        swipe_dialog = window.open_swipe_dialog()
        assert swipe_dialog is not None and swipe_dialog.isVisible()
        assert swipe_dialog.swipe_list.count() == 2
        swipe_dialog.swipe_list.setCurrentRow(1)
        swipe_dialog.select_button.click()
        assert wait_for(
            qapp,
            lambda: client.list_chat_messages(chat_id)[0].content
            == "Well met. State your name.",
        )
        swipe_dialog.swipe_list.setCurrentRow(1)
        swipe_dialog.delete_button.click()
        assert wait_for(
            qapp, lambda: swipe_dialog.swipe_list.count() == 1
        )
        swipe_dialog.close()
        qapp.processEvents()

        # Pin the reply; the button flips to Unpin with words.
        window.open_chat_blocking(chat_id)
        select_message(window, 2)
        window.pin_button.click()
        assert wait_for(qapp, lambda: window.pin_button.text() == "Unpin")
        assert [m.id for m in client.list_pinned_messages(chat_id)] == [
            client.list_chat_messages(chat_id)[2].id
        ]
        assert "pinned" in window.message_view.toPlainText()

        # Copy puts the exact text on the clipboard.
        from PySide6.QtWidgets import QApplication as _App

        copied = window.copy_selected_message()
        assert copied == "Rúnmál hears you."
        assert _App.clipboard().text() == "Rúnmál hears you."

        # Delete the user line through its confirmation box; the
        # journal then restores it through the checkpoints dialog
        # state (undo entries exist).
        select_message(window, 1)
        box = window.confirm_delete_selected_message()
        assert box is not None and box.isVisible()
        delete_button = next(b for b in box.buttons() if b.text() == "Delete")
        box.buttonClicked.emit(delete_button)
        assert wait_for(qapp, lambda: window.message_list.count() == 2)
        assert len(client.list_chat_messages(chat_id)) == 2
        window.undo_blocking()
        assert len(client.list_chat_messages(chat_id)) == 3
    finally:
        window.close()


def test_chat_actions_drive_the_window(qapp) -> None:
    window, client, _engine = make_window(qapp)
    try:
        chat_id = open_seeded_chat(qapp, window)

        # Author's Note through its dialog.
        window.open_authors_note_dialog()
        assert wait_for(qapp, lambda: window._note_dialog is not None)
        note_dialog = window._note_dialog
        note_dialog.text_edit.setPlainText("The keeper is terse.")
        note_dialog.accept()
        assert wait_for(
            qapp, lambda: client.get_authors_note(chat_id).text
            == "The keeper is terse."
        )

        # Continue extends the last reply in the window.
        outcome = window.continue_blocking()
        assert outcome.mode == "extend"
        assert "And onward." in window.message_view.toPlainText()

        # Impersonate: draft in its dialog, accept lands a user line.
        window.open_impersonate()
        assert wait_for(qapp, lambda: window._impersonate_dialog is not None)
        imp_dialog = window._impersonate_dialog
        assert imp_dialog.text() == "I will go on, then."
        imp_dialog.accept_button.click()
        assert wait_for(
            qapp,
            lambda: client.list_chat_messages(chat_id)[-1].role == "user",
        )

        # Regenerate replaces the (now last) reply only after a
        # fresh user turn — send one, then regenerate it.
        window.composer_edit.setPlainText("Open the gate.")
        window.send_button.click()
        assert wait_for(qapp, lambda: not window._streaming)
        result = window.regenerate_blocking()
        assert result.landed is True
        history = client.list_chat_messages(chat_id)
        assert history[-1].content == "Rúnmál hears you."

        # Branch from the first message through its dialog: the
        # window lands in the new chat; the source is untouched.
        window.open_chat_blocking(chat_id)
        select_message(window, 0)
        branch_dialog = window.open_branch_dialog()
        assert branch_dialog is not None and branch_dialog.isVisible()
        branch_dialog.title_edit.setText("The other road")
        branch_dialog.accept()
        assert wait_for(
            qapp,
            lambda: window.current_chat_id not in (None, chat_id),
        )
        branch_id = window.current_chat_id
        assert len(client.list_chat_messages(branch_id)) == 1
        assert len(client.list_chat_messages(chat_id)) == len(history)

        # Search dialog finds the seeded line and lists the hit.
        search_dialog = window.open_search_dialog()
        search_dialog.query_edit.setText("traveller")
        search_dialog.run_search()
        assert wait_for(
            qapp, lambda: search_dialog.results_list.count() >= 1
        )
        assert "match" in search_dialog.results_label.text()
        search_dialog.close()

        # Checkpoints dialog: create + undo state surface.
        window.open_chat_blocking(chat_id)
        cp_dialog = window.open_checkpoints_dialog()
        assert cp_dialog is not None
        assert wait_for(
            qapp, lambda: cp_dialog.undo_list.count() >= 0
        )
        checkpoints, entries = window.checkpoints_state_blocking()
        assert entries, "appends must be journaled in the mock too"
        created = window.create_checkpoint_blocking("Before the storm")
        assert created.message_count == len(history)
        restored = window.restore_checkpoint_blocking(created.id)
        assert restored.id != chat_id
        assert window.current_chat_id == restored.id
    finally:
        window.close()
