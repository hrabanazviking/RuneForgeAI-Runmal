"""W-08 acceptance: Voice + Vision tabs.

Unit half: the pure W-08 logic - the desktop's own words
renderers (voice status / devices / roles / backends / audit /
sessions / latency; vision providers / descriptions /
attachments / watch folders / scan reports), the backend-state
honesty (a selected backend is ready only when INSTALLED),
the no-road contracts (no synthesized-audio road, no upload-
transcription road - both refused in plain words, nothing
stored), the secure-context microphone note logic at the
served-JS level, and the payload shapes the flows send the
engine (session start, turn record, attach with its base64
body and describe opt-in, describe with the semantic flag).
Live half: a REAL served engine (throwaway data dir) + REAL
webface + REAL Ollama over HTTP: the voice overview served
through the webface equals direct engine reads; a voice
session starts on a real chat, a turn is recorded and
projected into the chat's messages; live start surfaces the
engine's own refusal (the selected speaking backend is not
installed on a fresh engine); a real PNG attaches through
the webface, its bytes come back identical, the metadata
description agrees with a direct engine call, a semantic
caption request is refused in the engine's own words, and a
send with the picture bound to the sent message lands a real
reply while the providers payload still declares no vision.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import httpx
import pytest

from runmal.webface import w08

REPO = Path(__file__).parent.parent

_STATUS = {"state": "LISTENING", "turns": 0, "waveform": [], "metrics": None}
_DEVICES = [
    {"device_id": "fix-mic", "name": "Fixture Microphone", "direction": "input",
     "host_api": "fixture", "max_channels": 1, "sample_rates": [16000],
     "is_system_default": True},
    {"device_id": "fix-headset", "name": "Fixture Headset", "direction": "output",
     "host_api": "fixture", "max_channels": 1, "sample_rates": [16000],
     "is_system_default": True},
]
_ROLES = {"assignments": {}, "resolution": {
    "user_mic": {"status": "unassigned", "device_id": None, "saved": None},
    "user_playback": {"status": "ok", "device_id": "fix-headset",
                      "saved": None},
    "room_capture": {"status": "remap_required", "device_id": None,
                     "saved": {"device_id": "gone-1"}},
}}
_COSY = {"key": "cosyvoice", "kind": "tts", "default_shipped": True,
         "verified": True, "installed": False, "install_status": "not_started",
         "install_step": "", "install_error": "", "installable": True,
         "notice": "", "unverified_label": "", "audit": None,
         "display_name": "CosyVoice 2 (0.5B)", "selected": True}
_PIPER = {"key": "piper", "kind": "tts", "default_shipped": False,
          "verified": False, "installed": True, "install_status": "done",
          "install_step": "", "install_error": "", "installable": True,
          "notice": "", "unverified_label": "", "audit": None,
          "display_name": "Piper", "selected": False}
_WHISPER = {"key": "faster-whisper", "kind": "stt", "default_shipped": True,
            "verified": True, "installed": False,
            "install_status": "not_started", "install_step": "",
            "install_error": "", "installable": True, "notice": "",
            "unverified_label": "", "audit": None,
            "display_name": "faster-whisper", "selected": True}
_BACKENDS = {"tts": [_COSY, _PIPER], "stt": [_WHISPER],
             "defaults": {"tts_backend": "cosyvoice",
                          "stt_backend": "faster-whisper"}}
_PROVIDERS = {
    "providers": [
        {"provider_id": "runmal.vision.metadata", "model": "sniff-1",
         "road": "metadata", "semantic": False, "available": True,
         "note": "Sniffed truth about the bytes only (format, dimensions, "
                 "size, sha256). Not a semantic caption."},
        {"provider_id": "runmal.vision.deterministic-test",
         "model": "byte-fingerprint-1", "road": "deterministic_test",
         "semantic": False, "available": True,
         "note": "Deterministic test road. Not a semantic caption."}],
    "semantic_caption_available": False,
    "semantic_caption_note": "No semantic caption provider exists in-tree "
    "and no chat backend declares Capabilities.vision; semantic requests "
    "are refused plainly until a real provider lands.",
    "backends": [{"backend_key": "ollama", "model_id": "llama3.1",
                  "vision_declared": False, "source": "declared"}]}


def _png(width=2, height=3):
    def chunk(kind, data):
        raw = kind + data
        return (struct.pack(">I", len(data)) + raw
                + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b""
    for _ in range(height):
        rows += b"\x00" + b"\xff\x00\x00" * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def test_voice_words_are_the_desktops():
    assert w08.status_words(_STATUS) == (
        "State: LISTENING\nTurns this session: 0\n"
        "No metrics collector is attached to this engine.")
    assert w08.device_line(_DEVICES[0]) == (
        "Fixture Microphone · input · fixture · 1 channel(s) · "
        "sample rates: 16000 Hz · system default")
    lines = w08.role_lines(_ROLES, _DEVICES)
    assert lines[0] == "user_mic · not assigned"
    assert lines[1] == "user_playback · ready · Fixture Headset"
    assert lines[2].startswith("room_capture · saved device missing")
    assert "never substitutes the OS default silently" in lines[2]
    assert w08.backend_line(_COSY) == (
        "CosyVoice 2 (0.5B) · shipped by default · installed: no · "
        "selected default")
    assert w08.backend_line(_PIPER) == "Piper · user-installed · installed: yes"
    assert w08.audit_words(_COSY) == "license audit: not installed yet"
    audited = dict(_PIPER, audit={"passed": True, "checked": 12,
                                  "binding": False})
    assert w08.audit_words(audited) == (
        "license audit: PASS (12 distributions checked) "
        "(information only — your choice, your terms)")
    session = {"state": "active", "chat_id": "c1", "turn_count": 2,
               "created_at": "2026-01-01", "stopped_at": "", "settings": {
                   "tts_backend": "cosyvoice", "voice_id": "v-1"},
               "turns": [{"turn_no": 1, "transcript_text": "hello there",
                          "response_text": "hi", "interrupted": False,
                          "error": ""}]}
    assert w08.session_line(session) == "active · chat c1 · 2 turn(s) · started 2026-01-01"
    words = w08.session_detail_words(session)
    assert "- tts_backend: cosyvoice" in words
    assert "Turn 1 · heard: hello there · said: hi" in words
    assert w08.session_detail_words({}) == "No voice session selected."
    assert w08.latency_words({}) == "No latency record."
    assert w08.latency_words({"turn_count": 1, "turns_with_evidence": 0,
                              "aggregate": {}}) == (
        "Turns: 1\nTurns with latency evidence: 0\n"
        "No latency evidence recorded yet.")


def test_backend_state_honesty():
    state = w08.backend_state(_BACKENDS)
    assert state["tts_selected"] == "cosyvoice"
    assert state["tts_installed"] is False
    assert state["synthesis_ready"] is False
    assert state["transcription_ready"] is False
    assert "not installed on this engine" in state["words"][0]
    assert "CosyVoice 2 (0.5B)" in state["words"][0]
    ready = w08.backend_state({"tts": [dict(_PIPER, selected=True)],
                               "stt": [dict(_WHISPER, installed=True)]})
    assert ready["synthesis_ready"] is True
    assert ready["transcription_ready"] is True
    empty = w08.backend_state({"tts": [], "stt": []})
    assert "No text-to-speech backend is selected" in empty["words"][0]


def test_no_road_contracts_are_plain():
    assert "No engine road returns synthesized audio" in w08.SYNTH_ROAD_NOTE
    assert "engine host's playback device" in w08.SYNTH_ROAD_NOTE
    attempt = w08.transcribe_attempt({"filename": "clip.wav"})
    assert attempt["no_road"] is True
    assert "No engine road transcribes an uploaded audio file" in attempt["error"]
    assert "secure context" in w08.MIC_SECURE_NOTE
    assert "plain HTTP" in w08.MIC_SECURE_NOTE
    # Amendment 1 superseded the no-road note: a profile road now exists.
    assert "stored S512 voice profile" in w08.CHARACTER_VOICE_NOTE
    assert "Register a new voice" in w08.CHARACTER_VOICE_NOTE
    assert "does not see an attached picture" in w08.VISION_SEND_NOTE


def test_vision_words_are_the_desktops():
    words = w08.providers_words(_PROVIDERS)
    assert "runmal.vision.metadata · sniff-1 · metadata · available" in words
    assert "No semantic caption provider exists in-tree" in words
    assert "ollama · llama3.1 · vision declared: no" in words
    att = {"filename": "gate.png", "image_format": "png", "image_width": 2,
           "image_height": 3, "image_size": 71, "created_at": "2026-01-01",
           "message_id": "m1"}
    assert w08.attachment_line(att) == (
        "gate.png · png · 2x3 · 71 bytes · 2026-01-01 · on a message")
    desc = {"description": "A PNG image, 2x3.", "provider_id": "p1",
            "provider_model": "sniff-1", "provider_road": "metadata",
            "source_kind": "attachment", "source_ref": "a1", "question": "",
            "image_format": "png", "image_width": 2, "image_height": 3,
            "image_size": 71, "created_at": "2026-01-01"}
    dwords = w08.description_words(desc)
    assert dwords.startswith("A PNG image, 2x3.")
    assert "Provider: p1 · sniff-1 · metadata" in dwords
    assert "Image: png · 2x3 · 71 bytes" in dwords
    assert w08.watch_line({"path": "/pics", "enabled": True,
                           "recursive": False, "chat_id": "c1"}) == (
        "/pics · enabled · flat · chat c1")
    report = w08.scan_report_words({"scanned": 3, "ingested": ["a.png"],
                                    "skipped": [{"path": "b.txt",
                                                 "reason": "not an image"}]})
    assert report == ("Scanned: 3 file(s).\nIngested: 1 new attachment(s).\n"
                      "- a.png\nSkipped:\n- b.txt: not an image")


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        self.calls.append((method, path, json_body, params))
        if path == "/api/v1/voice/status":
            return dict(_STATUS)
        if path == "/api/v1/voice/devices":
            return {"devices": list(_DEVICES), "provider": "fixture"}
        if path == "/api/v1/voice/roles":
            return dict(_ROLES)
        if path == "/api/v1/voice/backends":
            return json.loads(json.dumps(_BACKENDS))
        if path == "/api/v1/voice/settings/defaults":
            return {"tts_backend": "cosyvoice", "stt_backend": "faster-whisper"}
        if path == "/api/v1/voice/sessions":
            return {"session_id": "s1", "state": "active",
                    "chat_id": "c1", "turn_count": 0,
                    "settings": {}, "turns": []}
        if path.endswith("/turns"):
            return {"turn_no": 1}
        if path.endswith("/project"):
            return {"messages_created": 1}
        if path.endswith("/live/start"):
            return {"live": True}
        if path == "/api/v1/vision/providers":
            return json.loads(json.dumps(_PROVIDERS))
        if path == "/api/v1/vision/attachments" and method == "POST":
            return {"id": "a1", "filename": json_body["filename"],
                    "image_format": "png", "image_width": 2,
                    "image_height": 3, "image_size": 71,
                    "chat_id": json_body["chat_id"],
                    "message_id": json_body.get("message_id"),
                    "created_at": "2026-01-01"}
        if path == "/api/v1/vision/attachments":
            return {"chat_id": "c1", "attachments": []}
        if path == "/api/v1/vision/describe":
            return {"description": "facts", "provider_id": "p1"}
        raise AssertionError(f"unexpected {method} {path}")


def test_fake_engine_payload_shapes():
    eng = _FakeEngine()
    view = w08.voice_overview(eng)
    assert view["provider"] == "fixture"
    assert "fixture provider" in view["provider_note"]
    assert view["state"]["synthesis_ready"] is False
    assert view["defaults"]["tts_backend"] == "cosyvoice"
    started = w08.start_session(eng, "c1", auto_project=True)
    body = [c for c in eng.calls if c[1] == "/api/v1/voice/sessions"][0][2]
    assert body == {"chat_id": "c1", "auto_project": True}
    assert started["session"]["session_id"] == "s1"
    w08.record_turn(eng, "s1", {"transcript_text": "hello",
                                "response_text": "hi"})
    tbody = [c for c in eng.calls if c[1].endswith("/turns")][0][2]
    assert tbody == {"transcript_text": "hello", "response_text": "hi"}
    png = _png()
    attached = w08.attach_image(eng, "c1", "gate.png", png,
                                message_id="m1", describe=True,
                                question="what is it?")
    abody = [c for c in eng.calls
             if c[1] == "/api/v1/vision/attachments" and c[0] == "POST"][0][2]
    assert abody["chat_id"] == "c1" and abody["message_id"] == "m1"
    assert base64.b64decode(abody["image_b64"]) == png
    assert abody["describe"] is True
    assert abody["describe_question"] == "what is it?"
    assert attached["attachment"]["id"] == "a1"
    w08.attach_image(eng, "c1", "gate.png", png)
    pbody = [c for c in eng.calls
             if c[1] == "/api/v1/vision/attachments" and c[0] == "POST"][-1][2]
    assert "message_id" not in pbody and "describe" not in pbody
    described = w08.describe(eng, {"chat_id": "c1", "attachment_id": "a1",
                                   "require_semantic": True})
    dbody = [c for c in eng.calls if c[1] == "/api/v1/vision/describe"][0][2]
    assert dbody == {"chat_id": "c1", "question": "",
                     "attachment_id": "a1", "require_semantic": True}
    assert described["words"].startswith("facts")
    prov = w08.providers_view(eng)
    assert prov["semantic_available"] is False
    assert "does not see an attached picture" in prov["send_note"]

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


def test_live_voice_vision_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    model = "llama3.2:3b" if "llama3.2:3b" in pair["models"] else pair["models"][0]
    eng = httpx.Client(base_url=engine, trust_env=False, timeout=300,
                       headers=headers)
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        assert web.get("/webface/voice/overview").status_code == 401
        assert web.get("/webface/vision/providers").status_code == 401
        assert web.get("/voice").status_code == 303
        assert web.get("/vision").status_code == 303
        reg = web.post("/register", data={"username": "w08live",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303, reg.status_code
        for slug, marker in (("/voice", "v-chat"), ("/vision", "s-chat")):
            page = web.get(slug)
            assert page.status_code == 200
            assert marker in page.text and "arrives in slice" not in page.text
        # ---- the mic note logic at served-JS level ----
        voice_js = web.get("/static/voice.js").text
        assert "window.isSecureContext" in voice_js
        assert "navigator.mediaDevices" in voice_js
        assert "will not grant the microphone" in voice_js
        assert "MediaRecorder" in voice_js
        vision_js = web.get("/static/vision.js").text
        assert "uploadWithProgress" in vision_js
        assert "/webface/vision/attachments" in vision_js
        # ---- voice overview equals direct engine reads ----
        view = web.get("/webface/voice/overview").json()
        assert view["status"] == eng.get("/api/v1/voice/status").json()
        direct_devices = eng.get("/api/v1/voice/devices").json()
        assert view["devices"] == direct_devices["devices"]
        assert view["provider"] == direct_devices["provider"]
        assert view["roles"] == eng.get("/api/v1/voice/roles").json()
        direct_backends = eng.get("/api/v1/voice/backends").json()
        assert view["backends"]["tts"] == direct_backends["tts"]
        assert view["backends"]["stt"] == direct_backends["stt"]
        assert view["defaults"] == eng.get(
            "/api/v1/voice/settings/defaults").json()
        selected_tts = next(r for r in direct_backends["tts"]
                            if r["selected"])
        assert view["state"]["synthesis_ready"] is bool(
            selected_tts["installed"])
        assert "No engine road returns synthesized audio" in (
            view["notes"]["synthesis"])
        assert "No engine road transcribes" in view["notes"]["transcription"]
        # ---- the upload-transcribe attempt is refused honestly ----
        attempt = web.post("/webface/voice/transcribe",
                           json={"filename": "clip.wav"})
        assert attempt.status_code == 422
        assert "No engine road transcribes" in attempt.json()["error"]
        # ---- a real chat + profile for the send road ----
        keeper = web.post("/webface/characters", json={
            "name": "W08 Keeper", "description": "Keeps the W-08 gate.",
            "system_prompt": "You are the W08 Keeper. Answer briefly.",
            "first_mes": "W08 Keeper at the gate."})
        assert keeper.status_code == 200, keeper.text
        keeper_id = keeper.json()["id"]
        chat = eng.post("/api/v1/chats", json={"character_id": keeper_id})
        assert chat.status_code in (200, 201), chat.text
        chat_id = chat.json()["id"]
        prof = web.post("/webface/profiles", json={
            "name": "w08-ollama", "chat_backend": "ollama",
            "chat_model": model, "base_url": pair["ollama"]})
        assert prof.status_code == 200, prof.text
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": prof.json()["id"]})
        assert pin.status_code == 200, pin.text
        # ---- voice session: start, record, project, live refusal ----
        started = web.post("/webface/voice/sessions",
                           json={"chat_id": chat_id})
        assert started.status_code == 200, started.text
        session = started.json()["session"]
        sid = session["session_id"]
        direct_session = eng.get(f"/api/v1/voice/sessions/{sid}").json()
        assert session["settings"] == direct_session["settings"]
        turn = web.post(f"/webface/voice/sessions/{sid}/turns", json={
            "transcript_text": "W08 heard this at the gate.",
            "response_text": "W08 keeper answers."})
        assert turn.status_code == 200, turn.text
        detail = web.get(f"/webface/voice/sessions/{sid}").json()
        assert "W08 heard this at the gate." in detail["words"]
        projected = web.post(f"/webface/voice/sessions/{sid}/project",
                             json={})
        assert projected.status_code == 200, projected.text
        assert projected.json()["messages_created"] >= 1
        msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        assert any("W08 heard this at the gate." in str(m.get("content"))
                   for m in msgs), msgs
        live = web.post(f"/webface/voice/sessions/{sid}/live/start", json={})
        assert live.status_code >= 400, live.text
        assert live.json()["error"], live.text  # the engine's own words
        stopped = web.post(f"/webface/voice/sessions/{sid}/stop",
                           json={"note": "w08 live circuit"})
        assert stopped.status_code == 200, stopped.text
        # ---- vision: providers truth equals the direct read ----
        prov = web.get("/webface/vision/providers").json()
        direct_prov = eng.get("/api/v1/vision/providers").json()
        assert prov["providers"] == direct_prov
        assert prov["semantic_available"] is False
        assert direct_prov["semantic_caption_note"] in prov["words"]
        assert all(not b["vision_declared"]
                   for b in direct_prov["backends"])
        # ---- attach a real PNG through the webface ----
        png = _png()
        attached = web.post(
            "/webface/vision/attachments",
            files={"file": ("gate.png", png, "image/png")},
            data={"chat_id": chat_id})
        assert attached.status_code == 200, attached.text
        record = attached.json()["attachment"]
        assert record["image"]["format"] == "png"
        assert (record["image"]["width"], record["image"]["height"]) == (2, 3)
        assert "gate.png · png · 2x3" in attached.json()["line"]
        att_id = record["id"]
        listed = web.get("/webface/vision/attachments",
                         params={"chat_id": chat_id}).json()
        assert [a["id"] for a in listed["attachments"]] == [att_id]
        direct_list = eng.get("/api/v1/vision/attachments",
                              params={"chat_id": chat_id}).json()
        assert listed["attachments"] == direct_list["attachments"]
        content = web.get(f"/webface/vision/attachments/{att_id}/content")
        assert content.status_code == 200 and content.content == png
        # ---- describe: metadata facts agree; semantic refused ----
        described = web.post("/webface/vision/describe", json={
            "chat_id": chat_id, "attachment_id": att_id})
        assert described.status_code == 200, described.text
        direct_desc = eng.post("/api/v1/vision/describe", json={
            "chat_id": chat_id, "attachment_id": att_id})
        assert direct_desc.status_code == 200, direct_desc.text
        mine = described.json()["description"]
        theirs = direct_desc.json()
        for key in ("provider", "image", "description", "source_kind"):
            assert mine[key] == theirs[key], key
        assert "Provider:" in described.json()["words"]
        semantic = web.post("/webface/vision/describe", json={
            "chat_id": chat_id, "attachment_id": att_id,
            "require_semantic": True})
        assert semantic.status_code == 422, semantic.text
        assert semantic.json()["error"], semantic.text
        # ---- send with the picture bound to the sent message ----
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "Who keeps this gate? (W-08 picture send)"})
        assert any(e.get("type") == "landed" for e in events), events
        msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        mine_msg = [m for m in msgs if m.get("role") == "user"][-1]
        bound = web.post(
            "/webface/vision/attachments",
            files={"file": ("gate2.png", png, "image/png")},
            data={"chat_id": chat_id, "message_id": mine_msg["id"]})
        assert bound.status_code == 200, bound.text
        assert bound.json()["attachment"]["message_id"] == mine_msg["id"]
        assert "on a message" in bound.json()["line"]
        landed = [m for m in eng.get(
            f"/api/v1/chats/{chat_id}/messages").json()
            if m.get("role") == "assistant"]
        assert landed  # a real reply landed; the mind saw no picture
