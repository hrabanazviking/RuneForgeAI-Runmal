"""R-07 acceptance (chat actions logic): the Qt-free Chat Stage II
layer over a MockTransport engine — message edit/delete, the swipe
deck (add/select/delete/list words), pin/unpin verified by re-read,
branch, Author's Note round trip, regenerate (clean landing + the
stopped stream restoring the old reply), continue, impersonate
(draft/accept/discard), chat search, and checkpoints/undo.

No Qt here: the stage widgets are gated separately
(``test_r07_desktop_window.py``) and the live engine end-to-end in
``test_r07_chat_live.py``.
"""

import json
import subprocess
import sys

import httpx
import pytest

from runmal.desktop.chat_logic import (
    ChatFlow,
    message_list_label,
    transcript_html,
)
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import MessageView

TOKEN = "r07-logic-token"
GREETING = "Well met, traveller. The pass is open."


class FakeEngine:
    """A stateful in-memory stand-in for the R-07 chats roads.

    ``generate_mode`` steers the composed SSE stream like the R-06
    fake: ``normal`` lands "Rúnmál hears you.", ``cancelled``
    answers one token then done/cancelled (a Stop). The undo
    journal is modelled as a stack of before-images for message
    deletes — enough to prove the regenerate restore road."""

    def __init__(self, *, generate_mode: str = "normal"):
        self.profiles: dict[str, dict] = {}
        self.characters: dict[str, dict] = {}
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.presets: dict[str, dict] = {}
        self.notes: dict[str, dict] = {}
        self.pinned: dict[str, set[str]] = {}
        self.checkpoints: dict[str, list[dict]] = {}
        self.journal: dict[str, list[dict]] = {}
        self.generate_mode = generate_mode
        self.generate_bodies: list[dict] = []
        self._seq = 0

    def _id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    # ------------------------------------------------------------ seeding

    def seed_chat(self, contents: list[tuple[str, str]]) -> str:
        cid = self._id("c")
        self.chats[cid] = {
            "id": cid, "title": "Gate chat", "character_id": None,
            "backend_profile_id": None, "preset_id": None,
            "message_count": len(contents),
        }
        self.messages[cid] = [
            {
                "id": self._id("m"), "role": role, "content": content,
                "speaker_name": None, "swipes": [content], "swipe_id": 0,
                "pinned": False,
            }
            for role, content in contents
        ]
        self.notes[cid] = {
            "text": "", "depth": 4, "frequency": 1,
            "enabled": True, "role": "system",
        }
        self.pinned[cid] = set()
        self.checkpoints[cid] = []
        self.journal[cid] = []
        return cid

    # ------------------------------------------------------------ helpers

    def _message(self, chat_id: str, message_id: str) -> dict | None:
        for message in self.messages.get(chat_id, []):
            if message["id"] == message_id:
                return message
        return None

    def _sync_message(self, chat_id: str, message: dict) -> None:
        message["content"] = message["swipes"][message["swipe_id"]]
        message["pinned"] = message["id"] in self.pinned.get(chat_id, set())
        if chat_id in self.chats:
            self.chats[chat_id]["message_count"] = len(
                self.messages.get(chat_id, [])
            )

    def _public(self, chat_id: str, message: dict) -> dict:
        self._sync_message(chat_id, message)
        return {
            "id": message["id"], "role": message["role"],
            "content": message["content"],
            "speaker_name": message["speaker_name"],
            "swipes": list(message["swipes"]),
            "swipe_id": message["swipe_id"],
            "swipe_count": len(message["swipes"]),
            "pinned": message["pinned"],
        }

    # ------------------------------------------------------------ routing

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body: dict = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}

        if path == "/api/v1/backend-profiles":
            return httpx.Response(200, json=list(self.profiles.values()))
        if path == "/api/v1/characters":
            return httpx.Response(200, json=list(self.characters.values()))
        if path == "/api/v1/presets":
            return httpx.Response(200, json=list(self.presets.values()))
        if path == "/api/v1/chats/search":
            query = request.url.params.get("q", "")
            scope = request.url.params.get("chat_id")
            results = []
            for cid, messages in self.messages.items():
                if scope and cid != scope:
                    continue
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
        if path == "/api/v1/generate" and request.method == "POST":
            self.generate_bodies.append(body)
            if self.generate_mode == "cancelled":
                lines = [
                    'data: {"type": "token", "text": "partial "}',
                    'data: {"type": "done", "finish_reason": "cancelled"}',
                ]
            else:
                lines = [
                    'data: {"type": "token", "text": "Rúnmál "}',
                    'data: {"type": "token", "text": "hears you."}',
                    'data: {"type": "done", "finish_reason": "stop"}',
                ]
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "X-Backend-Key": "fake",
                    "X-Generation-Mode": "composed",
                },
                content="\n".join(lines) + "\n",
            )
        if path == "/api/v1/generate/cancel":
            return httpx.Response(200, json={"cancelled": True})

        if not path.startswith("/api/v1/chats/"):
            return httpx.Response(404, json={"detail": "not found"})
        rest = path[len("/api/v1/chats/"):]
        parts = rest.split("/")
        chat_id = parts[0]
        if chat_id not in self.chats and parts != ["search"]:
            # Chat-level roads on unknown chats 404 like the engine.
            if len(parts) == 1 or parts[1] in (
                "messages", "authors-note", "branches", "checkpoints",
                "undo", "continue", "impersonate", "pinned-messages",
                "persona",
            ):
                return httpx.Response(404, json={"detail": "chat not found"})

        if len(parts) == 1:
            if request.method == "GET":
                return httpx.Response(200, json=self.chats[chat_id])
        if parts[1:] == ["persona"]:
            return httpx.Response(200, json={"chat_id": chat_id, "persona": None})
        if parts[1:] == ["messages"] and request.method == "GET":
            return httpx.Response(200, json=[
                self._public(chat_id, m) for m in self.messages[chat_id]
            ])
        if parts[1:] == ["messages"] and request.method == "POST":
            message = {
                "id": self._id("m"), "role": body["role"],
                "content": body["content"], "speaker_name": None,
                "swipes": [body["content"]], "swipe_id": 0, "pinned": False,
            }
            self.messages[chat_id].append(message)
            self.journal[chat_id].append({
                "id": self._id("u"), "operation": "message.append",
                "detail": "append", "_undo": ("append", message["id"]),
            })
            return httpx.Response(201, json=self._public(chat_id, message))
        if parts[1:] == ["authors-note"]:
            if request.method == "GET":
                return httpx.Response(200, json=self.notes[chat_id])
            self.notes[chat_id] = {
                "text": body.get("text", ""), "depth": body.get("depth", 4),
                "frequency": body.get("frequency", 1),
                "enabled": body.get("enabled", True),
                "role": body.get("role", "system"),
            }
            return httpx.Response(200, json=self.chats[chat_id])
        if parts[1:] == ["branches"] and request.method == "POST":
            new_id = self._id("c")
            source = self.messages[chat_id]
            if body.get("message_id"):
                cut = next(
                    i for i, m in enumerate(source)
                    if m["id"] == body["message_id"]
                )
                source = source[: cut + 1]
            self.chats[new_id] = {
                "id": new_id,
                "title": body.get("name") or f"Branch of {chat_id}",
                "character_id": None, "backend_profile_id": None,
                "preset_id": None, "message_count": len(source),
            }
            self.messages[new_id] = [
                dict(m, swipes=list(m["swipes"])) for m in source
            ]
            self.notes[new_id] = dict(self.notes[chat_id])
            self.pinned[new_id] = set()
            self.checkpoints[new_id] = []
            self.journal[new_id] = []
            return httpx.Response(201, json=self.chats[new_id])
        if parts[1:] == ["branches"] and request.method == "GET":
            return httpx.Response(200, json={"chat_id": chat_id, "family": []})
        if parts[1:] == ["continue"] and request.method == "POST":
            mode = body.get("mode", "auto")
            last = self.messages[chat_id][-1]
            resolved = "extend" if (
                mode == "extend" or (mode == "auto" and last["role"] == "assistant")
            ) else "next"
            if resolved == "extend":
                last["swipes"][last["swipe_id"]] += " And onward."
                message = last
                content = " And onward."
            else:
                message = {
                    "id": self._id("m"), "role": "assistant",
                    "content": "A new step.", "speaker_name": None,
                    "swipes": ["A new step."], "swipe_id": 0, "pinned": False,
                }
                self.messages[chat_id].append(message)
                content = "A new step."
            return httpx.Response(201, json={
                "chat_id": chat_id, "kind": "continue", "mode": resolved,
                "content": content, "backend": "fake",
                "message": self._public(chat_id, message),
            })
        if parts[1:] == ["impersonate"] and request.method == "POST":
            return httpx.Response(201, json={
                "id": "draft1", "chat_id": chat_id, "kind": "impersonate",
                "status": "draft", "draft": True, "role": "user",
                "content": "I will go on, then.", "message_id": None,
                "backend": "fake",
            })
        if parts[1:] == ["impersonate", "accept"]:
            message = {
                "id": self._id("m"), "role": "user",
                "content": body["content"], "speaker_name": None,
                "swipes": [body["content"]], "swipe_id": 0, "pinned": False,
            }
            self.messages[chat_id].append(message)
            return httpx.Response(201, json=self._public(chat_id, message))
        if parts[1:] == ["impersonate", "discard"]:
            return httpx.Response(200, json={"discarded": True, "chat_id": chat_id})
        if parts[1:] == ["pinned-messages"]:
            return httpx.Response(200, json=[
                self._public(chat_id, m) for m in self.messages[chat_id]
                if m["id"] in self.pinned[chat_id]
            ])
        if parts[1:] == ["checkpoints"]:
            if request.method == "GET":
                return httpx.Response(200, json=self.checkpoints[chat_id])
            checkpoint = {
                "id": self._id("k"),
                "name": body.get("name") or "Checkpoint 1",
                "created_at": "2026-11-14T00:00:00+00:00",
                "message_count": len(self.messages[chat_id]),
                "chat_title": self.chats[chat_id]["title"],
                "_snapshot": [m["content"] for m in self.messages[chat_id]],
            }
            self.checkpoints[chat_id].append(checkpoint)
            public = {k: v for k, v in checkpoint.items() if k != "_snapshot"}
            return httpx.Response(201, json=public)
        if len(parts) == 3 and parts[1] == "checkpoints":
            checkpoint_id = parts[2]
            if request.method == "DELETE":
                self.checkpoints[chat_id] = [
                    c for c in self.checkpoints[chat_id]
                    if c["id"] != checkpoint_id
                ]
                return httpx.Response(200, json={"deleted": True, "id": checkpoint_id})
        if len(parts) == 4 and parts[1] == "checkpoints" and parts[3] == "restore":
            checkpoint = next(
                c for c in self.checkpoints[chat_id] if c["id"] == parts[2]
            )
            new_id = self._id("c")
            self.chats[new_id] = {
                "id": new_id, "title": body.get("name") or checkpoint["name"],
                "character_id": None, "backend_profile_id": None,
                "preset_id": None,
                "message_count": len(checkpoint["_snapshot"]),
            }
            self.messages[new_id] = [
                {
                    "id": self._id("m"), "role": "assistant", "content": text,
                    "speaker_name": None, "swipes": [text], "swipe_id": 0,
                    "pinned": False,
                }
                for text in checkpoint["_snapshot"]
            ]
            self.notes[new_id] = dict(self.notes[chat_id])
            self.pinned[new_id] = set()
            self.checkpoints[new_id] = []
            self.journal[new_id] = []
            return httpx.Response(201, json=self.chats[new_id])
        if parts[1:] == ["undo"]:
            if request.method == "GET":
                entries = [
                    {k: v for k, v in e.items() if not k.startswith("_")}
                    | {"detail": e["operation"], "created_at": "",
                       "message_count": 0}
                    for e in reversed(self.journal[chat_id])
                ]
                return httpx.Response(200, json={
                    "entries": entries, "count": len(entries),
                    "can_undo": bool(entries),
                })
            if request.method == "POST":
                if not self.journal[chat_id]:
                    return httpx.Response(
                        404, json={"detail": "chat not found or nothing to undo"}
                    )
                entry = self.journal[chat_id].pop()
                kind, payload = entry["_undo"]
                if kind == "delete":
                    self.messages[chat_id].insert(
                        min(payload[0], len(self.messages[chat_id])), payload[1]
                    )
                elif kind == "append":
                    self.messages[chat_id] = [
                        m for m in self.messages[chat_id] if m["id"] != payload
                    ]
                return httpx.Response(200, json={
                    "undone": entry["operation"], "chat_id": chat_id,
                })
        if len(parts) >= 3 and parts[1] == "messages":
            message_id = parts[2]
            message = self._message(chat_id, message_id)
            if message is None:
                return httpx.Response(404, json={"detail": "message not found"})
            if len(parts) == 3 and request.method == "PATCH":
                if not body.get("content"):
                    return httpx.Response(422, json={"detail": "empty"})
                message["swipes"][message["swipe_id"]] = body["content"]
                return httpx.Response(200, json=self._public(chat_id, message))
            if len(parts) == 3 and request.method == "DELETE":
                index = self.messages[chat_id].index(message)
                removed = self.messages[chat_id].pop(index)
                self.journal[chat_id].append({
                    "id": self._id("u"), "operation": "message.delete",
                    "detail": "delete", "_undo": ("delete", (index, removed)),
                })
                return httpx.Response(200, json={"deleted": True, "id": message_id})
            if parts[3:] == ["swipes"] and request.method == "POST":
                # P-065: the new alternate becomes the active one.
                message["swipes"].append(body["content"])
                message["swipe_id"] = len(message["swipes"]) - 1
                return httpx.Response(201, json=self._public(chat_id, message))
            if parts[3:] == ["swipes", "select"]:
                if body.get("index") is not None:
                    index = body["index"]
                    if not 0 <= index < len(message["swipes"]):
                        return httpx.Response(422, json={"detail": "out of range"})
                    message["swipe_id"] = index
                elif body.get("action") == "next":
                    message["swipe_id"] = min(
                        message["swipe_id"] + 1, len(message["swipes"]) - 1
                    )
                elif body.get("action") == "prev":
                    message["swipe_id"] = max(message["swipe_id"] - 1, 0)
                return httpx.Response(200, json=self._public(chat_id, message))
            if len(parts) == 5 and parts[3] == "swipes" and request.method == "DELETE":
                index = int(parts[4])
                if len(message["swipes"]) <= 1:
                    return httpx.Response(
                        422, json={"detail": "cannot delete the only swipe"}
                    )
                message["swipes"].pop(index)
                message["swipe_id"] = min(
                    message["swipe_id"], len(message["swipes"]) - 1
                )
                return httpx.Response(200, json=self._public(chat_id, message))
            if parts[3:] == ["pin"]:
                if request.method == "POST":
                    self.pinned[chat_id].add(message_id)
                    return httpx.Response(201, json={"id": "mem1"})
                self.pinned[chat_id].discard(message_id)
                return httpx.Response(200, json={"unpinned": True, "id": message_id})
        return httpx.Response(404, json={"detail": "not found"})


