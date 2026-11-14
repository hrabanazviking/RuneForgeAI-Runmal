"""R-06 acceptance (chat logic): the Qt-free Chat Stage layer over a
MockTransport engine — the new client roads (chat get/rename/
delete/export, append, persona, presets, streaming + cancel), the
Session view resolution, the transcript rendering, and the composed
turn's landing discipline (user line first; reply landed only on a
clean finish; a stopped or errored stream stores nothing).

No Qt here: the stage widgets are gated separately
(``test_r06_desktop_window.py``) and the live engine end-to-end in
``test_r06_chat_live.py``.
"""

import json
import subprocess
import sys

import httpx
import pytest

from runmal.desktop.chat_logic import (
    ChatFlow,
    StreamDraft,
    export_filename,
    resolve_session,
    speaker_label,
    transcript_html,
)
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.client.errors import ClientError, NotFoundError
from runmal.desktop.client.models import (
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    MessageView,
    PersonaView,
    PresetSummary,
    StreamEvent,
)

TOKEN = "R06-TEST-CREDENTIAL"
GREETING = "Well met, traveller. The pass is open."


class FakeEngine:
    """A stateful in-memory stand-in for the R-06 roads.

    ``generate_mode`` steers the SSE stream: ``normal`` (three
    tokens + done/stop), ``cancelled`` (one token + done/cancelled,
    as the engine answers a Stop), ``error`` (an error event)."""

    def __init__(self, *, generate_mode: str = "normal"):
        self.profiles: dict[str, dict] = {}
        self.characters: dict[str, dict] = {}
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.presets: dict[str, dict] = {}
        self.generate_mode = generate_mode
        self.cancel_calls: list[str] = []
        self.generate_bodies: list[dict] = []
        self._seq = 0

    def _id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    # ------------------------------------------------------------ seeding

    def seed_profile(self, **over) -> dict:
        pid = self._id("p")
        profile = {
            "id": pid, "name": "Demo mode", "chat_backend": "fake",
            "chat_model": "fake-1", "embedding_backend": "",
            "embedding_model": "", "has_chat_secret": False,
            "has_embedding_secret": False, "config": {},
        }
        profile.update(over)
        self.profiles[pid] = profile
        return profile

    def seed_character(self, **over) -> dict:
        kid = self._id("k")
        character = {"id": kid, "name": "Gate Keeper", "has_avatar": False}
        character.update(over)
        self.characters[kid] = character
        return character

    def seed_preset(self, **over) -> dict:
        pid = self._id("s")
        preset = {"id": pid, "name": "Storyteller", "params": {}}
        preset.update(over)
        self.presets[pid] = preset
        return preset

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

        if path == "/api/v1/backend-profiles" and request.method == "GET":
            return httpx.Response(200, json=list(self.profiles.values()))
        if path == "/api/v1/characters" and request.method == "GET":
            return httpx.Response(200, json=[
                {"id": c["id"], "name": c["name"],
                 "has_avatar": c.get("has_avatar", False)}
                for c in self.characters.values()
            ])
        if path.startswith("/api/v1/characters/"):
            character = self.characters.get(path.rsplit("/", 1)[1])
            if character is None:
                return httpx.Response(404, json={"detail": "character not found"})
            return httpx.Response(200, json=character)
        if path == "/api/v1/presets" and request.method == "GET":
            return httpx.Response(200, json=list(self.presets.values()))
        if path.startswith("/api/v1/presets/"):
            preset = self.presets.get(path.rsplit("/", 1)[1])
            if preset is None:
                return httpx.Response(404, json={"detail": "preset not found"})
            return httpx.Response(200, json=preset)

        if path == "/api/v1/chats" and request.method == "POST":
            cid = self._id("c")
            chat = {
                "id": cid, "title": body.get("title", ""),
                "character_id": body.get("character_id"),
                "backend_profile_id": None, "preset_id": None,
                "message_count": 0,
            }
            self.chats[cid] = chat
            self.messages[cid] = []
            if chat["character_id"]:
                character = self.characters.get(chat["character_id"])
                if character is not None:
                    self.messages[cid].append({
                        "id": self._id("m"), "role": "assistant",
                        "content": GREETING,
                        "speaker_name": character["name"],
                    })
                    chat["message_count"] = 1
            return httpx.Response(201, json=chat)
        if path == "/api/v1/chats" and request.method == "GET":
            rows = []
            for chat in self.chats.values():
                row = dict(chat)
                row["message_count"] = len(self.messages[chat["id"]])
                rows.append(row)
            return httpx.Response(200, json=rows)
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
                self.messages.pop(cid, None)
                return httpx.Response(200, json={"deleted": True, "id": cid})
            if tail == "messages" and request.method == "GET":
                return httpx.Response(200, json=self.messages[cid])
            if tail == "messages" and request.method == "POST":
                message = {
                    "id": self._id("m"), "role": body.get("role", ""),
                    "content": body.get("content", ""), "speaker_name": None,
                }
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
                if chat["character_id"]:
                    character = self.characters.get(chat["character_id"])
                    if character is not None:
                        persona = {
                            "character_id": character["id"],
                            "name": character["name"],
                        }
                return httpx.Response(
                    200, json={"chat_id": cid, "persona": persona}
                )
            if tail == "preset" and request.method == "POST":
                chat["preset_id"] = body.get("preset_id")
                return httpx.Response(200, json=chat)
            if tail == "backend-profile" and request.method == "POST":
                chat["backend_profile_id"] = body.get("profile_id")
                return httpx.Response(200, json=chat)

        if path == "/api/v1/generate" and request.method == "POST":
            self.generate_bodies.append(body)
            cid = body.get("chat_id")
            history = self.messages.get(cid, [])
            last_user = next(
                (m["content"] for m in reversed(history)
                 if m["role"] == "user"),
                "",
            )
            if self.generate_mode == "error":
                sse = (
                    'data: {"type": "error", "message": '
                    '"the backend refused"}\n\n'
                )
            elif self.generate_mode == "cancelled":
                sse = (
                    'data: {"type": "token", "text": "Partial "}\n\n'
                    'data: {"type": "done", "finish_reason": "cancelled"}\n\n'
                )
            else:
                sse = (
                    'data: {"type": "token", "text": "Reply "}\n\n'
                    'data: {"type": "token", "text": "to: "}\n\n'
                    f'data: {json.dumps({"type": "token", "text": last_user})}\n\n'
                    'data: {"type": "done", "finish_reason": "stop"}\n\n'
                )
            return httpx.Response(
                200,
                content=sse.encode(),
                headers={
                    "content-type": "text/event-stream",
                    "x-backend-key": "fake",
                    "x-generation-mode": "composed",
                    "x-request-id": body.get("request_id", ""),
                },
            )
        if path == "/api/v1/generate/cancel" and request.method == "POST":
            self.cancel_calls.append(body.get("request_id", ""))
            return httpx.Response(
                200, json={"cancelled": bool(body.get("request_id"))}
            )
        return httpx.Response(404, json={"detail": "not found"})


