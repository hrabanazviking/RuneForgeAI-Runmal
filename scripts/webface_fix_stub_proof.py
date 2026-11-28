#!/usr/bin/env python3
"""FIX-STUB live proof: real HTTP against the running engine+webface pair.

Volmarr's exact path with a FRESH proof account: register -> meet
the Gate Keeper -> new chat (nothing pinned) -> send -> HONEST
BLOCK (no stub in engine history, the user message never appended)
-> one-click connect (the pin road the button calls) -> send ->
REAL ollama reply lands. Plus: the W-01 proof chat (already pinned)
still answers for real; a group room refuses generation until its
chat is pinned, then answers for real through the deepening
resolution; and a fake-kind profile pinned on purpose is the
labelled Demo case (mind line says so, its canned reply may land).
Every check prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

RESULTS: list[tuple[str, bool, str]] = []
STUB = "Rúnmál hears you. This is a stub."


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))
    return ok


def sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        assert resp.status_code == 200, resp.status_code
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


def finish() -> int:
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FIX-STUB webface proof")
    parser.add_argument("--webface-url", default=os.environ.get(
        "RUNMAL_WEBFACE_URL", "http://100.67.240.22:8195"))
    parser.add_argument("--engine-url", default=os.environ.get(
        "RUNMAL_ENGINE_URL", "http://127.0.0.1:8098"))
    parser.add_argument("--engine-data-dir", default=os.environ.get(
        "RUNMAL_DATA_DIR", os.path.expanduser("~/.local/share/runmal")))
    args = parser.parse_args()

    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=300,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    profiles = eng.get("/api/v1/backend-profiles").json()
    house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
    check("house ollama profile present", house is not None,
          f"{house['chat_backend']}/{house['chat_model']}" if house else "missing")
    chars = eng.get("/api/v1/characters").json()
    keeper = next((c for c in chars if c.get("name") == "Webface Gate Keeper"), None)
    second = next((c for c in chars if c.get("name") == "W-02 Proof Scratch"), None)
    check("Gate Keeper + second character present", bool(keeper and second))
    if not (house and keeper and second):
        return finish()

    stamp = str(int(time.time()))
    username = f"fixstub-{stamp}"
    web = httpx.Client(base_url=args.webface_url, trust_env=False, timeout=300,
                       follow_redirects=False)
    reg = web.post("/register", data={"username": username,
                                      "password": "fix-stub-pass-1"})
    check("fresh proof account registered", reg.status_code == 303, username)
    page = web.get("/chat")
    check("chat page carries the mind line", 'id="mind-line"' in page.text
          and 'id="no-mind"' in page.text)

    chat = web.post("/webface/chats", json={"character_id": keeper["id"]}).json()
    chat_id = chat["id"]
    check("new chat pins nothing", chat.get("backend_profile_id") is None)
    mind = web.get(f"/webface/chats/{chat_id}/mind").json()
    check("disclosure: no mind yet", mind["words"] ==
          "No mind is connected to this chat yet.", mind["words"])
    before = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    events = sse(web, f"/webface/chats/{chat_id}/send",
                 {"content": "Hello, keeper — who answers here?"})
    check("send blocked with the honest no-mind words",
          [e["type"] for e in events] == ["no_mind"]
          and events[0]["words"] == "No mind is connected to this chat yet",
          json.dumps(events)[:160])
    check("connect walk offers the house profile",
          any(c["profile_id"] == house["id"] for c in events[0]["connect"])
          and events[0]["connections_url"] == "/connections")
    after = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    check("nothing appended by the blocked send (no stub, no user line)",
          after == before and all(STUB not in m["content"] for m in after),
          f"{len(before)} -> {len(after)} messages")
    regen = sse(web, f"/webface/chats/{chat_id}/regenerate", {})
    check("regenerate blocked unpinned too",
          [e["type"] for e in regen] == ["no_mind"])
    cont = web.post(f"/webface/chats/{chat_id}/continue", json={"mode": "auto"})
    check("continue blocked unpinned (409 + words)", cont.status_code == 409
          and cont.json()["no_mind"]["words"].startswith("No mind"), cont.text[:120])

    pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                   json={"profile_id": house["id"]})
    check("one-click connect (pin road) succeeds", pin.status_code == 200, pin.text[:120])
    mind = web.get(f"/webface/chats/{chat_id}/mind").json()
    check("disclosure after connect", mind["words"] ==
          f"Answering: w01-house-ollama · {house['chat_model']}", mind["words"])
    events = sse(web, f"/webface/chats/{chat_id}/send",
                 {"content": "Hello, keeper — who answers here?"})
    kinds = [e["type"] for e in events]
    started = next((e for e in events if e["type"] == "started"), {})
    reply = "".join(e.get("text", "") for e in events if e["type"] == "token")
    check("real reply lands after connect", "landed" in kinds
          and started.get("backend_key") == "ollama"
          and reply.strip() and STUB not in reply,
          f"backend={started.get('backend_key')} reply={reply.strip()[:80]!r}")
    history = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    check("engine history holds the real reply, no stub anywhere",
          history[-1]["content"].strip() == reply.strip()
          and all(STUB not in m["content"] for m in history))

    # Demo-labelled case: a fake-kind profile is constructible via
    # the engine's profile road; pinned on purpose it is Demo.
    demo = eng.post("/api/v1/backend-profiles", json={
        "name": f"fix-stub-demo-{stamp}", "chat_backend": "fake",
        "chat_model": "fake-1"})
    check("fake-kind profile constructible via the engine road",
          demo.status_code in (200, 201), demo.text[:120])
    if demo.status_code in (200, 201):
        dchat = web.post("/webface/chats", json={"character_id": keeper["id"]}).json()
        web.post(f"/webface/chats/{dchat['id']}/backend-profile",
                 json={"profile_id": demo.json()["id"]})
        dmind = web.get(f"/webface/chats/{dchat['id']}/mind").json()
        check("disclosure: Demo labelled", dmind["words"] == "Demo — not a real model",
              dmind["words"])
        devents = sse(web, f"/webface/chats/{dchat['id']}/send",
                      {"content": "Demo check."})
        check("Demo send passes, labelled (canned text may land)",
              "landed" in [e["type"] for e in devents])

    # Group room: guarded until its chat is pinned, then real.
    room = web.post("/webface/groups", json={
        "name": f"FIX-STUB Proof Room {stamp}",
        "member_character_ids": [keeper["id"], second["id"]]}).json()
    gid, room_chat = room["id"], room["chat_id"]
    blocked = web.post(f"/webface/groups/{gid}/next", json={"generate": True})
    check("group next refused with no mind", blocked.status_code == 409
          and blocked.json()["no_mind"]["chat_id"] == room_chat, blocked.text[:120])
    web.post(f"/webface/chats/{room_chat}/backend-profile",
             json={"profile_id": house["id"]})
    gmind = web.get(f"/webface/groups/{gid}/mind").json()
    check("group disclosure after pin", gmind["state"] == "real", gmind["words"])
    turn = web.post(f"/webface/groups/{gid}/next", json={"generate": True})
    gmsg = (turn.json().get("result") or {}).get("message") or {}
    check("group turn answers for real after pin", turn.status_code == 200
          and gmsg.get("content", "").strip() and STUB not in gmsg["content"],
          (gmsg.get("content") or "")[:80])

    # Pinned-chat regression: the W-01 proof chat still answers.
    web2 = httpx.Client(base_url=args.webface_url, trust_env=False, timeout=300,
                        follow_redirects=False)
    login = web2.post("/login", data={"username": "w01proof",
                                      "password": "w01-proof-pass"})
    check("w01proof login", login.status_code == 303, str(login.status_code))
    chats = eng.get("/api/v1/chats").json()
    w01 = next((c for c in chats if c.get("title") == "W-01 proof chat"), None)
    check("W-01 proof chat found", w01 is not None)
    if w01 is not None:
        events = sse(web2, f"/webface/chats/{w01['id']}/send",
                     {"content": "FIX-STUB regression ping: one short line, please."})
        started = next((e for e in events if e["type"] == "started"), {})
        reply = "".join(e.get("text", "") for e in events if e["type"] == "token")
        check("W-01 proof chat still answers for real",
              "landed" in [e["type"] for e in events]
              and started.get("backend_key") == "ollama" and STUB not in reply,
              f"backend={started.get('backend_key')} reply={reply.strip()[:80]!r}")
    print(f"\nstate: account={username} chat={chat_id} group={gid}")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
