#!/usr/bin/env python3
"""W-10 launch proof: real HTTP against the running pair.

Fresh proof account -> hardening: password change closes the
session (old password refused, new one works); recovery codes
generated (shown once), recovery sets a fresh password logged
out, code reuse refused -> the agent door: a token is created
through the account roads (plaintext in-process only, never
printed), used from this script as an EXTERNAL agent (whoami,
characters, the pinned Webface Gate Keeper chat: a real reply
+ history read-back), an unpinned chat answers no-mind, and
the token is REVOKED (401 after) - no live unrecorded tokens
are left behind; the standing Yrsa token is issued by Volmarr
from his own account when he wants it -> audit spot-checks:
the password-toggle inventory over the served face, a spaced-
filename avatar upload landing on the live pair (FIX-AVATAR),
and a fresh account's unpinned chat refusing with no-mind
(FIX-STUB). Leg E (second-device launch from Mimir) is run
as a separate documented step; its results are in the W-10
report. Secret hygiene: no password, code, or token plaintext
is ever printed - ids, names and counts only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

RESULTS: list = []
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", default="http://100.67.240.22:8195")
    ap.add_argument("--engine", default="http://127.0.0.1:8098")
    ap.add_argument("--engine-data-dir", default=str(Path.home() / ".local/share/runmal"))
    args = ap.parse_args()
    stamp = str(int(time.time()))[-6:]
    username = f"w10proof{stamp}"
    pw1, pw2, pw3 = "w10-first-pass-1", "w10-second-pass-1", "w10-third-pass-1"
    cred = (Path(args.engine_data_dir) / "local_credential").read_text().strip()
    eng_headers = {"Authorization": f"Bearer {cred}"}
    with httpx.Client(base_url=args.face, trust_env=False, timeout=180,
        follow_redirects=False) as web, \
            httpx.Client(trust_env=False, timeout=120) as eng:
        reg = web.post("/register", data={"username": username, "password": pw1})
        check("fresh proof account registers + lands on /chat", reg.status_code == 303)
        # --- hardening: password change ---
        bad = web.post("/account/password", data={"current_password": "wrong-wrong",
            "new_password": pw2})
        check("wrong current password refused in words", "did not match" in bad.text)
        changed = web.post("/account/password", data={"current_password": pw1, "new_password": pw2})
        check("password change closes the current session",
            changed.status_code == 303 and web.get("/webface/chats").status_code == 401)
        check("old password refused at login", "did not match" in web.post("/login",
            data={"username": username, "password": pw1}).text)
        check("new password logs in", web.post("/login", data={"username": username,
            "password": pw2}).status_code == 303)
        # --- hardening: recovery ---
        gen = web.post("/account/recovery-codes", data={})
        codes = re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", gen.text)
        check("recovery set generated (count only)", len(codes) == 10, f"{len(codes)} codes")
        check("codes not shown again on the account page",
            codes and codes[0] not in web.get("/account").text)
        web.post("/logout")
        rec = web.post("/recover", data={"username": username, "code": codes[0],
            "new_password": pw3})
        check("recovery sets a new password logged out", "Password set" in rec.text)
        check("recovery code reuse refused", "did not" in web.post("/recover",
            data={"username": username, "code": codes[0],
                "new_password": "w10-fourth-pass-1"}).text)
        check("account usable on its final password", web.post("/login",
            data={"username": username, "password": pw3}).status_code == 303)
        # --- agent door ---
        check("agent road without a token is 401", web.get("/agent/v1/whoami").status_code == 401)
        made = web.post("/account/agent-tokens", data={"name": "w10-proof-agent"})
        found = re.findall(r"rma_[A-Za-z0-9_\-]+", made.text)
        check("agent token issued via the account roads (shown once)", len(found) == 1)
        check("token not listed again on the account page",
            found and found[0] not in web.get("/account").text)
        auth = {"Authorization": f"Bearer {found[0]}"}
        who = web.get("/agent/v1/whoami", headers=auth)
        check("agent whoami answers with name + account",
            who.status_code == 200 and who.json().get("agent") == "w10-proof-agent")
        chars = web.get("/agent/v1/characters", headers=auth).json()
        keeper = next((c for c in chars if c.get("name") == "Webface Gate Keeper"), None)
        check("agent sees the Gate Keeper character", keeper is not None)
        chats = eng.get(f"{args.engine}/api/v1/chats", headers=eng_headers).json()
        profiles = eng.get(f"{args.engine}/api/v1/backend-profiles", headers=eng_headers).json()
        house = next((p for p in profiles if p.get("name") == "w01-house-ollama"), None)
        keeper_chat = next(
            (c for c in chats
             if c.get("character_id") == (keeper or {}).get("id")
             and house and c.get("backend_profile_id") == house["id"]),
            None)
        if keeper_chat is None and keeper and house:
            made_chat = web.post("/agent/v1/chats", headers=auth,
                json={"character_id": keeper["id"], "title": "W-10 proof"})
            keeper_chat = made_chat.json()
            pin = eng.post(f"{args.engine}/api/v1/chats/{keeper_chat['id']}/backend-profile",
                headers=eng_headers, json={"profile_id": house["id"]})
            check("agent-created chat pinned to the house profile", pin.status_code == 200)
        reply = web.post(f"/agent/v1/chats/{keeper_chat['id']}/send", headers=auth,
            json={"content": "Hello, keeper. Who are you?"})
        payload = reply.json() if reply.status_code == 200 else {}
        check("agent send gets a real reply",
            payload.get("type") == "reply" and bool(payload.get("reply",
                "").strip()), f"type={payload.get('type')}")
        hist = web.get(f"/agent/v1/chats/{keeper_chat['id']}/messages", headers=auth).json()
        check("history read-back holds the reply",
            bool(hist) and hist[-1].get("role") == "assistant" and hist[-1].get("content",
                "").strip() == payload.get("reply", "").strip())
        bare = web.post("/agent/v1/chats", headers=auth, json={"character_id": keeper["id"],
            "title": "W-10 proof unpinned"}).json()
        none = web.post(f"/agent/v1/chats/{bare['id']}/send", headers=auth,
            json={"content": "anyone there?"})
        check("unpinned chat answers no-mind to the agent", none.json().get("type") == "no_mind")
        acct = web.get("/account").text
        ids = re.findall(r"/account/agent-tokens/(\d+)/revoke", acct)
        web.post(f"/account/agent-tokens/{ids[-1]}/revoke", data={})
        check("revoked token is 401 immediately", web.get("/agent/v1/whoami",
            headers=auth).status_code == 401)
        # --- audit spot-checks ---
        tabs = ["chat", "groups", "characters", "library", "personas", "lorebooks", "connections",
            "generation", "memory", "scenarios", "inspector", "tools",
            "voice", "vision", "backups", "plugins", "bridge",
            "appearance", "account", "firstrun"]
        unhooked, pending = [], []
        for tab in tabs:
            page = web.get(f"/{tab}")
            if "arrives in slice" in page.text:
                pending.append(tab)
            for tag in re.findall(r"<input[^>]*>", page.text):
                if 'type="password"' in tag and "data-pw-toggle" not in tag:
                    unhooked.append((tab, tag))
        for page_path in ("/", "/login", "/register", "/recover"):
            anon = httpx.get(args.face + page_path, trust_env=False, timeout=30)
            for tag in re.findall(r"<input[^>]*>", anon.text):
                if 'type="password"' in tag and "data-pw-toggle" not in tag:
                    unhooked.append((page_path, tag))
        check("password-toggle inventory: every served password field hooked", not unhooked,
            f"{len(unhooked)} unhooked")
        check("no tab is a pending placeholder", not pending, ",".join(pending))
        # FIX-AVATAR re-verify: spaced filename lands
        up = web.post(f"/webface/characters/{keeper['id']}/avatar",
            files={"file": ("w10 proof avatar.png", PNG, "image/png")})
        got = eng.get(f"{args.engine}/api/v1/characters/{keeper['id']}/avatar", headers=eng_headers)
        check("FIX-AVATAR: spaced-filename avatar upload lands",
            up.status_code == 200 and got.status_code == 200
            and len(got.content) > 0,
            f"upload={up.status_code} read={got.status_code}")
        # FIX-STUB re-verify: fresh account, unpinned chat, SSE no-mind
        fresh = httpx.Client(base_url=args.face, trust_env=False, timeout=60,
            follow_redirects=False)
        fresh.post("/register", data={"username": f"w10stub{stamp}", "password": "w10-stub-pass-1"})
        events = []
        with fresh.stream("POST", f"/webface/chats/{bare['id']}/send",
            json={"content": "hello?"}) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
        check("FIX-STUB: fresh account unpinned chat -> no-mind, no stub",
            any(e.get("type") == "no_mind" for e in events),
            f"events={[e.get('type') for e in events]}")
        fresh.close()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
