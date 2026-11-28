#!/usr/bin/env python3
"""W-09 launch proof: real HTTP against the running pair.

Login as the W-01 proof account -> every W-09 tab graduated
(Backups / Plugins / Bridge / Appearance, plus the Library
search section) and NO feature tab pending anywhere ->
Backups: a database backup is created through the webface
on the REAL data dir, listed with agreement against the
direct engine read, downloaded with bytes identical to
the engine's own file, and restore-STAGED (staging only -
this proof restores NOTHING; the live database is never
touched); a full backup is created and staged by name;
both backup files are LEFT in place, named by the engine
-> Plugins: the overview agrees with the direct reads; a
real pack (built by the engine's own pack builder) is
previewed (writing nothing), installed, enabled, given a
setting through the validated road, disabled, and
uninstalled - the registry is left exactly as found ->
Library search: the W-05 proof lorebook's real pack is
exported, written under the webface data dir, and
registered in the hub; the search finds it and agrees
with the direct unified search -> Bridge: a credential
is created (token shown once, absent from every list),
its token answers the engine's real bridge whoami, and
it is revoked (the revoked row is the left artifact) ->
Appearance: the as-found prefs are recorded, a light /
125% appearance is set and seen in the served pages, the
WEBFACE ONLY is restarted, a fresh login still carries
the appearance, and the proof ends by resetting to the
house theme and restoring the account's appearance
exactly as found. Every assertion prints PASS/FAIL; the
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

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from runmal.plugins.packs import build_pack  # noqa: E402
from runmal.webface import w09  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []

_PACK_MANIFEST = {
    "id": "w09.proof", "name": "W09 Proof Pack", "version": "1.0.0",
    "api_version": 1, "description": "W-09 live proof pack plugin.",
    "author": "W-09", "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.created", "message.created"],
    "ui_slots": [{"id": "w09-proof-panel", "slot": "chat.sidebar",
                  "label": "W09", "order": 100,
                  "payload": {"kind": "panel", "route": "w09"}}],
    "settings": {
        "schema": {
            "volume": {"type": "integer", "minimum": 0, "maximum": 11}},
        "defaults": {"volume": 5}},
    "enabled_by_default": False,
}


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
    parser = argparse.ArgumentParser(description="W-09 webface proof")
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
    for slug, marker in (("/backups", "b-list"), ("/plugins", "p-list"),
                         ("/bridge", "br-list"),
                         ("/appearance", "a-variant"),
                         ("/library", "ls-q")):
        page = web.get(slug)
        check(f"{slug} graduated", page.status_code == 200
              and marker in page.text and "arrives in slice" not in page.text)
    check("no feature tab pending anywhere",
          all("arrives in slice" not in web.get(s).text
              for s in ("/backups", "/plugins", "/bridge", "/appearance")))
    # ---- appearance: record as-found first ----
    as_found = web.get("/webface/appearance").json()["appearance"]
    check("appearance as found recorded", isinstance(as_found, dict),
          json.dumps(as_found))
    # ---- backups on the REAL data dir ----
    created = web.post("/webface/backups", json={"full": False})
    check("database backup created through the webface",
          created.status_code == 200, created.text[:140])
    info = created.json().get("backup", {})
    name = info.get("name", "")
    check("backup named by the engine, no secrets in it",
          name.startswith("runmal-backup-")
          and info.get("secrets_included") is False, name)
    listed = web.get("/webface/backups").json()
    direct = eng.get("/api/v1/backups").json()
    check("backup list agrees with the direct engine read",
          [b["name"] for b in listed.get("backups", [])]
          == [d["name"] for d in direct])
    download = web.get("/webface/backups/download", params={"name": name})
    engine_file = Path(args.engine_data_dir) / "backups" / name
    check("download bytes identical to the engine's own file",
          download.status_code == 200 and engine_file.is_file()
          and download.content == engine_file.read_bytes(),
          f"{len(download.content)} bytes; LEFT in place: {engine_file}")
    staged = web.post("/webface/backups/stage",
                      json={"name": name, "full": False})
    check("restore staged (never applied)",
          staged.status_code == 200
          and "live installation was not touched" in staged.json().get("words", ""),
          staged.text[:140])
    full = web.post("/webface/backups", json={"full": True})
    full_name = full.json().get("backup", {}).get("name", "")
    check("full backup created", full.status_code == 200
          and full_name.startswith("runmal-full-backup-"), full_name)
    staged_full = web.post("/webface/backups/stage",
                           json={"name": full_name, "full": True})
    check("full backup staged and verified",
          staged_full.status_code == 200
          and "Full backup staged and verified" in staged_full.json().get("words", ""))
    check("no delete road is offered or hidden",
          "no road that deletes a backup" in listed.get("notes", {}).get("delete", ""))
    # ---- plugins: preview -> install -> enable -> settings -> disable -> uninstall
    before = eng.get("/api/v1/plugins").json()
    overview = web.get("/webface/plugins").json()
    check("plugin overview agrees with the direct read",
          [p["id"] for p in overview.get("plugins", [])]
          == [p["id"] for p in before])
    pack = build_pack(_PACK_MANIFEST)
    preview = web.post("/webface/plugins/install/preview", json={"pack": pack})
    check("install preview renders the permission card",
          preview.status_code == 200
          and "Permissions for" in preview.json().get("words", ""))
    check("preview wrote nothing",
          eng.get("/api/v1/plugins").json() == before)
    installed = web.post("/webface/plugins/install", json={"pack": pack})
    check("pack installed", installed.status_code == 200, installed.text[:140])
    enabled = web.post("/webface/plugins/w09.proof/enable", json={})
    check("plugin enabled", enabled.status_code == 200
          and eng.get("/api/v1/plugins/w09.proof").json().get("state") == "enabled")
    saved = web.post("/webface/plugins/w09.proof/settings",
                     json={"values": {"volume": 7}})
    def _volume():
        doc = eng.get("/api/v1/plugins/w09.proof/settings").json()
        return doc.get("values", {}).get("volume")
    check("settings saved through the validated road",
          saved.status_code == 200 and _volume() == 7)
    refused = web.post("/webface/plugins/w09.proof/settings",
                       json={"values": {"volume": 99}})
    check("an out-of-range setting is refused by the engine",
          refused.status_code >= 400 and _volume() == 7)
    web.post("/webface/plugins/w09.proof/disable", json={})
    ungated = web.post("/webface/plugins/w09.proof/uninstall",
                       json={"confirm": False})
    check("unconfirmed uninstall refused", ungated.status_code == 422)
    gone = web.post("/webface/plugins/w09.proof/uninstall",
                    json={"confirm": True})
    check("plugin uninstalled; registry left as found",
          gone.status_code == 200
          and eng.get("/api/v1/plugins").json() == before)
    # ---- library search: the W-05 proof lorebook, via its real pack ----
    books = eng.get("/api/v1/lorebooks").json()
    proof_book = next((b for b in books if b.get("name") == "W-05 Proof Lore"), None)
    check("W-05 proof lorebook exists", bool(proof_book))
    pack_doc = eng.get(f"/api/v1/lorebooks/{proof_book['id']}/pack").json()
    pack_file = Path(args.webface_data_dir) / "w09-proof-lorebook-pack.json"
    pack_file.write_text(json.dumps(pack_doc))
    existing = eng.get("/api/v1/hub").json().get("entries", [])
    entry = next((e for e in existing
                  if e.get("locator") == str(pack_file)), None)
    if entry is None:
        registered = eng.post("/api/v1/hub/entries", json={
            "kind": "lorebook_pack", "title": "W09 Proof Lorebook",
            "locator": str(pack_file),
            "note": "W-09 live proof: the W-05 proof lorebook's pack"})
        check("hub entry registered for the proof lorebook pack",
              registered.status_code == 201, registered.text[:140])
        entry = registered.json().get("entry", {})
    entry_id = entry.get("id", "")
    found = web.get("/webface/library-search", params={"q": "W09 Proof"})
    hits = found.json().get("sources", {}).get("hub", {}).get("hits", [])
    direct_doc = eng.get("/api/v1/hub/unified-search",
                         params={"q": "W09 Proof"}).json()
    check("library search finds the known lorebook pack",
          any(h.get("id") == entry_id for h in hits), f"entry {entry_id}")
    check("search hits agree with the direct unified search",
          [h.get("id") for h in hits]
          == [m.get("id") for m in direct_doc.get("matches", [])])
    mine = next((h for h in hits if h.get("id") == entry_id), {})
    check("the hit jumps to the Lorebooks tab",
          mine.get("jump", {}).get("tab") == "lorebooks")
    check("faces honestly not a searched source",
          "faces" not in found.json().get("sources", {}))
    # ---- bridge: create -> whoami -> revoke ----
    created_cred = web.post("/webface/bridge/credentials", json={
        "name": "W09 proof bridge", "scopes": ["chat:read:*"]})
    check("bridge credential created", created_cred.status_code == 200,
          created_cred.text[:140])
    cred_token = created_cred.json().get("token", "")
    cred_id = created_cred.json().get("id", "")
    check("token shown exactly once, in the creation response",
          bool(cred_token))
    listed_creds = web.get("/webface/bridge/credentials")
    check("token absent from the credential list (INV-023)",
          bool(cred_token) and cred_token not in listed_creds.text)
    whoami = httpx.get(args.engine_url + "/api/v1/bridge/whoami",
                       headers={"Authorization": f"Bearer {cred_token}"},
                       trust_env=False, timeout=30)
    check("the token answers the engine's real bridge whoami",
          whoami.status_code == 200
          and whoami.json().get("name") == "W09 proof bridge")
    ungated_revoke = web.post(
        f"/webface/bridge/credentials/{cred_id}/revoke",
        json={"confirm": False})
    check("unconfirmed revoke refused", ungated_revoke.status_code == 422)
    revoked = web.post(f"/webface/bridge/credentials/{cred_id}/revoke",
                       json={"confirm": True})
    check("credential revoked (row left as the proof artifact)",
          revoked.status_code == 200
          and revoked.json().get("credential", {}).get("state") == "revoked")
    dead = httpx.get(args.engine_url + "/api/v1/bridge/whoami",
                     headers={"Authorization": f"Bearer {cred_token}"},
                     trust_env=False, timeout=30)
    check("the revoked token no longer answers", dead.status_code == 401)
    # ---- appearance: set -> webface-only restart -> still applied -> restore
    set_view = web.post("/webface/appearance", json={
        "variant": "light", "ornament": "standard",
        "text_scale": 1.25, "reduced_motion": False})
    check("appearance set (light, 125%)",
          set_view.status_code == 200
          and set_view.json().get("appearance", {}).get("variant") == "light")
    check("the light theme is in the served pages",
          "--void-000: #E8EDF1" in web.get("/chat").text)
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
    prefs = web2.get("/webface/appearance").json().get("appearance", {})
    check("appearance survives the restart + a fresh login",
          prefs.get("variant") == "light"
          and prefs.get("text_scale") == 1.25, json.dumps(prefs))
    check("tabs still graduated after the restart",
          "b-list" in web2.get("/backups").text
          and "br-list" in web2.get("/bridge").text)
    web2.post("/webface/appearance/reset", json={})
    restored = web2.post("/webface/appearance", json=as_found)
    check("appearance restored exactly as found",
          restored.status_code == 200
          and restored.json().get("appearance") == w09.normalize_appearance(as_found),
          f"as found: {json.dumps(as_found)}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
