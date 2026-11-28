"""W-09 acceptance: Backups + Plugins + Library Search +
Bridge tabs, and the webface-local Appearance settings.

Unit half: the pure W-09 logic - the desktop's own words
renderers (backups / plugins / bridge / library search),
cross-checked byte-for-byte against the desktop logic
modules themselves on the same payloads; the payload
shapes the flows send the engine (install body resolution,
credential body, settings body); the no-road contracts
(no delete road, staging-only restore, download name law +
colocation honesty, uninstall / revoke / settings-delete
confirmation gates); and the appearance store round-trip
(normalisation, CSS overrides, per-account persistence in
the real webface store).
Live half: a REAL served engine (throwaway data dir) +
REAL webface over HTTP: a backup is created through the
webface, listed, downloaded with bytes identical to the
engine's own file, and staged; a full backup is created
and staged by name; a real plugin pack installs, enables,
takes settings through the validated road, disables and
uninstalls (the unconfirmed uninstall is refused first);
the library search finds a lorebook registered in the hub
from its real pack file and agrees with a direct engine
search; a bridge credential is created (token shown once,
absent from every list), works against the engine's real
bridge road, and revokes; appearance set through the
webface survives a webface-only restart and a fresh
login, and resets to the house theme.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from runmal.desktop import (
    backups_logic,
    bridge_logic,
    library_search_logic,
    plugin_logic,
)
from runmal.desktop.client.models import (
    BackupView,
    BridgeCredentialView,
    LibraryHitView,
    PluginFailureReportView,
    PluginView,
)
from runmal.plugins.packs import build_pack
from runmal.webface import w09
from runmal.webface.engine import EngineError
from runmal.webface.store import Store

REPO = Path(__file__).parent.parent

_BACKUP_ROW = {
    "name": "runmal-backup-20261127T101112.db", "size_bytes": 2048,
    "modified_at": "2026-11-27T10:11:12+00:00"}
_FULL_INFO = {
    "name": "runmal-full-backup-20261127T101112.zip",
    "path": "/data/backups/runmal-full-backup-20261127T101112.zip",
    "sha256": "ab" * 32, "size_bytes": 3_500_000,
    "created_at": "2026-11-27T10:11:12+00:00",
    "schema_revision": "0041", "app_version": "1.0",
    "asset_files": 7, "secrets_included": False}
_PLUGIN_ROW = {
    "id": "pack.alpha", "name": "Pack Alpha", "version": "1.0.0",
    "api_version": 1, "state": "enabled",
    "capabilities": ["chat.events"], "permissions": ["chat.read"],
    "events": ["chat.created"], "prompt_hooks": 0, "ui_slots": 1,
    "consecutive_failures": 2,
    "last_error": {"error_type": "Boom", "surface": "s", "hook": "h",
                   "at": "t"}}
_CREDENTIAL_ROW = {
    "id": "cred-1", "name": "Harbour bridge",
    "scopes": ["chat:read:*", "tts:request"],
    "created_at": "2026-11-27T09:00:00+00:00", "revoked_at": None,
    "last_used_at": None}


# ------------------------------------------------------------- unit: words


def test_backup_words_are_the_desktops():
    rows = [_BACKUP_ROW, _FULL_INFO]
    views = [BackupView.from_dict(r) for r in rows]
    assert w09.backups_words(rows) == backups_logic.backups_words(views)
    assert w09.backup_line(_BACKUP_ROW) == backups_logic.backup_line(views[0])
    assert w09.backups_words([]) == backups_logic.backups_words([])
    staged = {"name": "restore-x.db", "path": "/staging/restore-x.db",
              "schema_revision": "0041"}
    assert w09.stage_words(staged) == backups_logic.stage_words(staged)
    report = {"ok": True, "bundle": "b.zip", "staged_db": "/s/db",
              "staged_assets_dir": "/s/assets",
              "schema_revision": "0041", "counts": {"chats": 3},
              "checks": [{"name": "db", "ok": True, "detail": "fine"}],
              "warnings": ["w1"]}
    assert w09.stage_words(report) == backups_logic.stage_words(report)


def test_plugin_words_are_the_desktops():
    view = PluginView.from_dict(_PLUGIN_ROW)
    assert w09.plugin_line(_PLUGIN_ROW) == plugin_logic.plugin_line(view)
    detail = {**_PLUGIN_ROW, "manifest": {
        "description": "Alpha pack plugin.", "author": "Tester"},
        "reserved_permissions": ["admin.all"], "failure_log": [
            {"surface": "chat", "hook": "on_send",
             "error_type": "Boom", "at": "2026-11-27"}]}
    assert w09.plugin_detail_words(detail) == (
        plugin_logic.plugin_detail_words(detail))
    card = {"name": "Pack Alpha", "version": "1.0.0",
            "requires_grant": True, "permissions": [
                {"name": "chat.read", "granted": True,
                 "effect": "read chats"},
                {"name": "admin.all", "reserved": True,
                 "granted": False}], "capabilities": [],
            "notes": ["note one"]}
    assert w09.permission_words(card) == plugin_logic.permission_words(card)
    report = {"plugin_id": "pack.alpha", "state": "enabled",
              "total_recorded": 4, "consecutive_failures": 2,
              "self_disabled": False, "plain": "It broke twice."}
    assert w09.failure_line(report) == plugin_logic.failure_line(
        PluginFailureReportView.from_dict(report))
    qr = {"id": "q1", "name": "Hello", "steps": [{"text": "hi"}],
          "scope": "user", "chat_id": None, "enabled": True}
    from runmal.desktop.client.models import QuickReplyView
    assert w09.quick_reply_line(qr) == plugin_logic.quick_reply_line(
        QuickReplyView.from_dict(qr))


def test_bridge_words_are_the_desktops():
    view = BridgeCredentialView.from_dict(_CREDENTIAL_ROW)
    assert w09.credential_line(_CREDENTIAL_ROW) == (
        bridge_logic.credential_line(view))
    rows = [_CREDENTIAL_ROW,
            {**_CREDENTIAL_ROW, "id": "cred-2", "name": "Old",
             "revoked_at": "2026-11-27T10:00:00+00:00"}]
    views = [BridgeCredentialView.from_dict(r) for r in rows]
    assert w09.bridge_status_words(rows) == (
        bridge_logic.bridge_status_words(views))
    assert w09.bridge_status_words([]) == bridge_logic.bridge_status_words([])
    # INV-023: no words function can carry a token.
    poisoned = {**_CREDENTIAL_ROW, "token": "SECRET-TOKEN"}
    assert "SECRET-TOKEN" not in w09.credential_line(poisoned)
    assert "SECRET-TOKEN" not in w09.bridge_status_words([poisoned])


def test_search_words_are_the_desktops():
    hub_hit = {"id": "e1", "title": "Gate Pack", "kind": "lorebook_pack",
               "matched_by": "both", "occurrences": 3,
               "excerpt": "the gate word", "locator": "/packs/gate.json"}
    view = LibraryHitView.from_hub(hub_hit)
    assert w09.hit_line("hub", hub_hit) == (
        library_search_logic.hit_line("hub", view))
    results = {"hub": [hub_hit], "workspaces": []}
    views = {"hub": [view], "workspaces": []}
    assert w09.results_words(results) == (
        library_search_logic.results_words(views))
    assert w09.results_words({}) == "No library sources were searched."
    hit = w09._hub_hit(hub_hit)
    assert hit["jump"]["tab"] == "lorebooks"


# ------------------------------------------------- unit: payloads + gates


class FakeEngine:
    def __init__(self, replies=None, data_dir=None):
        self.replies = replies or {}
        self.calls: list = []
        self.data_dir = data_dir

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        self.calls.append((method, path, json_body, params))
        key = (method, path)
        if key in self.replies:
            value = self.replies[key]
            if isinstance(value, Exception):
                raise value
            return value
        return {}


def test_install_body_laws():
    pack = {"plugin": {"id": "pack.alpha",
                       "permissions": ["chat.read", "ui.contribute"]}}
    body = w09.install_body({"pack": pack})
    assert body["granted_permissions"] == ["chat.read", "ui.contribute"]
    assert w09.install_body({"pack": pack}, for_preview=True) == {
        "pack": pack}
    with pytest.raises(EngineError) as refused:
        w09.install_body({})
    assert "needs a pack" in refused.value.message
    with pytest.raises(EngineError) as no_update:
        w09.update_plugin(FakeEngine(), "pack.alpha", None)
    assert "requires the new pack" in no_update.value.message


def test_destructive_gates_refuse_first():
    eng = FakeEngine()
    for call in (
            lambda: w09.uninstall_plugin(eng, "pack.alpha", False),
            lambda: w09.delete_plugin_settings(eng, "pack.alpha", False),
            lambda: w09.revoke_credential(eng, "cred-1", False),
            lambda: w09.import_archive(eng, "/x.zip", False)):
        with pytest.raises(EngineError):
            call()
    assert eng.calls == []  # nothing reached the engine ungated


def test_backup_name_law_and_download_honesty(tmp_path):
    eng = FakeEngine(data_dir=tmp_path)
    with pytest.raises(EngineError) as bad:
        w09.backup_download(eng, "../../etc/passwd")
    assert bad.value.status == 400
    with pytest.raises(EngineError) as missing:
        w09.backup_download(eng, _BACKUP_ROW["name"])
    assert missing.value.status == 404
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / _BACKUP_ROW["name"]).write_bytes(b"DBBYTES")
    data, name = w09.backup_download(eng, _BACKUP_ROW["name"])
    assert data == b"DBBYTES" and name == _BACKUP_ROW["name"]
    homeless = FakeEngine(data_dir=None)
    with pytest.raises(EngineError) as no_dir:
        w09.backup_download(homeless, _BACKUP_ROW["name"])
    assert no_dir.value.status == 501
    assert "no honest download road" in no_dir.value.message
    with pytest.raises(EngineError):
        w09.stage_backup(eng, "evil.db", False)
    assert eng.calls == []


def test_credential_create_body():
    eng = FakeEngine(replies={
        ("POST", "/api/v1/bridge/credentials"): {
            "id": "cred-9", "name": "Harbour", "token": "shown-once"}})
    result = w09.create_credential(
        eng, {"label": "Harbour", "scopes": "chat:read:*, tts:request"})
    assert result["token"] == "shown-once"  # raw, exactly once
    method, path, body, _params = eng.calls[-1]
    assert (method, path) == ("POST", "/api/v1/bridge/credentials")
    assert body == {"name": "Harbour",
                    "scopes": ["chat:read:*", "tts:request"]}
    with pytest.raises(EngineError):
        w09.create_credential(eng, {"name": "", "scopes": []})


def test_search_refuses_empty_and_fans_out():
    hub_doc = {"matches": [{"id": "e1", "title": "Gate",
                            "kind": "scenario_pack",
                            "matched_by": "metadata"}]}
    eng = FakeEngine(replies={
        ("GET", "/api/v1/hub/unified-search"): hub_doc,
        ("GET", "/api/v1/workspaces/unified-search"): {"matches": []}})
    with pytest.raises(EngineError):
        w09.search_library(eng, "  ")
    view = w09.search_library(eng, "gate")
    assert set(view["sources"]) == {"hub"}  # no chat named
    assert "faces" not in view["sources"]  # no road, no key
    assert view["sources"]["hub"]["hits"][0]["jump"]["tab"] == "scenarios"
    view2 = w09.search_library(eng, "gate", chat_id="chat-1")
    assert set(view2["sources"]) == {"hub", "workspaces"}


# ------------------------------------------------------- unit: appearance


def test_appearance_normalise_and_css():
    assert w09.normalize_appearance(None) == w09.HOUSE_THEME
    assert w09.normalize_appearance({"variant": "neon"})["variant"] == "dark"
    prefs = w09.normalize_appearance({
        "variant": "light", "ornament": "quiet", "text_scale": 9,
        "reduced_motion": 1})
    assert prefs == {"variant": "light", "ornament": "quiet",
                     "text_scale": 2.0, "reduced_motion": True}
    css = w09.appearance_css(prefs)
    assert "--void-000: #E8EDF1" in css  # the desktop LIGHT_TOKENS
    assert "font-size: 32" in css
    assert "polygon(3px" in css
    assert "transition: none" in css
    assert w09.appearance_css(w09.HOUSE_THEME) == ""
    assert "light theme" in w09.appearance_words({"variant": "light"})


def test_appearance_store_round_trip(tmp_path):
    store = Store(tmp_path)
    user = store.create_user("keeper", "hash")
    assert w09.get_appearance(store, user["id"]) == w09.HOUSE_THEME
    saved = w09.set_appearance(store, user["id"], {
        "variant": "light", "ornament": "ceremonial",
        "text_scale": 1.5, "reduced_motion": True})
    assert w09.get_appearance(store, user["id"]) == saved
    other = store.create_user("other", "hash")
    assert w09.get_appearance(store, other["id"]) == w09.HOUSE_THEME
    reset = w09.reset_appearance(store, user["id"])
    assert reset == w09.HOUSE_THEME
    assert w09.get_appearance(store, user["id"]) == w09.HOUSE_THEME

# ------------------------------------------------------------- live circuit


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(url, timeout_s=60.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2, trust_env=False).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _start_face(env, port, data_dir, engine_port, engine_data):
    proc = subprocess.Popen(
        [sys.executable, "-m", "runmal.webface", "--host", "127.0.0.1",
         "--port", str(port), "--engine-url",
         f"http://127.0.0.1:{engine_port}", "--data-dir", str(data_dir),
         "--engine-data-dir", str(engine_data)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    if not _wait_health(f"http://127.0.0.1:{port}/"):
        raise RuntimeError("webface did not come up")
    return proc


@pytest.fixture()
def pair(tmp_path):
    engine_port, webface_port = _free_port(), _free_port()
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    env["PYTHONPATH"] = str(REPO / "src")
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    engine = subprocess.Popen(
        [sys.executable, "-m", "runmal", "serve", "--host", "127.0.0.1",
         "--port", str(engine_port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    face = None
    try:
        if not _wait_health(f"http://127.0.0.1:{engine_port}/healthz"):
            raise RuntimeError("engine did not come up")
        face = _start_face(env, webface_port, tmp_path / "webface-data",
                           engine_port, tmp_path / "engine-data")
        yield {"engine": f"http://127.0.0.1:{engine_port}",
               "webface": f"http://127.0.0.1:{webface_port}",
               "webface_port": webface_port, "engine_port": engine_port,
               "data_dir": tmp_path / "engine-data",
               "webface_data": tmp_path / "webface-data", "env": env,
               "face": face}
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _headers(data_dir):
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


_PACK_MANIFEST = {
    "id": "w09.alpha", "name": "W09 Alpha", "version": "1.0.0",
    "api_version": 1, "description": "W-09 live-circuit pack plugin.",
    "author": "W-09", "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.created", "message.created"],
    "ui_slots": [{"id": "w09-panel", "slot": "chat.sidebar",
                  "label": "W09", "order": 100,
                  "payload": {"kind": "panel", "route": "w09"}}],
    "settings": {
        "schema": {
            "volume": {"type": "integer", "minimum": 0, "maximum": 11},
            "mode": {"type": "string", "enum": ["calm", "brave"]}},
        "defaults": {"volume": 5, "mode": "calm"}},
    "enabled_by_default": False,
}


def test_live_w09_circuit(pair):
    face, engine = pair["webface"], pair["engine"]
    headers = _headers(pair["data_dir"])
    eng = httpx.Client(base_url=engine, trust_env=False, timeout=300,
                       headers=headers)
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        assert web.get("/webface/backups").status_code == 401
        assert web.get("/webface/plugins").status_code == 401
        assert web.get("/webface/bridge/credentials").status_code == 401
        assert web.get("/webface/appearance").status_code == 401
        for slug in ("/backups", "/plugins", "/bridge", "/appearance"):
            assert web.get(slug).status_code == 303
        reg = web.post("/register", data={"username": "w09live",
                                          "password": "long-enough-1"})
        assert reg.status_code == 303, reg.status_code
        for slug, marker in (("/backups", "b-list"),
                             ("/plugins", "p-list"),
                             ("/bridge", "br-list"),
                             ("/appearance", "a-variant"),
                             ("/library", "ls-q")):
            page = web.get(slug)
            assert page.status_code == 200, slug
            assert marker in page.text and "arrives in slice" not in page.text
        # ---- backups: create -> list -> download -> stage ----
        created = web.post("/webface/backups", json={"full": False})
        assert created.status_code == 200, created.text
        info = created.json()["backup"]
        name = info["name"]
        assert name.startswith("runmal-backup-")
        assert info["secrets_included"] is False
        listed = web.get("/webface/backups").json()
        direct = eng.get("/api/v1/backups").json()
        assert [b["name"] for b in listed["backups"]] == [d["name"] for d in direct]
        assert name in listed["words"]
        download = web.get("/webface/backups/download", params={"name": name})
        engine_file = pair["data_dir"] / "backups" / name
        assert download.status_code == 200
        assert download.content == engine_file.read_bytes()
        staged = web.post("/webface/backups/stage",
                          json={"name": name, "full": False})
        assert staged.status_code == 200, staged.text
        assert "live installation was not touched" in staged.json()["words"]
        # The staged copy is on disk in the engine's staging
        # area. (A second stage in the same second is refused
        # by the engine itself - staging names are per-second
        # and staging never overwrites - so agreement is read
        # from the staged file, not a re-stage.)
        staged_files = list((pair["data_dir"] / "staging").glob("restore-*.db"))
        assert staged_files and staged_files[0].stat().st_size == info["size_bytes"]
        full = web.post("/webface/backups", json={"full": True})
        assert full.status_code == 200, full.text
        full_name = full.json()["backup"]["name"]
        assert full_name.startswith("runmal-full-backup-")
        assert full.json()["backup"]["asset_files"] is not None
        staged_full = web.post("/webface/backups/stage",
                               json={"name": full_name, "full": True})
        assert staged_full.status_code == 200, staged_full.text
        assert "Full backup staged and verified" in staged_full.json()["words"]
        bad = web.get("/webface/backups/download",
                      params={"name": "../runmal.db"})
        assert bad.status_code == 400
        # ---- plugins: install -> enable -> settings -> disable -> uninstall
        overview = web.get("/webface/plugins").json()
        assert overview["plugins"] == []
        pack = build_pack(_PACK_MANIFEST)
        preview = web.post("/webface/plugins/install/preview",
                           json={"pack": pack})
        assert preview.status_code == 200, preview.text
        assert "Permissions for" in preview.json()["words"]
        assert eng.get("/api/v1/plugins").json() == []  # preview wrote nothing
        installed = web.post("/webface/plugins/install", json={"pack": pack})
        assert installed.status_code == 200, installed.text
        direct_plugins = eng.get("/api/v1/plugins").json()
        assert [p["id"] for p in direct_plugins] == ["w09.alpha"]
        overview = web.get("/webface/plugins").json()
        assert overview["plugins"][0]["line"].startswith("W09 Alpha")
        detail = web.get("/webface/plugins/w09.alpha").json()
        direct_detail = eng.get("/api/v1/plugins/w09.alpha").json()
        assert detail["detail"]["state"] == direct_detail["state"]
        assert detail["settings_form"]["has_settings"] is True
        field_names = [f["name"] for f in detail["settings_form"]["fields"]]
        assert field_names == ["volume", "mode"]
        saved = web.post("/webface/plugins/w09.alpha/settings",
                         json={"values": {"volume": 9}})
        assert saved.status_code == 200, saved.text
        direct_settings = eng.get("/api/v1/plugins/w09.alpha/settings").json()
        assert direct_settings["values"]["volume"] == 9
        refused = web.post("/webface/plugins/w09.alpha/settings",
                           json={"values": {"volume": 99}})
        assert refused.status_code >= 400  # the engine's own refusal
        assert eng.get("/api/v1/plugins/w09.alpha/settings").json()["values"]["volume"] == 9
        enabled = web.post("/webface/plugins/w09.alpha/enable", json={})
        assert enabled.status_code == 200, enabled.text
        assert eng.get("/api/v1/plugins/w09.alpha").json()["state"] == "enabled"
        disabled = web.post("/webface/plugins/w09.alpha/disable", json={})
        assert disabled.status_code == 200, disabled.text
        assert eng.get("/api/v1/plugins/w09.alpha").json()["state"] != "enabled"
        ungated = web.post("/webface/plugins/w09.alpha/uninstall",
                           json={"confirm": False})
        assert ungated.status_code == 422
        assert [p["id"] for p in eng.get("/api/v1/plugins").json()] == ["w09.alpha"]
        gone = web.post("/webface/plugins/w09.alpha/uninstall",
                        json={"confirm": True})
        assert gone.status_code == 200, gone.text
        assert eng.get("/api/v1/plugins").json() == []
        # ---- library search: a known lorebook, via its real pack ----
        book = web.post("/webface/lorebooks", json={"values": {
            "name": "W09 Gate World", "description": "W-09 lore.",
            "scan_depth": "4", "token_budget": "",
            "scan_mode": "depth", "scan_external_context": False}})
        assert book.status_code == 200, book.text
        book_id = book.json()["id"]
        entry = web.post(f"/webface/lorebooks/{book_id}/entries",
                         json={"values": {
            "name": "Gate fact",
            "content": "The w09gate word keeps the harbour.",
            "keys": ["w09gate"], "secondary_keys": [],
            "selective_logic": "and_any", "inclusion_group": "",
            "group_weight": "100", "probability": "100",
            "priority": "100", "position": "before_char",
            "depth": "", "role": "system", "enabled": True,
            "constant": False, "vectorised": False,
            "case_sensitive": False, "whole_word": True,
            "sticky_prompts": "0", "cooldown_prompts": "0",
            "delay_prompts": "0"}})
        assert entry.status_code == 200, entry.text
        pack_doc = eng.get(f"/api/v1/lorebooks/{book_id}/pack").json()
        pack_file = pair["data_dir"] / "w09-gate-lorebook-pack.json"
        pack_file.write_text(json.dumps(pack_doc))
        registered = eng.post("/api/v1/hub/entries", json={
            "kind": "lorebook_pack", "title": "W09gate Lorebook",
            "locator": str(pack_file),
            "note": "W-09 live circuit"})
        assert registered.status_code == 201, registered.text
        entry_id = registered.json()["entry"]["id"]
        found = web.get("/webface/library-search",
                        params={"q": "w09gate"})
        assert found.status_code == 200, found.text
        hits = found.json()["sources"]["hub"]["hits"]
        direct_doc = eng.get("/api/v1/hub/unified-search",
                             params={"q": "w09gate"}).json()
        assert [h["id"] for h in hits] == [m["id"] for m in direct_doc["matches"]]
        mine = next(h for h in hits if h["id"] == entry_id)
        theirs = next(m for m in direct_doc["matches"] if m["id"] == entry_id)
        assert mine["matched_by"] == theirs["matched_by"]
        assert mine["jump"]["tab"] == "lorebooks"
        empty = web.get("/webface/library-search", params={"q": " "})
        assert empty.status_code == 422
        # ---- bridge: create (token once) -> whoami -> revoke ----
        created_cred = web.post("/webface/bridge/credentials", json={
            "name": "W09 circuit bridge",
            "scopes": ["chat:read:*", "tts:request"]})
        assert created_cred.status_code == 200, created_cred.text
        token = created_cred.json()["token"]
        cred_id = created_cred.json()["id"]
        listed_creds = web.get("/webface/bridge/credentials")
        assert token not in listed_creds.text  # INV-023: never listed
        direct_creds = eng.get("/api/v1/bridge/credentials").json()
        assert [c["id"] for c in direct_creds] == [cred_id]
        whoami = httpx.get(engine + "/api/v1/bridge/whoami",
                           headers={"Authorization": f"Bearer {token}"},
                           trust_env=False, timeout=30)
        assert whoami.status_code == 200, whoami.text
        assert whoami.json()["name"] == "W09 circuit bridge"
        ungated_revoke = web.post(
            f"/webface/bridge/credentials/{cred_id}/revoke",
            json={"confirm": False})
        assert ungated_revoke.status_code == 422
        revoked = web.post(
            f"/webface/bridge/credentials/{cred_id}/revoke",
            json={"confirm": True})
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["credential"]["state"] == "revoked"
        dead = httpx.get(engine + "/api/v1/bridge/whoami",
                         headers={"Authorization": f"Bearer {token}"},
                         trust_env=False, timeout=30)
        assert dead.status_code == 401
        # ---- appearance: set -> restart webface only -> still applied
        set_view = web.post("/webface/appearance", json={
            "variant": "light", "ornament": "quiet",
            "text_scale": 1.5, "reduced_motion": True})
        assert set_view.status_code == 200, set_view.text
        assert set_view.json()["appearance"]["variant"] == "light"
        chat_page = web.get("/chat")
        assert "--void-000: #E8EDF1" in chat_page.text
        pair["face"].terminate()
        pair["face"].wait(timeout=10)
        pair["face"] = _start_face(pair["env"], pair["webface_port"],
                                   pair["webface_data"],
                                   pair["engine_port"], pair["data_dir"])
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web2:
        login = web2.post("/login", data={"username": "w09live",
                                          "password": "long-enough-1"})
        assert login.status_code == 303, login.status_code
        prefs = web2.get("/webface/appearance").json()["appearance"]
        assert prefs == {"variant": "light", "ornament": "quiet",
                         "text_scale": 1.5, "reduced_motion": True}
        assert "--void-000: #E8EDF1" in web2.get("/chat").text
        reset = web2.post("/webface/appearance/reset", json={})
        assert reset.json()["appearance"] == w09.HOUSE_THEME
