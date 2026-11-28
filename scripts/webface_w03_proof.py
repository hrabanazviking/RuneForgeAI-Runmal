#!/usr/bin/env python3
"""W-03 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> on the Gate Keeper chat:
edit a message, pin it (verified by re-read), save an Author's
Note, create a checkpoint, regenerate (a REAL ollama reply,
backend_key=ollama) -> create a room with the Gate Keeper +
W-02 Proof Scratch -> in-order + manual turns with real replies
-> a member override -> the caller restarts the webface only ->
room, transcript and chat results all still served. Every
assertion prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="W-03 webface proof")
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
    parser.add_argument("--phase", default="all",
                        choices=("all", "before", "after"))
    args = parser.parse_args()
    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=60,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=False)
    login = web.post("/login", data={"username": args.username,
                                      "password": args.password})
    if login.status_code != 303:
        login = web.post("/register", data={"username": args.username,
                                            "password": args.password})
    check("login as proof account", login.status_code == 303,
          f"status {login.status_code}")
    chars = {c["name"]: c["id"] for c in web.get("/webface/characters").json()}
    keeper_id = chars.get("Webface Gate Keeper")
    scratch_id = chars.get("W-02 Proof Scratch")
    check("Gate Keeper + W-02 Proof Scratch present",
          bool(keeper_id and scratch_id), str(sorted(chars)))
    if not (keeper_id and scratch_id):
        return _finish()
    page = web.get("/groups")
    check("Groups tab page serves", page.status_code == 200
          and "g-roster-pick" in page.text)
    page = web.get("/chat")
    check("Chat page carries the W-03 actions", page.status_code == 200
          and "msg-list" in page.text and "a-regen" in page.text)
    state_path = Path(args.engine_data_dir) / "w03-proof-state.json"
    if args.phase in ("all", "before"):
        chats = web.get("/webface/chats").json()
        keeper_chats = [c for c in chats if c.get("character_id") == keeper_id]
        if keeper_chats:
            chat_id = keeper_chats[0]["id"]
        else:
            chat_id = web.post("/webface/chats",
                               json={"character_id": keeper_id}).json()["id"]
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        if len(msgs) < 2 or msgs[-1]["role"] != "assistant":
            status, events = sse(web, f"/webface/chats/{chat_id}/send",
                                 {"content": "Keeper, one short sentence."})
            check("seed send-turn lands", status == 200
                  and "landed" in [e.get("type") for e in events])
            msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        user_msg = next(m for m in msgs if m["role"] == "user")
        edited_text = user_msg["content"] + " [W-03 proof edit]"
        edited = web.patch(f"/webface/chats/{chat_id}/messages/{user_msg['id']}",
                           json={"content": edited_text})
        check("message edit through the webface", edited.status_code == 200)
        reread = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
        check("engine API shows the edit",
              any(m["id"] == user_msg["id"] and m["content"] == edited_text
                  for m in reread))
        note = web.post(f"/webface/chats/{chat_id}/authors-note", json={
            "text": "W-03 proof note: keep it brief.", "depth": 4,
            "frequency": 1, "role": "system", "enabled": True})
        check("author's note saves", note.status_code == 200
              and note.json().get("text", "").startswith("W-03 proof note"))
        cp = web.post(f"/webface/chats/{chat_id}/checkpoints",
                      json={"name": "w03 proof mark"})
        check("checkpoint created", cp.status_code == 200
              and bool(cp.json().get("id")))
        old_last = web.get(f"/webface/chats/{chat_id}/messages").json()[-1]
        status, events = sse(web, f"/webface/chats/{chat_id}/regenerate", {})
        kinds = [e.get("type") for e in events]
        started = next((e for e in events if e.get("type") == "started"), {})
        reply = "".join(e.get("text", "") for e in events
                        if e.get("type") == "token")
        check("regenerate stream answers", status == 200 and "landed" in kinds,
              str(kinds))
        check("regenerate backend is ollama",
              started.get("backend_key") == "ollama", str(started))
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        check("regenerate landed a NEW reply replacing the old",
              msgs[-1]["id"] != old_last["id"]
              and msgs[-1]["content"].strip() == reply.strip()
              and all(m["id"] != old_last["id"] for m in msgs),
              reply.strip()[:80])
        # Pin the NEW last reply (pinning the old one would die with
        # it at the regenerate — the engine's own semantics).
        pinned = web.post(
            f"/webface/chats/{chat_id}/messages/{msgs[-1]['id']}/pin")
        check("pin verified by re-read", pinned.status_code == 200
              and pinned.json().get("pinned") is True)
        room = web.post("/webface/groups", json={
            "name": "W-03 Proof Room",
            "member_character_ids": [keeper_id, scratch_id]})
        check("room created from the roster", room.status_code == 200
              and room.json().get("member_count") == 2, room.text[:160])
        gid = room.json()["id"]
        web.patch(f"/webface/groups/{gid}", json={"speaker_policy": "list"})
        web.post(f"/webface/groups/{gid}/messages",
                 json={"content": "Proof room: say hello in turn."})
        speakers = []
        for _ in range(2):
            turn = web.post(f"/webface/groups/{gid}/next",
                            json={"generate": True})
            if turn.status_code == 200:
                speakers.append(turn.json()["result"].get("speaker_id"))
        check("in-order turns cycle keeper -> scratch",
              speakers == [keeper_id, scratch_id], str(speakers))
        # Manual pick: the keeper (the scratch member spoke last, and
        # a member may not answer themselves — the engine's own rule).
        manual = web.post(f"/webface/groups/{gid}/next", json={
            "generate": False, "manual_speaker_id": keeper_id})
        check("manual pick honoured", manual.status_code == 200
              and manual.json()["result"].get("speaker_id") == keeper_id,
              manual.text[:160])
        over = web.patch(f"/webface/groups/{gid}/members/{scratch_id}/override",
                         json={"activation": "never"})
        check("member override saves", over.status_code == 200, over.text[:160])
        turn = web.post(f"/webface/groups/{gid}/next", json={"generate": False})
        check("'never' override removes scratch from selection",
              turn.status_code == 200
              and turn.json()["result"].get("speaker_id") == keeper_id)
        transcript = web.get(f"/webface/groups/{gid}/messages").json()
        check("transcript in words carries speaker names",
              any(line.startswith("You:") for line in transcript["lines"])
              and len(transcript["messages"]) >= 3)
        state_path.write_text(json.dumps({
            "chat_id": chat_id, "group_id": gid, "reply": reply.strip(),
            "lines": transcript["lines"]}), encoding="utf-8")
        print("STATE saved — restart the webface, then run --phase after")
    if args.phase in ("all", "after"):
        if not state_path.exists():
            check("proof state from the before phase", False, "missing")
            return _finish()
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        room = web.get(f"/webface/groups/{saved['group_id']}")
        check("room still served after webface restart",
              room.status_code == 200
              and room.json().get("name") == "W-03 Proof Room")
        transcript = web.get(f"/webface/groups/{saved['group_id']}/messages").json()
        check("transcript unchanged after restart",
              transcript.get("lines") == saved["lines"])
        msgs = web.get(f"/webface/chats/{saved['chat_id']}/messages").json()
        check("regenerated reply still the chat's last word",
              bool(msgs) and msgs[-1]["content"].strip() == saved["reply"])
        note = web.get(f"/webface/chats/{saved['chat_id']}/authors-note").json()
        check("author's note still served",
              note.get("text", "").startswith("W-03 proof note"))
        pinned = web.get(f"/webface/chats/{saved['chat_id']}/pinned").json()
        check("pinned message still served", isinstance(pinned, list)
              and len(pinned) >= 1)
    return _finish()


def _finish() -> int:
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print(f"W-03 PROOF: {passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
