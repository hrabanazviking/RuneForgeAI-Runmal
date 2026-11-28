"""W-10 acceptance: account hardening + agent access + audit pins.

Unit half: recovery-code digest storage + one-time semantics +
regeneration invalidation + the attempt throttle; password
change closing every session; agent-token digest storage,
name/date-only listing, immediate revocation; agent scope
refusals (a token is not a session and administers nothing);
the agent send over a stub engine rides stub_guard (unpinned ->
no-mind payload, nothing appended). Audit pins: templates.PENDING
== {} and every password input the face serves carries
data-pw-toggle (W-05B rule 9, final-face inventory).
Live half: a REAL served engine + REAL webface + real Ollama:
password change closes sessions (old password refused, new one
works); recovery end-to-end (code works once, reuse refused,
regeneration kills the old set); the agent door end-to-end
(no-token 401, whoami, characters, chat create, a real reply
from the pinned Gate Keeper chat, history read-back, unpinned
no-mind honesty, revoked token 401); and the engine bridge
counterpart fix (an unpinned bridge chat's generate refuses
no_mind and stores nothing).
Healed pin (listed per the campaign rule): test_w01's account
assertion - the Account page's "arrives in W-10" note was the
last pending exemplar; W-10 builds it, so the exemplar retires
to the built sections (change password / recovery / tokens).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.webface import templates, w10
from runmal.webface.app import WebfaceApp, make_handler
from runmal.webface.security import digest, hash_password
from runmal.webface.store import Store

REPO = Path(__file__).parent.parent


# ------------------------------------------------------------ unit: recovery


def _mkuser(store, name="volmarr", pw="long-enough-1"):
    return store.create_user(name, hash_password(pw))


def test_recovery_codes_are_digest_stored_and_shown_once_shape(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    codes = w10.generate_recovery_codes(store, user["id"])
    assert len(codes) == w10.RECOVERY_CODE_COUNT
    db = sqlite3.connect(str(tmp_path / "webface.db"))
    rows = db.execute("SELECT code_hash FROM recovery_codes").fetchall()
    assert len(rows) == len(codes)
    stored = {r[0] for r in rows}
    for code in codes:
        assert code not in stored  # plaintext never stored
        assert digest(w10.normalize_code(code)) in stored


def test_recovery_one_time_and_regeneration_invalidates(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    codes = w10.generate_recovery_codes(store, user["id"])
    ok, _ = w10.recover_account(store, "volmarr", codes[0], "brand-new-pw-1")
    assert ok
    assert store.get_user_by_name("volmarr")
    from runmal.webface.security import verify_password
    assert verify_password("brand-new-pw-1", store.get_user_by_name("volmarr")["pass_hash"])
    # reuse refused
    ok, words = w10.recover_account(store, "volmarr", codes[0], "another-pw-123")
    assert not ok and "did not" in words
    # regeneration invalidates the rest of the old set
    codes2 = w10.generate_recovery_codes(store, user["id"])
    ok, _ = w10.recover_account(store, "volmarr", codes[1], "another-pw-123")
    assert not ok
    ok, _ = w10.recover_account(store, "volmarr", codes2[3], "final-pw-12345")
    assert ok


def test_recovery_throttle_locks_after_five_failures(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    codes = w10.generate_recovery_codes(store, user["id"])
    for _ in range(w10.RECOVERY_MAX_FAILURES):
        ok, _ = w10.recover_account(store, "volmarr", "ZZZZ-ZZZZ-ZZZZ", "whatever-pw-1")
        assert not ok
    assert w10.recovery_locked(store, "volmarr")
    # even the genuine code is refused while locked
    ok, words = w10.recover_account(store, "volmarr", codes[0], "whatever-pw-1")
    assert not ok and "paused" in words


def test_recovery_closes_all_sessions(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    token = store.create_session(user["id"])
    codes = w10.generate_recovery_codes(store, user["id"])
    ok, _ = w10.recover_account(store, "volmarr", codes[0], "brand-new-pw-1")
    assert ok and store.user_for_session(token) is None


# ------------------------------------------------------------ unit: password + tokens


def test_change_password_closes_every_session(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    t1, t2 = store.create_session(user["id"]), store.create_session(user["id"])
    ok, words = w10.change_password(store, user, "wrong-current", "new-password-1")
    assert not ok and store.user_for_session(t1) is not None  # nothing changed
    fresh = store.get_user(user["id"])
    ok, words = w10.change_password(store, fresh, "long-enough-1", "new-password-1")
    assert ok and "closed" in words
    assert store.user_for_session(t1) is None and store.user_for_session(t2) is None
    from runmal.webface.security import verify_password
    assert verify_password("new-password-1", store.get_user(user["id"])["pass_hash"])


def test_agent_token_digest_storage_and_revocation(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    view, token = w10.create_agent_token(store, user["id"], "Yrsa")
    assert token.startswith("rma_")
    db = sqlite3.connect(str(tmp_path / "webface.db"))
    rows = db.execute("SELECT token_hash FROM agent_tokens").fetchall()
    assert rows[0][0] == digest(token) and rows[0][0] != token
    listed = store.list_agent_tokens(user["id"])
    blob = json.dumps([w10.token_view(r) for r in listed])
    assert token not in blob and digest(token) not in blob
    auth = store.agent_for_token(token)
    assert auth is not None and auth[1]["username"] == "volmarr"
    assert store.revoke_agent_token(user["id"], view["id"])
    assert store.agent_for_token(token) is None  # revocation is immediate
    assert store.agent_for_token("rma_not-a-token") is None
    assert store.agent_for_token("") is None


def test_sessions_list_shape(tmp_path):
    store = Store(tmp_path)
    user = _mkuser(store)
    store.create_session(user["id"])
    rows = store.list_sessions(user["id"])
    assert len(rows) == 1 and set(rows[0]) == {"created_at", "expires"}


# ------------------------------------------------------------ unit: HTTP + agent scope


class _StubEngine:
    """Stands in for the engine HTTP API (never for a backend)."""

    def __init__(self):
        self.chats = {"chat-real": {"id": "chat-real", "backend_profile_id": "p1"},
                      "chat-none": {"id": "chat-none", "backend_profile_id": None}}
        self.profiles = [{"id": "p1", "name": "House", "chat_backend": "ollama",
                          "chat_model": "llama3.2:3b"}]
        self.messages = []

    def request(self, method, path, **kw):
        if path == "/api/v1/backend-profiles":
            return self.profiles
        for cid, chat in self.chats.items():
            if path == f"/api/v1/chats/{cid}":
                return chat
        raise AssertionError(path)

    def list_characters(self):
        return [{"id": "char-1", "name": "Stub Character"}]

    def list_chats(self):
        return list(self.chats.values())

    def list_messages(self, chat_id):
        return [m for m in self.messages if m["chat_id"] == chat_id]

    def create_chat(self, *, character_id, title=""):
        chat = {"id": "chat-new", "backend_profile_id": None}
        self.chats["chat-new"] = chat
        return chat

    def append_message(self, chat_id, role, content):
        msg = {"chat_id": chat_id, "role": role, "content": content}
        self.messages.append(msg)
        return msg

    def stream_generate(self, chat_id, request_id):
        yield ("started", {"backend_key": "ollama", "mode": "composed"})
        yield ("token", {"type": "token", "text": "Stub reply."})
        yield ("done", {"type": "done", "finish_reason": "stop"})

    def cancel_generate(self, request_id):
        return True


@pytest.fixture()
def face(tmp_path):
    store = Store(tmp_path)
    engine = _StubEngine()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(WebfaceApp(store, engine)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, store, engine
    server.shutdown()


def _register(client, name="volmarr", pw="long-enough-1"):
    return client.post("/register", data={"username": name, "password": pw})


def test_http_password_change_and_recovery_circuits(face):
    base, store, _engine = face
    with httpx.Client(base_url=base, follow_redirects=False, trust_env=False) as c:
        _register(c)
        # wrong current password: refused in words, session survives
        bad = c.post("/account/password", data={
            "current_password": "nope-nope", "new_password": "new-password-1"})
        assert "did not match" in bad.text
        assert c.get("/webface/chats").status_code == 200
        # right current: all sessions close, incl. this one
        ok = c.post("/account/password", data={
            "current_password": "long-enough-1", "new_password": "new-password-1"})
        assert ok.status_code == 303
        assert c.get("/webface/chats").status_code == 401
        old = c.post("/login", data={"username": "volmarr", "password": "long-enough-1"})
        assert "did not match" in old.text
        new = c.post("/login", data={"username": "volmarr", "password": "new-password-1"})
        assert new.status_code == 303
        # recovery codes via the account road; plaintext shown once here
        gen = c.post("/account/recovery-codes", data={})
        found = re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", gen.text)
        assert len(found) == w10.RECOVERY_CODE_COUNT
        again = c.get("/account")
        assert found[0] not in again.text  # never shown again
        c.post("/logout")
        rec = c.post("/recover", data={
            "username": "volmarr", "code": found[0],
            "new_password": "recovered-pw-1"})
        assert "Password set" in rec.text
        reuse = c.post("/recover", data={
            "username": "volmarr", "code": found[0],
            "new_password": "recovered-pw-2"})
        assert "did not" in reuse.text
        login = c.post("/login", data={"username": "volmarr", "password": "recovered-pw-1"})
        assert login.status_code == 303


def test_http_agent_door_and_scope_refusals(face):
    base, store, engine = face
    with httpx.Client(base_url=base, follow_redirects=False, trust_env=False) as c:
        _register(c)
        made = c.post("/account/agent-tokens", data={"name": "Yrsa"})
        found = re.findall(r"rma_[A-Za-z0-9_\-]+", made.text)
        assert len(found) == 1
        token = found[0]
        assert token not in c.get("/account").text  # shown exactly once
        auth = {"Authorization": f"Bearer {token}"}
        # no token / bad token -> 401
        assert c.get("/agent/v1/whoami").status_code == 401
        assert c.get("/agent/v1/whoami",
            headers={"Authorization": "Bearer rma_x"}).status_code == 401
        who = c.get("/agent/v1/whoami", headers=auth)
        assert who.status_code == 200 and who.json()["account"] == "volmarr"
        assert token not in who.text
        chars = c.get("/agent/v1/characters", headers=auth)
        assert chars.json()[0]["name"] == "Stub Character"
        # unpinned chat -> no-mind payload, nothing appended
        none = c.post("/agent/v1/chats/chat-none/send", headers=auth,
                      json={"content": "hello?"})
        assert none.json()["type"] == "no_mind"
        assert engine.list_messages("chat-none") == []
        # pinned chat -> one JSON reply exchange
        real = c.post("/agent/v1/chats/chat-real/send", headers=auth,
                      json={"content": "hello keeper"})
        assert real.json()["type"] == "reply" and real.json()["reply"] == "Stub reply."
        hist = c.get("/agent/v1/chats/chat-real/messages", headers=auth)
        assert [m["role"] for m in hist.json()] == ["user", "assistant"]
        # SCOPE: the token administers nothing. These attempts ride
        # a cookie-free client: the agent holds ONLY the token, so
        # the account roads must refuse it as a stranger (redirect
        # to the account page), and nothing may change.
        with httpx.Client(base_url=base, follow_redirects=False,
                          trust_env=False) as agent_only:
            pw = agent_only.post("/account/password", headers=auth, data={
                "current_password": "long-enough-1", "new_password": "pwned-pw-123"})
            assert pw.status_code == 303  # bounced to / (not signed in)
            tk = agent_only.post("/account/agent-tokens", headers=auth,
                                 data={"name": "second"})
            assert tk.status_code == 303
        from runmal.webface.security import verify_password
        assert verify_password("long-enough-1", store.get_user_by_name("volmarr")["pass_hash"])
        assert len(store.list_agent_tokens(store.get_user_by_name("volmarr")["id"])) == 1
        # a session cookie is not an agent token
        assert c.get("/agent/v1/whoami").status_code == 401
        # revocation kills it immediately
        tid = store.list_agent_tokens(store.get_user_by_name("volmarr")["id"])[0]["id"]
        c.post(f"/account/agent-tokens/{tid}/revoke", data={})
        assert c.get("/agent/v1/whoami", headers=auth).status_code == 401


def test_audit_pins_pending_empty_and_password_inventory(face):
    base, _store, _engine = face
    assert templates.PENDING == {}
    pages = ["/", "/login", "/register", "/recover"]
    with httpx.Client(base_url=base, follow_redirects=False, trust_env=False) as c:
        for page in pages:
            text = c.get(page).text
            for tag in re.findall(r"<input[^>]*>", text):
                if 'type="password"' in tag:
                    assert "data-pw-toggle" in tag, (page, tag)
        _register(c)
        account = c.get("/account").text
        pw_tags = [t for t in re.findall(r"<input[^>]*>", account)
                   if 'type="password"' in t]
        assert len(pw_tags) == 2  # change-password pair
        assert all("data-pw-toggle" in t for t in pw_tags)


# ------------------------------------------------------------ live: real pair


def _ollama_base():
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
            if httpx.get(base + "/api/tags", timeout=5, trust_env=False).status_code == 200:
                return base
        except Exception:
            continue
    return None


def _free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_health(url, timeout_s=60.0):
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
    base = _ollama_base()
    if base is None:
        pytest.skip("no real Ollama backend answers on this machine")
    resp = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    names = [m.get("name", "") for m in resp.json().get("models", [])]
    model = next((n for n in names if "embed" not in n), None)
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
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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


def _engine_headers(data_dir):
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def test_live_w10_circuit(live_pair):
    engine, face = live_pair["engine"], live_pair["webface"]
    headers = _engine_headers(live_pair["data_dir"])
    with httpx.Client(trust_env=False, timeout=120) as eng:
        profile = eng.post(f"{engine}/api/v1/backend-profiles", headers=headers,
                           json={"name": "w10-house-ollama", "chat_backend": "ollama",
                                 "chat_model": live_pair["model"],
                                 "config": {"base_url": live_pair["ollama"]}})
        assert profile.status_code in (200, 201), profile.text
        character = eng.post(f"{engine}/api/v1/characters", headers=headers,
                             json={"card": {
                                 "name": "Webface Gate Keeper",
                                 "description": "Keeper of the W-10 gate.",
                                 "system_prompt": "You are the Webface Gate "
                                 "Keeper. Answer briefly and warmly.",
                                 "first_mes": "State your business."}})
        assert character.status_code in (200, 201), character.text
        char_id = character.json()["id"]
        chat = eng.post(f"{engine}/api/v1/chats", headers=headers,
                        json={"title": "W-10 live", "character_id": char_id})
        chat_id = chat.json()["id"]
        pin = eng.post(f"{engine}/api/v1/chats/{chat_id}/backend-profile",
                       headers=headers, json={"profile_id": profile.json()["id"]})
        assert pin.status_code == 200, pin.text
        bare = eng.post(f"{engine}/api/v1/chats", headers=headers,
                        json={"title": "W-10 unpinned", "character_id": char_id})
        bare_id = bare.json()["id"]
    with httpx.Client(base_url=face, trust_env=False, timeout=180,
                      follow_redirects=False) as web:
        reg = web.post("/register", data={"username": "w10live", "password": "first-password-1"})
        assert reg.status_code == 303
        # hardening: change password closes the session; old refused, new works
        changed = web.post("/account/password", data={
            "current_password": "first-password-1", "new_password": "second-password-1"})
        assert changed.status_code == 303
        assert web.get("/webface/chats").status_code == 401
        assert "did not match" in web.post("/login", data={
            "username": "w10live", "password": "first-password-1"}).text
        assert web.post("/login", data={
            "username": "w10live", "password": "second-password-1"}).status_code == 303
        # recovery codes: generate, recover logged-out, reuse refused
        gen = web.post("/account/recovery-codes", data={})
        codes = re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", gen.text)
        assert len(codes) == w10.RECOVERY_CODE_COUNT
        web.post("/logout")
        rec = web.post("/recover", data={"username": "w10live", "code": codes[0],
                                          "new_password": "third-password-1"})
        assert "Password set" in rec.text
        assert "did not" in web.post("/recover", data={
            "username": "w10live", "code": codes[0],
            "new_password": "fourth-password-1"}).text
        assert web.post("/login", data={
            "username": "w10live", "password": "third-password-1"}).status_code == 303
        # agent door
        made = web.post("/account/agent-tokens", data={"name": "w10-proof-agent"})
        found = re.findall(r"rma_[A-Za-z0-9_\-]+", made.text)
        assert len(found) == 1
        auth = {"Authorization": f"Bearer {found[0]}"}
        assert web.get("/agent/v1/whoami").status_code == 401
        who = web.get("/agent/v1/whoami", headers=auth)
        assert who.status_code == 200 and who.json()["agent"] == "w10-proof-agent"
        chars = web.get("/agent/v1/characters", headers=auth).json()
        assert any(c["id"] == char_id for c in chars)
        reply = web.post(f"/agent/v1/chats/{chat_id}/send", headers=auth,
                         json={"content": "Hello, keeper. Who are you?"})
        assert reply.status_code == 200, reply.text
        payload = reply.json()
        assert payload["type"] == "reply" and payload["reply"].strip(), payload
        hist = web.get(f"/agent/v1/chats/{chat_id}/messages", headers=auth).json()
        assert hist[-1]["role"] == "assistant"
        assert hist[-1]["content"].strip() == payload["reply"].strip()
        none = web.post(f"/agent/v1/chats/{bare_id}/send", headers=auth,
                        json={"content": "anyone there?"})
        assert none.json()["type"] == "no_mind"
        # revoke -> immediate 401
        acct = web.get("/account").text
        ids = re.findall(r"/account/agent-tokens/(\d+)/revoke", acct)
        assert ids
        web.post(f"/account/agent-tokens/{ids[-1]}/revoke", data={})
        assert web.get("/agent/v1/whoami", headers=auth).status_code == 401
    # engine bridge counterpart: unpinned generate refuses no_mind, stores nothing
    with httpx.Client(trust_env=False, timeout=60) as eng:
        cred = eng.post(f"{engine}/api/v1/bridge/credentials", headers=headers,
                        json={"name": "w10-check", "scopes": [f"chat:read:{bare_id}",
                            f"chat:write:{bare_id}"]})
        assert cred.status_code in (200, 201), cred.text
        bridge_auth = {"Authorization": f"Bearer {cred.json()['token']}"}
        before = eng.get(f"{engine}/api/v1/bridge/chats/{bare_id}", headers=bridge_auth).json()
        resp = eng.post(f"{engine}/api/v1/bridge/chats/{bare_id}/generate",
                        headers=bridge_auth, json={})
        events = [json.loads(line[6:]) for line in resp.text.splitlines()
                  if line.startswith("data: ")]
        assert events and events[0].get("code") == "no_mind", events
        after = eng.get(f"{engine}/api/v1/bridge/chats/{bare_id}", headers=bridge_auth).json()
        assert len(after["messages"]) == len(before["messages"])
