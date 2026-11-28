"""W-04 acceptance: Connections + Generation tabs + first-run.

Unit half: the pure W-04 logic (sampler form model set-equal to
the engine's canonical bag keys, tri-state secrets via a fake
engine, resolve-words renderer, first-run rule). Live half: a
REAL served engine (throwaway data dir) + REAL webface + REAL
Ollama (two models) over HTTP, plus a recording OpenAI-compatible
echo fixture proving a preset value reaches the backend, plus
the first-run circuit on a FRESH engine data dir.
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

from runmal.presets.service import _CANONICAL
from runmal.webface import w04
from runmal.webface.engine import EngineError

REPO = Path(__file__).parent.parent
CANARY = "CANARY-W04-never-echo-7d21"


# ------------------------------------------------------------ unit: w04


def test_sampler_catalogue_matches_engine_canonical():
    assert len(w04.SAMPLER_FIELDS) == 29
    assert {f.key for f in w04.SAMPLER_FIELDS} == set(_CANONICAL)
    model = w04.sampler_form_model()
    assert len(model) == 29 and all(m["label"] and m["group"] for m in model)


def test_split_merge_bag_carries_unknown_keys_verbatim():
    known, extra = w04.split_bag({"temperature": 0.5, "vendor_flag": True})
    assert known == {"temperature": 0.5} and extra == {"vendor_flag": True}
    assert w04.merge_bag(known, extra) == {"temperature": 0.5, "vendor_flag": True}


def test_parse_sampler_form_types_and_refusals():
    bag = w04.parse_sampler_form({"temperature": "0.9", "top_k": "40", "stop": ["END"], "seed": ""})
    assert bag == {"temperature": 0.9, "top_k": 40, "stop": ["END"]}
    with pytest.raises(EngineError):
        w04.parse_sampler_form({"temperature": "hot"})
    with pytest.raises(EngineError):
        w04.parse_sampler_form({"top_p": "2"})


class _FakeEngine:
    """Records roads; speaks the profile shapes (refs only)."""

    def __init__(self):
        self.calls = []
        self.profile = {
            "id": "p1",
            "name": "Fake",
            "chat_backend": "openai",
            "chat_model": "m",
            "embedding_backend": "",
            "embedding_model": "",
            "stt_ref": "",
            "tts_ref": "",
            "chat_secret_ref": "",
            "embedding_secret_ref": "",
            "has_chat_secret": False,
            "has_embedding_secret": False,
            "config": {},
        }

    def request(self, method, path, json_body=None, params=None, **kw):
        self.calls.append((method, path, json_body))
        if path.endswith("-secret") and method == "PUT":
            self.profile = {**self.profile, "has_chat_secret": True, "chat_secret_ref": "secret:x"}
            return dict(self.profile)
        if path.endswith("-secret") and method == "DELETE":
            self.profile = {**self.profile, "has_chat_secret": False, "chat_secret_ref": ""}
            return dict(self.profile)
        if method == "POST" and path == "/api/v1/backend-profiles":
            return {
                **self.profile,
                **(json_body or {}),
                "id": "p1",
                "config": (json_body or {}).get("config") or {},
            }
        if method in ("GET", "PATCH"):
            return dict(self.profile)
        return {}

    def list_characters(self):
        return []


def _save_body(**over):
    body = {
        "name": "Fake",
        "chat_backend": "openai",
        "chat_model": "m",
        "base_url": "http://127.0.0.1:9",
    }
    body.update(over)
    return body


def test_secret_tri_state_leave_set_clear():
    eng = _FakeEngine()
    w04.save_profile(eng, None, _save_body(chat_secret_action="leave", chat_secret=CANARY))
    assert not any(c[1].endswith("-secret") for c in eng.calls), eng.calls
    eng = _FakeEngine()
    out = w04.save_profile(eng, None, _save_body(chat_secret_action="set", chat_secret=CANARY))
    puts = [c for c in eng.calls if c[0] == "PUT" and c[1].endswith("chat-secret")]
    assert len(puts) == 1 and puts[0][2] == {"value": CANARY}
    assert CANARY not in json.dumps(out)  # never rendered back
    assert out["secret_words"]["chat"] == "a key is stored"
    eng = _FakeEngine()
    out = w04.save_profile(eng, "p1", _save_body(chat_secret_action="clear"))
    assert any(c[0] == "DELETE" and c[1].endswith("chat-secret") for c in eng.calls)
    assert out["secret_words"]["chat"] == "no key stored"
    with pytest.raises(EngineError):
        w04.save_profile(_FakeEngine(), None, _save_body(chat_secret_action="set", chat_secret=""))


def test_secret_words_and_demo_label():
    words = w04.secret_words({"has_chat_secret": True, "has_embedding_secret": False})
    assert words == {"chat": "a key is stored", "embedding": "no key stored"}
    pub = w04.public_profile({"chat_backend": "fake", "config": {}})
    assert pub["is_demo"] is True and "not a real model" in pub["backend_label"]


def test_health_words_plain_no_json():
    ok = w04.health_words(
        "Ollama",
        {"ok": True, "latency_ms": 12},
        [{"model_id": "phi3:mini"}, {"model_id": "llama3.2:3b"}],
    )
    assert ok.startswith("Reachable") and "2 model(s)" in ok and "{" not in ok
    bad = w04.health_words("Ollama", {"ok": False, "detail": '{"x": 1}'})
    assert bad.startswith("Not reachable") and "could not read" in bad


def test_first_run_rule():
    class E(_FakeEngine):
        def request(self, method, path, **kw):
            if path == "/api/v1/backend-profiles":
                return []
            return {}

    assert w04.first_run_status(E())["first_run"] is True

    class E2(_FakeEngine):
        def request(self, method, path, **kw):
            if path == "/api/v1/backend-profiles":
                return [{"id": "p"}]
            return {}

    assert w04.first_run_status(E2())["first_run"] is False


def test_set_user_name_empty_never_clears():
    class E(_FakeEngine):
        def request(self, method, path, json_body=None, **kw):
            self.calls.append((method, path, json_body))
            if method == "GET":
                return {"user_name": "Volmarr"}
            return {"user_name": (json_body or {}).get("user_name", "")}

    eng = E()
    out = w04.set_user_name(eng, "  ")
    assert out == {"user_name": "Volmarr", "kept": True}
    assert not any(c[0] == "PUT" for c in eng.calls)
    out = w04.set_user_name(eng, "Yrsa")
    assert out["user_name"] == "Yrsa" and out["kept"] is False


def test_resolve_preview_sources_in_words():
    class E(_FakeEngine):
        def request(self, method, path, json_body=None, params=None, **kw):
            if path.startswith("/api/v1/chats/"):
                return {"id": "c1", "title": "T", "preset_id": "pr1", "backend_profile_id": "p1"}
            if path == "/api/v1/presets/pr1":
                return {"id": "pr1", "name": "Warm", "params": {"temperature": 0.9}}
            if path == "/api/v1/presets/resolve":
                return {
                    "effective": {
                        "bundle_id": "b1",
                        "bundle_name": "Story",
                        "effective": {"sampler": {"temperature": 0.3, "top_k": 40}},
                        "sources": {"sampler": {"temperature": "chat", "top_k": "bundle"}},
                        "applied": [{"scope_kind": "chat", "owner_id": "c1"}],
                        "shadowed": [],
                    }
                }
            return {}

    view = w04.resolve_preview(E(), "c1")
    rows = {r["key"]: r for r in view["rows"]}
    assert rows["temperature"]["value"] == "0.9"
    assert "preset 'Warm'" in rows["temperature"]["source"]
    assert rows["top_k"]["source"] == "the bundle 'Story'"
    assert any("both the preset and the chat override" in n for n in view["notes"])
    assert "engine default" in view["words"]


# ------------------------------------------------------------ live pair


def _ollama_base() -> str | None:
    candidates = []
    if os.environ.get("RUNMAL_TEST_OLLAMA_URL"):
        candidates.append(os.environ["RUNMAL_TEST_OLLAMA_URL"])
    candidates.append("http://127.0.0.1:11434")
    try:
        ip = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
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


def _ollama_models(base: str) -> list[str]:
    resp = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    return [m["name"] for m in resp.json().get("models", []) if "embed" not in m.get("name", "")]


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
    models = _ollama_models(base)
    if len(models) < 2:
        pytest.skip("need two real Ollama chat models for pin switching")
    engine_port, webface_port = _free_port(), _free_port()
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    env["PYTHONPATH"] = str(REPO / "src")
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    engine = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "runmal",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(engine_port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    face = None
    try:
        if not _wait_health(f"http://127.0.0.1:{engine_port}/healthz"):
            raise RuntimeError("engine did not come up")
        face = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runmal.webface",
                "--host",
                "127.0.0.1",
                "--port",
                str(webface_port),
                "--engine-url",
                f"http://127.0.0.1:{engine_port}",
                "--data-dir",
                str(tmp_path / "webface-data"),
                "--engine-data-dir",
                str(tmp_path / "engine-data"),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        yield {
            "engine": f"http://127.0.0.1:{engine_port}",
            "webface": f"http://127.0.0.1:{webface_port}",
            "ollama": base,
            "models": models,
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


def _headers(data_dir: Path) -> dict:
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def _sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        assert resp.status_code == 200, resp.status_code
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events


class _Echo:
    """A real transient OpenAI-compatible HTTP fixture that
    records request bodies (the R-05/R-09 proof pattern)."""

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
                    "data: [DONE]",
                    "",
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


def _register(web, name="w04live"):
    reg = web.post("/register", data={"username": name, "password": "long-enough-1"})
    assert reg.status_code == 303, reg.status_code


def test_live_connections_generation_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    m_a = "phi3:mini" if "phi3:mini" in pair["models"] else pair["models"][0]
    m_b = "llama3.2:3b" if "llama3.2:3b" in pair["models"] else pair["models"][1]
    assert m_a != m_b
    with httpx.Client(base_url=face, trust_env=False, timeout=300, follow_redirects=False) as web:
        # Auth gating on the new roads + pages.
        assert web.get("/webface/profiles").status_code == 401
        assert web.get("/connections").status_code == 303
        _register(web)
        assert web.get("/connections").status_code == 200
        gen_page = web.get("/generation")
        assert gen_page.status_code == 200 and "g-presets" in gen_page.text
        chat_page = web.get("/chat")
        assert "preset-select" in chat_page.text and "firstrun-banner" in chat_page.text
        # Fresh data dir: first-run is offered.
        status = web.get("/webface/firstrun/status").json()
        assert status["first_run"] is True, status
        # Profile create (no secret yet).
        created = web.post(
            "/webface/profiles",
            json={
                "name": "w04-a",
                "chat_backend": "ollama",
                "chat_model": m_a,
                "base_url": pair["ollama"],
            },
        )
        assert created.status_code == 200, created.text
        prof_a = created.json()
        assert prof_a["secret_words"]["chat"] == "no key stored"
        # Secret set: the canary appears in NO webface response.
        secret = web.patch(
            f"/webface/profiles/{prof_a['id']}",
            json={
                "name": "w04-a",
                "chat_backend": "ollama",
                "chat_model": m_a,
                "base_url": pair["ollama"],
                "chat_secret_action": "set",
                "chat_secret": CANARY,
            },
        )
        assert secret.status_code == 200, secret.text
        assert CANARY not in secret.text
        assert secret.json()["secret_words"]["chat"] == "a key is stored"
        listing = web.get("/webface/profiles")
        assert CANARY not in listing.text
        probe = web.get(f"/webface/profiles/{prof_a['id']}/probe")
        assert CANARY not in probe.text
        pj = probe.json()
        assert pj["ok"] is True and pj["words"].startswith("Reachable"), pj
        assert m_a in pj["models"] and "{" not in pj["words"]
        # Secret clear (tri-state third leg).
        cleared = web.patch(
            f"/webface/profiles/{prof_a['id']}",
            json={
                "name": "w04-a",
                "chat_backend": "ollama",
                "chat_model": m_a,
                "base_url": pair["ollama"],
                "chat_secret_action": "clear",
            },
        )
        assert cleared.json()["secret_words"]["chat"] == "no key stored"
        # Second profile on the other real model.
        prof_b = web.post(
            "/webface/profiles",
            json={
                "name": "w04-b",
                "chat_backend": "ollama",
                "chat_model": m_b,
                "base_url": pair["ollama"],
            },
        ).json()
        # Character + chat via the webface roads.
        char = web.post(
            "/webface/characters",
            json={
                "name": "W04 Keeper",
                "description": "Keeps the W-04 gate.",
                "system_prompt": "You are the W04 Keeper. Answer briefly.",
                "first_mes": "W04 Keeper at the gate.",
            },
        )
        assert char.status_code == 200, char.text
        chat = web.post("/webface/chats", json={"character_id": char.json()["id"]})
        chat_id = chat.json()["id"]
        # Pin A -> send -> ollama answers; pin B -> send -> the
        # other backend/model answers (engine-side evidence).
        pin = web.post(
            f"/webface/chats/{chat_id}/backend-profile", json={"profile_id": prof_a["id"]}
        )
        assert pin.json()["backend_profile_id"] == prof_a["id"]
        events = _sse(web, f"/webface/chats/{chat_id}/send", {"content": "Say one short sentence."})
        started = next(e for e in events if e.get("type") == "started")
        assert started["backend_key"] == "ollama", started
        assert "landed" in [e.get("type") for e in events]
        with httpx.Client(trust_env=False, timeout=30) as eng:
            msgs = eng.get(f"{engine}/api/v1/chats/{chat_id}/messages", headers=headers).json()
            prov = [m for m in msgs if m.get("role") == "assistant"]
            assert prov, msgs
            pin_b = web.post(
                f"/webface/chats/{chat_id}/backend-profile", json={"profile_id": prof_b["id"]}
            )
            assert pin_b.json()["backend_profile_id"] == prof_b["id"]
        events = _sse(
            web, f"/webface/chats/{chat_id}/send", {"content": "Say one different short sentence."}
        )
        assert "landed" in [e.get("type") for e in events]
        # Model evidence: the two profiles name different models and
        # the chat's pin (engine re-read) is B after the switch.
        chats = web.get("/webface/chats").json()
        row = next(c for c in chats if c["id"] == chat_id)
        assert row["backend_profile_id"] == prof_b["id"]
        assert prof_a["chat_model"] != prof_b["chat_model"]
        # Preset with a sampler value + an unknown key.
        preset = web.post(
            "/webface/presets",
            json={
                "name": "w04-warm",
                "sampler": {"temperature": "0.9"},
                "extra": {"vendor_flag": True},
                "template_ref": "",
            },
        )
        assert preset.status_code == 200, preset.text
        preset = preset.json()
        assert preset["params"]["temperature"] == 0.9
        assert preset["params"]["vendor_flag"] is True
        # Quick-apply from the Chat tab road.
        applied = web.post(f"/webface/chats/{chat_id}/preset", json={"preset_id": preset["id"]})
        assert applied.json()["preset_id"] == preset["id"]
        # Edit keeps the unknown key verbatim.
        edited = web.patch(
            f"/webface/presets/{preset['id']}",
            json={
                "name": "w04-warm",
                "sampler": {"temperature": "0.8"},
                "extra": preset["extra"],
                "template_ref": "",
            },
        )
        assert edited.json()["params"]["vendor_flag"] is True
        assert edited.json()["params"]["temperature"] == 0.8
        web.patch(
            f"/webface/presets/{preset['id']}",
            json={
                "name": "w04-warm",
                "sampler": {"temperature": "0.9"},
                "extra": preset["extra"],
                "template_ref": "",
            },
        )
        # Bundle + per-chat override delta.
        bundle = web.post(
            "/webface/bundles",
            json={
                "name": "w04-story",
                "sampler": {"temperature": "0.3", "top_k": "40"},
                "extra": {},
                "template_ref": "",
            },
        )
        assert bundle.status_code == 200, bundle.text
        bundle_id = bundle.json()["id"]
        override = web.put(
            f"/webface/overrides/chat/{chat_id}",
            json={"bundle_id": bundle_id, "sampler": {"temperature": "0.7"}, "extra": {}},
        )
        assert override.status_code == 200, override.text
        # Resolve preview: sources in words.
        view = web.get("/webface/resolve", params={"chat_id": chat_id}).json()
        rows = {r["key"]: r for r in view["rows"]}
        assert rows["temperature"]["value"] == "0.9", view
        assert "preset" in rows["temperature"]["source"]
        assert rows["top_k"]["value"] == "40"
        assert "bundle" in rows["top_k"]["source"]
        assert "engine default" in view["words"]
        # The preset value REACHES a backend: echo fixture records it.
        echo = _Echo()
        try:
            echo_prof = web.post(
                "/webface/profiles",
                json={
                    "name": "w04-echo",
                    "chat_backend": "openai",
                    "chat_model": "echo-1",
                    "base_url": echo.url,
                },
            ).json()
            web.post(
                f"/webface/chats/{chat_id}/backend-profile", json={"profile_id": echo_prof["id"]}
            )
            events = _sse(web, f"/webface/chats/{chat_id}/send", {"content": "Echo, please."})
            assert "landed" in [e.get("type") for e in events], events
            assert echo.bodies, "echo fixture recorded no request"
            assert echo.bodies[-1].get("temperature") == 0.9, echo.bodies[-1]
        finally:
            echo.stop()
        # Unpin returns the chat to the engine default.
        unpin = web.post(f"/webface/chats/{chat_id}/backend-profile", json={"profile_id": None})
        assert unpin.json()["backend_profile_id"] is None
        # First-run no longer triggers (profiles + character exist).
        assert web.get("/webface/firstrun/status").json()["first_run"] is False


def test_live_first_run_circuit(pair):
    face = pair["webface"]
    with httpx.Client(base_url=face, trust_env=False, timeout=300, follow_redirects=False) as web:
        _register(web, name="w04firstrun")
        status = web.get("/webface/firstrun/status").json()
        assert status["first_run"] is True, status
        options = web.get("/webface/firstrun/options").json()
        demo = next(o for o in options if o["kind"] == "fake")
        assert "not a real model" in demo["title"]
        # Connect Ollama (the house backend) through the flow.
        profile = web.post(
            "/webface/firstrun/connect",
            json={"kind": "ollama", "base_url": pair["ollama"], "chat_model": pair["models"][0]},
        )
        assert profile.status_code == 200, profile.text
        profile = profile.json()
        assert profile["chat_backend"] == "ollama"
        # Prove it: plain words + models.
        proof = web.post("/webface/firstrun/prove", json={"profile_id": profile["id"]}).json()
        assert proof["ok"] is True and proof["words"].startswith("Reachable")
        assert pair["models"][0] in proof["models"]
        # Switching minds mid-flow deletes the draft (R-05 rule):
        # connect Demo, then connect Ollama again under a new name;
        # the Demo draft must be gone.
        demo_prof = web.post(
            "/webface/firstrun/connect", json={"kind": "fake", "draft_id": ""}
        ).json()
        final = web.post(
            "/webface/firstrun/connect",
            json={
                "kind": "ollama",
                "name": "W04 First Run Ollama",
                "base_url": pair["ollama"],
                "chat_model": pair["models"][0],
                "draft_id": demo_prof["id"],
            },
        )
        assert final.status_code == 200, final.text
        names = [p["name"] for p in web.get("/webface/profiles").json()]
        assert "Demo mode" not in names, names
        profile = final.json()
        # Meet someone: character + greeted chat + pin.
        met = web.post(
            "/webface/firstrun/meet",
            json={
                "mode": "create",
                "name": "W04 First Friend",
                "description": "The first-run friend.",
                "first_mes": "Well met, traveller.",
                "profile_id": profile["id"],
            },
        )
        assert met.status_code == 200, met.text
        met = met.json()
        assert met["greeting"] == "Well met, traveller."
        assert met["pinned"] is True
        chat_id = met["chat"]["id"]
        # Your name (and empty never clears).
        named = web.put("/webface/user-name", json={"user_name": "W04 Tester"})
        assert named.json()["user_name"] == "W04 Tester"
        kept = web.put("/webface/user-name", json={"user_name": ""})
        assert kept.json()["user_name"] == "W04 Tester" and kept.json()["kept"] is True
        # A real reply in the greeted chat.
        events = _sse(
            web, f"/webface/chats/{chat_id}/send", {"content": "Hello, friend. One short sentence."}
        )
        started = next(e for e in events if e.get("type") == "started")
        assert started["backend_key"] == "ollama", started
        assert "landed" in [e.get("type") for e in events]
        # First-run flips to configured.
        assert web.get("/webface/firstrun/status").json()["first_run"] is False
