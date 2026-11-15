"""R-09 acceptance (settings widgets): the real QMainWindow's
Connections and Generation dialogs over a MockTransport engine —
profile create + write-only key + probe + pin through the
dialog, preset create/apply through the sampler form, the
Session dock's quick-apply, and bundle assignment + resolve
preview through the dialog.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on the
fleet devices' R-01 environments, offscreen. The live engine in
the real window is scripts/desktop_r09_proof.py.
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

TOKEN = "test-" + "token-r09"
CANARY = "CANARY-WIN-77aa-never-echo"


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
    """The roads the R-09 window tests touch, in-memory."""

    def __init__(self):
        self.profiles = {
            "p1": {"id": "p1", "name": "Demo mode", "chat_backend": "fake",
                   "chat_model": "fake-1", "embedding_backend": "",
                   "embedding_model": "", "config": {}}
        }
        self.secrets: dict[str, dict[str, str]] = {}
        self.presets: dict[str, dict] = {}
        self.bundles: dict[str, dict] = {}
        self.overrides: dict[tuple[str, str], dict] = {}
        self.characters = {
            "k1": {"id": "k1", "name": "Gate Keeper",
                   "created_at": "2026-11-15T00:00:00+00:00",
                   "has_avatar": False, "avatar_asset": None,
                   "version_no": 1, "lineage_id": "k1",
                   "content_hash": "x" * 64}
        }
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self._seq = 100

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _profile_row(self, row):
        stored = self.secrets.get(row["id"], {})
        return {**row, "config": dict(row["config"]),
                "has_chat_secret": "chat" in stored,
                "has_embedding_secret": "embedding" in stored}

    def _preset_row(self, row):
        return {"id": row["id"], "name": row["name"],
                "params": dict(row["params"]),
                "template_ref": row["template_ref"],
                "source_format": "native", "prompts": []}

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
        parts = [p for p in path.split("/") if p]
        if parts[:3] == ["api", "v1", "backend-profiles"]:
            return self._profiles(request, parts, body)
        if parts[:3] == ["api", "v1", "presets"]:
            return self._presets(request, parts, body)
        if parts[:3] == ["api", "v1", "chats"]:
            return self._chats(request, parts, body)
        if path == "/api/v1/characters" and request.method == "GET":
            return httpx.Response(200, json=list(self.characters.values()))
        return httpx.Response(404, json={"detail": f"no road {path}"})

    def _profiles(self, request, parts, body):
        if len(parts) == 3:
            if request.method == "GET":
                return httpx.Response(
                    200, json=[self._profile_row(r) for r in self.profiles.values()])
            if request.method == "POST":
                row = {"id": self._id("p"), "name": body.get("name", ""),
                       "chat_backend": body.get("chat_backend", ""),
                       "chat_model": body.get("chat_model", ""),
                       "embedding_backend": body.get("embedding_backend", ""),
                       "embedding_model": body.get("embedding_model", ""),
                       "config": dict(body.get("config") or {})}
                self.profiles[row["id"]] = row
                return httpx.Response(201, json=self._profile_row(row))
        row = self.profiles.get(parts[3]) if len(parts) > 3 else None
        if row is None:
            return httpx.Response(404, json={"detail": "profile not found"})
        if len(parts) == 4:
            if request.method == "GET":
                return httpx.Response(200, json=self._profile_row(row))
            if request.method == "PATCH":
                for key in ("name", "chat_backend", "chat_model",
                            "embedding_backend", "embedding_model", "config"):
                    if key in body:
                        row[key] = body[key]
                return httpx.Response(200, json=self._profile_row(row))
            if request.method == "DELETE":
                del self.profiles[row["id"]]
                return httpx.Response(200, json={"ok": True})
        if len(parts) == 5 and parts[4] == "health":
            return httpx.Response(200, json={"ok": True, "detail": "reachable"})
        if len(parts) == 5 and parts[4] == "models":
            return httpx.Response(200, json={"models": [{"model_id": "fake-1"}]})
        if len(parts) == 5 and parts[4] in ("chat-secret", "embedding-secret"):
            kind = "chat" if parts[4] == "chat-secret" else "embedding"
            if request.method == "PUT":
                self.secrets.setdefault(row["id"], {})[kind] = body.get("value", "")
            elif request.method == "DELETE":
                self.secrets.get(row["id"], {}).pop(kind, None)
            return httpx.Response(200, json=self._profile_row(row))
        return httpx.Response(404, json={"detail": "no profile road"})

    def _presets(self, request, parts, body):
        if len(parts) == 3:
            if request.method == "GET":
                return httpx.Response(
                    200, json=[self._preset_row(r) for r in self.presets.values()])
            if request.method == "POST":
                row = {"id": self._id("pr"), "name": body.get("name", ""),
                       "params": dict(body.get("params") or {}),
                       "template_ref": body.get("template_ref", "")}
                self.presets[row["id"]] = row
                return httpx.Response(201, json=self._preset_row(row))
        if len(parts) == 4 and parts[3] == "bundles":
            if request.method == "GET":
                return httpx.Response(200, json=[
                    {"id": bid, "name": doc.get("name", ""), "bundle": doc}
                    for bid, doc in self.bundles.items()
                ])
            if request.method == "POST":
                document = dict(body.get("bundle") or {})
                bundle_id = self._id("b")
                self.bundles[bundle_id] = document
                return httpx.Response(201, json={
                    "id": bundle_id, "name": document.get("name", ""),
                    "bundle": document})
        if len(parts) == 5 and parts[3] == "bundles":
            bundle_id = parts[4]
            if bundle_id not in self.bundles:
                return httpx.Response(404, json={"detail": "bundle not found"})
            if request.method == "GET":
                doc = self.bundles[bundle_id]
                return httpx.Response(200, json={
                    "id": bundle_id, "name": doc.get("name", ""),
                    "bundle": doc})
            if request.method in ("PUT", "PATCH"):
                self.bundles[bundle_id] = dict(body.get("bundle") or {})
                doc = self.bundles[bundle_id]
                return httpx.Response(200, json={
                    "id": bundle_id, "name": doc.get("name", ""),
                    "bundle": doc})
            if request.method == "DELETE":
                del self.bundles[bundle_id]
                return httpx.Response(200, json={"ok": True})
        if len(parts) == 4 and parts[3] == "overrides":
            return httpx.Response(200, json=list(self.overrides.values()))
        if len(parts) == 6 and parts[3] == "overrides":
            scope_kind, owner_id = parts[4], parts[5]
            if request.method == "PUT":
                row = {"id": self._id("ov"), "bundle_id": body.get("bundle_id", ""),
                       "scope_kind": scope_kind, "owner_id": owner_id,
                       "overrides": body.get("overrides") or {}}
                self.overrides[(scope_kind, owner_id)] = row
                return httpx.Response(200, json=row)
            if request.method == "DELETE":
                self.overrides.pop((scope_kind, owner_id), None)
                return httpx.Response(200, json={"ok": True})
        if len(parts) == 4 and parts[3] == "resolve":
            chat_id = request.url.params.get("chat_id")
            row = self.overrides.get(("chat", chat_id or ""))
            if row is None:
                return httpx.Response(200, json={"effective": None})
            bundle = self.bundles[row["bundle_id"]]
            sampler = dict(bundle.get("sampler") or {})
            sources = {key: "bundle" for key in sampler}
            delta = (row.get("overrides") or {}).get("sampler") or {}
            for key, value in delta.items():
                sampler[key] = value
                sources[key] = "chat"
            return httpx.Response(200, json={"effective": {
                "bundle_id": row["bundle_id"],
                "bundle_name": bundle.get("name", ""),
                "effective": {**bundle, "sampler": sampler},
                "sources": {"sampler": sources},
                "applied": [{"scope_kind": "chat", "owner_id": chat_id,
                             "bundle_id": row["bundle_id"]}],
                "shadowed": [],
            }})
        if len(parts) == 4:
            row = self.presets.get(parts[3])
            if row is None:
                return httpx.Response(404, json={"detail": "preset not found"})
            if request.method == "GET":
                return httpx.Response(200, json=self._preset_row(row))
            if request.method == "PATCH":
                for key in ("name", "params", "template_ref"):
                    if key in body:
                        row[key] = body[key]
                return httpx.Response(200, json=self._preset_row(row))
            if request.method == "DELETE":
                del self.presets[row["id"]]
                return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"detail": "no preset road"})

    def _chats(self, request, parts, body):
        if len(parts) == 3:
            if request.method == "GET":
                return httpx.Response(200, json=list(self.chats.values()))
            if request.method == "POST":
                chat = {"id": self._id("c"), "title": body.get("title", ""),
                        "character_id": body.get("character_id"),
                        "backend_profile_id": None, "preset_id": None,
                        "message_count": 0}
                self.chats[chat["id"]] = chat
                self.messages[chat["id"]] = []
                return httpx.Response(201, json=chat)
        chat = self.chats.get(parts[3]) if len(parts) > 3 else None
        if chat is None:
            return httpx.Response(404, json={"detail": "chat not found"})
        if len(parts) == 4 and request.method == "GET":
            return httpx.Response(200, json=chat)
        if len(parts) == 5:
            tail = parts[4]
            if tail == "messages" and request.method == "GET":
                return httpx.Response(200, json=self.messages[chat["id"]])
            if tail == "persona":
                row = self.characters.get(chat["character_id"] or "")
                persona = (
                    {"character_id": row["id"], "name": row["name"]}
                    if row else None
                )
                return httpx.Response(
                    200, json={"chat_id": chat["id"], "persona": persona})
            if tail == "backend-profile":
                chat["backend_profile_id"] = body.get("profile_id")
                return httpx.Response(200, json=chat)
            if tail == "preset":
                chat["preset_id"] = body.get("preset_id")
                return httpx.Response(200, json=chat)
        return httpx.Response(404, json={"detail": "no chat road"})


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


def open_chat(window, client):
    chat = client.create_chat(title="Gate chat", character_id="k1")
    window.refresh_blocking()
    window.open_chat_blocking(chat.id)
    return chat


def test_connections_dialog_round_trip(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        chat = open_chat(window, client)
        dialog = window.open_connections_dialog()
        assert dialog.isVisible()
        assert wait_for(qapp, lambda: dialog.profiles_list.count() >= 1)
        # Create a profile with a write-only key through the form.
        dialog.new_profile()
        dialog.name_edit.setText("Local Echo")
        index = dialog.chat_backend_combo.findData("ollama")
        dialog.chat_backend_combo.setCurrentIndex(index)
        dialog.chat_model_edit.setText("llama3")
        dialog.chat_key_edit.setText(CANARY)
        dialog.save_button.click()
        assert wait_for(
            qapp,
            lambda: any(
                p["name"] == "Local Echo" for p in engine.profiles.values()
            ),
        )
        created = next(
            p for p in engine.profiles.values() if p["name"] == "Local Echo"
        )
        assert engine.secrets[created["id"]]["chat"] == CANARY
        assert CANARY not in json.dumps(list(engine.profiles.values()))
        assert wait_for(
            qapp, lambda: "Saved profile" in dialog.status_label.text()
        )
        assert wait_for(qapp, lambda: dialog._current_id == created["id"])
        assert dialog.chat_key_state.text().startswith("A chat key is stored")
        # Probe: save & test reports the fake's verdict in words.
        dialog.test_button.click()
        assert wait_for(
            qapp, lambda: "Reachable" in dialog.status_label.text()
        )
        assert dialog.model_combo.count() >= 1
        # Pin to the open chat; the window's Session dock follows.
        dialog.pin_button.click()
        assert wait_for(
            qapp,
            lambda: engine.chats[chat.id]["backend_profile_id"]
            == created["id"],
        )
        assert wait_for(
            qapp,
            lambda: "Local Echo" in window.session_profile_label.text(),
        )
        dialog.close()
    finally:
        window.close()


def test_generation_dialog_and_session_quick_apply(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        chat = open_chat(window, client)
        dialog = window.open_generation_dialog()
        assert dialog.isVisible()
        assert wait_for(
            qapp, lambda: "preset(s)" in dialog.status_label.text()
        )
        # Create a preset through the sampler form.
        dialog.new_preset()
        dialog.preset_name_edit.setText("Warm")
        dialog.preset_sampler_form.set_field_value("temperature", 0.9)
        dialog.preset_save_button.click()
        assert wait_for(
            qapp,
            lambda: any(
                p["name"] == "Warm" for p in engine.presets.values()
            ),
        )
        warm = next(
            p for p in engine.presets.values() if p["name"] == "Warm"
        )
        assert warm["params"] == {"temperature": 0.9}
        assert wait_for(qapp, lambda: dialog._preset_detail is not None)
        dialog.preset_apply_button.click()
        assert wait_for(
            qapp, lambda: engine.chats[chat.id]["preset_id"] == warm["id"]
        )
        assert wait_for(
            qapp, lambda: "Warm" in window.session_preset_label.text()
        )
        # A second preset, applied from the Session dock combo.
        cool = client.create_preset("Cool", params={"temperature": 0.2})
        window.open_chat_blocking(chat.id)
        assert wait_for(
            qapp, lambda: window.session_preset_combo.count() >= 3
        )
        combo = window.session_preset_combo
        index = next(
            i for i in range(combo.count()) if combo.itemData(i) == cool.id
        )
        combo.activated.emit(index)
        assert wait_for(
            qapp, lambda: engine.chats[chat.id]["preset_id"] == cool.id
        )
        dialog.close()
    finally:
        window.close()


def test_bundle_assignment_and_resolve_preview(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        chat = open_chat(window, client)
        dialog = window.open_generation_dialog()
        assert wait_for(
            qapp, lambda: "preset(s)" in dialog.status_label.text()
        )
        dialog.tabs.setCurrentIndex(1)
        dialog.new_bundle()
        dialog.bundle_name_edit.setText("Story")
        dialog.bundle_sampler_form.set_field_value("temperature", 0.3)
        dialog.bundle_save_button.click()
        assert wait_for(qapp, lambda: len(engine.bundles) == 1)
        bundle_id = next(iter(engine.bundles))
        assert engine.bundles[bundle_id]["sampler"] == {"temperature": 0.3}
        # Assign it to the open chat with a sampler delta.
        scope_combo = dialog.override_scope_combo
        scope_index = next(
            i for i in range(scope_combo.count())
            if scope_combo.itemData(i) == ("chat", chat.id)
        )
        scope_combo.setCurrentIndex(scope_index)
        assert wait_for(
            qapp,
            lambda: dialog.override_bundle_combo.findData(bundle_id) >= 0,
        )
        bundle_index = dialog.override_bundle_combo.findData(bundle_id)
        dialog.override_bundle_combo.setCurrentIndex(bundle_index)
        dialog.override_delta_form.set_field_value("temperature", 0.7)
        dialog.override_set_button.click()
        assert wait_for(
            qapp, lambda: ("chat", chat.id) in engine.overrides
        )
        assert wait_for(
            qapp,
            lambda: any(
                "Story" in dialog.overrides_list.item(i).text()
                for i in range(dialog.overrides_list.count())
            ),
        )
        # The resolve preview shows the delta winning, with source.
        dialog.tabs.setCurrentIndex(2)
        dialog.resolve_refresh_button.click()

        def resolved() -> bool:
            for i in range(dialog.resolve_list.count()):
                text = dialog.resolve_list.item(i).text()
                if "Temperature" in text and "0.7" in text and "chat" in text:
                    return True
            return False

        assert wait_for(qapp, resolved)
        assert "Story" in dialog.resolve_notes_label.text()
        dialog.close()
    finally:
        window.close()
