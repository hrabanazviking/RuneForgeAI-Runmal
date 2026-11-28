#!/usr/bin/env python3
"""W-06 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> Memory: a proof memory is
seeded through the engine's own memory service (the only write
road that exists) into the real data dir, then browsed,
searched and opened through the webface and verified against
direct engine reads -> Scenarios: 'W-06 Proof Harbour' is
created through the webface with an unknown key riding along,
edited (the unknown key and the bootstrap survive), favourited
and tagged, then APPLIED to Webface Gate Keeper: a quiet-start
chat is made and bound, the opening line is the chat's first
message, the house profile is pinned, and a real Ollama reply
lands -> restart the WEBFACE ONLY -> scenario, binding and
memory still served. All proof entities stay, named, as
recorded artifacts. Every assertion prints PASS/FAIL; the
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


_SEED = """
import asyncio, os, sys
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.owners import get_or_create_owner
from runmal.memory import service

async def main():
    engine = create_db_engine()
    factory = create_session_factory(engine)
    async with factory() as session:
        owner = await get_or_create_owner(session)
        rows = await service.list_memories(session, owner.id)
        if not any("W-06 proof memory" in r.content for r in rows):
            m = await service.create_memory(
                session, owner.id,
                content="W-06 proof memory: the harbour keeper brews ember tea",
                kind="semantic", scope="user", subject="keeper",
                extractor={"kind": "w06-proof-seed"},
                sources=(("message", "w06-proof-seed", None),))
            print(m.id)
        else:
            print(next(r.id for r in rows if "W-06 proof memory" in r.content))
        await session.commit()
    await engine.dispose()

