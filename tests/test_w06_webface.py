"""W-06 acceptance: Memory + Scenarios tabs.

Unit half: the pure W-06 logic - memory words (scope in words,
detail with sources/provenance/extractor/embedding), the
scenario compose-over-stored discipline (authored fields
overlay; structured sections replaced only wholesale; unknown
keys survive verbatim), the apply payload shape (fresh chat +
bind {chat_id}), and the honest read-only memory contract.
Live half: a REAL served engine (throwaway data dir) + REAL
webface + REAL Ollama over HTTP. Memories are seeded through
the engine's own memory service (the only write road that
exists - there is no memory HTTP write road) into the served
engine's database, then browsed through the webface and
verified against direct engine reads.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from runmal.webface import w06
from runmal.webface.engine import EngineError

REPO = Path(__file__).parent.parent


# ------------------------------------------------------------ unit: memory


def test_scope_words():
    assert w06.scope_words("chat") == "tied to a chat"
    assert w06.scope_words("character") == "tied to a character"
    assert w06.scope_words("global") == "everywhere (global)"
    assert w06.scope_words("") == "no scope recorded"


def test_memory_line_and_detail_words():
    row = {"content": "The keeper likes ember tea.\nSecond line.",
           "kind": "semantic", "state": "active", "scope": "chat",
           "pinned": True, "chat_id": "c1"}
    line = w06.memory_line(row)
    assert line.startswith("The keeper likes ember tea.")
    assert "semantic" in line and "tied to a chat" in line and "pinned" in line
    detail = dict(row, subject="keeper", salience=0.5, stability=0.25,
                  confidence=1.0, recall_count=3, witnesses=["Maera"],
                  extractor={"kind": "llm", "model": "m1"}, embedding={},
                  sources=[{"source_kind": "message", "source_id": "msg-9",
                            "chat_id": "c1"}],
                  graph={"nodes": [1, 2], "edges": [1]})
    words = w06.detail_words(detail)
    assert "Scope: tied to a chat (chat)" in words
    assert "Salience: 0.50" in words and "Recalled: 3 time(s)" in words
    assert "Witnesses: Maera" in words and "Chat: c1" in words
    assert "Extractor:" in words and "llm" in words
    assert "Embedding: none recorded on this memory" in words
    assert "- message · msg-9 · chat c1" in words
    assert "Provenance graph: 2 node(s), 1 edge(s)." in words
    assert w06.detail_words({}) == "No memory selected."
    assert "no road to create, edit or delete" in w06.MEMORY_READ_ONLY_NOTE


# --------------------------------------------------------- unit: scenarios


def test_compose_definition_lossless():
    stored = {"name": "Old", "description": "d",
              "roles": [{"name": "Narrator"}],
              "bootstrap_messages": [{"kind": "note", "text": "hi"}],
              "initial_flags": {"met": True},
              "vendor_future_field": "keep-me",
              "future_blob": {"x": [1, 2]}}
    out = w06.compose_definition(stored, {"name": "New"})
    assert out["name"] == "New" and out["description"] == "d"
    assert out["vendor_future_field"] == "keep-me"
    assert out["future_blob"] == {"x": [1, 2]}
    assert out["roles"] == [{"name": "Narrator"}]
    out2 = w06.compose_definition(
        stored, {}, {"roles": [{"name": "Other"}]})
    assert out2["roles"] == [{"name": "Other"}]
    assert out2["bootstrap_messages"] == [{"kind": "note", "text": "hi"}]
    assert stored["name"] == "Old"  # stored untouched


def test_parse_section_shapes():
    assert w06.parse_section("roles", "list", '[{"name": "N"}]') == [{"name": "N"}]
    assert w06.parse_section("initial_flags", "object", '{"a": true}') == {"a": True}
    assert w06.parse_section("roles", "list", "  ") is None
    assert w06.parse_section("roles", "list", None) is None
    with pytest.raises(EngineError):
        w06.parse_section("roles", "list", "{not json")
    with pytest.raises(EngineError):
        w06.parse_section("roles", "list", '{"a": 1}')


def test_scenario_line_and_carried_and_binding_words():
    row = {"name": "Harbour", "role_count": 2, "bootstrap_count": 1,
           "is_favourite": True, "tags": ["sea"], "has_unmappable": True}
    line = w06.scenario_line(row)
    assert "2 role(s)" in line and "1 opening line(s)" in line
    assert "★ favourite" in line and "tags: sea" in line
    assert "unmappable" in line
    carried = w06.carried_words({"roles": [1], "initial_flags": {"a": True}})
    assert "roles: 1" in carried and "initial flags: 1" in carried
    assert w06.carried_words({}).startswith("No structured sections")
    words = w06.binding_words({
        "definition_name": "Harbour", "seeded_messages": [{"id": "m"}],
        "seeded_keys": ["trust"], "skipped": []})
    assert "Bound scenario: Harbour" in words
    assert "1 opening line(s) seeded" in words and "seeded: trust" in words
    assert w06.binding_words({}) == "This chat has no scenario bound."
    assert w06.editor_model()["fields"][0]["name"] == "name"
    assert [s["name"] for s in w06.editor_model()["sections"]] == list(w06.SECTION_KEYS)


# ------------------------------------------------------- unit: fake engine


class _FakeEngine:
    def __init__(self):
        self.calls = []
        self.memories = [{"id": "m1", "content": "Ember fact one",
                          "kind": "semantic", "state": "active",
                          "scope": "user", "sources": []}]
        self.definition = {"name": "Harbour", "description": "d",
                           "roles": [{"name": "Narrator"}],
                           "extra_future": "keep"}
        self.record = {"id": "d1", "name": "Harbour",
                       "definition": self.definition, "revision": 1,
                       "source_format": "native", "report": {}}

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        self.calls.append((method, path, json_body, params))
        if path == "/api/v1/memories":
            return {"memories": self.memories}
        if path == "/api/v1/memories/m1":
            return dict(self.memories[0], graph={"nodes": [], "edges": []})
        if path == "/api/v1/scenarios/d1" and method == "PUT":
            self.record = dict(self.record, definition=json_body, revision=2)
            return self.record
        if path == "/api/v1/scenarios/d1":
            return self.record
        if path == "/api/v1/scenarios/d1/organisation":
            return {"tags": ["sea"], "is_favourite": False}
        if path == "/api/v1/scenarios/d1/bindings":
            return {"bindings": []}
        if path == "/api/v1/scenarios" and method == "POST":
            return dict(self.record, id="d2")
        if path == "/api/v1/chats" and method == "POST":
            return {"id": "chat-new", "character_id": json_body["character_id"]}
        if path == "/api/v1/scenarios/d1/bind":
            return {"definition_name": "Harbour",
                    "seeded_messages": [{"id": "x"}], "seeded_keys": [],
                    "skipped": []}
        raise AssertionError(f"unexpected {method} {path}")

    def create_chat(self, *, character_id, title=""):
        raise AssertionError("apply must not use the greeting chat road")


def test_fake_engine_memory_and_scenario_flows():
    eng = _FakeEngine()
    view = w06.list_memories(eng, q="ember")
    assert view["total"] == 1 and "Ember fact one" in view["lines"][0]
    assert eng.calls[0][3] == {"q": "ember"}
    detail = w06.memory_detail(eng, "m1")
    assert detail["memory"]["id"] == "m1"
    full = w06.scenario_detail(eng, "d1")
    assert full["organisation"]["tags"] == ["sea"]
    assert full["sections"][0]["name"] == "roles"
    saved = w06.save_scenario(eng, "d1", {"values": {"name": "Harbour II"}})
    put = [c for c in eng.calls if c[0] == "PUT"][0]
    assert put[2]["name"] == "Harbour II"
    assert put[2]["extra_future"] == "keep"  # unknown key survived
    assert put[2]["roles"] == [{"name": "Narrator"}]  # carried verbatim
    assert saved["record"]["revision"] == 2
    applied = w06.apply_scenario(eng, "d1", "char-1")
    create = [c for c in eng.calls if c[1] == "/api/v1/chats"][0]
    assert create[2] == {"character_id": "char-1", "greeting_mode": "quiet"}
    bind = [c for c in eng.calls if c[1].endswith("/bind")][0]
    assert bind[2] == {"chat_id": "chat-new"}  # engine bind contract
    assert applied["chat_id"] == "chat-new"
    assert "1 opening line(s) seeded" in applied["words"]
    with pytest.raises(EngineError):
        w06.apply_scenario(eng, "d1", "")


# ------------------------------------------------------------- live circuit


def _ollama_base():
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


def _ollama_models(base):
    r = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    return [m["name"] for m in r.json().get("models", [])]


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(url, timeout_s=60.0):
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
               "data_dir": tmp_path / "engine-data", "env": env}
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _headers(data_dir):
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


_SEED = """
import asyncio, os, sys
sys.path.insert(0, os.environ["PYTHONPATH"].split(":")[0] + "/src")
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.owners import get_or_create_owner
from runmal.memory import service

