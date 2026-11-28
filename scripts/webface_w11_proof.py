#!/usr/bin/env python3
"""W-11 launch proof: real HTTP against the running pair.

Two phases, because the webface is restarted between them
(the runner restarts ONLY the webface; the engine is never
touched):
  phase1: login as w01proof -> (a) every tab loads 200;
          (d) the served entrybox.js carries the clear-with-
          confirm + clipboard-ladder words and the chat page
          loads the shared control; (b) a composer draft for
          the pinned proof chat is saved through the draft
          road exactly as entrybox.js does. State (chat id,
          draft key, stamp) is written to the state file.
  phase2: fresh login -> the draft is served back for that
          chat and NOT for another; the message sends for real
          (house profile pinned) and the retire call the
          browser makes on a landed send leaves no draft;
          (c) a character-editor draft round trip on a scratch
          character (created, then deleted); no proof drafts
          are left behind. The pair is left RUNNING.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

RESULTS: list = []
TABS = ["chat", "groups", "characters", "library", "personas",
        "lorebooks", "connections", "generation", "memory",
        "scenarios", "inspector", "tools", "voice", "vision",
        "backups", "plugins", "bridge", "appearance", "account",
        "firstrun"]


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


def summary(tag):
    failed = [n for n, ok in RESULTS if not ok]
    print(f"W-11 PROOF {tag}: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


def phase1(web, state_path):
    stamp = str(int(time.time()))[-6:]
    draft_text = f"w11 proof draft {stamp} - typing that must survive"
    login = web.post("/login", data={
        "username": "w01proof", "password": "w01-proof-pass"})
    check("w01proof logs in", login.status_code == 303)
    bad = [slug for slug in TABS if web.get("/" + slug).status_code != 200]
    check("(a) every tab loads 200", not bad,
          ", ".join(bad) or f"{len(TABS)} tabs")
    js = web.get("/static/entrybox.js")
    check("(d) entrybox.js served", js.status_code == 200)
    for needle in ("Are you sure?", "Ctrl+C copies it",
                   "Ctrl+V pastes as usual", "Draft saved",
                   "MutationObserver", "/webface/draft"):
        check(f"(d) entrybox.js carries: {needle}", needle in js.text)
    chat_page = web.get("/chat")
    check("(d) chat page loads the shared control",
          '<script src="/static/entrybox.js"></script>' in chat_page.text
          and 'id="composer"' in chat_page.text)
    chat_js = web.get("/static/chat.js")
    check("(d) chat.js wires per-chat composer drafts + retire-on-send",
          ":composer" in chat_js.text and "retireDraft" in chat_js.text)
    chats = web.get("/webface/chats").json()
    profiles = web.get("/webface/profiles").json()
    house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
    check("house profile present", house is not None)
    pinned = next((c for c in chats
                   if house and c.get("backend_profile_id") == house["id"]), None)
    check("a chat is pinned to the house profile", pinned is not None,
          (pinned or {}).get("id", "")[:8])
    other = next((c for c in chats if pinned and c["id"] != pinned["id"]), None)
    key = f"chat:{pinned['id']}:composer"
    put = web.put("/webface/draft", json={"key": key, "text": draft_text})
    check("(b) composer draft saved via the draft road",
          put.status_code == 200 and put.json().get("saved") is True)
    Path(state_path).write_text(json.dumps({
        "stamp": stamp, "draft_text": draft_text, "key": key,
        "chat_id": pinned["id"], "other_chat_id": other["id"] if other else None}))
    return summary("phase1")


def phase2(web, state_path):
    state = json.loads(Path(state_path).read_text())
    stamp, draft_text, key = state["stamp"], state["draft_text"], state["key"]
    login = web.post("/login", data={
        "username": "w01proof", "password": "w01-proof-pass"})
    check("fresh login after the webface restart", login.status_code == 303)
    got = web.get("/webface/draft", params={"key": key})
    check("(b) the draft is served back for that chat",
          got.json().get("text") == draft_text)
    if state.get("other_chat_id"):
        got2 = web.get("/webface/draft", params={
            "key": f"chat:{state['other_chat_id']}:composer"})
        check("(b) no draft leaks to another chat", got2.json().get("text") is None)
    resp = web.post(f"/webface/chats/{state['chat_id']}/send", json={
        "content": draft_text, "request_id": f"w11proof{stamp}"})
    check("(b) the drafted message sends for real (landed)",
          resp.status_code == 200 and '"type": "landed"' in resp.text)
    retired = web.request("DELETE", "/webface/draft", json={"key": key})
    check("(b) the retire-on-send call lands", retired.status_code == 200
          and retired.json().get("retired") is True)
    after = web.get("/webface/draft", params={"key": key})
    check("(b) draft is retired after the send", after.json().get("text") is None)
    created = web.post("/webface/characters", json={
        "name": f"W11 Proof Scratch {stamp}",
        "description": "scratch character for the W-11 proof"})
    check("(c) scratch character created", created.status_code == 200)
    cid = (created.json() or {}).get("id")
    ckey = f"character:{cid}:description"
    ctext = f"w11 editor draft {stamp}"
    web.put("/webface/draft", json={"key": ckey, "text": ctext})
    got3 = web.get("/webface/draft", params={"key": ckey})
    check("(c) character-editor draft round trip", got3.json().get("text") == ctext)
    web.request("DELETE", "/webface/draft", json={"key": ckey})
    check("(c) character-editor draft retired by the proof",
          web.get("/webface/draft", params={"key": ckey}).json().get("text") is None)
    if cid:
        web.request("DELETE", f"/webface/characters/{cid}")
    listing = web.get("/webface/drafts")
    keys = [d["draft_key"] for d in listing.json().get("drafts", [])]
    check("(e) no proof drafts left behind",
          listing.status_code == 200 and key not in keys and ckey not in keys)
    return summary("phase2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", default="http://100.67.240.22:8195")
    ap.add_argument("--phase", choices=("phase1", "phase2"), required=True)
    ap.add_argument("--state", default="/tmp/w11_proof_state.json")
    args = ap.parse_args()
    with httpx.Client(base_url=args.face, trust_env=False, timeout=180,
                      follow_redirects=False) as web:
        return phase1(web, args.state) if args.phase == "phase1" \
            else phase2(web, args.state)


if __name__ == "__main__":
    sys.exit(main())
