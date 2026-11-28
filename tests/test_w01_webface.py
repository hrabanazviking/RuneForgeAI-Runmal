"""W-01 acceptance: the Rúnmál web face (ADR-0012).

Unit half: password hashing round-trip (self-describing hashes),
session digest storage + TTL pruning, store CRUD, and HTTP auth
gating against the real handler with a stub engine client (the stub
stands in for the ENGINE, never for a generation backend — no chat
reply is ever asserted from it).

Live half (test_live_*): drives a REAL served engine (throwaway
data dir, real server process) + the REAL webface over HTTP, with
the house Ollama as the generation backend: register -> login
cookie -> character + chat via the engine API -> send through the
webface -> streamed reply non-empty, NOT from the fake backend, and
history identical via the engine API. Where no real backend answers
on this machine the live tests skip with the reason printed — never
a fake-backend pass (campaign law: no mock mode, ever).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.webface import security
from runmal.webface.app import WebfaceApp, make_handler
from runmal.webface.store import SESSION_TTL_SECONDS, Store

REPO = Path(__file__).parent.parent

# ------------------------------------------------------------ unit: security


def test_password_hash_round_trip_and_self_describing():
    stored = security.hash_password("correct horse battery")
    assert stored.startswith(("argon2id:", "scrypt:"))
    assert security.verify_password("correct horse battery", stored)
    assert not security.verify_password("wrong horse", stored)
    assert not security.verify_password("correct horse battery", "bogus")
    assert "correct horse" not in stored


def test_scrypt_fallback_shape(monkeypatch):
    monkeypatch.setattr(security, "_HAS_ARGON2", False)
    stored = security.hash_password("pw-nine-nine")
    assert stored.startswith("scrypt:32768:8:1:")
    assert security.verify_password("pw-nine-nine", stored)


def test_digest_is_sha256_and_secret_is_fresh():
    token = security.new_secret()
    assert token != security.new_secret()
    assert security.digest(token) == security.digest(token)
    assert len(security.digest(token)) == 64
    assert token not in security.digest(token)

# ------------------------------------------------------------ unit: store


def test_store_user_crud_and_unique_username(tmp_path):
    store = Store(tmp_path)
    user = store.create_user("volmarr", "hash-1")
    assert user is not None and user["username"] == "volmarr"
    assert user["account_type"] == "human"
    assert store.create_user("VOLMARR", "hash-2") is None  # NOCASE unique
    agent = store.create_user("yrsa", "hash-3", account_type="agent")
    assert agent["account_type"] == "agent"
    assert store.get_user_by_name("volmarr")["id"] == user["id"]
    assert store.get_user(user["id"])["username"] == "volmarr"
    # The password hash is stored, never a plaintext password.
    assert user["pass_hash"] == "hash-1"


def test_store_session_digest_ttl_and_close_all(tmp_path):
    store = Store(tmp_path)
    user = store.create_user("volmarr", "hash-1")
    token = store.create_session(user["id"])
    # Only the digest is on disk.
    rows = store.db.execute("SELECT token_hash FROM web_sessions").fetchall()
    assert rows[0]["token_hash"] == security.digest(token)
    assert rows[0]["token_hash"] != token
    row = store.session_row(token)
    assert row is not None
    assert 0 < row["expires"] - time.time() <= SESSION_TTL_SECONDS
    assert store.user_for_session(token)["id"] == user["id"]
    # Expired sessions are refused and pruned.
    store.db.execute("UPDATE web_sessions SET expires = ?",
                     (time.time() - 1,))
    store.db.commit()
    assert store.user_for_session(token) is None
    assert store.session_row(token) is None
    # close-all-sessions ends every live session for the user.
    t1 = store.create_session(user["id"])
    t2 = store.create_session(user["id"])
    store.close_all_sessions(user["id"])
    assert store.user_for_session(t1) is None
    assert store.user_for_session(t2) is None
    # delete_session ends just that one.
    t3 = store.create_session(user["id"])
    store.delete_session(t3)
    assert store.user_for_session(t3) is None

# ------------------------------------------------------------ unit: HTTP gate


class _StubEngine:
    """Stands in for the engine HTTP API (never for a backend)."""

    def list_characters(self):
        return [{"id": "char-1", "name": "Stub Character"}]

    def list_chats(self):
        return []

    def list_messages(self, chat_id):
        return []


@pytest.fixture()
def webface(tmp_path):
    store = Store(tmp_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(WebfaceApp(store, _StubEngine())))
    server.daemon_threads = True
    thread = __import__("threading").Thread(target=server.serve_forever,
                                            daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()


def test_http_auth_gating_and_entry_flow(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        # Logged out: / is the account page; pages redirect; APIs 401.
        landing = client.get("/")
        assert landing.status_code == 200
        assert "Log in" in landing.text and "Register" in landing.text
        assert client.get("/chat").status_code == 303
        assert client.get("/account").status_code == 303
        assert client.get("/characters").status_code == 303
        assert client.get("/webface/characters").status_code == 401
        assert client.get("/webface/chats").status_code == 401
        # Register auto-logs-in and lands on /chat.
        reg = client.post("/register", data={
            "username": "volmarr", "password": "long-enough-1"})
        assert reg.status_code == 303
        assert reg.headers["location"] == "/chat"
        assert "webface_session" in reg.headers.get("set-cookie", "")
        # Logged in: / goes straight to /chat; the shell shows tabs.
        root = client.get("/")
        assert root.status_code == 303 and root.headers["location"] == "/chat"
        chat = client.get("/chat")
        assert chat.status_code == 200
        for label in ("Chat", "Characters", "Connections", "Account"):
            assert label in chat.text
        chars = client.get("/webface/characters")
        assert chars.status_code == 200 and chars.json()[0]["id"] == "char-1"
        # A pending tab is an honest labelled page, not a dead control.
        # (W-02 superseded the /characters placeholder with the real
        # tab; W-03 superseded /groups the same way; W-05 then
        # superseded /personas + /lorebooks; W-06 superseded /memory
        # + /scenarios, so /inspector — arriving in W-07 — is the
        # pending exemplar now.)
        pending = client.get("/inspector")
        assert pending.status_code == 200 and "W-07" in pending.text
        groups_page = client.get("/groups")
        assert groups_page.status_code == 200 and "g-roster-pick" in groups_page.text
        chars_page = client.get("/characters")
        assert chars_page.status_code == 200 and "c-roster" in chars_page.text
        account = client.get("/account")
        assert account.status_code == 200 and "volmarr" in account.text
        # Duplicate register is refused in plain words.
        dup = client.post("/register", data={
            "username": "volmarr", "password": "long-enough-1"})
        assert "taken" in dup.text
        # Logout ends the session.
        out = client.post("/logout")
        assert out.status_code == 303
        assert client.get("/webface/characters").status_code == 401


def test_http_login_wrong_password(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        client.post("/register", data={
            "username": "volmarr", "password": "long-enough-1"})
        client.post("/logout")
        bad = client.post("/login", data={
            "username": "volmarr", "password": "not-the-password"})
        assert "did not match" in bad.text
        assert client.get("/webface/chats").status_code == 401
        good = client.post("/login", data={
            "username": "volmarr", "password": "long-enough-1"})
        assert good.status_code == 303
        assert client.get("/webface/chats").status_code == 200

# ------------------------------------------------------------ live: real pair

OLLAMA_TAGS_PATHS = ("/api/tags",)


def _ollama_base() -> str | None:
    """The house Ollama base URL, from env or the loopback default;
    the tailnet bind is found via `tailscale ip -4` when loopback
    does not answer (this house serves Ollama on the tailnet)."""
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
            resp = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
            if resp.status_code == 200:
                return base
        except Exception:
            continue
    return None


def _ollama_chat_model(base: str) -> str | None:
    resp = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    names = [m.get("name", "") for m in resp.json().get("models", [])]
    for name in names:
        if "embed" not in name:
            return name
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
def live_pair(tmp_path):
    """A real engine (throwaway data dir) + the real webface."""
    base = _ollama_base()
    if base is None:
        pytest.skip("no real Ollama backend answers on this machine")
    model = _ollama_chat_model(base)
    if model is None:
        pytest.skip("Ollama answers but lists no chat model")
    engine_port, webface_port = _free_port(), _free_port()
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    env["PYTHONPATH"] = str(REPO / "src")
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    engine = subprocess.Popen(
        [sys.executable, "-m", "runmal", "serve", "--host", "127.0.0.1",
         "--port", str(engine_port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    webface_env = dict(env)
    webface_env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    face = None
    try:
        if not _wait_health(f"http://127.0.0.1:{engine_port}/healthz"):
            raise RuntimeError("engine did not come up")
        face = subprocess.Popen(
            [sys.executable, "-m", "runmal.webface", "--host", "127.0.0.1",
             "--port", str(webface_port), "--engine-url",
             f"http://127.0.0.1:{engine_port}", "--data-dir",
             str(tmp_path / "webface-data"), "--engine-data-dir",
             str(tmp_path / "engine-data")],
            env=webface_env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        yield {
            "engine": f"http://127.0.0.1:{engine_port}",
            "webface": f"http://127.0.0.1:{webface_port}",
            "ollama": base, "model": model,
            "data_dir": tmp_path / "engine-data",
        }
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _engine_headers(data_dir: Path) -> dict:
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def test_live_send_turn_real_backend(live_pair):
    engine, face = live_pair["engine"], live_pair["webface"]
    headers = _engine_headers(live_pair["data_dir"])
    with httpx.Client(trust_env=False, timeout=120) as eng:
        profile = eng.post(f"{engine}/api/v1/backend-profiles", headers=headers,
                           json={"name": "w01-live", "chat_backend": "ollama",
                                 "chat_model": live_pair["model"],
                                 "config": {"base_url": live_pair["ollama"]}})
        assert profile.status_code in (200, 201), profile.text
        profile_id = profile.json()["id"]
        character = eng.post(f"{engine}/api/v1/characters", headers=headers,
                             json={"card": {
                                 "name": "Live Gate Keeper",
                                 "description": "Keeper of the W-01 gate.",
                                 "system_prompt": "You are the Live Gate "
                                 "Keeper. Answer briefly and warmly.",
                                 "first_mes": "State your business."}})
        assert character.status_code in (200, 201), character.text
        chat = eng.post(f"{engine}/api/v1/chats", headers=headers, json={
            "title": "W-01 live", "character_id": character.json()["id"]})
        assert chat.status_code in (200, 201), chat.text
        chat_id = chat.json()["id"]
        pin = eng.post(f"{engine}/api/v1/chats/{chat_id}/backend-profile",
                       headers=headers, json={"profile_id": profile_id})
        assert pin.status_code == 200, pin.text
    with httpx.Client(base_url=face, trust_env=False, timeout=180,
                      follow_redirects=False) as web:
        reg = web.post("/register", data={
            "username": "w01live", "password": "long-enough-1"})
        assert reg.status_code == 303
        events = []
        with web.stream("POST", f"/webface/chats/{chat_id}/send",
                        json={"content": "Hello, keeper. Who are you?"}) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[len("data:"):].strip()))
        kinds = [e.get("type") for e in events]
        assert "token" in kinds and "done" in kinds and "landed" in kinds
        started = next(e for e in events if e.get("type") == "started")
        assert started["backend_key"] != "fake", started
        assert started["mode"] == "composed", started
        reply = "".join(e.get("text", "") for e in events
                        if e.get("type") == "token")
        assert reply.strip(), "streamed reply must be non-empty"
    with httpx.Client(trust_env=False, timeout=30) as eng:
        history = eng.get(f"{engine}/api/v1/chats/{chat_id}/messages",
                          headers=headers).json()
        roles = [m["role"] for m in history]
        assert "user" in roles and "assistant" in roles
        landed = [m for m in history if m["role"] == "assistant"][-1]
        assert landed["content"].strip() == reply.strip()
