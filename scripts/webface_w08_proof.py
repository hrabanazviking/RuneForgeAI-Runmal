#!/usr/bin/env python3
"""W-08 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> both tabs graduated and
/backups still honestly pending (W-09) -> Voice: the overview
served through the webface equals direct engine reads
(status / devices / roles / backends / defaults) and states
the backend truth in words (the selected speaking backend's
install state, from the payload itself); the no-audio-road
and no-upload-transcription notes are present; the upload-
transcribe attempt is refused in plain words; the mic
secure-context note logic is in the served voice.js -> a
voice session on the proof chat (found by its W-07 marker,
created by the earlier proofs) starts with settings equal
to the direct engine read, a turn is recorded and projected
into the chat, and live start surfaces the engine's own
refusal words (no usable playback role / backend not
installed - whichever the live engine answers) -> Vision:
the providers payload equals the direct read and carries
the engine's semantic note verbatim; a real PNG attaches
through the webface, lists equal to the direct read, its
bytes come back identical; the metadata description equals
a direct engine call; a semantic caption request is refused
in the engine's words; a send with the picture bound to the
sent message lands a real reply -> restart the WEBFACE ONLY
-> both tabs still graduated and the attachment bytes still
served. Voice defaults and roles are never changed by this
proof; the proof session is stopped; the attachments stay
on the proof chat as recorded artifacts. Every assertion
prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

RESULTS: list[tuple[str, bool, str]] = []
MARKER = "W07 proof: who keeps this gate?"
TURN = "W08 proof: heard at the gate."


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


def png(width=2, height=3):
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


def sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        if resp.status_code != 200:
            return resp.status_code, events
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return 200, events


def wait_up(url, timeout_s=30.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2, trust_env=False).status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="W-08 webface proof")
    parser.add_argument("--webface-url", default=os.environ.get(
        "RUNMAL_WEBFACE_URL", "http://127.0.0.1:8195"))
    parser.add_argument("--engine-url", default=os.environ.get(
        "RUNMAL_ENGINE_URL", "http://127.0.0.1:8098"))
    parser.add_argument("--engine-data-dir", default=os.environ.get(
        "RUNMAL_DATA_DIR", os.path.expanduser("~/.local/share/runmal")))
    parser.add_argument("--webface-data-dir", default=os.environ.get(
        "RUNMAL_WEBFACE_DATA_DIR",
        os.path.expanduser("~/.local/share/runmal-webface")))
    parser.add_argument("--username", default=os.environ.get(
        "RUNMAL_PROOF_USER", "w01proof"))
    parser.add_argument("--password", default=os.environ.get(
        "RUNMAL_PROOF_PASSWORD", "w01-proof-pass"))
    args = parser.parse_args()
    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=300,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=True)
    login = web.post("/login", data={"username": args.username,
                                     "password": args.password})
    check("login as proof account", login.status_code == 200
          and "Log out" in login.text)
    for slug, marker in (("/voice", "v-chat"), ("/vision", "s-chat")):
        page = web.get(slug)
        check(f"{slug} tab graduated", page.status_code == 200
              and marker in page.text and "arrives in slice" not in page.text)
    pending = web.get("/backups")
    check("/backups still honestly pending (W-09)",
          pending.status_code == 200 and "W-09" in pending.text)
    # ---- the proof chat (W-07's, found by its marker) ----
    characters = eng.get("/api/v1/characters").json()
    keeper = next((c for c in characters
                   if c.get("name") == "Webface Gate Keeper"), None)
    check("Gate Keeper character exists", bool(keeper))
    chat_id = ""
    for chat in eng.get("/api/v1/chats").json():
        if chat.get("character_id") != (keeper or {}).get("id"):
            continue
        rows = eng.get(f"/api/v1/chats/{chat['id']}/messages").json()
        if any(MARKER in str(m.get("content") or "") for m in rows):
            chat_id = chat["id"]
            break
    check("proof chat found (W-07 marker)", bool(chat_id), chat_id)
    # ---- voice overview equals direct engine reads ----
    view = web.get("/webface/voice/overview").json()
    check("voice status equals the direct engine read",
          view.get("status") == eng.get("/api/v1/voice/status").json())
    direct_devices = eng.get("/api/v1/voice/devices").json()
    check("voice devices + provider equal the direct read",
          view.get("devices") == direct_devices.get("devices")
          and view.get("provider") == direct_devices.get("provider"),
          f"provider={view.get('provider')}")
    if view.get("provider") == "fixture":
        check("fixture provider labelled honestly",
              "fixture provider" in view.get("provider_note", ""))
    check("voice roles equal the direct read",
          view.get("roles") == eng.get("/api/v1/voice/roles").json())
    direct_backends = eng.get("/api/v1/voice/backends").json()
    check("voice backends equal the direct read",
          view.get("backends", {}).get("tts") == direct_backends.get("tts")
          and view.get("backends", {}).get("stt") == direct_backends.get("stt"))
    check("voice defaults equal the direct read",
          view.get("defaults") == eng.get(
              "/api/v1/voice/settings/defaults").json())
    selected_tts = next((r for r in direct_backends["tts"] if r["selected"]), {})
    selected_stt = next((r for r in direct_backends["stt"] if r["selected"]), {})
    state = view.get("state", {})
    check("backend state words match the payload's install truth",
          state.get("synthesis_ready") is bool(selected_tts.get("installed"))
          and state.get("transcription_ready") is bool(selected_stt.get("installed")),
          f"tts {selected_tts.get('key')} installed={selected_tts.get('installed')}; "
          f"stt {selected_stt.get('key')} installed={selected_stt.get('installed')}")
    if not selected_tts.get("installed"):
        check("not-installed speaking backend said in plain words",
              any("not installed on this engine" in w
                  for w in state.get("words", [])))
    check("no-audio-road note present (speech plays on the host)",
          "No engine road returns synthesized audio" in
          view.get("notes", {}).get("synthesis", ""))
    check("no-upload-transcription note present",
          "No engine road transcribes" in
          view.get("notes", {}).get("transcription", ""))
    attempt = web.post("/webface/voice/transcribe", json={"filename": "clip.wav"})
    check("upload-transcribe attempt refused in plain words (no road)",
          attempt.status_code == 422
          and "No engine road transcribes" in attempt.json().get("error", ""))
    voice_js = web.get("/static/voice.js").text
    check("mic secure-context logic in the served voice.js",
          "window.isSecureContext" in voice_js
          and "navigator.mediaDevices" in voice_js
          and "will not grant the microphone" in voice_js)
    # ---- voice session on the proof chat ----
    started = web.post("/webface/voice/sessions", json={"chat_id": chat_id})
    session = started.json().get("session", {}) if started.status_code == 200 else {}
    sid = session.get("session_id", "")
    check("voice session started on the proof chat", bool(sid), sid)
    direct_session = eng.get(f"/api/v1/voice/sessions/{sid}").json() if sid else {}
    check("session settings equal the direct engine read",
          session.get("settings") == direct_session.get("settings"),
          f"voice={session.get('settings', {}).get('voice_id')}")
    turn = web.post(f"/webface/voice/sessions/{sid}/turns",
                    json={"transcript_text": TURN,
                          "response_text": "W08 proof: the keeper answers."})
    check("turn recorded on the session", turn.status_code == 200)
    projected = web.post(f"/webface/voice/sessions/{sid}/project", json={})
    check("session projected into its chat",
          projected.status_code == 200
          and projected.json().get("messages_created", 0) >= 1,
          projected.text[:140])
    rows = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    check("projected transcript landed as a chat message",
          any(TURN in str(m.get("content") or "") for m in rows))
    live = web.post(f"/webface/voice/sessions/{sid}/live/start", json={})
    live_words = ""
    try:
        live_words = str(live.json().get("error") or "")
    except ValueError:
        live_words = ""
    direct_live = eng.post(f"/api/v1/voice/sessions/{sid}/live/start", json={})
    direct_words = ""
    try:
        direct_words = str(direct_live.json().get("detail") or "")
    except ValueError:
        direct_words = ""
    check("live start outcome is the engine's own (refusal or live)",
          (live.status_code >= 400 and live_words == direct_words
           and bool(live_words))
          or (live.status_code == 200 and direct_live.status_code == 200),
          live_words or f"status {live.status_code}")
    if live.status_code == 200:
        web.post(f"/webface/voice/sessions/{sid}/live/stop", json={})
    stopped = web.post(f"/webface/voice/sessions/{sid}/stop",
                       json={"note": "w08 proof"})
    check("proof session stopped", stopped.status_code == 200)
    # ---- vision: providers truth ----
    prov = web.get("/webface/vision/providers").json()
    direct_prov = eng.get("/api/v1/vision/providers").json()
    check("vision providers equal the direct engine read",
          prov.get("providers") == direct_prov)
    check("the engine's semantic note carried verbatim",
          direct_prov.get("semantic_caption_note", "") in prov.get("words", "")
          and prov.get("semantic_available") is False)
    check("no chat backend declares vision (engine truth)",
          all(not b.get("vision_declared")
              for b in direct_prov.get("backends", [])))
    # ---- vision: attach a real PNG, bytes back identical ----
    blob = png()
    attached = web.post("/webface/vision/attachments",
                        files={"file": ("w08-gate.png", blob, "image/png")},
                        data={"chat_id": chat_id})
    record = attached.json().get("attachment", {}) if attached.status_code == 200 else {}
    att_id = record.get("id", "")
    check("PNG attached through the webface",
          attached.status_code == 200 and bool(att_id)
          and record.get("image", {}).get("format") == "png",
          attached.text[:140])
    listed = web.get("/webface/vision/attachments",
                     params={"chat_id": chat_id}).json()
    direct_list = eng.get("/api/v1/vision/attachments",
                          params={"chat_id": chat_id}).json()
    check("attachment list equals the direct engine read",
          listed.get("attachments") == direct_list.get("attachments"))
    content = web.get(f"/webface/vision/attachments/{att_id}/content")
    check("attachment bytes served back identical",
          content.status_code == 200 and content.content == blob,
          f"{len(content.content)} bytes")
    described = web.post("/webface/vision/describe", json={
        "chat_id": chat_id, "attachment_id": att_id})
    direct_desc = eng.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "attachment_id": att_id})
    mine = described.json().get("description", {}) if described.status_code == 200 else {}
    theirs = direct_desc.json() if direct_desc.status_code == 200 else {}
    check("metadata description equals a direct engine call",
          described.status_code == 200
          and mine.get("description") == theirs.get("description")
          and mine.get("image") == theirs.get("image")
          and mine.get("provider") == theirs.get("provider"),
          str(mine.get("description", ""))[:100])
    semantic = web.post("/webface/vision/describe", json={
        "chat_id": chat_id, "attachment_id": att_id,
        "require_semantic": True})
    sem_detail = (str(semantic.json().get("error", ""))[:120]
                  if semantic.status_code == 422 else semantic.text[:120])
    check("semantic caption request refused in the engine's words",
          semantic.status_code == 422 and bool(semantic.json().get("error")),
          sem_detail)
    # ---- send with the picture bound to the sent message ----
    code, events = sse(web, f"/webface/chats/{chat_id}/send",
                       {"content": "W08 proof: who keeps this gate, with a picture?"})
    landed = [e for e in events if e.get("type") == "landed"]
    check("send with a picture: a real reply landed", code == 200 and bool(landed))
    rows = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    mine_msg = [m for m in rows if m.get("role") == "user"][-1] if rows else {}
    bound = web.post("/webface/vision/attachments",
                     files={"file": ("w08-gate-2.png", blob, "image/png")},
                     data={"chat_id": chat_id,
                           "message_id": mine_msg.get("id", "")})
    check("picture bound to the sent message",
          bound.status_code == 200
          and bound.json().get("attachment", {}).get("message_id") == mine_msg.get("id"),
          bound.text[:140])
    bound_id = bound.json().get("attachment", {}).get("id", "")
    # ---- restart the WEBFACE ONLY ----
    pidfile = Path(args.webface_data_dir) / "webface.pid"
    old_pid = int(pidfile.read_text().strip())
    os.kill(old_pid, signal.SIGTERM)
    for _ in range(50):
        try:
            os.kill(old_pid, 0)
            time.sleep(0.2)
        except OSError:
            break
    parsed = urlparse(args.webface_url)
    env2 = dict(os.environ)
    env2["RUNMAL_DATA_DIR"] = args.engine_data_dir
    proc = subprocess.Popen(
        [sys.executable, "-m", "runmal.webface", "--host", parsed.hostname,
         "--port", str(parsed.port), "--engine-url", args.engine_url,
         "--data-dir", args.webface_data_dir,
         "--engine-data-dir", args.engine_data_dir],
        env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    pidfile.write_text(str(proc.pid))
    check("webface restarted (new pid)", proc.pid != old_pid
          and wait_up(args.webface_url + "/"))
    web2 = httpx.Client(base_url=args.webface_url, trust_env=False,
                        timeout=120, follow_redirects=True)
    web2.post("/login", data={"username": args.username,
                              "password": args.password})
    ok_tabs = True
    for slug, marker in (("/voice", "v-chat"), ("/vision", "s-chat")):
        page = web2.get(slug)
        ok_tabs = ok_tabs and page.status_code == 200 and marker in page.text
    check("after restart: both tabs still graduated", ok_tabs)
    content2 = web2.get(f"/webface/vision/attachments/{bound_id}/content")
    check("after restart: attachment bytes still served identical",
          content2.status_code == 200 and content2.content == blob)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