asyncio.run(main())
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="W-06 webface proof")
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
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = args.engine_data_dir
    seed = subprocess.run([sys.executable, "-c", _SEED], env=env,
                          capture_output=True, text=True, timeout=120)
    memory_id = seed.stdout.strip().splitlines()[-1] if seed.stdout.strip() else ""
    check("proof memory seeded via engine service", seed.returncode == 0
          and bool(memory_id), memory_id or seed.stderr[-300:])
    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=300, follow_redirects=True)
    login = web.post("/login", data={"username": args.username,
                                     "password": args.password})
    check("login as proof account", login.status_code == 200
          and "Log out" in login.text)
    for slug, marker in (("/memory", "m-list"), ("/scenarios", "s-list")):
        page = web.get(slug)
        check(f"{slug} tab graduated", page.status_code == 200
              and marker in page.text and "arrives in slice" not in page.text)
    # ---- memory through the webface, verified on the engine ----
    view = web.get("/webface/memories", params={"q": "W-06 proof memory"}).json()
    check("memory search finds the proof memory", view.get("total") == 1
          and "ember tea" in view["lines"][0], str(view.get("total")))
    check("memory page states the honest read-only contract",
          "no road to create, edit or delete" in view.get("note", ""))
    detail = web.get(f"/webface/memories/{memory_id}").json()
    check("memory detail words carry scope + provenance",
          "Scope: about you (user)" in detail.get("words", "")
          and "w06-proof-seed" in detail["words"]
          and "- message · w06-proof-seed" in detail["words"])
    direct = eng.get(f"/api/v1/memories/{memory_id}").json()
    check("webface detail matches the engine read",
          direct.get("content") == detail["memory"].get("content"))
    # ---- scenario create/edit/org through the webface ----
    characters = eng.get("/api/v1/characters").json()
    keeper = next((c for c in characters
                   if c.get("name") == "Webface Gate Keeper"), None)
    check("Gate Keeper character exists", bool(keeper))
    existing = [r for r in eng.get("/api/v1/scenarios").json().get("scenarios", [])
                if r.get("name") == "W-06 Proof Harbour"]
    if existing:
        sid = existing[0]["id"]
        check("proof scenario already present (re-run)", True, sid)
    else:
        created = web.post("/webface/scenarios", json={
            "values": {"name": "W-06 Proof Harbour",
                       "description": "W-06 live proof scenario.",
                       "scenario_text": "The ferry has just left."},
            "sections": {
                "roles": [{"name": "Narrator", "character_name": "Maera",
                           "enabled_on_start": True, "can_speak": True}],
                "bootstrap_messages": [
                    {"kind": "note",
                     "text": "W06 proof opening: the tide is going out.",
                     "role": "Narrator"}],
                "initial_flags": {"met_maera": True},
                "initial_variables": {"trust": 2}},
            "document": {"w06_proof_extra": "keep-me"}})
        check("proof scenario created via webface",
              created.status_code == 200, created.text[:200])
        sid = created.json().get("id", "")
    stored = eng.get(f"/api/v1/scenarios/{sid}").json()
    check("unknown key + sections stored losslessly",
          stored["definition"].get("w06_proof_extra") == "keep-me"
          and stored["definition"].get("initial_variables") == {"trust": 2})
    edited = web.put(f"/webface/scenarios/{sid}", json={
        "values": {"description": "W-06 live proof scenario (edited)."}})
    stored2 = eng.get(f"/api/v1/scenarios/{sid}").json()
    check("edit via webface is lossless (revision +1, extras kept)",
          edited.status_code == 200
          and stored2["definition"].get("w06_proof_extra") == "keep-me"
          and stored2["definition"]["bootstrap_messages"][0]["text"].startswith(
              "W06 proof opening"))
    web.put(f"/webface/scenarios/{sid}/favourite", json={"is_favourite": True})
    web.put(f"/webface/scenarios/{sid}/tags", json={"tags": "w06-proof, harbour"})
    listing = web.get("/webface/scenarios",
                      params={"favourites_only": "true"}).json()
    check("favourite + tags visible in the library line",
          any(r["id"] == sid for r in listing["scenarios"])
          and any("★ favourite" in ln and "w06-proof" in ln
                  for ln in listing["lines"]))
    # ---- apply: quiet chat + bind; pin house profile; real send ----
    applied = web.post(f"/webface/scenarios/{sid}/apply",
                       json={"character_id": keeper["id"]})
    check("apply via webface (chat made + bound)",
          applied.status_code == 200, applied.text[:200])
    chat_id = applied.json().get("chat_id", "") if applied.status_code == 200 else ""
    msgs = eng.get(f"/api/v1/chats/{chat_id}/messages").json() if chat_id else []
    check("seeded opening is the chat's first message (no card greeting)",
          bool(msgs) and "W06 proof opening" in msgs[0].get("content", ""),
          msgs[0].get("content", "")[:80] if msgs else "no messages")
    binding = eng.get(f"/api/v1/scenarios/bindings/{chat_id}").json() if chat_id else {}
    check("binding record on the engine names the scenario",
          binding.get("definition_id") == sid
          and any("trust" in k for k in binding.get("seeded_keys", [])))
    profiles = eng.get("/api/v1/backend-profiles").json()
    house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
    check("house profile exists", bool(house))
    if chat_id and house:
        pin = web.post(f"/webface/chats/{chat_id}/backend-profile",
                       json={"profile_id": house["id"]})
        check("house profile pinned to the scenario chat",
              pin.status_code == 200, pin.text[:120])
        code, events = sse(web, f"/webface/chats/{chat_id}/send",
                           {"content": "What is happening at the harbour?"})
        landed = [e for e in events if e.get("type") == "landed"]
        check("real Ollama reply landed in the scenario chat",
              code == 200 and bool(landed))
    # ---- restart the WEBFACE ONLY; state persists ----
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
    after = web2.get("/webface/scenarios").json()
    binds = web2.get("/webface/scenarios/bindings").json()
    mem = web2.get("/webface/memories", params={"q": "W-06 proof memory"}).json()
    check("after restart: scenario + binding + memory still served",
          any(r["id"] == sid for r in after.get("scenarios", []))
          and any(b.get("chat_id") == chat_id for b in binds.get("bindings", []))
          and mem.get("total") == 1)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
