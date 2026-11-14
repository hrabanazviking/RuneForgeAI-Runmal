"""R-08 acceptance (Characters widgets): the real QMainWindow's
library dock (search / favourites) and the full card editor
dialog — create-from-scratch through the dialog, edit + save,
greetings editor, duplicate, delete-with-undo through its
confirmation box, and chatting with an editor-made character.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on the
fleet devices' R-01 environments, offscreen. The engine behind
the window is a MockTransport stand-in; the live engine in the
real window is scripts/desktop_r08_proof.py.
"""

import json
import os
import re
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client import DesktopSession, RunmalClient  # noqa: E402
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.window import MainWindow  # noqa: E402

TOKEN = "r08-window-token"
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


def wrapped(data: dict) -> dict:
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


class MiniEngine:
    """The characters/library/assets roads + the chat roads the
    stage needs, in-memory (a trimmed sibling of the logic
    test's FakeEngine)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.orgs: dict[str, dict] = {}
        self.assets: dict[str, list[dict]] = {}
        self.bindings: dict[str, dict] = {}
        self.lorebooks = {"lb1": {"id": "lb1", "name": "Pass Lore", "entry_count": 2}}
        self.profiles = {
            "p1": {"id": "p1", "name": "Demo mode", "chat_backend": "fake",
                   "chat_model": "fake-1", "embedding_backend": "",
                   "embedding_model": "", "has_chat_secret": False,
                   "has_embedding_secret": False, "config": {}}
        }
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self._seq = 100

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _summary(self, row):
        return {
            "id": row["id"], "name": row["name"],
            "created_at": "2026-11-14T00:00:00+00:00",
            "has_avatar": row["avatar"] is not None,
            "avatar_asset": row["avatar"],
            "version_no": row["version_no"],
            "lineage_id": row["lineage_id"], "content_hash": "x" * 64,
        }

    def _org(self, row):
        org = self.orgs.setdefault(row["id"], {
            "character_id": row["id"], "name": row["name"],
            "tags": list(row["card"]["data"].get("tags", [])),
            "is_favourite": False,
        })
        org["name"] = row["name"]
        return org

    def _create(self, card_data, name):
        card = wrapped(dict(card_data))
        for row in self.rows.values():
            if not row["deleted"] and row["name"] == name and row["card"] == card:
                return row, True
        siblings = [r for r in self.rows.values() if r["name"] == name]
        row = {
            "id": self._id("k"), "name": name, "card": card,
            "deleted": False, "avatar": None,
            "version_no": max([r["version_no"] for r in siblings], default=0) + 1,
            "lineage_id": siblings[0]["lineage_id"] if siblings else "",
        }
        if not row["lineage_id"]:
            row["lineage_id"] = row["id"]
        self.rows[row["id"]] = row
        self.assets[row["id"]] = []
        return row, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content and "json" in request.headers.get("content-type", ""):
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        if path == "/api/v1/backend-profiles":
            return httpx.Response(200, json=list(self.profiles.values()))
        if path == "/api/v1/presets":
            return httpx.Response(200, json=[])
        if path == "/api/v1/lorebooks":
            return httpx.Response(200, json=list(self.lorebooks.values()))
        if path == "/api/v1/characters" and request.method == "POST":
            row, dup = self._create(
                body.get("card", {}),
                body.get("name") or body.get("card", {}).get("name", ""),
            )
            return httpx.Response(200 if dup else 201, json=self._summary(row))
        if path == "/api/v1/characters" and request.method == "GET":
            return httpx.Response(200, json=[
                self._summary(r) for r in self.rows.values() if not r["deleted"]
            ])
        if path == "/api/v1/library/cards":
            q = (request.url.params.get("q") or "").lower()
            favourites_only = request.url.params.get("favourites_only") == "true"
            items = []
            for row in self.rows.values():
                if row["deleted"]:
                    continue
                org = self._org(row)
                if q and q not in row["name"].lower():
                    continue
                if favourites_only and not org["is_favourite"]:
                    continue
                items.append({
                    "id": row["id"], "name": row["name"],
                    "created_at": "2026-11-14T00:00:00+00:00",
                    "has_avatar": row["avatar"] is not None,
                    "tags": list(org["tags"]),
                    "is_favourite": org["is_favourite"],
                })
            return httpx.Response(200, json={"total": len(items), "items": items})
        if path == "/api/v1/library/tags":
            return httpx.Response(200, json={"tags": []})
        if path.startswith("/api/v1/library/cards/"):
            character_id = path.split("/")[5]
            row = self.rows.get(character_id)
            if row is None or row["deleted"]:
                return httpx.Response(404, json={"detail": "not found"})
            org = self._org(row)
            if path.endswith("/organisation"):
                return httpx.Response(200, json=dict(org))
            if path.endswith("/tags"):
                org["tags"] = list(body.get("tags", []))
                row["card"]["data"]["tags"] = org["tags"]
                return httpx.Response(200, json=dict(org))
            if path.endswith("/favourite"):
                org["is_favourite"] = bool(body.get("is_favourite"))
                return httpx.Response(200, json=dict(org))
        if path.startswith("/api/v1/characters/"):
            rest = path[len("/api/v1/characters/"):]
            character_id, _, tail = rest.partition("/")
            return self._character_road(request, character_id, tail, body)
        if path == "/api/v1/chats" and request.method == "POST":
            cid = self._id("c")
            chat = {"id": cid, "title": body.get("title", ""),
                    "character_id": body.get("character_id"),
                    "backend_profile_id": None, "preset_id": None,
                    "message_count": 0}
            self.chats[cid] = chat
            self.messages[cid] = []
            row = self.rows.get(chat["character_id"] or "")
            if row is not None:
                greeting = row["card"]["data"].get("first_mes", "")
                if greeting:
                    self.messages[cid].append({
                        "id": self._id("m"), "role": "assistant",
                        "content": greeting, "speaker_name": row["name"],
                        "swipes": [greeting], "swipe_id": 0, "pinned": False,
                    })
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
            return httpx.Response(200, content=sse.encode(), headers={
                "content-type": "text/event-stream",
                "x-backend-key": "fake", "x-generation-mode": "composed",
            })
        if path == "/api/v1/generate/cancel":
            return httpx.Response(200, json={"cancelled": True})
        if path.startswith("/api/v1/chats/"):
            rest = path[len("/api/v1/chats/"):]
            cid, _, tail = rest.partition("/")
            chat = self.chats.get(cid)
            if chat is None:
                return httpx.Response(404, json={"detail": "chat not found"})
            if tail == "" and request.method == "GET":
                return httpx.Response(200, json=chat)
            if tail == "messages" and request.method == "GET":
                return httpx.Response(200, json=self.messages[cid])
            if tail == "messages" and request.method == "POST":
                message = {
                    "id": self._id("m"), "role": body.get("role", ""),
                    "content": body.get("content", ""), "speaker_name": None,
                    "swipes": [body.get("content", "")], "swipe_id": 0,
                    "pinned": False,
                }
                self.messages[cid].append(message)
                return httpx.Response(201, json=message)
            if tail == "persona":
                persona = None
                row = self.rows.get(chat["character_id"] or "")
                if row is not None:
                    persona = {"character_id": row["id"], "name": row["name"]}
                return httpx.Response(200, json={"chat_id": cid, "persona": persona})
            if tail == "backend-profile":
                chat["backend_profile_id"] = body.get("profile_id")
                return httpx.Response(200, json=chat)
            if tail == "preset":
                chat["preset_id"] = body.get("preset_id")
                return httpx.Response(200, json=chat)
        return httpx.Response(404, json={"detail": "not found"})

    def _character_road(self, request, character_id, tail, body):
        method = request.method
        row = self.rows.get(character_id)
        if tail == "restore" and method == "POST":
            if row is None or not row["deleted"]:
                return httpx.Response(404, json={"detail": "not found"})
            row["deleted"] = False
            return httpx.Response(200, json=self._summary(row))
        if row is None or row["deleted"]:
            return httpx.Response(404, json={"detail": "character not found"})
        if tail == "" and method == "GET":
            return httpx.Response(200, json=self._summary(row))
        if tail == "" and method == "PATCH":
            if body.get("card") is not None:
                card = body["card"]
                row["card"] = card if "data" in card else wrapped(card)
            if body.get("name"):
                row["name"] = body["name"]
                row["card"]["data"]["name"] = body["name"]
            return httpx.Response(200, json=self._summary(row))
        if tail == "" and method == "DELETE":
            row["deleted"] = True
            return httpx.Response(200, json={"deleted": True, "id": character_id, "undoable": True})
        if tail == "duplicate" and method == "POST":
            clone, _ = self._create(dict(row["card"]["data"]), f"{row['name']} (copy)")
            return httpx.Response(201, json=self._summary(clone))
        if tail == "versions":
            lineage = sorted(
                [r for r in self.rows.values() if r["lineage_id"] == row["lineage_id"]],
                key=lambda r: r["version_no"],
            )
            latest = max(r["version_no"] for r in lineage if not r["deleted"])
            return httpx.Response(200, json={
                "character_id": row["id"], "lineage_id": row["lineage_id"],
                "name": row["name"], "latest_version_no": latest,
                "versions": [{
                    "character_id": r["id"], "name": r["name"],
                    "version_no": r["version_no"], "lineage_id": r["lineage_id"],
                    "content_hash": "x" * 64,
                    "created_at": "2026-11-14T00:00:00+00:00",
                    "deleted": r["deleted"],
                    "is_latest": r["version_no"] == latest,
                } for r in lineage],
            })
        if tail.startswith("versions/"):
            version_no = int(tail.split("/")[1])
            target = next(
                (r for r in self.rows.values()
                 if r["lineage_id"] == row["lineage_id"]
                 and r["version_no"] == version_no),
                None,
            )
            if target is None:
                return httpx.Response(404, json={"detail": "version not found"})
            return httpx.Response(200, json={
                "character_id": target["id"], "name": target["name"],
                "version_no": target["version_no"],
                "lineage_id": target["lineage_id"], "content_hash": "x" * 64,
                "created_at": "2026-11-14T00:00:00+00:00",
                "deleted": target["deleted"], "is_latest": False,
                "card": target["card"],
            })
        if tail == "avatar":
            if method == "POST":
                names = re.findall(rb'filename="([^"]+)"', request.content)
                filename = names[0].decode() if names else "avatar.png"
                row["avatar"] = filename
                return httpx.Response(200, json={"filename": filename})
            if row["avatar"] is None:
                return httpx.Response(404, json={"detail": "avatar not found"})
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        if tail == "assets":
            if method == "GET":
                return httpx.Response(200, json=self.assets[character_id])
            names = re.findall(rb'filename="([^"]+)"', request.content)
            asset = {
                "id": self._id("a"), "character_id": character_id,
                "kind": "embedded",
                "name": names[0].decode() if names else "asset.bin",
                "source_type": "", "status": "stored", "format": "",
                "media_type": "", "width": None, "height": None,
                "byte_size": 4, "has_thumbnail": False,
                "thumbnail_status": "not_applicable",
            }
            self.assets[character_id].append(asset)
            return httpx.Response(201, json=asset)
        if tail == "character-book":
            book = row["card"]["data"].get("character_book")
            return httpx.Response(200, json=book if isinstance(book, dict) else {"entries": []})
        if tail == "lorebook-binding":
            if method == "GET":
                binding = self.bindings.get(character_id)
                return httpx.Response(
                    200,
                    json=binding
                    or {"bound": False, "character_id": character_id},
                )
            if method == "PUT":
                book = self.lorebooks[body["lorebook_id"]]
                binding = {
                    "bound": True, "character_id": character_id,
                    "lorebook_id": book["id"], "precedence": body.get("precedence"),
                    "entry_count": book["entry_count"],
                    "lorebook": {"name": book["name"]},
                }
                self.bindings[character_id] = binding
                return httpx.Response(200, json=binding)
            if method == "DELETE":
                self.bindings.pop(character_id, None)
                return httpx.Response(200, json={"unbound": True})
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


def seed_keeper(engine) -> str:
    row, _ = engine._create({
        "name": "Gate Keeper",
        "description": "Guards the high pass.",
        "personality": "Calm, dry, kind.",
        "first_mes": GREETING,
        "alternate_greetings": ["Well met. State your name."],
        "tags": ["guard"],
    }, "Gate Keeper")
    return row["id"]


def test_characters_structure_is_real(qapp) -> None:
    window, _client, _engine = make_window(qapp)
    try:
        assert "New Character…" not in window.placeholder_actions
        assert "Character Editor…" not in window.placeholder_actions
        assert window.action_new_character.text() == "New Character…"
        assert window.new_character_button.text() == "New Character…"
        assert window.edit_character_button.text() == "Edit Character…"
        assert window.undo_delete_character_button.isEnabled() is False
        dialog = window.open_new_character_editor()
        assert dialog.isVisible()
        assert dialog.name_edit is not None
        assert dialog.system_prompt_edit is not None
        assert dialog.tabs.count() == 5
        dialog.close()
    finally:
        window.close()


def test_create_edit_and_library_through_the_window(qapp) -> None:
    window, client, _engine = make_window(qapp)
    try:
        # Create-from-scratch through the editor dialog.
        dialog = window.open_new_character_editor()
        dialog.name_edit.setText("Gate Keeper")
        dialog.description_edit.setPlainText("Guards the high pass.")
        dialog.first_mes_edit.setPlainText(GREETING)
        dialog.tags_edit.setText("guard, pass")
        dialog.greeting_edit.setPlainText("Well met. State your name.")
        dialog.add_greeting_button.click()
        created = window.save_editor_blocking(dialog)
        dialog.close()
        assert created.name == "Gate Keeper"
        card = client.get_character_card(created.id)
        assert card.description == "Guards the high pass."
        assert card.alternate_greetings == ["Well met. State your name."]
        assert window.character_flow().organisation(created.id).tags == [
            "guard", "pass",
        ]
        window.refresh_blocking()
        assert window.characters_list.count() == 1

        # Edit through the dialog: fields arrive filled, saving lands.
        window.characters_list.setCurrentRow(0)
        editor = window.open_character_editor_blocking(created.id)
        assert editor.name_edit.text() == "Gate Keeper"
        assert editor.description_edit.toPlainText() == "Guards the high pass."
        assert editor.greetings_list.count() == 1
        assert editor.versions_list.count() == 1
        editor.description_edit.setPlainText("Now guards the LOW pass.")
        saved = window.save_editor_blocking(editor)
        assert saved.description == "Now guards the LOW pass."
        editor.close()

        # Library search + favourite through the dock controls.
        window.character_search_edit.setText("keeper")
        total, items = window.refresh_library_blocking()
        assert total == 1 and items[0].id == created.id
        assert window.toggle_favourite_blocking(created.id) is True
        window.favourites_only_check.setChecked(True)
        total, _items = window.refresh_library_blocking()
        assert total == 1
        window.favourites_only_check.setChecked(False)
        window.character_search_edit.setText("nobody")
        total, _items = window.refresh_library_blocking()
        assert total == 0
        window.character_search_edit.setText("")
        window.refresh_library_blocking()

        # Duplicate, then delete-with-undo through the confirm box.
        clone = window.duplicate_character_blocking(created.id)
        assert clone.name == "Gate Keeper (copy)"
        window.refresh_blocking()
        # Select the clone in the list and delete it via the box.
        for index in range(window.characters_list.count()):
            item = window.characters_list.item(index)
            if item.data(0x0100) == clone.id:  # UserRole == 256
                window.characters_list.setCurrentItem(item)
                break
        box = window.confirm_delete_selected_character()
        assert box is not None and box.isVisible()
        delete_button = next(b for b in box.buttons() if b.text() == "Delete")
        box.buttonClicked.emit(delete_button)
        assert wait_for(
            qapp,
            lambda: all(c.id != clone.id for c in client.list_characters()),
        )
        assert wait_for(
            qapp,
            lambda: window.undo_delete_character_button.isEnabled() is True,
        )
        restored = window.undo_delete_character_blocking()
        assert restored.id == clone.id
    finally:
        window.close()


def test_chat_with_editor_made_character(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        character_id = seed_keeper(engine)
        window.refresh_blocking()
        dialog = window.open_new_chat_dialog()
        dialog.select_character(character_id)
        dialog.accept()
        assert wait_for(qapp, lambda: window.current_chat_id is not None)
        assert GREETING in window.message_view.toPlainText()
        window.composer_edit.setPlainText("I seek passage.")
        window.send_button.click()
        assert wait_for(
            qapp,
            lambda: "Rúnmál hears you." in window.message_view.toPlainText()
            and not window._streaming,
        )
    finally:
        window.close()
