#!/usr/bin/env python3
"""W-04 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> Connections: create a
phi3:mini profile, probe words, pin it to the Gate Keeper chat,
send (reply evidence names ollama/phi3:mini) -> Generation:
create a preset (temperature 0.9), quick-apply it, resolve
preview with sources in words -> prove the value REACHES a
backend via a local OpenAI-compatible echo fixture that records
the request body -> restore the chat's pin to w01-house-ollama.
Every assertion prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

RESULTS: list[tuple[str, bool, str]] = []
CANARY = "CANARY-W04-PROOF-never-echo-31"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


def sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        if resp.status_code != 200:
            return resp.status_code, events
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return 200, events


class Echo:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="W-04 webface proof")
    parser.add_argument("--webface-url", default=os.environ.get(
        "RUNMAL_WEBFACE_URL", "http://127.0.0.1:8195"))
    parser.add_argument("--engine-url", default=os.environ.get(
        "RUNMAL_ENGINE_URL", "http://127.0.0.1:8098"))
    parser.add_argument("--engine-data-dir", default=os.environ.get(
        "RUNMAL_DATA_DIR", os.path.expanduser("~/.local/share/runmal")))
    parser.add_argument("--username", default=os.environ.get(
        "RUNMAL_PROOF_USER", "w01proof"))
    parser.add_argument("--password", default=os.environ.get(
        "RUNMAL_PROOF_PASSWORD", "w01-proof-pass"))
    parser.add_argument("--ollama-url", default=os.environ.get(
        "RUNMAL_PROOF_OLLAMA_URL", ""))
    args = parser.parse_args()
    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=60,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    ollama = args.ollama_url
    if not ollama:
        profiles = eng.get("/api/v1/backend-profiles").json()
        house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
        ollama = ((house or {}).get("config") or {}).get("base_url", "")
    check("house Ollama address known from w01-house-ollama", bool(ollama), ollama)
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=False)
    login = web.post("/login", data={"username": args.username,
                                      "password": args.password})
    if login.status_code != 303:
        login = web.post("/register", data={"username": args.username,
                                             "password": args.password})
    check("login as proof account", login.status_code == 303,
          f"status {login.status_code}")
    page = web.get("/connections")
    check("Connections tab serves", page.status_code == 200 and "p-list" in page.text)
    page = web.get("/generation")
    check("Generation tab serves", page.status_code == 200 and "g-presets" in page.text)
    page = web.get("/firstrun")
    check("First-Run page serves", page.status_code == 200 and "fr-minds" in page.text)
    page = web.get("/account")
    check("Account page links First-Run Setup", "First-Run Setup" in page.text)
    status = web.get("/webface/firstrun/status").json()
    check("first-run not triggered on the real data", status["first_run"] is False,
          str(status))
    profiles = {p["name"]: p for p in web.get("/webface/profiles").json()}
    house = profiles.get("w01-house-ollama")
    check("w01-house-ollama profile present", bool(house))
    chars = {c["name"]: c["id"] for c in web.get("/webface/characters").json()}
    keeper_id = chars.get("Webface Gate Keeper")
    check("Gate Keeper present", bool(keeper_id))
    chats = web.get("/webface/chats").json()
    keeper_chats = [c for c in chats if c.get("character_id") == keeper_id]
    if keeper_chats:
        chat_id = keeper_chats[0]["id"]
        prior_pin = keeper_chats[0].get("backend_profile_id")
    else:
        chat_id = web.post("/webface/chats",
                           json={"character_id": keeper_id}).json()["id"]
        prior_pin = None
    # --- Connections: phi3 profile, secret canary, probe words ---
    existing = profiles.get("w04-proof-phi3")
    if existing:
        phi = existing
    else:
        created = web.post("/webface/profiles", json={
            "name": "w04-proof-phi3", "chat_backend": "ollama",
            "chat_model": "phi3:mini", "base_url": ollama,
            "chat_secret_action": "set", "chat_secret": CANARY})
        check("phi3 profile created via Connections", created.status_code == 200,
              created.text[:120])
        phi = created.json()
        check("canary secret never echoed", CANARY not in created.text)
    check("secret words say a key is stored",
          phi["secret_words"]["chat"] == "a key is stored", str(phi.get("secret_words")))
    listing = web.get("/webface/profiles")
    check("canary absent from the profile list", CANARY not in listing.text)
    probe = web.get(f"/webface/profiles/{phi['id']}/probe").json()
    check("probe words: reachable, plain, no raw JSON",
          probe["ok"] is True and probe["words"].startswith("Reachable")
          and "{" not in probe["words"], probe["words"][:110])
    check("probe models include phi3:mini", "phi3:mini" in probe["models"],
          str(probe["models"]))
    # --- Pin phi3 to the Gate Keeper chat and send ---
    pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                   json={"profile_id": phi["id"]})
    check("phi3 profile pinned to the Gate Keeper chat",
          pin.json().get("backend_profile_id") == phi["id"])
    status_code, events = sse(web, f"/webface/chats/{chat_id}/send",
                              {"content": "Keeper, one short sentence please."})
    kinds = [e.get("type") for e in events]
    started = next((e for e in events if e.get("type") == "started"), {})
    check("send landed through the webface", status_code == 200 and "landed" in kinds,
          str(kinds))
    check("reply evidence: backend ollama (profile model phi3:mini)",
          started.get("backend_key") == "ollama" and phi["chat_model"] == "phi3:mini",
          f"backend_key={started.get('backend_key')} model={phi['chat_model']}")
    # --- Generation: preset 0.9, quick-apply, resolve preview ---
    presets = {p["name"]: p for p in web.get("/webface/presets").json()}
    preset = presets.get("w04-proof-warm")
    if preset is None:
        made = web.post("/webface/presets", json={
            "name": "w04-proof-warm", "sampler": {"temperature": "0.9"},
            "extra": {}, "template_ref": ""})
        check("preset created (temperature 0.9)", made.status_code == 200, made.text[:120])
        preset = made.json()
    check("preset carries temperature 0.9",
          (preset.get("params") or {}).get("temperature") == 0.9, str(preset.get("params")))
    applied = web.post(f"/webface/chats/{chat_id}/preset",
                       json={"preset_id": preset["id"]})
    check("preset quick-applied to the chat",
          applied.json().get("preset_id") == preset["id"])
    view = web.get("/webface/resolve", params={"chat_id": chat_id}).json()
    rows = {r["key"]: r for r in view["rows"]}
    check("resolve preview: temperature 0.9 from the preset, in words",
          rows.get("temperature", {}).get("value") == "0.9"
          and "preset" in rows.get("temperature", {}).get("source", ""),
          str(rows.get("temperature")))
    check("resolve preview names the engine default",
          "engine default" in view["words"])
    # --- The value reaches a backend: echo fixture ---
    echo = Echo()
    try:
        ep = web.post("/webface/profiles", json={
            "name": "w04-proof-echo", "chat_backend": "openai",
            "chat_model": "echo-1", "base_url": echo.url})
        echo_id = ep.json()["id"]
        web.post(f"/webface/chats/{chat_id}/backend-profile",
                 json={"profile_id": echo_id})
        status_code, events = sse(web, f"/webface/chats/{chat_id}/send",
                                  {"content": "Echo, please."})
        check("echo send landed", "landed" in [e.get("type") for e in events])
        check("recorded backend body carries temperature 0.9",
              bool(echo.bodies) and echo.bodies[-1].get("temperature") == 0.9,
              json.dumps(echo.bodies[-1])[:160] if echo.bodies else "no body recorded")
        web.request("DELETE", f"/webface/profiles/{echo_id}")
    finally:
        echo.stop()
    # --- Restore the prior state ---
    if house:
        back = web.post(f"/webface/chats/{chat_id}/backend-profile",
                        json={"profile_id": house["id"]})
        check("chat re-pinned to w01-house-ollama",
              back.json().get("backend_profile_id") == house["id"])
    elif prior_pin:
        web.post(f"/webface/chats/{chat_id}/backend-profile",
                 json={"profile_id": prior_pin})
    cleared = web.patch(f"/webface/profiles/{phi['id']}", json={
        "name": "w04-proof-phi3", "chat_backend": "ollama",
        "chat_model": "phi3:mini", "base_url": ollama,
        "chat_secret_action": "clear"})
    check("proof canary secret cleared again",
          cleared.json()["secret_words"]["chat"] == "no key stored")
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print(f"W-04 PROOF: {passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
