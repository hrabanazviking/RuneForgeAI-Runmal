#!/usr/bin/env python3
"""W-05 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> Personas: read the current
user name, set a proof name, verify on the engine, restore the
original exactly -> switch the Gate Keeper chat's persona to
W-02 Proof Scratch and back -> Lorebooks: create 'W-05 Proof
Lore' with a keyworded entry (ember) through the webface,
assign a character scope to Webface Gate Keeper, send a chat
message mentioning ember (real Ollama reply), layered preview
shows the entry Included with matched key 'ember', a message
without it shows Not triggered -> restart the WEBFACE ONLY ->
book, entry and scope still served. The proof lorebook remains
as a recorded artifact. Every assertion prints PASS/FAIL; the
exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

RESULTS: list[tuple[str, bool, str]] = []


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
    parser = argparse.ArgumentParser(description="W-05 webface proof")
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
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=120,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=True)
    login = web.post("/login", data={"username": args.username,
                                      "password": args.password})
    check("login as proof account", login.status_code == 200
          and "Log out" in login.text)
    check("Personas tab graduated", web.get("/personas").status_code == 200
          and "arrives in slice" not in web.get("/personas").text)
    check("Lorebooks tab graduated", web.get("/lorebooks").status_code == 200
          and "arrives in slice" not in web.get("/lorebooks").text)
    census = web.get("/webface/lorebooks/schema").json()
    check("census over the wire (6 book / 21 entry fields)",
          len(census["forms"]["book"]) == 6
          and len(census["forms"]["entry"]) == 21)
    characters = eng.get("/api/v1/characters").json()
    keeper = next((c for c in characters
                   if c.get("name") == "Webface Gate Keeper"), None)
    scratch = next((c for c in characters
                    if c.get("name") == "W-02 Proof Scratch"), None)
    check("proof characters exist", bool(keeper) and bool(scratch))
    chats = eng.get("/api/v1/chats").json()
    chat = next((c for c in chats
                 if c.get("character_id") == keeper["id"]), None)
    if chat is None:
        chat = web.post("/webface/chats",
                        json={"character_id": keeper["id"]}).json()
    chat_id = chat["id"]
    check("Gate Keeper chat open", bool(chat_id))
    profiles = eng.get("/api/v1/backend-profiles").json()
    house = next((p for p in profiles
                  if p.get("name") == "w01-house-ollama"), None)
    original_pin = chat.get("backend_profile_id")
    if house and original_pin != house["id"]:
        web.post(f"/webface/chats/{chat_id}/backend-profile",
                 json={"profile_id": house["id"]})
    # ---- lorebook + entry + character scope, all via the webface ----
    book = web.post("/webface/lorebooks", json={"values": {
        "name": "W-05 Proof Lore", "description": "W-05 live proof lore.",
        "scan_depth": "4", "token_budget": "", "scan_mode": "depth",
        "scan_external_context": False}}).json()
    book_id = book.get("id", "")
    check("proof lorebook created via webface", bool(book_id), book.get("name", ""))
    entry = web.post(f"/webface/lorebooks/{book_id}/entries", json={"values": {
        "name": "Ember proof fact",
        "content": "The gate ember remembers every traveller.",
        "keys": ["ember"], "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": "100", "probability": "100", "priority": "100",
        "position": "before_char", "depth": "", "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": "0", "cooldown_prompts": "0",
        "delay_prompts": "0"}}).json()
    entry_id = entry.get("id", "")
    check("keyworded entry created via webface", bool(entry_id)
          and entry.get("keys") == ["ember"])
    scope = web.put(f"/webface/lorebooks/{book_id}/scope", json={
        "scope_kind": "character", "owner_id": keeper["id"],
        "token_budget": 500, "position": 0}).json()
    check("character scope assigned to Webface Gate Keeper",
          scope.get("scope_kind") == "character"
          and "budget 500" in scope.get("words", ""), scope.get("words", ""))
    # ---- real sends + layered preview verdicts ----
    code, events = sse(web, f"/webface/chats/{chat_id}/send",
                       {"content": "Tell me about the ember at the gate."})
    landed = [e for e in events if e.get("type") == "landed"]
    check("real Ollama send landed", code == 200 and bool(landed))
    fired = web.post(f"/webface/chats/{chat_id}/lore-preview", json={
        "messages": ["Tell me about the ember at the gate."]}).json()
    rows = [r for r in fired.get("rows", []) if r.get("entry_id") == entry_id]
    check("layered preview: Included with matched key 'ember'",
          bool(rows) and rows[0].get("status") == "included"
          and "ember" in (rows[0].get("matched_primary") or []),
          rows[0].get("words", "") if rows else "no row")
    code, events = sse(web, f"/webface/chats/{chat_id}/send",
                       {"content": "A quiet evening, nothing more."})
    check("second real send landed", code == 200
          and any(e.get("type") == "landed" for e in events))
    quiet = web.post(f"/webface/chats/{chat_id}/lore-preview", json={
        "messages": ["A quiet evening, nothing more."]}).json()
    rows = [r for r in quiet.get("rows", []) if r.get("entry_id") == entry_id]
    check("layered preview: Not triggered without the keyword",
          bool(rows) and rows[0].get("status") == "not_triggered",
          rows[0].get("words", "") if rows else "no row")
    # ---- user name: set a proof value, restore the original exactly ----
    original_name = eng.get("/api/v1/user-name").json()
    state = web.put("/webface/persona/user-name",
                    json={"user_name": "W05 Proof Name"}).json()
    check("user name set via webface", state.get("user_name") == "W05 Proof Name"
          and eng.get("/api/v1/user-name").json().get("is_set") is True)
    if original_name.get("is_set"):
        web.put("/webface/persona/user-name",
                json={"user_name": original_name["user_name"]})
    else:
        web.put("/webface/persona/user-name", json={"clear": True})
    restored = eng.get("/api/v1/user-name").json()
    check("user name restored exactly as found",
          restored == original_name, json.dumps(restored))
    # ---- persona switch and back ----
    original_persona = eng.get(f"/api/v1/chats/{chat_id}/persona").json().get("persona")
    switched = web.post(f"/webface/chats/{chat_id}/persona",
                        json={"character_id": scratch["id"]}).json()
    check("persona switched to W-02 Proof Scratch",
          (switched.get("persona") or {}).get("character_id") == scratch["id"]
          and (eng.get(f"/api/v1/chats/{chat_id}/persona").json()
               .get("persona") or {}).get("character_id") == scratch["id"])
    back_id = (original_persona or {}).get("character_id")
    web.post(f"/webface/chats/{chat_id}/persona",
             json={"character_id": back_id})
    now_persona = eng.get(f"/api/v1/chats/{chat_id}/persona").json().get("persona")
    check("persona restored as found",
          (now_persona or {}).get("character_id") == back_id)
    if house and original_pin != house["id"]:
        web.post(f"/webface/chats/{chat_id}/backend-profile",
                 json={"profile_id": original_pin})
    # ---- restart the WEBFACE ONLY; book/entry/scope still served ----
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
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = args.engine_data_dir
    proc = subprocess.Popen(
        [sys.executable, "-m", "runmal.webface", "--host", parsed.hostname,
         "--port", str(parsed.port), "--engine-url", args.engine_url,
         "--data-dir", args.webface_data_dir,
         "--engine-data-dir", args.engine_data_dir],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    pidfile.write_text(str(proc.pid))
    check("webface restarted (new pid)", proc.pid != old_pid
          and wait_up(args.webface_url + "/"))
    web2 = httpx.Client(base_url=args.webface_url, trust_env=False,
                        timeout=120, follow_redirects=True)
    web2.post("/login", data={"username": args.username,
                              "password": args.password})
    detail = web2.get(f"/webface/lorebooks/{book_id}").json()
    check("after restart: book + entry + scope still served",
          detail.get("book", {}).get("id") == book_id
          and any(e.get("id") == entry_id and e.get("keys") == ["ember"]
                  for e in detail.get("entries", []))
          and any(s.get("scope_kind") == "character"
                  for s in detail.get("scopes", [])),
          f"entries={len(detail.get('entries', []))} scopes={len(detail.get('scopes', []))}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