def make_flow(engine: FakeEngine) -> ChatFlow:
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return ChatFlow(RunmalClient(session, http=http))


@pytest.fixture()
def seeded():
    engine = FakeEngine()
    chat_id = engine.seed_chat([
        ("assistant", GREETING),
        ("user", "I seek passage."),
        ("assistant", "The pass is open."),
    ])
    return engine, make_flow(engine), chat_id


# ------------------------------------------------------------------ tests


def test_client_layer_stays_qt_free() -> None:
    code = (
        "import runmal.desktop.chat_logic, runmal.desktop.client; "
        "import sys; "
        "sys.exit(1 if 'PySide6' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_edit_and_delete_message(seeded) -> None:
    engine, flow, chat_id = seeded
    target = engine.messages[chat_id][1]
    updated = flow.edit_message(chat_id, target["id"], "I seek the high pass.")
    assert updated.content == "I seek the high pass."
    with pytest.raises(ClientError):
        flow.edit_message(chat_id, target["id"], "   ")
    assert flow.delete_message(chat_id, target["id"]) is True
    remaining = flow._client.list_chat_messages(chat_id)
    assert [m.content for m in remaining] == [GREETING, "The pass is open."]


def test_swipe_deck_add_select_delete(seeded) -> None:
    engine, flow, chat_id = seeded
    last = engine.messages[chat_id][-1]
    updated = flow.add_swipe(chat_id, last["id"], "The pass is closed.")
    assert updated.swipe_count == 2
    # P-065: the new alternate becomes the active one.
    assert updated.swipe_id == 1
    assert updated.content == "The pass is closed."
    updated = flow.swipe_prev(chat_id, last["id"])
    assert updated.swipe_id == 0
    assert updated.content == "The pass is open."
    updated = flow.select_swipe(chat_id, last["id"], 1)
    assert updated.content == "The pass is closed."
    updated = flow.delete_swipe(chat_id, last["id"], 1)
    assert updated.swipe_count == 1
    # Transcript + list words carry the deck position.
    decked = flow.add_swipe(chat_id, last["id"], "A third telling.")
    html = transcript_html([decked])
    assert "swipe 2 of 2" in html
    assert "swipe 2/2" in message_list_label(decked)


def test_pin_unpin_verified_by_reread(seeded) -> None:
    engine, flow, chat_id = seeded
    first = flow._client.list_chat_messages(chat_id)[0]
    assert flow.set_pinned(chat_id, first, True) is True
    assert [m.id for m in flow.pinned_messages(chat_id)] == [first.id]
    reloaded = flow._client.list_chat_messages(chat_id)[0]
    assert reloaded.pinned is True
    assert "pinned" in transcript_html([reloaded])
    assert flow.set_pinned(chat_id, reloaded, False) is False
    assert flow.pinned_messages(chat_id) == []


def test_branch_forks_without_touching_source(seeded) -> None:
    engine, flow, chat_id = seeded
    middle = engine.messages[chat_id][1]
    branch = flow.branch_from(chat_id, message_id=middle["id"], name="What if")
    assert branch.id != chat_id
    assert branch.title == "What if"
    assert len(engine.messages[branch.id]) == 2
    assert len(engine.messages[chat_id]) == 3  # source untouched


def test_authors_note_round_trip(seeded) -> None:
    _engine, flow, chat_id = seeded
    saved = flow.save_authors_note(
        chat_id, text="The keeper is terse.", depth=2, frequency=3,
        enabled=True, role="system",
    )
    assert saved.text == "The keeper is terse."
    assert saved.depth == 2 and saved.frequency == 3
    assert flow.authors_note(chat_id).text == "The keeper is terse."


def test_regenerate_lands_a_fresh_reply(seeded) -> None:
    engine, flow, chat_id = seeded
    old_id = engine.messages[chat_id][-1]["id"]
    result = flow.regenerate(chat_id)
    assert result.landed is True
    assert result.message is not None and result.message.id != old_id
    history = flow._client.list_chat_messages(chat_id)
    assert [m.role for m in history] == ["assistant", "user", "assistant"]
    assert history[-1].content == "Rúnmál hears you."
    # The composed prompt was built AFTER the old reply was set
    # aside: the generate body names the chat, and history holds
    # exactly one assistant reply at the end.
    assert engine.generate_bodies[-1]["chat_id"] == chat_id


def test_regenerate_stopped_restores_old_reply() -> None:
    engine = FakeEngine(generate_mode="cancelled")
    chat_id = engine.seed_chat([
        ("assistant", GREETING),
        ("user", "I seek passage."),
        ("assistant", "The pass is open."),
    ])
    flow = make_flow(engine)
    old_id = engine.messages[chat_id][-1]["id"]
    result = flow.regenerate(chat_id)
    assert result.landed is False
    assert result.restored is True
    assert "restored" in result.status_words
    history = flow._client.list_chat_messages(chat_id)
    assert history[-1].id == old_id  # exact restore via the journal
    assert history[-1].content == "The pass is open."


def test_regenerate_refuses_when_last_is_user() -> None:
    engine = FakeEngine()
    chat_id = engine.seed_chat([("user", "Anyone there?")])
    flow = make_flow(engine)
    with pytest.raises(ClientError):
        flow.regenerate(chat_id)


def test_continue_extends_last_reply(seeded) -> None:
    _engine, flow, chat_id = seeded
    outcome = flow.continue_turn(chat_id)
    assert outcome.mode == "extend"
    assert "extended" in outcome.status_words
    history = flow._client.list_chat_messages(chat_id)
    assert history[-1].content == "The pass is open. And onward."


def test_impersonate_draft_accept_discard(seeded) -> None:
    engine, flow, chat_id = seeded
    before = len(engine.messages[chat_id])
    draft = flow.impersonate(chat_id)
    assert draft.content == "I will go on, then."
    assert len(engine.messages[chat_id]) == before  # draft stores nothing
    landed = flow.accept_impersonate(chat_id, draft, "I will go on, then.")
    assert landed.role == "user"
    assert len(engine.messages[chat_id]) == before + 1
    draft2 = flow.impersonate(chat_id)
    assert flow.discard_impersonate(chat_id, draft2) is True
    assert len(engine.messages[chat_id]) == before + 1


def test_search_scoped_and_global(seeded) -> None:
    _engine, flow, chat_id = seeded
    outcome = flow.search("passage")
    assert outcome.total == 1
    assert outcome.hits[0].chat_id == chat_id
    assert "match" in outcome.status_words
    scoped = flow.search("pass", chat_id=chat_id)
    assert scoped.total == 3  # greeting + "passage" + "pass is open"
    with pytest.raises(ClientError):
        flow.search("   ")


def test_checkpoints_and_undo(seeded) -> None:
    _engine, flow, chat_id = seeded
    checkpoint = flow.create_checkpoint(chat_id, name="Before the storm")
    assert checkpoint.message_count == 3
    assert [c.id for c in flow.checkpoints(chat_id)] == [checkpoint.id]
    # Mutate, then restore the checkpoint as a NEW chat.
    first = flow._client.list_chat_messages(chat_id)[0]
    flow.delete_message(chat_id, first.id)
    restored = flow.restore_checkpoint(chat_id, checkpoint.id)
    assert restored.id != chat_id
    assert len(flow._client.list_chat_messages(restored.id)) == 3
    assert len(flow._client.list_chat_messages(chat_id)) == 2
    # The delete was journaled: undo brings the message back.
    journal = flow.undo_journal(chat_id)
    assert journal and journal[0].operation == "message.delete"
    result = flow.undo_last(chat_id)
    assert result["undone"] == "message.delete"
    assert len(flow._client.list_chat_messages(chat_id)) == 3
    assert flow.delete_checkpoint(chat_id, checkpoint.id) is True
    assert flow.checkpoints(chat_id) == []


def test_message_view_parses_engine_shape() -> None:
    view = MessageView.from_dict({
        "id": "m1", "role": "assistant", "content": "hi",
        "swipes": ["hi", "hello"], "swipe_id": 1, "pinned": True,
    })
    assert view.swipe_count == 2 and view.swipe_id == 1 and view.pinned
