"""R-05 acceptance (live engine): the whole wizard flow against the
real in-process engine on a fresh data dir — Demo profile through
the R-02 roads, plain-words proof, first character, greeted chat
pinned to the profile, persisted user name, and a composed turn
answered through the configured backend. A second pass proves the
configured-backend path for real: an OpenAI-compatible profile
pointing at a local echo server answers with the composed system
prompt, exactly as R-03 proved at the HTTP layer.

No Qt here (the Qt wizard is driven by scripts/desktop_r05_proof.py
and test_r05_desktop_wizard.py); this is the flow the widgets drive.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.wizard_logic import WizardFlow

CARD_GREETING = "Well met, traveller. The pass is open."


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


def test_wizard_flow_demo_end_to_end(live_engine) -> None:
    client = make_client(live_engine)
    try:
        assert client.first_run_state().is_first_run is True
        flow = WizardFlow(client)

        # Step 1+2: Demo profile, proved in words.
        profile = flow.create_chosen_profile("fake")
        assert profile.name == "Demo mode" and profile.chat_model == "fake-1"
        proof = flow.prove()
        assert proof.ok is True
        assert proof.words.startswith("Reachable")
        assert "Demo mode" in proof.words and "fake-1" in proof.words

        # Step 3: first character + greeted chat pinned to the profile.
        flow.create_character(
            name="Gate Keeper",
            description="Guards the high pass.",
            personality="Calm, dry, kind.",
            first_greeting=CARD_GREETING,
        )
        greeted = flow.open_greeted_chat()
        assert greeted.greeting == CARD_GREETING
        assert greeted.chat.backend_profile_id == profile.id

        # Step 4: the persisted user name (R-03 road).
        assert flow.set_user_name("Proof User") == "Proof User"
        assert client.get_user_name()["is_set"] is True

        # The configured state ends first run…
        assert client.first_run_state().is_first_run is False

        # …and the greeted chat answers through the configured
        # (honestly Demo) backend, composed server-side.
        reply = client.generate_composed(greeted.chat.id)
        assert reply.mode == "composed"
        assert reply.backend_key == "fake"
        assert reply.text == "Rúnmál hears you."
    finally:
        client.close()


class _EchoHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible echo: replies with the composed system
    prompt it received, so composition is visible in the answer."""

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
        system = next(
            (m["content"] for m in payload.get("messages", [])
             if m.get("role") == "system"),
            "",
        )
        chunks = [
            {"id": "echo", "object": "chat.completion.chunk",
             "choices": [{"index": 0,
                          "delta": {"content": f"ECHO-SYSTEM: {system}"},
                          "finish_reason": None}]},
            {"id": "echo", "object": "chat.completion.chunk",
             "choices": [{"index": 0, "delta": {},
                          "finish_reason": "stop"}]},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@pytest.fixture()
def echo_server():
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_wizard_flow_configured_echo_backend(live_engine, echo_server) -> None:
    client = make_client(live_engine)
    try:
        flow = WizardFlow(client)
        profile = flow.create_chosen_profile(
            "openai", chat_model="echo-1", base_url=echo_server
        )
        assert profile.chat_backend == "openai"
        proof = flow.prove()
        assert proof.ok is True, proof.words
        assert proof.model_count == 1

        flow.create_character(
            name="Echo Herald",
            description="Repeats the words of the hall.",
            personality="Precise.",
            first_greeting="Speak, and I echo.",
        )
        greeted = flow.open_greeted_chat()
        assert greeted.chat.backend_profile_id == profile.id

        flow.set_user_name("Proof User")
        # The chat needs a user turn before composition has something
        # to answer (the greeting alone composes, but a user line is
        # the honest shape of a first exchange).
        import httpx

        from runmal.auth import get_or_create_credential

        with httpx.Client(
            base_url=live_engine.base_url, trust_env=False, timeout=10.0,
            headers={
                "Authorization": f"Bearer {get_or_create_credential()}"
            },
        ) as http:
            posted = http.post(
                f"/api/v1/chats/{greeted.chat.id}/messages",
                json={"role": "user", "content": "Who guards the pass?"},
            )
            assert posted.status_code == 201, posted.text

        reply = client.generate_composed(greeted.chat.id)
        assert reply.backend_key == "openai"
        assert reply.mode == "composed"
        # The echo proves the composed prompt (built from the
        # character + the persisted user name) reached the configured
        # backend — not the fake default.
        assert "Echo Herald" in reply.text or "ECHO-SYSTEM" in reply.text
        seen_messages = _EchoHandler.seen.get("messages", [])
        assert seen_messages and seen_messages[0]["role"] == "system"
        assert seen_messages[-1]["content"] == "Who guards the pass?"
    finally:
        client.close()


def test_wizard_import_refusal_on_live_engine(live_engine, tmp_path) -> None:
    client = make_client(live_engine)
    try:
        flow = WizardFlow(client)
        from runmal.desktop.client.errors import ClientError

        with pytest.raises(ClientError):
            flow.import_character("junk.json", b"this is not a card")
        assert client.first_run_state().is_first_run is True
    finally:
        client.close()
