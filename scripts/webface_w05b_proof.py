#!/usr/bin/env python3
"""W-05B launch proof: password show/hide toggles on the live pair.

Restarts the WEBFACE ONLY from this worktree's code, then proves
over real HTTP: the logged-out account page's password input
carries the shared data-pw-toggle hook and the shell loads
/static/pwtoggle.js; a fresh proof account registers and logs
in with the toggle present; the logged-in Connections page +
its served connections.js carry the hook on the W-04 write-only
secret fields (chat + embedding), and a canary key set through
the profile road is never echoed anywhere - the stored-key
state shows words only. The scratch profile is deleted after.
Every assertion prints PASS/FAIL; the exit code is honest.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

RESULTS: list[tuple[str, bool, str]] = []
CANARY = "CANARY-W05B-PROOF-never-echo-47"
HOOK = "data-pw-toggle"
SCRIPT_TAG = '<script src="/static/pwtoggle.js"></script>'
REPO = Path(__file__).parent.parent


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


def wait_up(url, timeout_s=30.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3, trust_env=False).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def password_inputs(html_text):
    return [t for t in re.findall(r"<input[^>]*>", html_text)
            if 'type="password"' in t]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webface-url", default=os.environ.get(
        "RUNMAL_WEBFACE_URL", "http://100.67.240.22:8195"))
    parser.add_argument("--engine-url", default=os.environ.get(
        "RUNMAL_ENGINE_URL", "http://127.0.0.1:8098"))
    parser.add_argument("--webface-data-dir", default=os.environ.get(
        "RUNMAL_WEBFACE_DATA_DIR",
        os.path.expanduser("~/.local/share/runmal-webface")))
    parser.add_argument("--engine-data-dir", default=os.environ.get(
        "RUNMAL_DATA_DIR", os.path.expanduser("~/.local/share/runmal")))
    parser.add_argument("--username", default=os.environ.get(
        "RUNMAL_PROOF_USER", "w01proof"))
    parser.add_argument("--password", default=os.environ.get(
        "RUNMAL_PROOF_PASSWORD", "w01-proof-pass"))
    args = parser.parse_args()

    check("engine /healthz",
          httpx.get(args.engine_url + "/healthz", timeout=5,
                    trust_env=False).status_code == 200)

    # ---- restart the WEBFACE ONLY, from this worktree's code ----
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
    env["PYTHONPATH"] = str(REPO / "src")
    proc = subprocess.Popen(
        [sys.executable, "-m", "runmal.webface", "--host", parsed.hostname,
         "--port", str(parsed.port), "--engine-url", args.engine_url,
         "--data-dir", args.webface_data_dir,
         "--engine-data-dir", args.engine_data_dir],
        cwd=str(REPO), env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    pidfile.write_text(str(proc.pid))
    check("webface restarted from worktree code (new pid)",
          proc.pid != old_pid and wait_up(args.webface_url + "/"),
          f"pid {old_pid} -> {proc.pid}")

    web = httpx.Client(base_url=args.webface_url, trust_env=False,
                       timeout=60, follow_redirects=False)
    # ---- logged-out inventory: account page ----
    landing = web.get("/")
    inputs = password_inputs(landing.text)
    check("account page (logged out) serves a password input", bool(inputs))
    check("account page password input carries the toggle hook",
          bool(inputs) and all(HOOK in t for t in inputs), str(inputs))
    check("shell loads the shared pwtoggle script", SCRIPT_TAG in landing.text)
    script = web.get("/static/pwtoggle.js")
    check("shared toggle script serves with the flip logic",
          script.status_code == 200
          and 'input.type = show ? "text" : "password"' in script.text
          and "MutationObserver" in script.text)
    for path in ("/login", "/register"):
        page = web.get(path)
        tags = password_inputs(page.text)
        check(f"{path} password input carries the toggle hook",
              bool(tags) and all(HOOK in t for t in tags))

    # ---- fresh proof account: register + login round trip ----
    fresh = f"w05bproof{int(time.time()) % 100000}"
    reg = web.post("/register", data={"username": fresh,
                                      "password": "w05b-proof-pass"})
    check("fresh account registers with the toggle present",
          reg.status_code == 303 and reg.headers.get("location") == "/chat",
          f"status {reg.status_code}")
    check("fresh session works", web.get("/webface/chats").status_code == 200)
    web.post("/logout")
    bad = web.post("/login", data={"username": fresh,
                                   "password": "not-the-password"})
    check("wrong password still refused", "did not match" in bad.text)
    good = web.post("/login", data={"username": fresh,
                                    "password": "w05b-proof-pass"})
    check("fresh account logs in again", good.status_code == 303)
    web.post("/logout")

    # ---- logged in as w01proof: connections + firstrun ----
    login = web.post("/login", data={"username": args.username,
                                     "password": args.password})
    check("login as w01proof", login.status_code == 303,
          f"status {login.status_code}")
    page = web.get("/connections")
    check("Connections page serves with the shell toggle script",
          page.status_code == 200 and SCRIPT_TAG in page.text)
    conn_js = web.get("/static/connections.js")
    check("connections.js secret fields carry the toggle hook",
          conn_js.status_code == 200
          and 'input.type = "password"' in conn_js.text
          and f'input.setAttribute("{HOOK}", "")' in conn_js.text)
    fr_page = web.get("/firstrun")
    fr_js = web.get("/static/firstrun.js")
    check("First-Run page serves; its API-key field carries the hook",
          fr_page.status_code == 200 and SCRIPT_TAG in fr_page.text
          and f'input.setAttribute("{HOOK}", "")' in fr_js.text)

    # ---- W-04 write-only secret handling is untouched ----
    created = web.post("/webface/profiles", json={
        "name": "w05b-proof-scratch", "chat_backend": "ollama",
        "chat_model": "phi3:mini",
        "chat_secret_action": "set", "chat_secret": CANARY,
        "embedding_secret_action": "set", "embedding_secret": CANARY})
    check("scratch profile created", created.status_code == 200,
          created.text[:120])
    if created.status_code == 200:
        prof = created.json()
        check("canary never echoed in the create response",
              CANARY not in created.text)
        check("stored-key state shows words only",
              prof["secret_words"]["chat"] == "a key is stored"
              and prof["secret_words"]["embedding"] == "a key is stored",
              str(prof.get("secret_words")))
        listing = web.get("/webface/profiles")
        check("canary absent from the profile list", CANARY not in listing.text)
        gone = web.delete(f"/webface/profiles/{prof['id']}")
        check("scratch profile deleted after proof",
              gone.status_code in (200, 204), f"status {gone.status_code}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
