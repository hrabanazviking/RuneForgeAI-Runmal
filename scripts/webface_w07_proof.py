#!/usr/bin/env python3
"""W-07 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> a proof chat with
Webface Gate Keeper (house profile pinned, a real Ollama
reply landed; the chat is found again on re-runs by its
proof marker message) -> Inspector: the overview / events /
reasoning documents served through the webface equal the
direct engine reads; the trace served through the webface
agrees with a direct engine prompt-inspect call (ledger,
slot kinds/statuses/tokens, lore account) and its composed
sections equal the direct call's preview messages, with a
section carrying the Keeper's own text; the landed reply's
provenance through the webface equals the direct road ->
Tools: the macro registry equals the engine's; a seeded
expansion through the webface equals a direct engine call
exactly and repeats identically (seeded = deterministic);
variables, resolve and compose preview agree with direct
calls -> restart the WEBFACE ONLY -> both tabs still
graduated and the trace still agrees. The tools roads write
nothing, so there is nothing to restore; the proof chat
stays, named by its marker, as a recorded artifact. Every
assertion prints PASS/FAIL; the exit code is honest.
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
MARKER = "W07 proof: who keeps this gate?"


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
    parser = argparse.ArgumentParser(description="W-07 webface proof")
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
    for slug, marker in (("/inspector", "i-chat"), ("/tools", "t-macros")):
        page = web.get(slug)
        check(f"{slug} tab graduated", page.status_code == 200
              and marker in page.text and "arrives in slice" not in page.text)
    pending = web.get("/voice")
    check("/voice still honestly pending (W-08)",
          pending.status_code == 200 and "W-08" in pending.text)
    # ---- the proof chat: find by marker, else make + land ----
    characters = eng.get("/api/v1/characters").json()
    keeper = next((c for c in characters
                   if c.get("name") == "Webface Gate Keeper"), None)
    check("Gate Keeper character exists", bool(keeper))
    profiles = eng.get("/api/v1/backend-profiles").json()
    house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
    check("house profile exists", bool(house))
    chat_id = ""
    for chat in eng.get("/api/v1/chats").json():
        if chat.get("character_id") != (keeper or {}).get("id"):
            continue
        rows = eng.get(f"/api/v1/chats/{chat['id']}/messages").json()
        if any(MARKER in str(m.get("content") or "") for m in rows) and \
                any(m.get("role") == "assistant" for m in rows):
            chat_id = chat["id"]
            break
    if chat_id:
        check("proof chat found again (re-run)", True, chat_id)
    elif keeper and house:
        made = web.post("/webface/chats", json={"character_id": keeper["id"]})
        chat_id = made.json().get("id", "") if made.status_code == 200 else ""
        check("proof chat created via webface", bool(chat_id), made.text[:160])
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": house["id"]})
        check("house profile pinned (stub guard: real mind)",
              pin.status_code == 200, pin.text[:120])
        code, events = sse(web, f"/webface/chats/{chat_id}/send",
                           {"content": MARKER})
        landed = [e for e in events if e.get("type") == "landed"]
        check("real Ollama reply landed in the proof chat",
              code == 200 and bool(landed))
    msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json() if chat_id else []
    landed_rows = [m for m in msgs if m.get("role") == "assistant"]
    check("proof chat carries a landed reply", bool(landed_rows))
    # ---- inspector documents agree with direct engine reads ----
    docs = web.get(f"/webface/inspector/chats/{chat_id}").json()
    agree = True
    for key, road in (("overview", ""), ("events", "/events"),
                      ("reasoning", "/reasoning")):
        direct = eng.get(f"/api/v1/inspector/chats/{chat_id}{road}").json()
        agree = agree and docs.get(key) == direct
    check("inspector documents equal direct engine reads", agree)
    total = docs.get("overview", {}).get("sections", {}).get(
        "provenance", {}).get("summary", {}).get("total", 0)
    check("overview provenance summary counts the landed exchange",
          total >= 2, f"total={total}")
    check("inspector states the no-send honesty note",
          "sends nothing" in docs.get("note", ""))
    # ---- trace agrees with a direct engine prompt-inspect ----
    view = web.post(f"/webface/inspector/chats/{chat_id}/trace", json={}).json()
    texts = [str(m.get("content") or "") for m in msgs][-20:]
    direct = eng.post("/api/v1/debug/prompt-inspect", json={
        "chat_id": chat_id, "character_id": keeper["id"],
        "include_activation_inspection": True, "include_preview": True,
        "messages": texts}).json()
    def slim(rows):
        return [(r.get("kind"), r.get("status"), r.get("tokens"))
                for r in rows or []]
    check("trace ledger + slots + lore account equal the direct call",
          view["trace"]["ledger"] == direct["ledger"]
          and slim(view["trace"]["slots"]) == slim(direct["slots"])
          and view["trace"].get("lore_account") == direct.get("lore_account"))
    direct_sections = [{"slot_id": str(m.get("slot_id") or ""),
                        "role": str(m.get("role") or ""),
                        "content": str(m.get("content") or "")}
                       for m in direct["prompt_preview"]["messages"]]
    check("composed sections equal the direct preview messages",
          view["sections"] == direct_sections, f"{len(direct_sections)} sections")
    check("a composed section carries the Keeper's own text",
          any("Gate Keeper" in s["content"] for s in view["sections"]))
    check("trace content honesty note present (S214)",
          "no prompt text" in view.get("content_note", ""))
    check("engine token counts carried, not recounted (ledger words)",
          str(direct["ledger"]["total_input_tokens"]) in view["ledger_words"])
    # ---- reply provenance agrees with the direct road ----
    mid = landed_rows[-1]["id"] if landed_rows else ""
    prov = web.get(f"/webface/inspector/chats/{chat_id}/messages/{mid}/provenance").json()
    direct_prov = eng.get(f"/api/v1/chats/{chat_id}/messages/{mid}/provenance").json()
    check("reply provenance equals the direct engine road",
          prov.get("provenance") == direct_prov)
    # ---- tools flows agree with direct engine calls ----
    macros = web.get("/webface/tools/macros").json()
    check("macro registry equals the engine's",
          macros.get("macros") == eng.get("/api/v1/tools/macros").json()
          and macros.get("total", 0) > 10, f"total={macros.get('total')}")
    check("tools page states the honest no-tool-registry scope",
          "no callable-tool registry" in macros.get("note", ""))
    payload = {"text": "{{char}} rolls {{roll::2d6}} for {{user}}",
               "char": "Maera", "user": "Volmarr", "seed": 42}
    expanded = web.post("/webface/tools/macros/expand", json=payload).json()
    direct_exp = eng.post("/api/v1/tools/macros/expand", json=payload).json()
    check("seeded expansion equals a direct engine call exactly",
          expanded.get("result") == direct_exp)
    again = web.post("/webface/tools/macros/expand", json=payload).json()
    check("seeded expansion repeats identically (deterministic)",
          again.get("result") == expanded.get("result"))
    variables = web.get("/webface/tools/variables").json()
    check("variable registry equals the engine's",
          variables.get("variables") == eng.get("/api/v1/tools/variables").json())
    resolved = web.post("/webface/tools/resolve", json={
        "text": "{{char}} at {{weekday}}", "char": "Maera"}).json()
    direct_res = eng.post("/api/v1/tools/resolve", json={
        "text": "{{char}} at {{weekday}}", "char": "Maera", "user": "User"}).json()
    check("variable resolve equals a direct engine call",
          resolved.get("result") == direct_res)
    compose_body = {"system": "Be brief.", "persona": "Maera the keeper.",
                    "history": ["hello", "hi there"],
                    "authors_note": "Stay in character.", "note_depth": 1}
    composed = web.post("/webface/tools/compose", json=compose_body).json()
    direct_comp = eng.post("/api/v1/tools/compose", json=dict(
        compose_body, context_limit=4096, reserve_response=512)).json()
    check("compose preview messages + manifest equal a direct call",
          composed["result"]["messages"] == direct_comp["messages"]
          and composed["result"]["manifest"] == direct_comp["manifest"])
    # ---- restart the WEBFACE ONLY; tabs + trace still agree ----
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
    page = web2.get("/inspector")
    view2 = web2.post(f"/webface/inspector/chats/{chat_id}/trace", json={}).json()
    check("after restart: inspector graduated + trace still agrees",
          page.status_code == 200 and "i-chat" in page.text
          and view2["trace"]["ledger"] == direct["ledger"])
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
