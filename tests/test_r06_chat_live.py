"""R-06 acceptance (live engine): the ChatFlow against the real
in-process engine on a fresh data dir — a greeted chat through the
client roads, a composed turn landed in history, the Session view
resolved from real R-02/R-03 data, rename/export/delete — plus the
Stop road for real: a slow OpenAI-compatible echo backend streams
for seconds, the flow is cancelled mid-flight from another thread,
and the partial reply is proven absent from the stored history.

No Qt here (the stage widgets are driven by
``scripts/desktop_r06_proof.py`` and ``test_r06_desktop_window.py``).
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from runmal.auth import get_or_create_credential
from runmal.desktop.chat_logic import ChatFlow
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState

GREETING = "Well met, traveller. The pass is open."


@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    yield handle
    handle.stop()


def make_client(handle) -> RunmalClient:
    return RunmalClient(DesktopSession.from_local_credential(handle.base_url))


def raw_http(handle) -> httpx.Client:
    return httpx.Client(
        base_url=handle.base_url, trust_env=False, timeout=10.0,
        headers={"Authorization": f"Bearer {get_or_create_credential()}"},
    )


def seed_demo_chat(client: RunmalClient):
    """A Demo profile + a character + a greeted chat pinned to the
    profile — the R-05 wizard's landing, via the client roads."""
    profile = client.create_backend_profile(
        "Demo mode", "fake", chat_model="fake-1"
    )
    character = client.create_character(
        {
            "name": "Gate Keeper",
            "description": "Guards the high pass.",
            "personality": "Calm, dry, kind.",
            "first_mes": GREETING,
        },
        name="Gate Keeper",
    )
    flow = ChatFlow(client)
    opened = flow.create_chat(
        character_id=character.id, title="First chat with Gate Keeper"
    )
    client.set_chat_backend_profile(opened.chat.id, profile.id)
    return flow, profile, character, opened.chat.id


def test_flow_end_to_end_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow, profile, character, chat_id = seed_demo_chat(client)

        opened = flow.open_chat(chat_id)
        assert [m.content for m in opened.messages] == [GREETING]
        assert opened.messages[0].speaker_name == "Gate Keeper"

        # A preset through the real presets road, applied to the
        # chat: the Session view must name it from real data.
        with raw_http(live_engine) as http:
            created = http.post(
                "/api/v1/presets",
                json={"name": "Storyteller", "params": {"temperature": 0.4}},
            )
            assert created.status_code == 201, created.text
            preset_id = created.json()["id"]
        client.set_chat_preset(chat_id, preset_id)
        opened = flow.open_chat(chat_id)
        assert opened.session is not None
        assert opened.session.character_label == "Gate Keeper"
        assert opened.session.persona_label == "Gate Keeper"
        assert "Demo mode" in opened.session.profile_label
        assert opened.session.model_label == "fake-1"
        assert opened.session.preset_label == "Storyteller"

        # One composed turn: the Demo backend answers and the reply
        # LANDS in the stored history (user line first).
        result = flow.send_turn(chat_id, "I seek passage.")
        assert result.landed is True
        assert result.draft.text == "Rúnmál hears you."
        assert result.draft.backend_key == "fake"
        assert result.draft.mode == "composed"
        history = client.list_chat_messages(chat_id)
        assert [m.role for m in history] == ["assistant", "user", "assistant"]
        assert history[1].content == "I seek passage."
        assert history[2].content == "Rúnmál hears you."

        # Rename + export carry the real history; delete removes it.
        renamed = flow.rename_chat(chat_id, "The Pass Chat")
        assert renamed.title == "The Pass Chat"
        document = json.loads(flow.export_text(chat_id))
        assert document["chat"]["title"] == "The Pass Chat"
        assert len(document["messages"]) == 3
        assert flow.delete_chat(chat_id) is True
        assert client.list_chats() == []
    finally:
        client.close()


class _SlowEchoHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible echo that streams slowly: eight chunks,
    one every 0.4s — long enough to stop mid-flight."""

    seen: dict = {}

    def log_message(self, *args):  # keep test output clean
        pass

    def do_GET(self):
        if self.path.startswith("/models"):
            body = {"data": [{"id": "echo-1", "object": "model"}]}
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen = payload
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for index in range(8):
                chunk = {
                    "id": "echo", "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"chunk-{index} "},
                        "finish_reason": None,
                    }],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.4)
            final = {
                "id": "echo", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {},
                             "finish_reason": "stop"}],
            }
            self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client cancelled — that is the point


@pytest.fixture()
def slow_echo():
    server = HTTPServer(("127.0.0.1", 0), _SlowEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_flow_stop_mid_flight_on_real_engine(live_engine, slow_echo) -> None:
    client = make_client(live_engine)
    try:
        profile = client.create_backend_profile(
            "Slow Echo", "openai", chat_model="echo-1",
            config={"base_url": slow_echo},
        )
        character = client.create_character(
            {"name": "Echo Herald", "first_mes": "Speak, and I echo."},
            name="Echo Herald",
        )
        flow = ChatFlow(client)
        opened = flow.create_chat(character_id=character.id)
        client.set_chat_backend_profile(opened.chat.id, profile.id)

        outcome: dict = {}
        events: list[str] = []

        def run_turn() -> None:
            outcome["result"] = flow.send_turn(
                opened.chat.id, "Tell me slowly.",
                on_event=lambda e: events.append(e.kind),
            )

        worker = threading.Thread(target=run_turn)
        worker.start()
        # Wait until tokens are actually arriving, then Stop.
        deadline = time.time() + 15
        while time.time() < deadline and "token" not in events:
            time.sleep(0.05)
        assert "token" in events, "the slow stream never started"
        assert flow.active_request_id is not None
        assert flow.cancel_active() is True
        worker.join(timeout=20)
        assert not worker.is_alive(), "the turn never finished after Stop"

        result = outcome["result"]
        assert result.draft.stopped is True, result.draft
        assert result.draft.text.startswith("chunk-")
        assert len(result.draft.text) < len("chunk-0 chunk-1 chunk-2 "
                                            "chunk-3 chunk-4 chunk-5 "
                                            "chunk-6 chunk-7 ")
        assert result.landed is False
        assert "not saved" in result.status_words
        # The stored history holds the greeting + the user line —
        # and NO partial assistant reply.
        history = client.list_chat_messages(opened.chat.id)
        assert [m.role for m in history] == ["assistant", "user"]
        assert history[1].content == "Tell me slowly."
    finally:
        client.close()
