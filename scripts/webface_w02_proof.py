#!/usr/bin/env python3
"""W-02 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> Characters tab lists the
Webface Gate Keeper -> edit its description through the webface
editor -> the engine API shows the edit -> create a scratch
character from scratch through the webface -> open a chat with it
-> send one message -> a REAL reply from the house Ollama
(backend_key=ollama, mode=composed) -> export + re-import round
trip -> delete the scratch character -> undo restores it.
Every assertion prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="W-02 webface proof")
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
    args = parser.parse_args()
    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng = httpx.Client(base_url=args.engine_url, trust_env=False, timeout=60,
                       headers={"Authorization": f"Bearer {token}"})
    check("engine /healthz", eng.get("/healthz").status_code == 200)
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=180, follow_redirects=False)
    login = web.post("/login", data={"username": args.username,
                                      "password": args.password})
    if login.status_code != 303:
        login = web.post("/register", data={"username": args.username,
                                            "password": args.password})
    check("login as proof account", login.status_code == 303,
          f"status {login.status_code}")
    page = web.get("/characters")
    check("Characters tab page serves", page.status_code == 200
          and "c-roster" in page.text)
    page = web.get("/library")
    check("Library tab page serves", page.status_code == 200
          and "l-files" in page.text)
    roster = web.get("/webface/library/cards").json()
    keeper = next((r for r in roster.get("items", [])
                   if r.get("name") == "Webface Gate Keeper"), None)
    check("roster lists Webface Gate Keeper", keeper is not None)
    if keeper is None:
        return _finish()
    kid = keeper["id"]
    bundle = web.get(f"/webface/characters/{kid}/editor").json()
    original = bundle["fields"]["description"]
    marker = " [W-02 proof edit]"
    edited = original if marker in original else original + marker
    fields = dict(bundle["fields"])
    fields["description"] = edited
    saved = web.patch(f"/webface/characters/{kid}", json=fields)
    check("editor save through the webface", saved.status_code == 200,
          saved.text[:160])
    versions = eng.get(f"/api/v1/characters/{kid}/versions").json()
    latest = versions["latest_version_no"]
    card = eng.get(f"/api/v1/characters/{kid}/versions/{latest}").json()["card"]
    data = card.get("data") or card
    check("engine API shows the edited description",
          data.get("description") == edited, str(data.get("description"))[:80])
    # Create a scratch character from scratch through the webface.
    made = web.post("/webface/characters", json={
        "name": "W-02 Proof Scratch", "description": "A scratch keeper made by the W-02 proof.",
        "personality": "brief and warm",
        "system_prompt": "You are the W-02 Proof Scratch keeper. Answer in one short sentence.",
        "first_mes": "Well met. Ask, and I answer briefly."})
    check("scratch character created via webface", made.status_code == 200,
          made.text[:160])
    scratch = made.json() if made.status_code == 200 else {}
    sid = scratch.get("id", "")
    roster2 = web.get("/webface/library/cards").json()
    check("roster lists the scratch character",
          sid in {r.get("id") for r in roster2.get("items", [])})
    # Open a chat with it and send one real message.
    profiles = eng.get("/api/v1/backend-profiles").json()
    profile = next((p for p in profiles if p.get("chat_backend") == "ollama"
                    and p.get("chat_model")), None)
    check("real ollama profile present", profile is not None,
          f"{profile.get('chat_model')}" if profile else "none")
    chat = web.post("/webface/chats", json={"character_id": sid})
    check("chat created bound to scratch character", chat.status_code == 200,
          chat.text[:160])
    chat_id = chat.json().get("id", "") if chat.status_code == 200 else ""
    if profile and chat_id:
        pin = eng.post(f"/api/v1/chats/{chat_id}/backend-profile",
                       json={"profile_id": profile["id"]})
        check("chat pinned to the ollama profile", pin.status_code == 200)
    events = []
    if chat_id:
        with web.stream("POST", f"/webface/chats/{chat_id}/send",
                        json={"content": "Hello! In one short sentence, who are you?"}) as resp:
            check("send stream answers", resp.status_code == 200)
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[len("data:"):].strip()))
    kinds = [e.get("type") for e in events]
    started = next((e for e in events if e.get("type") == "started"), {})
    check("stream started event", "started" in kinds, str(started))
    check("backend is ollama (not fake)", started.get("backend_key") == "ollama",
          str(started.get("backend_key")))
    check("mode is composed", started.get("mode") == "composed")
    reply = "".join(e.get("text", "") for e in events if e.get("type") == "token")
    check("real reply streamed", bool(reply.strip()), reply.strip()[:80])
    check("reply landed", "landed" in kinds)
    history = eng.get(f"/api/v1/chats/{chat_id}/messages").json() if chat_id else []
    check("reply persisted in engine history",
          any(m.get("role") == "assistant" and m.get("content", "").strip() == reply.strip()
              for m in history))
    # Export + re-import round trip.
    export = web.get(f"/webface/characters/{sid}/export")
    check("export downloads the card", export.status_code == 200
          and "attachment" in export.headers.get("content-disposition", ""))
    renamed = json.loads(export.content)
    (renamed.get("data") or renamed)["name"] = "W-02 Proof Scratch II"
    report = web.post("/webface/library/imports", files={
        "files": ("scratch.json", json.dumps(renamed).encode(), "application/json")})
    body = report.json() if report.status_code == 200 else {}
    check("re-import creates a second character",
          report.status_code == 200 and bool(body.get("created_ids")),
          str(body.get("words", "")))
    # Delete the scratch character + undo.
    deleted = web.delete(f"/webface/characters/{sid}")
    check("delete answers deleted", deleted.status_code == 200
          and bool(deleted.json().get("deleted")))
    roster3 = web.get("/webface/library/cards").json()
    check("deleted character leaves the roster",
          sid not in {r.get("id") for r in roster3.get("items", [])})
    undone = web.post(f"/webface/characters/{sid}/restore")
    check("undo restores the character", undone.status_code == 200,
          undone.text[:160])
    roster4 = web.get("/webface/library/cards").json()
    check("restored character is back in the roster",
          sid in {r.get("id") for r in roster4.get("items", [])})
    return _finish()


def _finish() -> int:
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
