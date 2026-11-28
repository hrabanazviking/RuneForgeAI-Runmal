"""FIX-STUB acceptance: a real webface user can never be answered
by the engine's fake/stub backend undisclosed.

Unit half: the guard decisions against a stub ENGINE CLIENT (the
stub stands in for the engine HTTP API, never for a generation
backend — where a reply text is asserted it is the stub client's
scripted stream, used to prove the relay's landing discipline).
Live half: a REAL served engine (throwaway data dir) + the REAL
webface + a REAL Ollama backend: fresh register -> unpinned chat
-> honest block (nothing appended, no stub) -> one-click connect
-> real reply lands; regenerate blocked unpinned; group room
guarded until its chat is pinned, then real group generation
through the FIX-STUB deepening resolution.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.webface import stub_guard
from runmal.webface.app import WebfaceApp, make_handler
from runmal.webface.engine import EngineError
from runmal.webface.store import Store

REPO = Path(__file__).parent.parent
STUB_TEXT = "Rúnmál hears you. This is a stub."

REAL = {"id": "p-real", "name": "House Ollama", "chat_backend": "ollama",
        "chat_model": "llama3.2:3b", "config": {}}
REAL2 = {"id": "p-real2", "name": "House Phi", "chat_backend": "ollama",
         "chat_model": "phi3:mini", "config": {}}
DEMO = {"id": "p-demo", "name": "Demo mode", "chat_backend": "fake",
        "chat_model": "fake-1", "config": {}}


# ------------------------------------------------------------ pure guard


def _chat(pin):
    return {"id": "c1", "backend_profile_id": pin}


def test_mind_words_unpinned_and_connect_list():
    mind = stub_guard.mind_for_chat(_chat(None), [REAL, DEMO, REAL2])
    assert mind["state"] == "none"
    assert mind["words"] == "No mind is connected to this chat yet."
    payload = mind["no_mind"]
    assert payload["words"] == "No mind is connected to this chat yet"
    assert [c["name"] for c in payload["connect"]] == ["House Ollama", "House Phi"]
    assert payload["connections_url"] == "/connections"
    assert payload["has_real_profiles"] is True


def test_mind_words_no_profiles_at_all():
    mind = stub_guard.mind_for_chat(_chat(None), [])
    assert mind["state"] == "none"
    assert mind["no_mind"]["connect"] == []
    assert mind["no_mind"]["has_real_profiles"] is False
    assert mind["no_mind"]["firstrun_url"] == "/firstrun"


def test_mind_words_pinned_real_and_demo():
    mind = stub_guard.mind_for_chat(_chat("p-real"), [REAL, DEMO])
    assert mind["state"] == "real"
    assert mind["words"] == "Answering: House Ollama · llama3.2:3b"
    assert mind["no_mind"] is None
    demo = stub_guard.mind_for_chat(_chat("p-demo"), [REAL, DEMO])
    assert demo["state"] == "demo"
    assert demo["words"] == "Demo — not a real model"
    assert demo["no_mind"] is None


def test_mind_dangling_pin_is_no_mind():
    mind = stub_guard.mind_for_chat(_chat("p-gone"), [REAL])
    assert mind["state"] == "none"


def test_kind_vocabulary_only_fake_is_not_real():
    for kind in ("ollama", "openrouter", "aesir", "openai"):
        assert stub_guard.is_real_profile({"chat_backend": kind})
    assert stub_guard.is_demo_profile({"chat_backend": "fake"})
    assert not stub_guard.is_real_profile({"chat_backend": "fake"})
    assert not stub_guard.is_real_profile({"chat_backend": ""})
    assert not stub_guard.is_real_profile(None)


# ------------------------------------------------------------ stub engine


class StubEngine:
    """Stands in for the engine HTTP API (never for a backend)."""

    def __init__(self, profiles=()):
        self.profiles = {p["id"]: dict(p) for p in profiles}
        self.chats = {"c1": {"id": "c1", "title": "t", "character_id": "k1",
                             "backend_profile_id": None}}
        self.groups = {"g1": {"id": "g1", "name": "Room", "chat_id": "gc1"}}
        self.chats["gc1"] = {"id": "gc1", "title": "Room", "character_id": None,
                              "backend_profile_id": None}
        self.messages = {"c1": [], "gc1": []}
        self.appended = []
        self.generated = []
        self.cancelled = []
        self.continued = []
        self.impersonated = []
        self.group_turns = []
        self.stream_backend = "ollama"
        self.stream_text = "A real reply."
        self._seq = 0

    # engine client surface used by the webface
    def list_characters(self):
        return [{"id": "k1", "name": "Keeper"}]

    def list_chats(self):
        return list(self.chats.values())

    def list_messages(self, chat_id):
        return list(self.messages.get(chat_id, []))

    def create_chat(self, *, character_id, title=""):
        self._seq += 1
        cid = f"c-new-{self._seq}"
        self.chats[cid] = {"id": cid, "title": title,
                           "character_id": character_id,
                           "backend_profile_id": None}
        self.messages[cid] = []
        return self.chats[cid]

    def append_message(self, chat_id, role, content):
        self._seq += 1
        msg = {"id": f"m{self._seq}", "chat_id": chat_id, "role": role,
               "content": content}
        self.messages.setdefault(chat_id, []).append(msg)
        self.appended.append(msg)
        return msg

    def cancel_generate(self, request_id):
        self.cancelled.append(request_id)
        return True

    def stream_generate(self, chat_id, request_id):
        self.generated.append((chat_id, request_id))
        yield ("started", {"backend_key": self.stream_backend, "mode": "composed"})
        yield ("token", {"type": "token", "text": self.stream_text})
        yield ("done", {"type": "done", "finish_reason": "stop"})

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        parts = [seg for seg in path.split("/") if seg]
        # /api/v1/...
        tail = parts[2:] if parts[:2] == ["api", "v1"] else parts
        if tail == ["backend-profiles"] and method == "GET":
            return list(self.profiles.values())
        if tail == ["backend-profiles", "default"] and method == "GET":
            # W-12: this stub engine has no house default named.
            return {"profile_id": "", "profile": None}
        if len(tail) == 2 and tail[0] == "chats" and method == "GET":
            chat = self.chats.get(tail[1])
            if chat is None:
                raise EngineError("chat not found", status=404)
            return chat
        if len(tail) == 2 and tail[0] == "groups" and method == "GET":
            group = self.groups.get(tail[1])
            if group is None:
                raise EngineError("group not found", status=404)
            return group
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "backend-profile":
            chat = self.chats[tail[1]]
            chat["backend_profile_id"] = (json_body or {}).get("profile_id")
            return chat
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "messages" and method == "GET":
            return list(self.messages.get(tail[1], []))
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "messages" and method == "POST":
            return self.append_message(tail[1], json_body["role"], json_body["content"])
        if len(tail) == 4 and tail[0] == "chats" and tail[2] == "messages" and method == "DELETE":
            rows = self.messages.get(tail[1], [])
            self.messages[tail[1]] = [m for m in rows if m["id"] != tail[3]]
            self._stashed = [m for m in rows if m["id"] == tail[3]]
            return {"deleted": True}
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "undo":
            self.messages.setdefault(tail[1], []).extend(getattr(self, "_stashed", []))
            self._stashed = []
            return {"undone": True}
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "continue":
            self.continued.append(tail[1])
            return {"mode": "auto", "content": "continued"}
        if len(tail) == 3 and tail[0] == "chats" and tail[2] == "impersonate":
            self.impersonated.append(tail[1])
            return {"id": "d1", "content": "a draft", "backend": "ollama"}
        if len(tail) == 3 and tail[0] == "groups" and tail[2] in ("next", "run"):
            self.group_turns.append((tail[1], tail[2]))
            return {"group_id": tail[1], "speaker_id": "k1"}
        raise EngineError(f"stub engine: no road {method} {path}", status=404)


@pytest.fixture()
def face(tmp_path):
    engine = StubEngine(profiles=[REAL, DEMO])
    store = Store(tmp_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(WebfaceApp(store, engine)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, engine
    server.shutdown()


@contextlib.contextmanager
def _client(base):
    web = httpx.Client(base_url=base, follow_redirects=False, timeout=30)
    try:
        reg = web.post("/register", data={"username": "guarduser",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303, reg.status_code
        yield web
    finally:
        web.close()


def _sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        assert resp.status_code == 200, resp.status_code
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_send_unpinned_blocked_nothing_appended(face):
    base, engine = face
    with _client(base) as web:
        mind = web.get("/webface/chats/c1/mind").json()
        assert mind["state"] == "none"
        assert mind["words"] == "No mind is connected to this chat yet."
        events = _sse(web, "/webface/chats/c1/send", {"content": "hello?"})
    assert [e["type"] for e in events] == ["no_mind"]
    assert events[0]["words"] == "No mind is connected to this chat yet"
    assert [c["name"] for c in events[0]["connect"]] == ["House Ollama"]
    assert engine.appended == []  # the user message was NOT appended
    assert engine.generated == []  # generation never ran
    assert engine.messages["c1"] == []


def test_send_pinned_real_passes_and_lands(face):
    base, engine = face
    engine.chats["c1"]["backend_profile_id"] = "p-real"
    with _client(base) as web:
        mind = web.get("/webface/chats/c1/mind").json()
        assert mind["words"] == "Answering: House Ollama · llama3.2:3b"
        events = _sse(web, "/webface/chats/c1/send", {"content": "hello"})
    kinds = [e["type"] for e in events]
    assert "landed" in kinds and "no_mind" not in kinds
    assert [m["role"] for m in engine.messages["c1"]] == ["user", "assistant"]
    assert engine.messages["c1"][-1]["content"] == "A real reply."


def test_send_pinned_demo_passes_labelled(face):
    base, engine = face
    engine.chats["c1"]["backend_profile_id"] = "p-demo"
    engine.stream_backend = "fake"
    engine.stream_text = STUB_TEXT
    with _client(base) as web:
        mind = web.get("/webface/chats/c1/mind").json()
        assert mind["state"] == "demo"
        assert mind["words"] == "Demo — not a real model"
        events = _sse(web, "/webface/chats/c1/send", {"content": "hello"})
    kinds = [e["type"] for e in events]
    assert "landed" in kinds and "no_mind" not in kinds  # explicit Demo passes
    assert engine.messages["c1"][-1]["content"] == STUB_TEXT


def test_safety_net_refuses_fake_stream_for_real_chat(face):
    base, engine = face
    engine.chats["c1"]["backend_profile_id"] = "p-real"
    engine.stream_backend = "fake"  # the pin raced away upstream
    engine.stream_text = STUB_TEXT
    with _client(base) as web:
        events = _sse(web, "/webface/chats/c1/send", {"content": "hello"})
    kinds = [e["type"] for e in events]
    assert "no_mind" in kinds and "landed" not in kinds
    assert engine.cancelled, "the fake stream must be cancelled upstream"
    assert [m["role"] for m in engine.messages["c1"]] == ["user"]  # no reply landed
    assert all(m["content"] != STUB_TEXT for m in engine.messages["c1"])


def test_regenerate_unpinned_blocked(face):
    base, engine = face
    engine.messages["c1"] = [{"id": "m-old", "role": "assistant",
                              "content": "old reply"}]
    with _client(base) as web:
        events = _sse(web, "/webface/chats/c1/regenerate", {})
    assert [e["type"] for e in events] == ["no_mind"]
    assert engine.generated == []
    assert engine.messages["c1"][0]["content"] == "old reply"  # untouched


def test_regenerate_safety_net_restores_old_reply(face):
    base, engine = face
    engine.chats["c1"]["backend_profile_id"] = "p-real"
    engine.messages["c1"] = [{"id": "m-old", "role": "assistant",
                              "content": "old reply"}]
    engine.stream_backend = "fake"
    engine.stream_text = STUB_TEXT
    with _client(base) as web:
        events = _sse(web, "/webface/chats/c1/regenerate", {})
    kinds = [e["type"] for e in events]
    assert "no_mind" in kinds and "landed" not in kinds
    contents = [m["content"] for m in engine.messages["c1"]]
    assert contents == ["old reply"], contents  # restored, stub never landed


def test_continue_and_impersonate_blocked_unpinned(face):
    base, engine = face
    with _client(base) as web:
        for road in ("continue", "impersonate"):
            resp = web.post(f"/webface/chats/c1/{road}", json={})
            assert resp.status_code == 409, (road, resp.status_code)
            body = resp.json()
            assert body["no_mind"]["words"] == "No mind is connected to this chat yet"
    assert engine.continued == [] and engine.impersonated == []


def test_continue_pinned_real_passes(face):
    base, engine = face
    engine.chats["c1"]["backend_profile_id"] = "p-real"
    with _client(base) as web:
        resp = web.post("/webface/chats/c1/continue", json={"mode": "auto"})
        assert resp.status_code == 200, resp.text
    assert engine.continued == ["c1"]


def test_group_guard_blocks_and_passes(face):
    base, engine = face
    with _client(base) as web:
        mind = web.get("/webface/groups/g1/mind").json()
        assert mind["state"] == "none" and mind["chat_id"] == "gc1"
        resp = web.post("/webface/groups/g1/next", json={"generate": True})
        assert resp.status_code == 409
        assert resp.json()["no_mind"]["chat_id"] == "gc1"
        # Selection without generation is not a generation road.
        resp = web.post("/webface/groups/g1/next", json={"generate": False})
        assert resp.status_code == 200, resp.text
        # Pin the room's chat -> the room has a mind -> generation passes.
        engine.chats["gc1"]["backend_profile_id"] = "p-real"
        mind = web.get("/webface/groups/g1/mind").json()
        assert mind["words"] == "Answering: House Ollama · llama3.2:3b"
        resp = web.post("/webface/groups/g1/run",
                        json={"generate": True, "turns": 1})
        assert resp.status_code == 200, resp.text
    assert engine.group_turns == [("g1", "next"), ("g1", "run")]


# ------------------------------------------------------------ live pair


def _ollama_base() -> str | None:
    candidates = []
    if os.environ.get("RUNMAL_TEST_OLLAMA_URL"):
        candidates.append(os.environ["RUNMAL_TEST_OLLAMA_URL"])
    candidates.append("http://127.0.0.1:11434")
    try:
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                            text=True, timeout=10).stdout.strip()
        if ip:
            candidates.append(f"http://{ip}:11434")
    except Exception:
        pass
    for base in candidates:
        try:
            if httpx.get(base + "/api/tags", timeout=5,
                         trust_env=False).status_code == 200:
                return base
        except Exception:
            continue
    return None


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_health(url: str, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3, trust_env=False).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture()
def pair(tmp_path):
    base = _ollama_base()
    if base is None:
        pytest.skip("no real Ollama backend answers on this machine")
    models = [m["name"] for m in httpx.get(base + "/api/tags", timeout=5,
             trust_env=False).json().get("models", [])
              if "embed" not in m.get("name", "")]
    if not models:
        pytest.skip("no real Ollama chat model on this machine")
    model = "llama3.2:3b" if "llama3.2:3b" in models else models[0]
    engine_port, webface_port = _free_port(), _free_port()
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    env["PYTHONPATH"] = str(REPO / "src")
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    engine = subprocess.Popen(
        [sys.executable, "-m", "runmal", "serve", "--host", "127.0.0.1",
         "--port", str(engine_port)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    face = None
    try:
        if not _wait_health(f"http://127.0.0.1:{engine_port}/healthz"):
            raise RuntimeError("engine did not come up")
        face = subprocess.Popen(
            [sys.executable, "-m", "runmal.webface", "--host", "127.0.0.1",
             "--port", str(webface_port), "--engine-url",
             f"http://127.0.0.1:{engine_port}", "--data-dir",
             str(tmp_path / "webface-data"), "--engine-data-dir",
             str(tmp_path / "engine-data")], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        yield {"engine": f"http://127.0.0.1:{engine_port}",
               "webface": f"http://127.0.0.1:{webface_port}",
               "ollama": base, "model": model,
               "data_dir": tmp_path / "engine-data"}
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _headers(data_dir: Path) -> dict:
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def _make_character(eng, engine_url, headers, name):
    resp = eng.post(f"{engine_url}/api/v1/characters", headers=headers, json={
        "card": {"name": name, "description": f"{name}, a test character.",
                 "system_prompt": f"You are {name}. Answer briefly, in your "
                                  "own voice, never with canned text.",
                 "first_mes": ""}})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _history(eng, engine_url, headers, chat_id):
    return eng.get(f"{engine_url}/api/v1/chats/{chat_id}/messages",
                   headers=headers).json()


def test_live_no_profiles_honest_walk(pair):
    headers = _headers(pair["data_dir"])
    with httpx.Client(trust_env=False, timeout=60) as eng:
        char_id = _make_character(eng, pair["engine"], headers, "Lonely Keeper")
    with httpx.Client(base_url=pair["webface"], trust_env=False, timeout=60,
                      follow_redirects=False) as web:
        reg = web.post("/register", data={"username": "stubfresh",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303
        chat = web.post("/webface/chats", json={"character_id": char_id}).json()
        mind = web.get(f"/webface/chats/{chat['id']}/mind").json()
        assert mind["state"] == "none"
        assert mind["no_mind"]["connect"] == []
        assert mind["no_mind"]["has_real_profiles"] is False
        events = _sse(web, f"/webface/chats/{chat['id']}/send",
                      {"content": "Anyone there?"})
        assert [e["type"] for e in events] == ["no_mind"]
        assert events[0]["firstrun_url"] == "/firstrun"
    with httpx.Client(trust_env=False, timeout=60) as eng:
        history = _history(eng, pair["engine"], headers, chat["id"])
        assert history == [], history  # nothing appended, no stub anywhere


def test_live_block_connect_real_reply_and_group(pair):
    headers = _headers(pair["data_dir"])
    with httpx.Client(trust_env=False, timeout=120) as eng:
        profile = eng.post(f"{pair['engine']}/api/v1/backend-profiles",
                           headers=headers, json={
                               "name": "fix-stub-live", "chat_backend": "ollama",
                               "chat_model": pair["model"],
                               "config": {"base_url": pair["ollama"]}})
        assert profile.status_code in (200, 201), profile.text
        profile_id = profile.json()["id"]
        keeper = _make_character(eng, pair["engine"], headers, "Stub Gate Keeper")
        second = _make_character(eng, pair["engine"], headers, "Stub Second Voice")
    with httpx.Client(base_url=pair["webface"], trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        reg = web.post("/register", data={"username": "stublive",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303
        chat = web.post("/webface/chats", json={"character_id": keeper}).json()
        chat_id = chat["id"]
        assert chat.get("backend_profile_id") is None
        # Blocked honestly: no stub, nothing appended.
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "Hello, keeper."})
        assert [e["type"] for e in events] == ["no_mind"], events
        assert events[0]["connect"][0]["profile_id"] == profile_id
        # Regenerate on the unpinned chat is blocked too.
        events = _sse(web, f"/webface/chats/{chat_id}/regenerate", {})
        assert [e["type"] for e in events] == ["no_mind"], events
        # One-click connect (the pin road the button calls).
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": profile_id})
        assert pin.status_code == 200, pin.text
        mind = web.get(f"/webface/chats/{chat_id}/mind").json()
        assert mind["words"].startswith("Answering: fix-stub-live"), mind
        # Now a REAL reply lands.
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "Hello, keeper. Who are you?"})
        kinds = [e["type"] for e in events]
        assert "landed" in kinds and "no_mind" not in kinds, events
        started = next(e for e in events if e["type"] == "started")
        assert started["backend_key"] == "ollama", started
        reply = "".join(e.get("text", "") for e in events if e["type"] == "token")
        assert reply.strip() and STUB_TEXT not in reply
        # Group room: guarded until the room's chat is pinned.
        room = web.post("/webface/groups", json={
            "name": "FIX-STUB Room", "member_character_ids": [keeper, second]})
        assert room.status_code == 200, room.text
        gid = room.json()["id"]
        blocked = web.post(f"/webface/groups/{gid}/next", json={"generate": True})
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["no_mind"]["words"] == \
            "No mind is connected to this chat yet"
    with httpx.Client(trust_env=False, timeout=300) as eng:
        history = _history(eng, pair["engine"], headers, chat_id)
        contents = [m["content"] for m in history]
        assert contents.count("Hello, keeper.") == 0  # blocked send never appended
        assert any(STUB_TEXT not in c for c in contents)
        assert all(STUB_TEXT not in c for c in contents), contents
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"].strip() == reply.strip()
        # Pin the room's chat via the engine road, then a real group turn.
        groups = eng.get(f"{pair['engine']}/api/v1/groups", headers=headers).json()
        room_row = next(g for g in groups if g["id"] == gid)
        room_chat = room_row["chat_id"]
        pin = eng.post(f"{pair['engine']}/api/v1/chats/{room_chat}/backend-profile",
                       headers=headers, json={"profile_id": profile_id})
        assert pin.status_code == 200, pin.text
    with httpx.Client(base_url=pair["webface"], trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        reg = web.post("/login", data={"username": "stublive",
                                       "password": "long-enough-1"})
        assert reg.status_code == 303
        mind = web.get(f"/webface/groups/{gid}/mind").json()
        assert mind["state"] == "real", mind
        turn = web.post(f"/webface/groups/{gid}/next", json={"generate": True})
        assert turn.status_code == 200, turn.text
        message = turn.json()["result"]["message"]
        assert message and message["content"].strip(), turn.text
        assert STUB_TEXT not in message["content"], message
