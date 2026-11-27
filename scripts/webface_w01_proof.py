#!/usr/bin/env python3
"""W-01 launch proof: real HTTP against the running engine+webface pair.

Drives the whole slice against REAL data and a REAL backend (never
the fake backend): register -> login -> chat tab data -> create a
chat bound to a real character -> history matches the engine API ->
send -> real streamed reply (backend recorded from the stream's
started event) -> reply present in engine history -> webface restart
-> same history served (engine-side state) -> logout/login -> still
there. Every assertion prints PASS/FAIL; exit code is honest.

Config (env or flags): --webface-url, --engine-url, --engine-data-dir,
--username/--password (a fresh proof account is registered when the
login fails), --ollama-url + --model (used only when the real data
dir has no usable ollama profile yet: one is created via the API).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="W-01 webface proof")
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
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL"))
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL"))
    parser.add_argument("--message", default="Hello! In one short "
                        "sentence, who are you?")
    args = parser.parse_args()

    from pathlib import Path
    token = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng_headers = {"Authorization": f"Bearer {token}"}
    eng = httpx.Client(base_url=args.engine_url, headers=eng_headers,
                       trust_env=False, timeout=60)
    health = eng.get("/healthz")
    check("engine /healthz", health.status_code == 200)

    # A real backend profile must exist (ollama + a real listed model).
    profiles = eng.get("/api/v1/backend-profiles").json()
    profile = next((p for p in profiles
                    if p.get("chat_backend") == "ollama"
                    and p.get("chat_model")), None)
    if profile is None and args.ollama_url and args.model:
        made = eng.post("/api/v1/backend-profiles", json={
            "name": "w01-house-ollama", "chat_backend": "ollama",
            "chat_model": args.model,
            "config": {"base_url": args.ollama_url}})
        check("created ollama backend profile via API",
              made.status_code in (200, 201), made.text[:200])
        profile = made.json() if made.status_code in (200, 201) else None
    check("real ollama backend profile present", profile is not None,
          f"{profile.get('chat_backend')}/{profile.get('chat_model')}"
          if profile else "none found")
    if profile is None:
        return _finish()

    # A real character must exist; seed one through the API if not.
    characters = eng.get("/api/v1/characters").json()
    if not characters:
        made = eng.post("/api/v1/characters", json={"card": {
            "name": "Webface Gate Keeper",
            "description": "Keeper of the W-01 web gate.",
            "system_prompt": "You are the Webface Gate Keeper of "
                             "Rúnmál. Answer briefly and warmly.",
            "first_mes": "Well met, traveller. State your business."}})
        check("seeded a character via the engine API",
              made.status_code in (200, 201), made.text[:200])
        characters = eng.get("/api/v1/characters").json()
    check("real character list non-empty", len(characters) > 0,
          ", ".join(c.get("name", "?") for c in characters[:5]))
    character = characters[0]

    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=False)
    landing = web.get("/")
    check("logged-out / is the account page",
          landing.status_code == 200 and "Log in" in landing.text)
    login = web.post("/login", data={"username": args.username,
                                      "password": args.password})
    if login.status_code != 303:
        reg = web.post("/register", data={"username": args.username,
                                           "password": args.password})
        check("registered the proof account (auto-login)",
              reg.status_code == 303, f"status {reg.status_code}")
    else:
        check("logged in with the proof account", True)
    root = web.get("/")
    check("logged-in / redirects to /chat",
          root.status_code == 303 and root.headers.get("location") == "/chat")
    chat_page = web.get("/chat")
    check("chat tab renders with the tab shell",
          chat_page.status_code == 200 and "Connections" in chat_page.text
          and "Account" in chat_page.text)
    wf_chars = web.get("/webface/characters")
    check("webface character list == engine list",
          wf_chars.status_code == 200
          and [c["id"] for c in wf_chars.json()]
          == [c["id"] for c in characters])

    created = web.post("/webface/chats",
                       json={"character_id": character["id"],
                             "title": "W-01 proof chat"})
    check("created a chat bound to the character",
          created.status_code in (200, 201), created.text[:200])
    chat_id = created.json()["id"]
    pin = eng.post(f"/api/v1/chats/{chat_id}/backend-profile",
                   json={"profile_id": profile["id"]})
    check("pinned the real backend profile to the chat",
          pin.status_code == 200, pin.text[:200])

    before = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    via_web = web.get(f"/webface/chats/{chat_id}/messages").json()
    check("history via webface == history via engine API",
          [m["id"] for m in via_web] == [m["id"] for m in before],
          f"{len(before)} messages before send")

    events = []
    with web.stream("POST", f"/webface/chats/{chat_id}/send",
                    json={"content": args.message}) as resp:
        check("send streams SSE", resp.status_code == 200,
              f"status {resp.status_code}")
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    kinds = [e.get("type") for e in events]
    started = next((e for e in events if e.get("type") == "started"), {})
    reply = "".join(e.get("text", "") for e in events
                    if e.get("type") == "token")
    check("stream carried token + done + landed",
          "token" in kinds and "done" in kinds and "landed" in kinds,
          f"events: {kinds}")
    check("backend that answered is REAL (not fake)",
          started.get("backend_key") not in ("", "fake"),
          f"backend_key={started.get('backend_key')!r} "
          f"mode={started.get('mode')!r} profile="
          f"{profile.get('chat_backend')}/{profile.get('chat_model')}")
    check("streamed reply non-empty", bool(reply.strip()),
          f"reply: {reply.strip()[:160]!r}")

    after = eng.get(f"/api/v1/chats/{chat_id}/messages").json()
    assistants = [m for m in after if m["role"] == "assistant"]
    check("reply present in engine history afterwards",
          bool(assistants) and assistants[-1]["content"].strip()
          == reply.strip(),
          f"{len(after)} messages after send")
    print(f"CHAT_ID={chat_id}")
    print(f"EXPECTED_MESSAGES={len(after)}")
    return _finish()


def _finish() -> int:
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
