"""W-05 acceptance: Personas + Lorebooks tabs.

Unit half: the pure W-05 logic - the census form model read
from the engine's own P-042 census (activation_kind derived,
never sent), the lossless compose (unknown fields survive,
only changed census fields are PATCHed), the verdict-words
renderers, and the user-name semantics (empty never clears;
clearing is explicit). Live half: a REAL served engine
(throwaway data dir) + REAL webface + REAL Ollama over HTTP,
plus a recording OpenAI-compatible echo fixture proving the
set {{user}} name reaches the backend inside the composed
system prompt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.lorebooks.editor import editor_schema
from runmal.webface import w05
from runmal.webface.engine import EngineError

REPO = Path(__file__).parent.parent


# ------------------------------------------------------------ unit: census


def test_census_form_model_matches_engine_census():
    schema = editor_schema()
    book = w05.schema_fields(schema, "book")
    entry = w05.schema_fields(schema, "entry")
    scope = w05.schema_fields(schema, "scope")
    assert [f.name for f in book] == [
        "name", "description", "scan_depth", "token_budget",
        "scan_mode", "scan_external_context"]
    assert len(entry) == 21
    assert [f.name for f in entry if f.derived] == ["activation_kind"]
    assert [f.name for f in scope] == [
        "scope_kind", "owner_id", "token_budget", "position"]
    assert book[4].options == ["depth", "whole_chat"]
    assert w05.schema_fields({}, "book") == []


def test_parse_form_values_types_and_derived_never_read():
    fields = w05.schema_fields(editor_schema(), "entry")
    values = w05.parse_form_values(fields, {
        "name": "Ember fact", "keys": ["ember", " gate "],
        "secondary_keys": "ash\ncoal", "probability": "90",
        "depth": "", "enabled": True, "constant": False,
        "activation_kind": "constant",
    })
    assert values["keys"] == ["ember", "gate"]
    assert values["secondary_keys"] == ["ash", "coal"]
    assert values["probability"] == 90 and values["depth"] is None
    assert "activation_kind" not in values
    with pytest.raises(EngineError):
        w05.parse_form_values(fields, {"probability": "lots"})


def test_collect_fields_carries_unknown_and_skips_derived():
    fields = w05.schema_fields(editor_schema(), "entry")
    base = {"name": "Old", "vendor_future_field": "keep-me",
            "activation_kind": "keyword", "future_blob": {"x": 1}}
    out = w05.collect_fields(fields, {"name": "New"}, base)
    assert out["name"] == "New"
    assert out["vendor_future_field"] == "keep-me"
    assert out["future_blob"] == {"x": 1}
    out2 = w05.collect_fields(fields, {"activation_kind": "constant"}, base)
    assert out2["activation_kind"] == "keyword"  # never overlaid


def test_activation_kind_words():
    assert w05.activation_kind_words({"constant": True}) == "constant (always on)"
    assert w05.activation_kind_words({"vectorised": True}) == "vectorised (similarity)"
    assert w05.activation_kind_words({}) == "keyword"


def test_verdict_and_layer_and_scope_words():
    row = {"name": "Ember fact", "status": "included",
           "matched_primary": ["ember"], "scope": "character",
           "tokens": 7}
    words = w05.verdict_words(row)
    assert words.startswith("Ember fact: Included")
    assert "matched key ember" in words and "7 tokens" in words
    quiet = w05.verdict_words({"name": "Ember fact",
                               "status": "not_triggered"})
    assert quiet == "Ember fact: Not triggered"
    layer = w05.layer_words({"scope": "character",
                             "books": [{"name": "Gate World"}],
                             "budget": 250, "tokens_used": 7,
                             "included": 1, "discarded": 0})
    assert "Gate World" in layer and "budget 250" in layer
    assert "1 included" in layer
    scope = w05.scope_words({"scope_kind": "character",
                             "owner_id": "c1", "token_budget": 500,
                             "position": 1}, "Keeper")
    assert "Character" in scope and "Keeper" in scope
    assert "budget 500 tokens" in scope and "position 1" in scope


# ------------------------------------------------------- unit: fake engine


class _FakeEngine:
    def __init__(self):
        self.calls = []
        self.user_name = {"user_name": "User", "is_set": False}
        self.entry = {
            "id": "e1", "lorebook_id": "b1", "name": "Old",
            "content": "c", "keys": ["ember"], "secondary_keys": [],
            "selective_logic": "and_any", "inclusion_group": "",
            "group_weight": 100, "probability": 100, "priority": 100,
            "position": "before_char", "depth": None, "role": "system",
            "enabled": True, "constant": False, "vectorised": False,
            "activation_kind": "keyword", "case_sensitive": False,
            "whole_word": True, "sticky_prompts": 0,
            "cooldown_prompts": 0, "delay_prompts": 0,
            "vendor_future_field": "keep-me",
        }

    def request(self, method, path, json_body=None, params=None, **kw):
        self.calls.append((method, path, json_body))
        if path == "/api/v1/lorebooks/editor-schema":
            return editor_schema()
        if path == "/api/v1/user-name":
            if method == "PUT":
                name = str((json_body or {}).get("user_name") or "")
                self.user_name = {"user_name": name or "User",
                                  "is_set": bool(name)}
            return dict(self.user_name)
        if path.endswith("/entries/e1") and method == "GET":
            return dict(self.entry)
        if path.endswith("/entries/e1") and method == "PATCH":
            self.entry.update(json_body or {})
            return dict(self.entry)
        return {}


def test_user_name_empty_never_clears_and_clear_is_explicit():
    eng = _FakeEngine()
    out = w05.set_user_name(eng, "Volmarr")
    assert out["is_set"] and out["user_name"] == "Volmarr"
    out = w05.set_user_name(eng, "   ")
    assert out["kept"] is True and out["user_name"] == "Volmarr"
    out = w05.set_user_name(eng, "", clear=True)
    assert out["cleared"] is True and out["is_set"] is False
    assert out["user_name"] == "User"


def test_save_entry_lossless_only_changed_census_fields_patch():
    eng = _FakeEngine()
    saved = w05.save_entry(eng, "b1", "e1", {"values": {
        "name": "New", "activation_kind": "constant"}})
    patches = [c for c in eng.calls if c[0] == "PATCH"]
    assert len(patches) == 1
    assert patches[0][2] == {"name": "New"}, patches
    assert saved["vendor_future_field"] == "keep-me"
    # A no-change save sends nothing at all.
    eng.calls.clear()
    w05.save_entry(eng, "b1", "e1", {"values": {"name": "New"}})
    assert not [c for c in eng.calls if c[0] == "PATCH"]


def test_persona_file_note_is_honest():
    assert "no engine route serves it" in w05.PERSONA_FILE_NOTE
    assert "future turns only" in w05.FUTURE_TURNS_NOTE.lower()


# ------------------------------------------------------------ live pair


def _ollama_base() -> str | None:
    candidates = []
    if os.environ.get("RUNMAL_TEST_OLLAMA_URL"):
        candidates.append(os.environ["RUNMAL_TEST_OLLAMA_URL"])
    candidates += ["http://100.67.240.22:11434", "http://127.0.0.1:11434"]
    for base in candidates:
        try:
            r = httpx.get(base + "/api/tags", timeout=3, trust_env=False)
            if r.status_code == 200:
                return base
        except Exception:
            continue
    return None


def _ollama_models(base: str) -> list[str]:
    r = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    return [m["name"] for m in r.json().get("models", [])]


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(url: str, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2, trust_env=False).status_code == 200:
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
    models = _ollama_models(base)
    if not models:
        pytest.skip("no real Ollama chat model on this machine")
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
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True)
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        yield {"engine": f"http://127.0.0.1:{engine_port}",
               "webface": f"http://127.0.0.1:{webface_port}",
               "ollama": base, "models": models,
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


def _sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        assert resp.status_code == 200, resp.status_code
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


class _Echo:
    """A real transient OpenAI-compatible HTTP fixture that
    records request bodies (the R-05/R-09/W-04 proof pattern)."""

    def __init__(self):
        self.bodies: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/models"):
                    body = json.dumps({"data": [{"id": "echo-1"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    outer.bodies.append(json.loads(raw.decode()))
                except ValueError:
                    outer.bodies.append({})
                lines = [
                    'data: {"choices": [{"delta": {"content": "echo reply"}}]}',
                    'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}',
                    "data: [DONE]", "",
                ]
                body = "\n".join(lines).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.shutdown()


def _register(web, name="w05live"):
    reg = web.post("/register", data={"username": name,
                                      "password": "long-enough-1"})
    assert reg.status_code == 303, reg.status_code


def _card(name, system_prompt):
    return {"name": name, "description": f"{name} of the gate.",
            "personality": "Calm.", "scenario": "The high pass.",
            "system_prompt": system_prompt,
            "first_mes": f"Well met, I am {name}."}


def test_live_personas_lorebooks_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    model = "llama3.2:3b" if "llama3.2:3b" in pair["models"] else pair["models"][0]
    eng = httpx.Client(base_url=engine, trust_env=False, timeout=300,
                       headers=headers)
    echo = _Echo()
    try:
        with httpx.Client(base_url=face, trust_env=False, timeout=300,
                          follow_redirects=False) as web:
            # Auth gating + graduated pages.
            assert web.get("/webface/persona/user-name").status_code == 401
            assert web.get("/webface/lorebooks/schema").status_code == 401
            assert web.get("/personas").status_code == 303
            _register(web)
            personas = web.get("/personas")
            assert personas.status_code == 200
            assert "Persona files" in personas.text
            assert "arrives in slice" not in personas.text
            lore_page = web.get("/lorebooks")
            assert lore_page.status_code == 200
            assert "lb-list" in lore_page.text
            assert "arrives in slice" not in lore_page.text
            # Census over the wire: 6 book fields, 21 entry fields.
            census = web.get("/webface/lorebooks/schema").json()
            assert len(census["forms"]["book"]) == 6
            assert len(census["forms"]["entry"]) == 21
            derived = [f for f in census["forms"]["entry"] if f["derived"]]
            assert [f["name"] for f in derived] == ["activation_kind"]
            # Characters + a real Ollama profile + chat.
            keeper = web.post("/webface/characters", json={
                "name": "W05 Keeper",
                "description": "Keeps the W-05 gate.",
                "system_prompt": "You speak with {{user}}. Answer briefly.",
                "first_mes": "W05 Keeper at the gate."})
            assert keeper.status_code == 200, keeper.text
            keeper_id = keeper.json()["id"]
            bearer = web.post("/webface/characters", json={
                "name": "W05 Bearer",
                "description": "Bears the W-05 mask.",
                "system_prompt": "You are the W05 Bearer. Answer briefly.",
                "first_mes": "W05 Bearer at the gate."})
            bearer_id = bearer.json()["id"]
            prof = web.post("/webface/profiles", json={
                "name": "w05-ollama", "chat_backend": "ollama",
                "chat_model": model, "base_url": pair["ollama"]})
            assert prof.status_code == 200, prof.text
            chat = web.post("/webface/chats",
                            json={"character_id": keeper_id})
            chat_id = chat.json()["id"]
            pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                           json={"profile_id": prof.json()["id"]})
            assert pin.status_code == 200, pin.text
            # ---- user name: set, empty-keeps, wire proof, clear ----
            state = web.put("/webface/persona/user-name",
                            json={"user_name": "W05 Tester"}).json()
            assert state["is_set"] and state["user_name"] == "W05 Tester"
            direct = eng.get("/api/v1/user-name").json()
            assert direct == {"user_name": "W05 Tester", "is_set": True}
            kept = web.put("/webface/persona/user-name",
                           json={"user_name": "  "}).json()
            assert kept["kept"] is True and kept["user_name"] == "W05 Tester"
            assert eng.get("/api/v1/user-name").json()["is_set"] is True
            # The name REACHES the backend inside the composed
            # system prompt (echo fixture records the wire body).
            echo_prof = web.post("/webface/profiles", json={
                "name": "w05-echo", "chat_backend": "openai",
                "chat_model": "echo-1", "base_url": echo.url}).json()
            web.post(f"/webface/chats/{chat_id}/backend-profile",
                     json={"profile_id": echo_prof["id"]})
            events = _sse(web, f"/webface/chats/{chat_id}/send",
                          {"content": "Who am I?"})
            assert any(e.get("type") == "landed" for e in events), events
            assert echo.bodies, "echo backend saw no request"
            wire = json.dumps(echo.bodies[-1])
            assert "W05 Tester" in wire and "{{user}}" not in wire
            web.post(f"/webface/chats/{chat_id}/backend-profile",
                     json={"profile_id": prof.json()["id"]})
            # ---- per-chat persona: switch, agree everywhere, clear ----
            before = web.get(f"/webface/chats/{chat_id}/persona").json()
            assert before["persona"]["character_id"] == keeper_id
            switched = web.post(f"/webface/chats/{chat_id}/persona",
                                json={"character_id": bearer_id}).json()
            assert switched["persona"]["character_id"] == bearer_id
            assert "future turns only" in switched["note"].lower()
            assert eng.get(f"/api/v1/chats/{chat_id}/persona").json()[
                "persona"]["character_id"] == bearer_id
            rows = web.get("/webface/chats").json()
            row = next(r for r in rows if r["id"] == chat_id)
            assert row["character_id"] == bearer_id  # Chat tab's read
            cleared = web.post(f"/webface/chats/{chat_id}/persona",
                               json={"character_id": None}).json()
            assert cleared["persona"] is None
            assert eng.get(f"/api/v1/chats/{chat_id}/persona").json()[
                "persona"] is None
            back = web.post(f"/webface/chats/{chat_id}/persona",
                            json={"character_id": keeper_id}).json()
            assert back["persona"]["character_id"] == keeper_id
            # ---- lorebook + entry through the census form shape ----
            book = web.post("/webface/lorebooks", json={"values": {
                "name": "W-05 Test World", "description": "W-05 lore.",
                "scan_depth": "4", "token_budget": "",
                "scan_mode": "depth", "scan_external_context": False}})
            assert book.status_code == 200, book.text
            book_id = book.json()["id"]
            entry = web.post(f"/webface/lorebooks/{book_id}/entries",
                             json={"values": {
                "name": "Ember fact",
                "content": "The gate ember remembers every traveller.",
                "keys": ["ember"], "secondary_keys": [],
                "selective_logic": "and_any", "inclusion_group": "",
                "group_weight": "100", "probability": "100",
                "priority": "100", "position": "before_char",
                "depth": "", "role": "system", "enabled": True,
                "constant": False, "vectorised": False,
                "case_sensitive": False, "whole_word": True,
                "sticky_prompts": "0", "cooldown_prompts": "0",
                "delay_prompts": "0",
                "activation_kind": "constant"}})  # derived: never sent
            assert entry.status_code == 200, entry.text
            entry_id = entry.json()["id"]
            stored = eng.get(
                f"/api/v1/lorebooks/{book_id}/entries/{entry_id}").json()
            assert stored["keys"] == ["ember"]
            # Derived by the engine; the form-sent "constant"
            # decoy value never travelled.
            assert stored["activation_kind"] == "selective"
            # Untouched fields survive a webface edit verbatim:
            # seed distinctive values straight on the engine, then
            # edit ONLY the name through the webface.
            eng.patch(f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
                      json={"inclusion_group": "suns",
                            "secondary_keys": ["gate"],
                            "probability": 90})
            renamed = web.patch(
                f"/webface/lorebooks/{book_id}/entries/{entry_id}",
                json={"values": {"name": "Ember fact, renamed"}})
            assert renamed.status_code == 200, renamed.text
            after = eng.get(
                f"/api/v1/lorebooks/{book_id}/entries/{entry_id}").json()
            assert after["name"] == "Ember fact, renamed"
            assert after["inclusion_group"] == "suns"
            assert after["secondary_keys"] == ["gate"]
            assert after["probability"] == 90
            assert after["content"].startswith("The gate ember")
            # Restore certainty for the preview leg (probability
            # rolls are real; 90 would make verdicts a coin toss).
            eng.patch(f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
                      json={"probability": 100})
            # ---- scope assignment + the binding shown separately ----
            scope = web.put(f"/webface/lorebooks/{book_id}/scope", json={
                "scope_kind": "character", "owner_id": keeper_id,
                "token_budget": 500, "position": 1})
            assert scope.status_code == 200, scope.text
            assert "budget 500 tokens" in scope.json()["words"]
            eng.put(f"/api/v1/characters/{bearer_id}/lorebook-binding",
                    json={"lorebook_id": book_id})
            detail = web.get(f"/webface/lorebooks/{book_id}").json()
            assert len(detail["scopes"]) == 1, detail["scopes"]
            assert len(detail["bindings"]) == 1, detail["bindings"]
            assert "Card binding" in detail["bindings"][0]["words"]
            assert "different mechanism" in detail["scope_note"]
            # ---- real send + layered preview verdicts in words ----
            events = _sse(web, f"/webface/chats/{chat_id}/send", {
                "content": "Tell me about the ember at the gate."})
            assert any(e.get("type") == "landed" for e in events), events
            fired = web.post(f"/webface/chats/{chat_id}/lore-preview",
                             json={"messages": [
                                 "Tell me about the ember at the gate."]}).json()
            rows = [r for r in fired["rows"] if r["entry_id"] == entry_id]
            assert rows and rows[0]["status"] == "included", fired
            assert "ember" in rows[0]["matched_primary"]
            assert any("Included" in w and "ember" in w
                       for w in fired["words"]), fired["words"]
            assert any(layer["scope"] == "character"
                       for layer in fired["layers"]), fired["layers"]
            quiet = web.post(f"/webface/chats/{chat_id}/lore-preview",
                             json={"messages": ["a quiet evening"]}).json()
            rows = [r for r in quiet["rows"] if r["entry_id"] == entry_id]
            assert rows and rows[0]["status"] == "not_triggered", quiet
            assert any("Not triggered" in w for w in quiet["words"])
            own = web.post(f"/webface/lorebooks/{book_id}/preview",
                           json={"messages": ["ember at the gate?"]}).json()
            assert own["rows"] and own["rows"][0]["status"] == "included"
            # ---- scope budget/position edit (upsert, still one) ----
            edited = web.put(f"/webface/lorebooks/{book_id}/scope", json={
                "scope_kind": "character", "owner_id": keeper_id,
                "token_budget": 250, "position": 2}).json()
            assert edited["token_budget"] == 250 and edited["position"] == 2
            detail = web.get(f"/webface/lorebooks/{book_id}").json()
            assert len(detail["scopes"]) == 1
            assert detail["scopes"][0]["token_budget"] == 250
            # ---- import / pack / upgrade roads, in words ----
            native = eng.get(f"/api/v1/lorebooks/{book_id}/export").json()
            imported = web.post("/webface/lorebooks/import",
                                json={"document": native}).json()
            assert "Imported" in imported["words"], imported
            imported_id = imported["book"]["id"]
            assert imported_id != book_id
            pack = eng.get(f"/api/v1/lorebooks/{book_id}/pack").json()
            inspected = web.post("/webface/lorebooks/pack/inspect",
                                 json={"document": pack}).json()
            assert "Nothing was imported" in inspected["words"]
            dup = web.post("/webface/lorebooks/import-pack",
                           json={"document": pack}).json()
            assert "exact duplicate" in dup["words"], dup["words"]
            check = web.post("/webface/lorebooks/upgrade/inspect",
                             json={"document": native}).json()
            assert check["words"].startswith("Upgrade check")
            upgraded = web.post("/webface/lorebooks/upgrade",
                                json={"document": native}).json()
            assert upgraded["lorebook"]["format"] == "runmal-lorebook"
            assert upgraded["words"].startswith("Upgraded lorebook file")
            # ---- deletes + user-name clear ----
            gone = web.delete(f"/webface/lorebooks/{imported_id}")
            assert gone.status_code == 200, gone.text
            assert all(b["id"] != imported_id for b in
                       eng.get("/api/v1/lorebooks").json())
            gone = web.delete(f"/webface/lorebooks/{book_id}")
            assert gone.status_code == 200, gone.text
            assert all(b["id"] != book_id for b in
                       eng.get("/api/v1/lorebooks").json())
            cleared_name = web.put("/webface/persona/user-name",
                                   json={"clear": True}).json()
            assert cleared_name["cleared"] is True
            assert eng.get("/api/v1/user-name").json() == {
                "user_name": "User", "is_set": False}
    finally:
        echo.stop()
        eng.close()
