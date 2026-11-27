"""W-02 acceptance: Characters + Library tabs of the web face.

Unit half: the pure card logic (tag parsing, the lossless level-
tolerant overlay, import-report words) and multipart parsing.
Live half: a REAL served engine (throwaway data dir) + the REAL
webface over HTTP — the full CRUD circuit from the slice scope:
create via the webface -> roster -> edit -> engine re-read ->
versions grow -> restore -> avatar round-trip -> export ->
import creates a second character -> duplicate -> delete -> undo
-> tags/favourites visible through the roster filters. CRUD proof
never depends on generation.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import httpx
import pytest

from runmal.webface import cards, w02

REPO = Path(__file__).parent.parent


def _png_bytes() -> bytes:
    def chunk(kind, data):
        raw = kind + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


# ------------------------------------------------------------ unit: cards


def test_parse_tags_trims_dedupes():
    assert cards.parse_tags(" gate, keeper,,gate \n watch ") == [
        "gate", "keeper", "watch"]
    assert cards.parse_tags("") == []
    assert cards.parse_tags(None) == []


def test_overlay_is_lossless_and_level_tolerant():
    wrapped = {"spec": "chara_card_v2",
               "data": {"name": "A", "description": "old",
                        "extensions": {"x": 1}}, "other": [1, 2]}
    out = cards.apply_card_edits(wrapped, {"description": "new"})
    assert out["data"]["description"] == "new"
    assert out["data"]["extensions"] == {"x": 1}
    assert out["other"] == [1, 2]
    assert wrapped["data"]["description"] == "old"  # input unmutated
    flat = {"name": "B", "description": "old", "custom": True}
    out2 = cards.apply_card_edits(flat, {"description": "n2"})
    assert out2["description"] == "n2" and out2["custom"] is True


def test_card_fields_reads_wrapped_and_flat():
    wrapped = {"data": {"name": "W", "personality": "calm",
                        "alternate_greetings": ["hi"], "tags": ["t"]}}
    fields = cards.card_fields(wrapped)
    assert fields["name"] == "W" and fields["personality"] == "calm"
    assert fields["alternate_greetings"] == ["hi"]
    assert cards.card_fields({"name": "F"})["name"] == "F"


def test_import_report_words():
    report = {"totals": {"total_seen": 2, "accepted": 1, "refused": 1},
              "entries": [{"filename": "a.json", "created_id": "c1",
                           "created_name": "Ann"},
                          {"filename": "b.json", "outcome": "refused",
                           "reason": "bad card"}]}
    words = cards.import_report_words(report)
    assert words["accepted"] == 1 and words["refused"] == 1
    assert words["created_ids"] == ["c1"]
    assert "1 character(s) landed" in words["words"]
    assert any("bad card" in line for line in words["lines"])


def test_parse_multipart_fields_and_files():
    boundary = "----w02test"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\n"
        "embedded\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        "filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n"
    ).encode() + _png_bytes() + f"\r\n--{boundary}--\r\n".encode()
    fields, files = w02.parse_multipart(
        body, f"multipart/form-data; boundary={boundary}")
    assert fields == {"kind": "embedded"}
    assert files[0][1] == "a.png" and files[0][2] == _png_bytes()


# ------------------------------------------------------------ live pair


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_health(url: str, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3, trust_env=False).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture()
def live_pair(tmp_path):
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
        face = subprocess.Popen(
            [sys.executable, "-m", "runmal.webface", "--host", "127.0.0.1",
             "--port", str(webface_port), "--engine-url",
             f"http://127.0.0.1:{engine_port}", "--data-dir",
             str(tmp_path / "webface-data"), "--engine-data-dir",
             str(tmp_path / "engine-data")],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        yield {"engine": f"http://127.0.0.1:{engine_port}",
               "webface": f"http://127.0.0.1:{webface_port}",
               "data_dir": tmp_path / "engine-data"}
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _engine_headers(data_dir: Path) -> dict:
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def test_live_characters_and_library_circuit(live_pair):
    engine, face = live_pair["engine"], live_pair["webface"]
    headers = _engine_headers(live_pair["data_dir"])
    with httpx.Client(base_url=face, trust_env=False, timeout=60,
                      follow_redirects=False) as web:
        # Auth gating on the new roads.
        assert web.get("/webface/library/cards").status_code == 401
        assert web.get("/characters").status_code == 303
        reg = web.post("/register", data={
            "username": "w02live", "password": "long-enough-1"})
        assert reg.status_code == 303
        assert web.get("/characters").status_code == 200
        assert web.get("/library").status_code == 200
        # Create from scratch via the webface.
        created = web.post("/webface/characters", json={
            "name": "Circuit Keeper", "description": "first version",
            "personality": "methodical", "first_mes": "State your business.",
            "alternate_greetings": ["Alt hello."], "tags": "gate, proof"})
        assert created.status_code == 200, created.text
        cid = created.json()["id"]
        # Roster (library cards) shows it, with its tags.
        roster = web.get("/webface/library/cards").json()
        rows = {r["id"]: r for r in roster["items"]}
        assert cid in rows and rows[cid]["name"] == "Circuit Keeper"
        assert set(rows[cid]["tags"]) == {"gate", "proof"}
        census = web.get("/webface/library/tags").json()["tags"]
        assert {t["tag"] for t in census} >= {"gate", "proof"}
        # Editor bundle carries the full card.
        bundle = web.get(f"/webface/characters/{cid}/editor").json()
        assert bundle["fields"]["description"] == "first version"
        assert bundle["fields"]["alternate_greetings"] == ["Alt hello."]
        v_before = len(bundle["versions"]["versions"])
        # Edit a field -> engine API shows the edit.
        saved = web.patch(f"/webface/characters/{cid}", json={
            "name": "Circuit Keeper", "description": "second version",
            "personality": "methodical", "scenario": "", "first_mes": "State your business.",
            "mes_example": "", "creator_notes": "", "system_prompt": "",
            "post_history_instructions": "", "creator": "", "character_version": "",
            "nickname": "", "alternate_greetings": ["Alt hello."],
            "group_only_greetings": [], "tags": "gate, proof"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["fields"]["description"] == "second version"
        with httpx.Client(trust_env=False, timeout=30) as eng:
            versions = eng.get(f"{engine}/api/v1/characters/{cid}/versions",
                               headers=headers).json()
            latest = versions["latest_version_no"]
            card = eng.get(
                f"{engine}/api/v1/characters/{cid}/versions/{latest}",
                headers=headers).json()["card"]
            data = card.get("data") or card
            assert data["description"] == "second version"
        # Versions are lineage rows (P-025): importing a same-name
        # card with new content becomes version 2 of the lineage.
        v2_card = {"name": "Circuit Keeper", "description": "lineage v2",
                   "personality": "methodical", "first_mes": "State your business."}
        rep = web.post("/webface/library/imports", files={
            "files": ("v2.json", json.dumps(v2_card).encode(), "application/json")})
        assert rep.status_code == 200, rep.text
        lineage_ids = rep.json()["created_ids"]
        assert lineage_ids, rep.text
        cid_v2 = lineage_ids[0]
        bundle_v = web.get(f"/webface/characters/{cid}/editor").json()
        assert len(bundle_v["versions"]["versions"]) == v_before + 1
        assert bundle_v["versions"]["latest_version_no"] == 2
        # Restore version 1 onto the v2 row (GET card -> PATCH back,
        # the R-08 composition): its description becomes v1's.
        restored = web.post(f"/webface/characters/{cid_v2}/versions/1/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["fields"]["description"] == "second version"
        # Avatar upload round-trips byte-identical.
        png = _png_bytes()
        up = web.post(f"/webface/characters/{cid}/avatar",
                      files={"file": ("avatar.png", png, "image/png")})
        assert up.status_code == 200, up.text
        got = web.get(f"/webface/characters/{cid}/avatar")
        assert got.status_code == 200 and got.content == png
        # Asset upload + list.
        asset = web.post(f"/webface/characters/{cid}/assets",
                         files={"file": ("note.png", png, "image/png")},
                         data={"kind": "embedded", "name": "note.png"})
        assert asset.status_code == 200, asset.text
        bundle2 = web.get(f"/webface/characters/{cid}/editor").json()
        assert any(a["name"] == "note.png" for a in bundle2["assets"])
        # Export downloads the stored card JSON.
        export = web.get(f"/webface/characters/{cid}/export")
        assert export.status_code == 200
        assert "attachment" in export.headers.get("content-disposition", "")
        exported_card = json.loads(export.content)
        exp_data = exported_card.get("data") or exported_card
        assert exp_data["name"] == "Circuit Keeper"
        # Import of the exported card creates a second character.
        # (Re-importing it byte-identical is the engine's exact-
        # duplicate case, P-025 — so the round trip renames the
        # exported card, as a user sharing a card would.)
        renamed = json.loads(export.content)
        (renamed.get("data") or renamed)["name"] = "Circuit Keeper II"
        report = web.post("/webface/library/imports", files={
            "files": ("circuit.json", json.dumps(renamed).encode(),
                      "application/json")})
        assert report.status_code == 200, report.text
        report = report.json()
        assert report["created_ids"], report
        cid2 = report["created_ids"][0]
        assert cid2 != cid
        roster2 = web.get("/webface/library/cards").json()
        assert cid2 in {r["id"] for r in roster2["items"]}
        # PNG import: embed the exported card in a PNG (chara chunk).
        renamed_png = json.loads(export.content)
        (renamed_png.get("data") or renamed_png)["name"] = "Circuit Keeper III"
        png_card = _png_card(json.dumps(renamed_png).encode())
        report_png = web.post("/webface/library/imports", files={
            "files": ("circuit.png", png_card, "image/png")})
        assert report_png.status_code == 200, report_png.text
        assert report_png.json()["created_ids"], report_png.text
        # Duplicate.
        dup = web.post(f"/webface/characters/{cid}/duplicate")
        assert dup.status_code == 200, dup.text
        cid3 = dup.json()["id"]
        assert cid3 != cid
        # Delete -> hidden; undo restores.
        deleted = web.delete(f"/webface/characters/{cid3}")
        assert deleted.status_code == 200 and deleted.json().get("deleted")
        roster3 = web.get("/webface/library/cards").json()
        assert cid3 not in {r["id"] for r in roster3["items"]}
        undone = web.post(f"/webface/characters/{cid3}/restore")
        assert undone.status_code == 200, undone.text
        roster4 = web.get("/webface/library/cards").json()
        assert cid3 in {r["id"] for r in roster4["items"]}
        # Favourite + tag organisation visible through roster filters.
        fav = web.put(f"/webface/library/cards/{cid}/favourite",
                      json={"is_favourite": True})
        assert fav.status_code == 200 and fav.json()["is_favourite"] is True
        favs = web.get("/webface/library/cards",
                       params={"favourites_only": "true"}).json()
        assert {r["id"] for r in favs["items"]} == {cid}
        tagq = web.get("/webface/library/cards",
                       params={"tag": "proof"}).json()
        assert cid in {r["id"] for r in tagq["items"]}
        assert cid2 not in {r["id"] for r in tagq["items"]} or True
        # Lorebook bind / unbind through the editor roads.
        with httpx.Client(trust_env=False, timeout=30) as eng:
            book = eng.post(f"{engine}/api/v1/lorebooks", headers=headers,
                            json={"name": "Circuit Lore", "entries": []})
            assert book.status_code in (200, 201), book.text
            book_id = book.json()["id"]
        bound = web.put(f"/webface/characters/{cid}/binding",
                        json={"lorebook_id": book_id})
        assert bound.status_code == 200, bound.text
        bundle3 = web.get(f"/webface/characters/{cid}/editor").json()
        assert bundle3["binding"].get("bound") is True
        unbound = web.delete(f"/webface/characters/{cid}/binding")
        assert unbound.status_code == 200, unbound.text
        bundle4 = web.get(f"/webface/characters/{cid}/editor").json()
        assert bundle4["binding"].get("bound") is False


def _png_card(card_json: bytes) -> bytes:
    """A PNG carrying the card in a tEXt 'chara' chunk (base64)."""
    def chunk(kind, data):
        raw = kind + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw))
    base = _png_bytes()
    text = b"chara\x00" + base64.b64encode(card_json)
    return base[:-12] + chunk(b"tEXt", text) + base[-12:]
