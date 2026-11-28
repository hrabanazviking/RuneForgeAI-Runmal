"""W-07 acceptance: Inspector + Tools tabs.

Unit half: the pure W-07 logic - the desktop's own words
renderers (ledger / slot lines / lore account / document
words), the preview-section extraction (the preview payload
is where section text lives; the S214 trace carries none),
the macro/variable/compose words, the honest no-tool-road
contract, and the payload shapes the flows send the engine
(the trace call is the desktop client's call verbatim;
seeded macro expansion passes the seed through untouched).
Live half: a REAL served engine (throwaway data dir) + REAL
webface + REAL Ollama over HTTP: a real reply lands in a
proof chat, then the inspector documents, trace, sections
and reply provenance served through the webface are checked
against direct engine reads of the same roads, and the
tools flows (macro list, seeded expansion, variable
resolve, compose preview) are checked byte-for-byte /
value-for-value against direct engine calls.
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

from runmal.webface import w07

REPO = Path(__file__).parent.parent

_TRACE = {
    "ledger": {"context_limit": 4096, "reserved_response": 512,
               "overhead": 7, "input_budget": 3577,
               "total_input_tokens": 120, "remaining_input_tokens": 3457},
    "slots": [
        {"slot_id": "system/main", "kind": "main_system", "status": "included",
         "tokens": 11, "reason": None, "trigger": None, "provenance": ""},
        {"slot_id": "lore/1", "kind": "lore_before", "status": "included",
         "tokens": 9, "trigger": "ember", "provenance": "lorebook:Harbour@chat"},
        {"slot_id": "lore/2", "kind": "lore_after", "status": "discarded",
         "tokens": 5, "reason": "over lore budget"},
    ],
    "lore_account": {"tokens_used": 9, "discarded_tokens": 5,
                     "entries": [{"id": "e1"}],
                     "by_provenance": {"lorebook:Harbour@chat":
                                       {"tokens_used": 9, "entries": 1}}},
}


def test_ledger_and_slot_words_are_the_desktops():
    words = w07.ledger_words(_TRACE)
    assert words == ("Context limit 4096 · reserved for the reply 512 · "
                     "overhead 7 · input budget 3577 · input used 120 · "
                     "remaining 3457")
    assert w07.ledger_words({}) == "No token ledger in this trace."
    lines = w07.slot_lines(_TRACE)
    assert lines[0] == "main_system — Included · 11 tokens"
    assert lines[1] == ('lore_before — Included · 9 tokens · '
                        'triggered by "ember" · from lorebook:Harbour@chat')
    assert lines[2] == "lore_after — Discarded · 5 tokens · over lore budget"
    lore = w07.lore_account_words(_TRACE)
    assert lore[0] == "Lore: 9 tokens used · 5 discarded · 1 entr(ies) in the prompt"
    assert lore[1] == "- lorebook:Harbour@chat: 9 tokens · 1 entr(ies)"
    assert w07.lore_account_words({}) == []


def test_document_words_renderer():
    doc = {"schema": "x-v1", "chat": {"id": "c1", "pinned": True},
           "tags": ["a", "b"], "rows": [{"n": 1}], "none": None}
    lines = w07.document_words(doc)
    assert "schema: x-v1" in lines and "  id: c1" in lines
    assert "  pinned: yes" in lines and "  - a" in lines
    assert "none: —" in lines


def test_preview_sections_come_from_the_preview_not_the_trace():
    preview = {"messages": [
        {"role": "system", "content": "SYS TEXT", "slot_id": "system/main"},
        {"role": "user", "content": "hello", "slot_id": None}],
        "template_name": "plain", "rendered_tokens": 42,
        "note": "backends receive the structured messages"}
    sections = w07.preview_sections(preview)
    assert sections == [
        {"slot_id": "system/main", "role": "system", "content": "SYS TEXT"},
        {"slot_id": "", "role": "user", "content": "hello"}]
    assert "SYS TEXT" not in json.dumps(_TRACE)  # trace carries no content
    words = w07.preview_words(preview)
    assert "plain" in words and "42 tokens" in words
    assert "no prompt text" in w07.TRACE_CONTENT_NOTE
    assert "sends nothing" in w07.INSPECT_NOTE


def test_tools_words_and_honest_scope():
    assert w07.macro_line({"name": "char", "syntax": "{{char}}",
                           "description": "The character"}) == "{{char}} — The character"
    assert w07.macro_line({"name": "date"}) == "{{date}}"
    result = {"text": "Hi Maera", "report": {
        "expansions": [{"raw": "{{char}}", "value": "Maera"}],
        "rolls": [{"raw": "{{roll::1d6}}", "seeded": True, "outcome": "4"}],
        "unknown": ["{{nope}}"], "errors": []}}
    assert w07.expansion_words(result) == "Hi Maera"
    report = w07.expansion_report_words(result)
    assert report[0] == "{{char}} → Maera"
    assert "seeded" in report[1] and "{{nope}}" in report[2]
    assert w07.variable_line({"name": "char", "description": "The name",
                              "example": "Yrsa"}) == "{{char}} — The name (e.g. Yrsa)"
    resolved = w07.resolve_words({"text": "Hi Yrsa", "resolved": ["char"],
                                  "unknown": ["nope"]})
    assert "Hi Yrsa" in resolved and "Unknown, left as written: nope" in resolved
    composed = w07.compose_words({"messages": [{"role": "system", "content": "S"}],
                                  "manifest": {}})
    assert composed == "[system] S"
    assert "no callable-tool registry" in w07.TOOLS_SCOPE_NOTE
    assert "no road records tool calls" in w07.TOOLS_SCOPE_NOTE


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        self.calls.append((method, path, json_body))
        if path == "/api/v1/chats/c1":
            return {"id": "c1", "character_id": "char-1", "title": "T"}
        if path == "/api/v1/debug/prompt-inspect":
            return dict(_TRACE, prompt_preview={
                "messages": [{"role": "system", "content": "SYS",
                              "slot_id": "system/main"}],
                "template_name": "plain", "rendered_tokens": 3, "note": "n"})
        if path == "/api/v1/tools/macros":
            return [{"name": "char", "syntax": "{{char}}", "description": "d"}]
        if path == "/api/v1/tools/macros/expand":
            return {"text": "ok", "report": {"expansions": [], "rolls": [],
                                             "unknown": [], "errors": []}}
        if path == "/api/v1/tools/variables":
            return [{"name": "char", "description": "d", "example": "Y"}]
        if path == "/api/v1/tools/resolve":
            return {"text": "ok", "resolved": [], "unknown": []}
        if path == "/api/v1/tools/compose":
            return {"messages": [], "manifest": {}}
        if path.startswith("/api/v1/inspector/"):
            return {"schema": "s", "chat_id": "c1"}
        if path.endswith("/provenance"):
            return {"message_id": "m1", "origin": "generated"}
        raise AssertionError(f"unexpected {method} {path}")

    def list_messages(self, chat_id):
        return [{"role": "user", "content": "first"},
                {"role": "assistant", "content": "second"}]


def test_fake_engine_payload_shapes():
    eng = _FakeEngine()
    view = w07.inspector_trace(eng, "c1")
    body = [c for c in eng.calls if c[1] == "/api/v1/debug/prompt-inspect"][0][2]
    assert body == {"chat_id": "c1", "character_id": "char-1",
                    "include_activation_inspection": True,
                    "include_preview": True,
                    "messages": ["first", "second"]}
    assert view["sections"][0]["content"] == "SYS"
    assert view["ledger_words"].startswith("Context limit 4096")
    docs = w07.inspector_documents(eng, "c1")
    assert docs["overview"]["schema"] == "s" and "chat_id: c1" in docs["events_words"]
    prov = w07.message_provenance(eng, "c1", "m1")
    assert "origin: generated" in prov["words"]
    macros = w07.list_macros(eng)
    assert macros["total"] == 1 and macros["lines"] == ["{{char}} — d"]
    expanded = w07.expand_macros(eng, {"text": "{{roll::1d6}}", "seed": 7})
    ebody = [c for c in eng.calls if c[1].endswith("/macros/expand")][0][2]
    assert ebody == {"text": "{{roll::1d6}}", "char": "", "user": "User", "seed": 7}
    assert expanded["words"] == "ok"
    w07.expand_macros(eng, {"text": "x"})
    ubody = [c for c in eng.calls if c[1].endswith("/macros/expand")][-1][2]
    assert "seed" not in ubody
    composed = w07.compose_preview(eng, {"system": "S", "history": "a\n\nb"})
    cbody = [c for c in eng.calls if c[1] == "/api/v1/tools/compose"][0][2]
    assert cbody["history"] == ["a", "b"] and cbody["context_limit"] == 4096
    assert composed["words"] == "(no messages — every field was empty)"


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


def test_live_inspector_tools_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    model = "llama3.2:3b" if "llama3.2:3b" in pair["models"] else pair["models"][0]
    eng = httpx.Client(base_url=engine, trust_env=False, timeout=300,
                       headers=headers)
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        assert web.get("/webface/tools/macros").status_code == 401
        assert web.get("/webface/inspector/chats/x").status_code == 401
        assert web.get("/inspector").status_code == 303
        reg = web.post("/register", data={"username": "w07live",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303, reg.status_code
        for slug, marker in (("/inspector", "i-chat"), ("/tools", "t-macros")):
            page = web.get(slug)
            assert page.status_code == 200
            assert marker in page.text and "arrives in slice" not in page.text
        # ---- a real chat with a landed real reply ----
        keeper = web.post("/webface/characters", json={
            "name": "W07 Keeper", "description": "Keeps the W-07 gate.",
            "system_prompt": "You are the W07 Keeper. Answer briefly.",
            "first_mes": "W07 Keeper at the gate."})
        assert keeper.status_code == 200, keeper.text
        keeper_id = keeper.json()["id"]
        chat = eng.post("/api/v1/chats", json={"character_id": keeper_id})
        assert chat.status_code in (200, 201), chat.text
        chat_id = chat.json()["id"]
        prof = web.post("/webface/profiles", json={
            "name": "w07-ollama", "chat_backend": "ollama",
            "chat_model": model, "base_url": pair["ollama"]})
        assert prof.status_code == 200, prof.text
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": prof.json()["id"]})
        assert pin.status_code == 200, pin.text
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "Who keeps this gate?"})
        assert any(e.get("type") == "landed" for e in events), events
        msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        landed = [m for m in msgs if m.get("role") == "assistant"]
        assert landed, msgs
        # ---- inspector documents agree with direct engine reads ----
        docs = web.get(f"/webface/inspector/chats/{chat_id}").json()
        for key, road in (("overview", ""), ("events", "/events"),
                          ("reasoning", "/reasoning")):
            direct = eng.get(f"/api/v1/inspector/chats/{chat_id}{road}").json()
            assert docs[key] == direct, key
        assert docs["overview"]["sections"]["provenance"]["summary"]["total"] >= 2
        assert "sends nothing" in docs["note"]
        # ---- trace + sections agree with a direct engine call ----
        view = web.post(f"/webface/inspector/chats/{chat_id}/trace", json={}).json()
        texts = [str(m.get("content") or "") for m in msgs][-20:]
        direct = eng.post("/api/v1/debug/prompt-inspect", json={
            "chat_id": chat_id, "character_id": keeper_id,
            "include_activation_inspection": True,
            "include_preview": True, "messages": texts}).json()
        assert view["trace"]["ledger"] == direct["ledger"]
        def slim(rows):
            return [(r.get("kind"), r.get("status"), r.get("tokens"))
                    for r in rows]
        assert slim(view["trace"]["slots"]) == slim(direct["slots"])
        assert view["trace"]["lore_account"] == direct.get("lore_account")
        assert view["sections"] == [
            {"slot_id": str(m.get("slot_id") or ""),
             "role": str(m.get("role") or ""),
             "content": str(m.get("content") or "")}
            for m in direct["prompt_preview"]["messages"]]
        assert any("W07 Keeper" in s["content"] for s in view["sections"])
        assert "no prompt text" in view["content_note"]
        # ---- reply provenance agrees with the direct road ----
        mid = landed[-1]["id"]
        prov = web.get(f"/webface/inspector/chats/{chat_id}/messages/{mid}/provenance").json()
        direct_prov = eng.get(
            f"/api/v1/chats/{chat_id}/messages/{mid}/provenance").json()
        assert prov["provenance"] == direct_prov
        # ---- tools: registry, seeded expansion, resolve, compose ----
        macros = web.get("/webface/tools/macros").json()
        direct_macros = eng.get("/api/v1/tools/macros").json()
        assert macros["macros"] == direct_macros and macros["total"] > 10
        assert "no callable-tool registry" in macros["note"]
        payload = {"text": "{{char}} rolls {{roll::2d6}} for {{user}}",
                   "char": "Maera", "user": "Volmarr", "seed": 42}
        expanded = web.post("/webface/tools/macros/expand", json=payload).json()
        direct_exp = eng.post("/api/v1/tools/macros/expand", json=payload).json()
        assert expanded["result"] == direct_exp  # byte-for-byte via JSON equality
        assert expanded["words"] == direct_exp["text"]
        again = web.post("/webface/tools/macros/expand", json=payload).json()
        assert again["result"] == expanded["result"]  # seeded = deterministic
        variables = web.get("/webface/tools/variables").json()
        assert variables["variables"] == eng.get("/api/v1/tools/variables").json()
        resolved = web.post("/webface/tools/resolve", json={
            "text": "{{char}} at {{weekday}}", "char": "Maera"}).json()
        direct_res = eng.post("/api/v1/tools/resolve", json={
            "text": "{{char}} at {{weekday}}", "char": "Maera",
            "user": "User"}).json()
        assert resolved["result"] == direct_res
        compose_body = {"system": "Be brief.", "persona": "Maera the keeper.",
                        "history": ["hello", "hi there"],
                        "authors_note": "Stay in character.", "note_depth": 1}
        composed = web.post("/webface/tools/compose", json=compose_body).json()
        direct_comp = eng.post("/api/v1/tools/compose", json=dict(
            compose_body, context_limit=4096, reserve_response=512)).json()
        assert composed["result"]["messages"] == direct_comp["messages"]
        assert composed["result"]["manifest"] == direct_comp["manifest"]
        assert "Maera the keeper." in composed["words"]
