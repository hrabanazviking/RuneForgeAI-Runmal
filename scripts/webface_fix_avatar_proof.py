#!/usr/bin/env python3
"""FIX-AVATAR launch proof: real HTTP against the running pair.

The 2026-11-27 repro filenames that got HTTP 400 \"bad filename\"
from the old whitelist are uploaded as an avatar to a SCRATCH
character through the WEBFACE road: all must land, and GET-back
must be byte-identical. Also: clean names land, .heic is refused
with clear display words, >16 MiB answers 413 with words, the
asset road takes a spaced name, and after a WEBFACE-ONLY restart
the avatar is still served. Scratch characters only -- Alfhild
and the Gate Keeper are never touched. Exit code is honest.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

RESULTS: list[tuple[str, bool, str]] = []
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415478da626001000000ffff03000006000557bfabd40000000049454e44ae426082")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail else ""))
    return ok


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
    parser = argparse.ArgumentParser(description="FIX-AVATAR webface proof")
    parser.add_argument("--webface-url", default=os.environ.get(
        "RUNMAL_WEBFACE_URL", "http://100.67.240.22:8195"))
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
    # served JS carries the upload-progress machinery (no silent road)
    js = web.get("/static/characters.js")
    check("characters.js serves XHR upload progress",
          js.status_code == 200 and "uploadWithProgress" in js.text
          and "XMLHttpRequest" in js.text)
    lib = web.get("/static/library.js")
    check("library.js serves XHR upload progress",
          lib.status_code == 200 and "uploadWithProgress" in lib.text)
    # scratch character via the webface (never Alfhild / Gate Keeper)
    made = web.post("/webface/characters", json={
        "name": "FIX-AVATAR Proof Scratch",
        "description": "Scratch character for the FIX-AVATAR proof.",
        "personality": "brief", "first_mes": "Hi."})
    if made.status_code == 200 and made.json().get("id"):
        cid = made.json()["id"]
        check("scratch character created", True, cid)
    else:
        chars = eng.get("/api/v1/characters").json()
        scratch = next((c for c in chars
                        if c.get("name") == "FIX-AVATAR Proof Scratch"), None)
        check("scratch character exists", scratch is not None,
              f"create status {made.status_code}")
        if scratch is None:
            return 1
        cid = scratch["id"]
    repro = ["IMG 20251127 1205.jpg", "photo (1).jpg",
             "volmarr's photo.jpg", "mynd_\u00fe.jpg", "a" * 136 + ".jpg"]
    for name in repro:
        up = web.post(f"/webface/characters/{cid}/avatar",
                      files={"file": (name, PNG, "image/jpeg")})
        ok = up.status_code == 200
        detail = f"status {up.status_code}"
        if ok:
            got = web.get(f"/webface/characters/{cid}/avatar")
            ok = got.status_code == 200 and got.content == PNG
            detail += f", stored as {up.json().get('filename')!r}, " \
                      f"GET-back {'byte-identical' if got.content == PNG else 'MISMATCH'}"
        else:
            detail += f", body {up.text[:160]}"
        check(f"avatar lands via webface: {name!r}", ok, detail)
    up = web.post(f"/webface/characters/{cid}/avatar",
                  files={"file": ("avatar.png", PNG, "image/png")})
    check("clean name still lands", up.status_code == 200
          and up.json().get("filename") == "avatar.png",
          f"status {up.status_code}")
    heic = web.post(f"/webface/characters/{cid}/avatar",
                    files={"file": ("photo.heic", b"data", "image/heic")})
    words = heic.text
    check(".heic refused with clear words via webface",
          heic.status_code == 400 and "browsers cannot display" in words,
          f"status {heic.status_code}, words: {words[:200]}")
    big = b"\x89PNG" + b"0" * (16 * 1024 * 1024 + 1)
    over = web.post(f"/webface/characters/{cid}/avatar",
                    files={"file": ("big.png", big, "image/png")})
    check(">16 MiB answers 413 with words via webface",
          over.status_code == 413 and len(over.text) > 10,
          f"status {over.status_code}, words: {over.text[:160]}")
    asset = web.post(f"/webface/characters/{cid}/assets",
                     files={"file": ("my photo.jpg", PNG, "image/jpeg")},
                     data={"kind": "embedded", "name": "my photo"})
    check("asset road lands spaced name", asset.status_code == 200,
          f"status {asset.status_code}, body {asset.text[:160]}")
    # webface-only restart: avatar still served
    pidfile = Path(args.webface_data_dir) / "webface.pid"
    pid = int(pidfile.read_text().strip())
    os.kill(pid, 15)
    time.sleep(1.5)
    env = dict(os.environ, RUNMAL_WEBFACE_HOST=args.webface_url.split("//")[1].split(":")[0],
               RUNMAL_WEBFACE_PORT=args.webface_url.rsplit(":", 1)[1].strip("/"),
               RUNMAL_PYTHON=sys.executable)
    import subprocess
    root = Path(__file__).resolve().parent.parent
    subprocess.run(["bash", str(root / "scripts" / "webface_on_demand.sh"), "start"],
                   cwd=root, env=env, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up_again = wait_up(args.webface_url + "/login")
    web2 = httpx.Client(base_url=args.webface_url, trust_env=False,
                        timeout=120, follow_redirects=True)
    web2.post("/login", data={"username": args.username,
                               "password": args.password})
    got = web2.get(f"/webface/characters/{cid}/avatar")
    check("webface-only restart: avatar still served", up_again
          and got.status_code == 200 and got.content == PNG,
          f"status {got.status_code}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