async def main():
    engine = create_db_engine()
    factory = create_session_factory(engine)
    async with factory() as session:
        owner = await get_or_create_owner(session)
        await service.create_memory(
            session, owner.id,
            content="W06 seeded memory: the keeper brews ember tea at dawn",
            kind="semantic", scope="user", subject="keeper",
            extractor={"kind": "w06-test-seed"},
            sources=(("message", "seed-msg-1", None),))
        await service.create_memory(
            session, owner.id,
            content="W06 seeded memory: harbour bells ring at dusk",
            kind="episodic", scope="chat", state="historical")
        await session.commit()
    await engine.dispose()

asyncio.run(main())
"""


def test_live_memory_scenarios_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    model = "llama3.2:3b" if "llama3.2:3b" in pair["models"] else pair["models"][0]
    eng = httpx.Client(base_url=engine, trust_env=False, timeout=300,
                       headers=headers)
    seed = subprocess.run([sys.executable, "-c", _SEED], env=pair["env"],
                          capture_output=True, text=True, timeout=120)
    assert seed.returncode == 0, seed.stderr[-2000:]
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        assert web.get("/webface/memories").status_code == 401
        assert web.get("/webface/scenarios").status_code == 401
        assert web.get("/memory").status_code == 303
        reg = web.post("/register", data={"username": "w06live",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303, reg.status_code
        for slug, marker in (("/memory", "m-list"), ("/scenarios", "s-list")):
            page = web.get(slug)
            assert page.status_code == 200
            assert marker in page.text and "arrives in slice" not in page.text
        # ---- memory: browse / search / filter / detail vs engine ----
        view = web.get("/webface/memories").json()
        assert view["total"] == 2, view
        assert "no road to create, edit or delete" in view["note"]
        found = web.get("/webface/memories", params={"q": "ember"}).json()
        assert found["total"] == 1 and "ember tea" in found["lines"][0]
        by_kind = web.get("/webface/memories",
                          params={"kind": "episodic"}).json()
        assert by_kind["total"] == 1
        by_state = web.get("/webface/memories",
                           params={"state": "historical"}).json()
        assert by_state["total"] == 1
        direct = eng.get("/api/v1/memories").json()["memories"]
        assert {m["id"] for m in direct} == {m["id"] for m in view["memories"]}
        mid = found["memories"][0]["id"]
        detail = web.get(f"/webface/memories/{mid}").json()
        assert "tied to a chat" not in detail["words"]  # user scope
        assert "Scope: about you (user)" in detail["words"]
        assert "- message · seed-msg-1" in detail["words"]
        assert "w06-test-seed" in detail["words"]
        eng_detail = eng.get(f"/api/v1/memories/{mid}").json()
        assert eng_detail["content"] == detail["memory"]["content"]
        # ---- scenarios: create (lossless) -> edit -> org -> apply ----
        keeper = web.post("/webface/characters", json={
            "name": "W06 Keeper", "description": "Keeps the W-06 gate.",
            "system_prompt": "You are the W06 Keeper. Answer briefly.",
            "first_mes": "W06 Keeper at the gate."})
        assert keeper.status_code == 200, keeper.text
        keeper_id = keeper.json()["id"]
        created = web.post("/webface/scenarios", json={
            "values": {"name": "W-06 Test Harbour",
                       "description": "A W-06 circuit scenario.",
                       "scenario_text": "The ferry has just left."},
            "sections": {
                "roles": [{"name": "Narrator", "character_name": "Maera",
                           "enabled_on_start": True, "can_speak": True}],
                "bootstrap_messages": [
                    {"kind": "note", "text": "W06 opening: the tide is going out.",
                     "role": "Narrator"}],
                "initial_flags": {"met_maera": True},
                "initial_variables": {"trust": 2}},
            "document": {"w06_custom_extra": "keep-me"}})
        assert created.status_code == 200, created.text
        sid = created.json()["id"]
        stored = eng.get(f"/api/v1/scenarios/{sid}").json()
        assert stored["definition"]["w06_custom_extra"] == "keep-me"
        assert stored["definition"]["initial_variables"] == {"trust": 2}
        edited = web.put(f"/webface/scenarios/{sid}", json={
            "values": {"description": "Edited by W-06."}})
        assert edited.status_code == 200, edited.text
        stored2 = eng.get(f"/api/v1/scenarios/{sid}").json()
        assert stored2["revision"] == 2
        assert stored2["definition"]["description"] == "Edited by W-06."
        assert stored2["definition"]["w06_custom_extra"] == "keep-me"
        assert stored2["definition"]["bootstrap_messages"][0]["text"].startswith("W06 opening")
        fav = web.put(f"/webface/scenarios/{sid}/favourite",
                      json={"is_favourite": True})
        assert fav.status_code == 200, fav.text
        tags = web.put(f"/webface/scenarios/{sid}/tags",
                       json={"tags": "sea, w06"})
        assert tags.status_code == 200 and tags.json()["tags"] == ["sea", "w06"]
        listing = web.get("/webface/scenarios",
                          params={"favourites_only": "true"}).json()
        assert any(r["id"] == sid for r in listing["scenarios"])
        assert "★ favourite" in listing["lines"][0]
        dup = web.post(f"/webface/scenarios/{sid}/duplicate", json={})
        assert dup.status_code == 200, dup.text
        dup_id = dup.json()["id"]
        assert eng.get(f"/api/v1/scenarios/{dup_id}").json()["name"].endswith("(copy)")
        # ---- apply: fresh chat + bind seeds the opening ----
        applied = web.post(f"/webface/scenarios/{sid}/apply",
                           json={"character_id": keeper_id})
        assert applied.status_code == 200, applied.text
        chat_id = applied.json()["chat_id"]
        assert "1 opening line(s) seeded" in applied.json()["words"]
        msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        texts = [m.get("content", "") for m in msgs]
        assert any("W06 opening: the tide is going out." in t for t in texts), texts
        binding = eng.get(f"/api/v1/scenarios/bindings/{chat_id}").json()
        assert binding["definition_id"] == sid
        assert any("trust" in k for k in binding["seeded_keys"]), binding
        # ---- send in the scenario chat: pin a real mind first ----
        prof = web.post("/webface/profiles", json={
            "name": "w06-ollama", "chat_backend": "ollama",
            "chat_model": model, "base_url": pair["ollama"]})
        assert prof.status_code == 200, prof.text
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": prof.json()["id"]})
        assert pin.status_code == 200, pin.text
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "What is happening at the harbour?"})
        assert any(e.get("type") == "landed" for e in events), events
        after = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        assert len(after) > len(msgs)
        # ---- import check (parse only) + stored export ----
        checked = web.post("/webface/scenarios/import-check", json={
            "document": {"name": "W-06 Checked File",
                         "description": "parse only"}})
        assert checked.status_code == 200, checked.text
        assert "Nothing was stored" in checked.json()["words"]
        names = [r["name"] for r in eng.get("/api/v1/scenarios").json()["scenarios"]]
        assert "W-06 Checked File" not in names
        dl = web.get(f"/webface/scenarios/{sid}/export-file",
                     params={"format": "native"})
        assert dl.status_code == 200
        assert json.loads(dl.content)["name"] == "W-06 Test Harbour"
        # ---- unbind + delete roads on scratch entities ----
        unbound = web.delete(f"/webface/scenarios/bindings/{chat_id}")
        assert unbound.status_code == 200, unbound.text
        assert eng.get(f"/api/v1/scenarios/bindings/{chat_id}").status_code == 404
        msgs_after = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        assert len(msgs_after) == len(after)  # seeded lines stay
        gone = web.delete(f"/webface/scenarios/{dup_id}")
        assert gone.status_code == 200
        assert eng.get(f"/api/v1/scenarios/{dup_id}").status_code == 404