def make_client(engine: FakeEngine | None = None):
    engine = engine or FakeEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http), engine


# ------------------------------------------------------------ Qt-freedom


def test_chat_logic_imports_without_qt() -> None:
    code = (
        "import sys\n"
        "import runmal.desktop.chat_logic as c\n"
        "assert 'PySide6' not in sys.modules, 'chat logic pulled in Qt'\n"
        "assert hasattr(c, 'ChatFlow')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


# ------------------------------------------------------------ client roads


def test_client_chat_roads_round_trip() -> None:
    client, engine = make_client()
    try:
        character = engine.seed_character()
        chat = client.create_chat(title="Gate chat", character_id=character["id"])
        assert client.get_chat(chat.id).title == "Gate chat"
        assert [m.content for m in client.list_chat_messages(chat.id)] == [GREETING]

        renamed = client.rename_chat(chat.id, "Pass chat")
        assert renamed.title == "Pass chat"

        appended = client.append_message(chat.id, "user", "I seek passage.")
        assert appended.role == "user" and appended.content == "I seek passage."

        persona = client.get_chat_persona(chat.id)
        assert persona.present is True and persona.name == "Gate Keeper"

        document = client.export_chat(chat.id)
        assert document["chat"]["title"] == "Pass chat"
        assert len(document["messages"]) == 2

        assert client.delete_chat(chat.id) is True
        with pytest.raises(NotFoundError):
            client.get_chat(chat.id)
    finally:
        client.close()


def test_client_preset_and_character_roads() -> None:
    client, engine = make_client()
    try:
        character = engine.seed_character()
        preset = engine.seed_preset()
        assert client.get_character(character["id"]).name == "Gate Keeper"
        assert [p.name for p in client.list_presets()] == ["Storyteller"]
        assert client.get_preset(preset["id"]).id == preset["id"]
        chat = client.create_chat(character_id=character["id"])
        applied = client.set_chat_preset(chat.id, preset["id"])
        assert applied.preset_id == preset["id"]
        cleared = client.set_chat_preset(chat.id, None)
        assert cleared.preset_id is None
    finally:
        client.close()


def test_stream_composed_events_and_cancel_road() -> None:
    client, engine = make_client()
    try:
        character = engine.seed_character()
        chat = client.create_chat(character_id=character["id"])
        client.append_message(chat.id, "user", "I seek passage.")
        events = list(
            client.stream_composed(chat.id, request_id="req-9")
        )
        assert events[0].kind == "started"
        assert events[0].backend_key == "fake" and events[0].mode == "composed"
        tokens = [e.text for e in events if e.kind == "token"]
        assert "".join(tokens) == "Reply to: I seek passage."
        assert events[-1].kind == "done" and events[-1].finish_reason == "stop"
        assert engine.generate_bodies[0]["request_id"] == "req-9"

        assert client.cancel_generate("req-9") is True
        assert engine.cancel_calls == ["req-9"]
    finally:
        client.close()


# ------------------------------------------------------------ session view


def _chat(**over) -> ChatSummary:
    base = {"id": "c1", "title": "Gate chat", "character_id": "k1",
            "backend_profile_id": "p1", "preset_id": "s1",
            "message_count": 3}
    base.update(over)
    return ChatSummary.from_dict(base)


def test_resolve_session_from_real_shapes() -> None:
    profile = BackendProfile.from_dict(
        {"id": "p1", "name": "Demo mode", "chat_backend": "fake",
         "chat_model": "fake-1"}
    )
    view = resolve_session(
        _chat(),
        persona=PersonaView(chat_id="c1", character_id="k1", name="Gate Keeper"),
        profiles=[profile],
        characters=[CharacterSummary(id="k1", name="Gate Keeper")],
        presets=[PresetSummary(id="s1", name="Storyteller")],
    )
    assert view.chat_title == "Gate chat"
    assert view.character_label == "Gate Keeper"
    assert view.persona_label == "Gate Keeper"
    assert view.profile_label == "Demo mode · fake · fake-1"
    assert view.model_label == "fake-1"
    assert view.preset_label == "Storyteller"


def test_resolve_session_unbound_unpinned_honest() -> None:
    view = resolve_session(
        _chat(character_id=None, backend_profile_id=None, preset_id=None),
        persona=PersonaView(chat_id="c1"),
        profiles=[], characters=[], presets=[],
    )
    assert "No character" in view.character_label
    assert "No persona" in view.persona_label
    assert "engine default" in view.profile_label
    assert "fake" in view.model_label  # the default IS the fake backend
    assert view.preset_label == "No preset applied"


def test_resolve_session_dangling_preset_named() -> None:
    view = resolve_session(
        _chat(),
        persona=None,
        profiles=[], characters=[], presets=[],
    )
    assert "no longer exists" in view.preset_label
    assert "no longer exists" in view.profile_label
    assert "Unknown" in view.persona_label


# ------------------------------------------------------------ transcript


def test_transcript_html_escapes_and_labels() -> None:
    messages = [
        MessageView(id="m1", role="assistant", content=GREETING,
                    speaker_name="Gate Keeper"),
        MessageView(id="m2", role="user", content="<script>x</script>"),
    ]
    rendered = transcript_html(messages, user_name="Volmarr")
    assert "Gate Keeper" in rendered and GREETING in rendered
    assert "Volmarr" in rendered
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_transcript_draft_states_are_words() -> None:
    draft = StreamDraft()
    draft.apply(StreamEvent(kind="token", text="Partial ans"))
    writing = transcript_html([], draft=draft, draft_speaker="Gate Keeper")
    assert "writing…" in writing and "Partial ans" in writing
    draft.apply(StreamEvent(kind="done", finish_reason="cancelled"))
    stopped = transcript_html([], draft=draft, draft_speaker="Gate Keeper")
    assert "stopped, not saved" in stopped
    assert draft.stopped is True and draft.completed_cleanly is False


def test_speaker_label_fallbacks() -> None:
    assert speaker_label(
        MessageView(id="m", role="assistant", content="x"),
        character_name="Gate Keeper",
    ) == "Gate Keeper"
    assert speaker_label(
        MessageView(id="m", role="user", content="x"), user_name="Volmarr"
    ) == "Volmarr"
    assert speaker_label(MessageView(id="m", role="system", content="x")) == "System"
    assert export_filename(ChatSummary(id="c9", title="My Chat!")) == (
        "runmal-chat-My-Chat.json"
    )


# ------------------------------------------------------------ the flow


def test_flow_open_chat_resolves_session() -> None:
    client, engine = make_client()
    try:
        profile = engine.seed_profile()
        character = engine.seed_character()
        preset = engine.seed_preset()
        flow = ChatFlow(client)
        opened = flow.create_chat(character_id=character["id"], title="Gate chat")
        assert [m.content for m in opened.messages] == [GREETING]
        client.set_chat_backend_profile(opened.chat.id, profile["id"])
        client.set_chat_preset(opened.chat.id, preset["id"])
        reopened = flow.open_chat(opened.chat.id)
        assert reopened.session is not None
        assert reopened.session.character_label == "Gate Keeper"
        assert reopened.session.persona_label == "Gate Keeper"
        assert "Demo mode" in reopened.session.profile_label
        assert reopened.session.preset_label == "Storyteller"
    finally:
        client.close()


def test_flow_send_turn_lands_user_then_reply() -> None:
    client, engine = make_client()
    try:
        character = engine.seed_character()
        flow = ChatFlow(client)
        opened = flow.create_chat(character_id=character["id"])
        seen: list[str] = []
        result = flow.send_turn(
            opened.chat.id, "I seek passage.",
            on_event=lambda e: seen.append(e.kind),
        )
        assert result.landed is True
        # The reply text proves the composition saw the stored user
        # line (the mock composes from history): append came first.
        assert result.draft.text == "Reply to: I seek passage."
        assert result.draft.backend_key == "fake"
        assert result.draft.mode == "composed"
        assert seen[0] == "started" and seen[-1] == "done"
        history = client.list_chat_messages(opened.chat.id)
        assert [m.role for m in history] == ["assistant", "user", "assistant"]
        assert history[-1].content == "Reply to: I seek passage."
        assert "saved" in result.status_words
        assert flow.active_request_id is None
    finally:
        client.close()


def test_flow_stopped_turn_is_not_landed() -> None:
    client, engine = make_client(FakeEngine(generate_mode="cancelled"))
    try:
        character = engine.seed_character()
        flow = ChatFlow(client)
        opened = flow.create_chat(character_id=character["id"])
        result = flow.send_turn(opened.chat.id, "I seek passage.")
        assert result.draft.stopped is True
        assert result.landed is False
        assert "not saved" in result.status_words
        history = client.list_chat_messages(opened.chat.id)
        # The user line landed (it was sent); the partial reply did not.
        assert [m.role for m in history] == ["assistant", "user"]
    finally:
        client.close()


def test_flow_error_turn_is_not_landed() -> None:
    client, engine = make_client(FakeEngine(generate_mode="error"))
    try:
        character = engine.seed_character()
        flow = ChatFlow(client)
        opened = flow.create_chat(character_id=character["id"])
        result = flow.send_turn(opened.chat.id, "I seek passage.")
        assert result.landed is False
        assert "refused" in result.draft.error
        assert "nothing was saved" in result.status_words
        history = client.list_chat_messages(opened.chat.id)
        assert [m.role for m in history] == ["assistant", "user"]
    finally:
        client.close()


def test_flow_dock_roads_and_cancel_active() -> None:
    client, engine = make_client()
    try:
        flow = ChatFlow(client)
        opened = flow.create_chat(title="Old name")
        renamed = flow.rename_chat(opened.chat.id, "New name")
        assert renamed.title == "New name"
        with pytest.raises(ClientError):
            flow.rename_chat(opened.chat.id, "   ")
        document = json.loads(flow.export_text(opened.chat.id))
        assert document["chat"]["title"] == "New name"

        assert flow.cancel_active() is False  # nothing in flight
        flow.active_request_id = "req-live"
        assert flow.cancel_active() is True
        assert engine.cancel_calls == ["req-live"]

        assert flow.delete_chat(opened.chat.id) is True
        with pytest.raises(NotFoundError):
            flow.open_chat(opened.chat.id)
    finally:
        client.close()
