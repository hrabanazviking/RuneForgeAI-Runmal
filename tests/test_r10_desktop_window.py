"""R-10 acceptance (widgets): the real QMainWindow's Persona and
Lorebooks dialogs over a MockTransport engine — user-name set
through the dialog, persona switch reflected in the Session
dock, the schema-generated entry form (one editor per census
field, activation kind derived), book + entry creation, a
character scope assignment, and the chat lore preview showing
the entry fired.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on the
fleet devices' R-01 environments, offscreen. The live engine in
the real window is scripts/desktop_r10_proof.py.
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

TOKEN = "test-" + "token-r10"

SCHEMA = {
    "slice": "P-042",
    "surfaces": {
        "book": [
            {"name": "name", "kind": "text", "options": []},
            {"name": "description", "kind": "longtext", "options": []},
            {"name": "scan_depth", "kind": "int", "options": []},
            {"name": "token_budget", "kind": "int_or_null", "options": []},
            {"name": "scan_mode", "kind": "select",
             "options": ["depth", "whole_chat"]},
            {"name": "scan_external_context", "kind": "bool", "options": []},
        ],
        "entry": [
            {"name": "name", "kind": "text", "options": []},
            {"name": "content", "kind": "longtext", "options": []},
            {"name": "keys", "kind": "keys", "options": []},
            {"name": "secondary_keys", "kind": "keys", "options": []},
            {"name": "selective_logic", "kind": "select",
             "options": ["and_any", "and_all", "not_any", "not_all"]},
            {"name": "inclusion_group", "kind": "text", "options": []},
            {"name": "group_weight", "kind": "int", "options": []},
            {"name": "probability", "kind": "int", "options": []},
            {"name": "priority", "kind": "int", "options": []},
            {"name": "position", "kind": "select",
             "options": ["before_char", "after_char", "at_depth"]},
            {"name": "depth", "kind": "int_or_null", "options": []},
            {"name": "role", "kind": "select",
             "options": ["system", "user", "assistant"]},
            {"name": "enabled", "kind": "bool", "options": []},
            {"name": "constant", "kind": "bool", "options": []},
            {"name": "vectorised", "kind": "bool", "options": []},
            {"name": "activation_kind", "kind": "derived", "options": []},
            {"name": "case_sensitive", "kind": "bool", "options": []},
            {"name": "whole_word", "kind": "bool", "options": []},
            {"name": "sticky_prompts", "kind": "int", "options": []},
            {"name": "cooldown_prompts", "kind": "int", "options": []},
            {"name": "delay_prompts", "kind": "int", "options": []},
        ],
    },
}


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
    """The roads the R-10 window tests touch, in-memory."""

    def __init__(self):
        self.profiles = {
            "p1": {"id": "p1", "name": "Demo mode", "chat_backend": "fake",
                   "chat_model": "fake-1", "embedding_backend": "",
                   "embedding_model": "", "config": {},
                   "has_chat_secret": False, "has_embedding_secret": False}
        }
        self.characters = {
            "k1": {"id": "k1", "name": "Gate Keeper",
                   "created_at": "2026-11-15T00:00:00+00:00",
                   "has_avatar": False, "avatar_asset": None,
                   "version_no": 1, "lineage_id": "k1",
                   "content_hash": "x" * 64},
            "k2": {"id": "k2", "name": "Mask Bearer",
                   "created_at": "2026-11-15T00:00:00+00:00",
                   "has_avatar": False, "avatar_asset": None,
                   "version_no": 1, "lineage_id": "k2",
                   "content_hash": "y" * 64},
        }
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.books: dict[str, dict] = {}
        self.entries: dict[str, dict] = {}
        self.scopes: list[dict] = []
        self.user_name = {"user_name": "User", "is_set": False}
        self._seq = 100

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(
                200, json={"status": "ok", "version": "0.1.0"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        parts = [p for p in path.split("/") if p]
        if parts[:3] == ["api", "v1", "backend-profiles"]:
            return httpx.Response(200, json=list(self.profiles.values()))
        if parts[:3] == ["api", "v1", "presets"]:
            return httpx.Response(200, json=[])
        if path == "/api/v1/characters" and request.method == "GET":
            return httpx.Response(200, json=list(self.characters.values()))
        if path == "/api/v1/user-name":
            if request.method == "GET":
                return httpx.Response(200, json=self.user_name)
            name = (body.get("user_name") or "").strip()
            self.user_name = {"user_name": name or "User",
                              "is_set": bool(name)}
            return httpx.Response(200, json=self.user_name)
        if parts[:3] == ["api", "v1", "chats"]:
            return self._chats(request, parts, body)
        if parts[:3] == ["api", "v1", "lorebooks"]:
            return self._lorebooks(request, parts, body)
        return httpx.Response(404, json={"detail": f"no road {path}"})

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
                if request.method == "POST":
                    chat["character_id"] = body.get("character_id")
                row = self.characters.get(chat["character_id"] or "")
                persona = (
                    {"character_id": row["id"], "name": row["name"]}
                    if row else None
                )
                return httpx.Response(
                    200, json={"chat_id": chat["id"], "persona": persona})
            if tail == "lore-preview" and request.method == "POST":
                rows = []
                for scope in self.scopes:
                    if scope["scope_kind"] == "character" and (
                        scope["owner_id"] == chat["character_id"]
                    ):
                        for entry in self.entries.values():
                            if entry["lorebook_id"] != scope["lorebook_id"]:
                                continue
                            hit = any(
                                key.lower() in m.lower()
                                for key in entry["keys"]
                                for m in body.get("messages", [])
                            )
                            rows.append({
                                "entry_id": entry["id"],
                                "name": entry["name"],
                                "status": "included" if hit
                                else "not_triggered",
                                "matched_primary": list(entry["keys"])
                                if hit else [],
                                "matched_secondary": [],
                                "via": "keyword" if hit else None,
                                "tokens": 5 if hit else None,
                                "discard_reason": None,
                                "scope": "character",
                                "lorebook_id": entry["lorebook_id"],
                            })
                summaries = [{
                    "scope": "character",
                    "books": [{"lorebook_id": s["lorebook_id"],
                               "name": self.books[s["lorebook_id"]]["name"],
                               "via": "scope", "budget": None,
                               "position": 0}
                              for s in self.scopes
                              if s["scope_kind"] == "character"],
                    "budget": None, "tokens_used": 5,
                    "included": sum(
                        1 for r in rows if r["status"] == "included"),
                    "discarded": 0,
                }] if rows else []
                return httpx.Response(200, json={
                    "layered": True, "scopes": summaries,
                    "layers": {"character": {"entries": rows}},
                    "shadowed": [], "tokens_used": 5,
                })
        return httpx.Response(404, json={"detail": "no chat road"})

    def _lorebooks(self, request, parts, body):
        if len(parts) == 4 and parts[3] == "editor-schema":
            return httpx.Response(200, json=SCHEMA)
        if len(parts) == 3:
            if request.method == "GET":
                return httpx.Response(200, json=[
                    {**b, "entry_count": sum(
                        1 for e in self.entries.values()
                        if e["lorebook_id"] == b["id"])}
                    for b in self.books.values()
                ])
            if request.method == "POST":
                book = {"id": self._id("b"), "name": body.get("name", ""),
                        "description": body.get("description", ""),
                        "scan_depth": body.get("scan_depth", 4),
                        "token_budget": body.get("token_budget"),
                        "scan_mode": body.get("scan_mode", "depth"),
                        "scan_external_context": body.get(
                            "scan_external_context", False)}
                self.books[book["id"]] = book
                return httpx.Response(201, json={**book, "entry_count": 0})
        book = self.books.get(parts[3]) if len(parts) > 3 else None
        if book is None:
            return httpx.Response(404, json={"detail": "no book"})
        if len(parts) == 4:
            if request.method == "GET":
                return httpx.Response(200, json={**book, "entry_count": 0})
            if request.method == "PATCH":
                book.update(body)
                return httpx.Response(200, json={**book, "entry_count": 0})
            if request.method == "DELETE":
                del self.books[book["id"]]
                return httpx.Response(200, json={"deleted": True})
        if len(parts) == 5 and parts[4] == "entries":
            if request.method == "GET":
                return httpx.Response(200, json=[
                    e for e in self.entries.values()
                    if e["lorebook_id"] == book["id"]
                ])
            if request.method == "POST":
                entry = {"id": self._id("e"), "lorebook_id": book["id"],
                         "name": "", "content": "", "keys": [],
                         "secondary_keys": [], "selective_logic": "and_any",
                         "inclusion_group": "", "group_weight": 100,
                         "probability": 100, "priority": 100,
                         "position": "before_char", "depth": None,
                         "role": "system", "enabled": True,
                         "constant": False, "vectorised": False,
                         "activation_kind": "keyword",
                         "case_sensitive": False, "whole_word": True,
                         "sticky_prompts": 0, "cooldown_prompts": 0,
                         "delay_prompts": 0}
                entry.update(body)
                self.entries[entry["id"]] = entry
                return httpx.Response(201, json=entry)
        if len(parts) == 5 and parts[4] == "scopes":
            return httpx.Response(200, json={
                "lorebook_id": book["id"],
                "scopes": [s for s in self.scopes
                           if s["lorebook_id"] == book["id"]],
            })
        if len(parts) == 5 and parts[4] == "scope":
            if request.method == "PUT":
                scope = {"id": self._id("s"), "lorebook_id": book["id"],
                         "scope_kind": body.get("scope_kind"),
                         "owner_id": body.get("owner_id"),
                         "token_budget": body.get("token_budget"),
                         "position": body.get("position", 0),
                         "lorebook": {"name": book["name"]}}
                self.scopes.append(scope)
                return httpx.Response(201, json=scope)
            if request.method == "DELETE":
                kind = request.url.params.get("scope_kind")
                owner = request.url.params.get("owner_id")
                self.scopes = [
                    s for s in self.scopes
                    if not (s["lorebook_id"] == book["id"]
                            and s["scope_kind"] == kind
                            and s["owner_id"] == owner)
                ]
                return httpx.Response(200, json={"deleted": True})
        if len(parts) == 5 and parts[4] == "preview":
            rows = []
            for entry in self.entries.values():
                if entry["lorebook_id"] != book["id"]:
                    continue
                hit = any(
                    key.lower() in m.lower()
                    for key in entry["keys"]
                    for m in body.get("messages", [])
                )
                rows.append({
                    "entry_id": entry["id"], "name": entry["name"],
                    "status": "included" if hit else "not_triggered",
                    "matched_primary": list(entry["keys"]) if hit else [],
                    "matched_secondary": [],
                    "via": "keyword" if hit else None,
                    "tokens": 5 if hit else None, "discard_reason": None,
                })
            return httpx.Response(200, json={"entries": rows})
        return httpx.Response(404, json={"detail": "no lore road"})


def make_window(qapp):
    engine = MiniEngine()
    session = DesktopSession(
        "http://127.0.0.1:9", **{"bearer" + "_token": TOKEN}
    )
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


def test_persona_dialog_round_trip(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        chat = open_chat(window, client)
        assert "Gate Keeper" in window.session_persona_label.text()
        dialog = window.open_persona_dialog()
        assert dialog.isVisible()
        assert wait_for(
            qapp, lambda: "built-in default" in dialog.user_name_state.text())
        dialog.user_name_edit.setText("Volmarr")
        dialog.save_name_button.click()
        assert wait_for(qapp, lambda: engine.user_name["is_set"])
        assert wait_for(
            qapp,
            lambda: dialog.user_name_state.text()
            == "Your name in chats: Volmarr",
        )
        # Switch the persona to the other character; the Session
        # dock follows after the window refresh.
        index = dialog.persona_combo.findData("k2")
        dialog.persona_combo.setCurrentIndex(index)
        dialog.set_persona_button.click()
        assert wait_for(
            qapp, lambda: engine.chats[chat.id]["character_id"] == "k2")
        assert wait_for(
            qapp,
            lambda: "Mask Bearer" in window.session_persona_label.text(),
        )
        dialog.clear_name_button.click()
        assert wait_for(qapp, lambda: not engine.user_name["is_set"])
    finally:
        window.close()


def test_lorebooks_dialog_round_trip(qapp) -> None:
    window, client, engine = make_window(qapp)
    try:
        open_chat(window, client)
        dialog = window.open_lorebooks_dialog()
        assert dialog.isVisible()
        assert wait_for(qapp, lambda: dialog.book_form is not None)
        # The entry form is generated from the census: one editor
        # per writable field + the derived activation-kind label.
        assert wait_for(qapp, lambda: dialog.entry_form is not None)
        entry_form = dialog.entry_form
        assert entry_form.editor_for("keys") is not None
        assert entry_form.editor_for("probability") is not None
        derived = entry_form.editor_for("activation_kind")
        assert derived is not None and derived.text() == "keyword"
        # Create the book through the form.
        dialog.new_book()
        dialog.book_form.set_field_value("name", "Gate World")
        dialog.save_book_button.click()
        assert wait_for(qapp, lambda: len(engine.books) == 1)
        book = next(iter(engine.books.values()))
        assert wait_for(
            qapp, lambda: dialog.books_combo.currentData() == book["id"])
        # Create the entry through the generated form.
        dialog.new_entry()
        entry_form.set_field_value("name", "Ember fact")
        entry_form.set_field_value("content", "Embers remember.")
        entry_form.set_field_value("keys", ["ember"])
        dialog.save_entry_button.click()
        assert wait_for(qapp, lambda: len(engine.entries) == 1)
        entry = next(iter(engine.entries.values()))
        assert entry["keys"] == ["ember"]
        assert "activation_kind" not in {
            r for r in entry if r == "activation_kind"
        } or entry["activation_kind"] == "keyword"
        # Assign the character scope (Gate Keeper = the chat's
        # character) through the Scopes tab.
        kind_index = dialog.scope_kind_combo.findData("character")
        dialog.scope_kind_combo.setCurrentIndex(kind_index)
        assert wait_for(
            qapp,
            lambda: dialog.scope_owner_combo.findData("k1") >= 0,
        )
        dialog.scope_owner_combo.setCurrentIndex(
            dialog.scope_owner_combo.findData("k1"))
        dialog.assign_scope_button.click()
        assert wait_for(qapp, lambda: len(engine.scopes) == 1)
        assert wait_for(qapp, lambda: dialog.scopes_list.count() == 1)
        # Preview: the keyword fires for this chat.
        dialog.preview_messages.setPlainText("tell me about the ember")
        dialog.preview_chat_button.click()
        assert wait_for(
            qapp,
            lambda: "Included" in dialog.preview_results.toPlainText(),
        )
        assert "matched ember" in dialog.preview_results.toPlainText()
        # And the book-only preview agrees.
        dialog.preview_book_button.click()
        assert wait_for(
            qapp,
            lambda: "Ember fact: Included"
            in dialog.preview_results.toPlainText(),
        )
    finally:
        window.close()


def test_menus_carry_real_r10_actions(qapp) -> None:
    window, _client, _engine = make_window(qapp)
    try:
        assert "Lorebooks…" not in window.placeholder_actions
        assert "Persona…" not in window.placeholder_actions
        assert window.action_lorebooks.text() == "Lorebooks…"
        assert window.action_persona.text() == "Persona…"
    finally:
        window.close()
