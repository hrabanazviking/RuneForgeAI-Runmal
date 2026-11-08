"""P-129 — Watcher registration control parity (Part VIII, DERIVED).

Pins: WatchStore.set_recursive (the recursive flag's first
handle: round-trip, preservation of every other field and
of ALL ingested records, unknown watch = None and no
write), scan depth following the flag at the service level
with the dedupe memory intact across flips, the harm the
handle avoids (delete + re-register re-ingests unchanged
files as duplicates), the HTTP roads (PATCH recursive
alone / enabled alone / both, empty body 422, owner-scoped
404s; scan depth following the PATCH end to end), the
DELETE road's custody reporting ({"deleted": true, "id",
"ingested_records_removed": n} — the count truthful, the
registration and its records gone, the ingested
attachments and their descriptions untouched under P-120
custody, honest re-registration afterwards), and the
migration head staying 0041 (NO migration). No network,
no daemon: fakes/fixtures only.
"""

from __future__ import annotations

import itertools
import struct
import zlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.imaging import sniff_image
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.vision import watcher as w

NOW = "2026-11-08T16:00:00+00:00"


def make_png_bytes(width=6, height=4, color=(200, 30, 30)) -> bytes:
    def chunk(ctype, data):
        raw = ctype + data
        return struct.pack(">I", len(data)) + raw + struct.pack(
            ">I", zlib.crc32(raw) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


PNG = make_png_bytes()
PNG2 = make_png_bytes(color=(30, 200, 30))
PNG3 = make_png_bytes(color=(30, 30, 200))


def _store(tmp_path):
    return w.WatchStore(tmp_path / "data")


def _register(store, folder, chat_id="c1", owner="u1", **kw):
    return w.register_watch(
        store, owner_id=owner, chat_id=chat_id,
        path=str(folder), now=NOW, **kw)


def _ingested(store, watch_id, attachment_id, path="/inbox/a.png",
              sha="ab" * 32):
    return store.record_ingested(w.IngestedRecord(
        watch_id=watch_id, source_path=path, sha256=sha,
        size=len(PNG), attachment_id=attachment_id,
        ingested_at=NOW))


def _fake_attacher():
    counter = itertools.count(1)
    calls = []

    def attach(data, *, chat_id, owner_id, filename):
        info = sniff_image(data)
        if info.format == "unknown" or info.error:
            raise ValueError("bytes do not sniff as a supported image")
        record = SimpleNamespace(
            id=f"att-{next(counter)}", chat_id=chat_id,
            owner_id=owner_id, filename=filename)
        calls.append(record)
        return record

    attach.calls = calls
    return attach


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, **kw):
    return client.post("/api/v1/chats", json=kw).json()["id"]


def _http_watch(client, chat_id, folder, recursive=False):
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": str(folder),
              "recursive": recursive})
    assert res.status_code == 201, res.text
    return res.json()


# -------------------------------------------- store: set_recursive


def test_set_recursive_round_trip_preserves_everything(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "inbox", recursive=False)
    _ingested(store, watch.id, "att-1")
    updated = store.set_recursive(watch.id, True)
    assert updated is not None
    assert updated.recursive is True
    # every other field preserved exactly
    assert updated.id == watch.id
    assert updated.owner_id == watch.owner_id
    assert updated.chat_id == watch.chat_id
    assert updated.path == watch.path
    assert updated.enabled is True
    assert updated.created_at == watch.created_at
    # the dedupe memory survives the flip — the whole point
    fresh = _store(tmp_path)
    assert [r.attachment_id for r in fresh.list_ingested(watch.id)] == ["att-1"]
    assert fresh.get_watch(watch.id).recursive is True
    assert fresh.set_recursive(watch.id, False).recursive is False


def test_set_recursive_unknown_returns_none_and_writes_nothing(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "inbox")
    _ingested(store, watch.id, "att-1")
    before = store.index_path.read_bytes()
    assert store.set_recursive("nope", True) is None
    assert store.index_path.read_bytes() == before


def test_scan_depth_follows_flag_and_dedupe_survives_flips(tmp_path):
    folder = tmp_path / "inbox"
    (folder / "sub").mkdir(parents=True)
    (folder / "top.png").write_bytes(PNG)
    (folder / "sub" / "deep.png").write_bytes(PNG2)
    store = _store(tmp_path)
    watch = _register(store, folder, recursive=False)
    attacher = _fake_attacher()
    report = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert len(report.ingested) == 1  # top only
    # flip on: the deep file lands, the top file is NOT re-ingested
    watch = store.set_recursive(watch.id, True)
    report = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert len(report.ingested) == 1
    assert [s["reason"] for s in report.skipped] == ["already_ingested"]
    assert len(attacher.calls) == 2
    # flip back off: a new subfolder file is out of reach again,
    # a new top-level file still lands
    watch = store.set_recursive(watch.id, False)
    (folder / "sub" / "deep2.png").write_bytes(PNG3)
    (folder / "top2.png").write_bytes(PNG3)
    report = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert len(report.ingested) == 1
    assert len(attacher.calls) == 3


def test_delete_reregister_reingests__the_harm_the_handle_avoids(tmp_path):
    # Evidence for the scout's claim, pinned as behaviour:
    # without a handle, the delete + re-register road loses
    # the dedupe memory and an unchanged file ingests twice.
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    store = _store(tmp_path)
    watch = _register(store, folder, recursive=False)
    attacher = _fake_attacher()
    first = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert len(first.ingested) == 1
    store.remove_watch(watch.id)
    again = _register(store, folder, recursive=True)
    second = w.scan_watch(store, again, attacher=attacher, now=NOW)
    assert len(second.ingested) == 1
    assert second.ingested[0] != first.ingested[0]
    assert len(attacher.calls) == 2  # the duplicate, in the open


# ------------------------------------------------------- HTTP: PATCH


def test_http_patch_recursive_alone_enabled_alone_and_both(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    res = client.patch(url, json={"recursive": True})
    assert res.status_code == 200, res.text
    assert res.json()["recursive"] is True
    assert res.json()["enabled"] is True
    # the P-124 road, unchanged: enabled alone still works
    res = client.patch(url, json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert res.json()["recursive"] is True
    # both at once
    res = client.patch(url, json={"enabled": True, "recursive": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is True
    assert res.json()["recursive"] is False
    assert client.get(url).json()["recursive"] is False


def test_http_patch_empty_body_422_and_scoped_404s(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    # the status P-124's battery pinned for {} survives the widening
    assert client.patch(url, json={}).status_code == 422
    assert client.patch(
        "/api/v1/vision/watch-folders/nope",
        json={"recursive": True}).status_code == 404
    foreign = w.WatchStore(tmp_path)
    other = w.register_watch(
        foreign, owner_id="other", chat_id=chat_id,
        path=str(tmp_path / "inbox"), now=NOW)
    res = client.patch(
        f"/api/v1/vision/watch-folders/{other.id}",
        json={"recursive": True})
    assert res.status_code == 404
    # the refused patches changed nothing
    assert w.WatchStore(tmp_path).get_watch(other.id).recursive is False
    assert client.get(url).json()["recursive"] is False


def test_http_scan_depth_follows_patch_end_to_end(tmp_path, monkeypatch):
    folder = tmp_path / "inbox"
    (folder / "sub").mkdir(parents=True)
    (folder / "top.png").write_bytes(PNG)
    (folder / "sub" / "deep.png").write_bytes(PNG2)
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, folder, recursive=False)
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    scan = client.post(f"{url}/scan")
    assert scan.status_code == 200, scan.text
    assert len(scan.json()["ingested"]) == 1
    res = client.patch(url, json={"recursive": True})
    assert res.status_code == 200
    scan = client.post(f"{url}/scan")
    assert len(scan.json()["ingested"]) == 1  # the deep file only
    listed = client.get(
        "/api/v1/vision/attachments", params={"chat_id": chat_id})
    assert len(listed.json()["attachments"]) == 2
    # flipping back: nothing new is in reach, nothing duplicates
    client.patch(url, json={"recursive": False})
    scan = client.post(f"{url}/scan")
    assert scan.json()["ingested"] == []
    listed = client.get(
        "/api/v1/vision/attachments", params={"chat_id": chat_id})
    assert len(listed.json()["attachments"]) == 2


# ------------------------------------------------------ HTTP: DELETE


def _scanned_watch(tmp_path, monkeypatch, files=("a.png", "b.png")):
    folder = tmp_path / "inbox"
    folder.mkdir(exist_ok=True)
    for i, name in enumerate(files):
        (folder / name).write_bytes(make_png_bytes(color=(10 + i, 20, 30)))
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, folder)
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    scan = client.post(f"{url}/scan")
    assert scan.status_code == 200, scan.text
    return client, chat_id, watch, url, scan.json()["ingested"]


def test_http_delete_reports_ingested_and_keeps_attachments(
        tmp_path, monkeypatch):
    client, chat_id, watch, url, att_ids = _scanned_watch(
        tmp_path, monkeypatch)
    assert len(att_ids) == 2
    # a description derived from one ingested attachment
    described = client.post(
        "/api/v1/vision/describe",
        json={"chat_id": chat_id, "attachment_id": att_ids[0],
              "provider": "metadata"})
    assert described.status_code == 200, described.text
    res = client.delete(url)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["deleted"] is True
    assert body["id"] == watch["id"]
    assert body["ingested_records_removed"] == 2
    # the registration and its records are gone
    assert client.get(url).status_code == 404
    assert client.get(f"{url}/ingested").status_code == 404
    # the attachments are NOT the watch's: rows, bytes, and the
    # derived description all survive under their own custody
    listed = client.get(
        "/api/v1/vision/attachments", params={"chat_id": chat_id})
    assert len(listed.json()["attachments"]) == 2
    content = client.get(f"/api/v1/vision/attachments/{att_ids[0]}/content")
    assert content.status_code == 200
    descriptions = client.get(
        "/api/v1/vision/descriptions", params={"chat_id": chat_id})
    assert len(descriptions.json()["descriptions"]) == 1


def test_http_delete_without_ingested_reports_zero(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    res = client.delete(f"/api/v1/vision/watch-folders/{watch['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True, "id": watch["id"],
                          "ingested_records_removed": 0}


def test_http_delete_unknown_and_foreign_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    assert client.delete(
        "/api/v1/vision/watch-folders/nope").status_code == 404
    foreign = w.WatchStore(tmp_path)
    other = w.register_watch(
        foreign, owner_id="other", chat_id=chat_id,
        path=str(tmp_path / "inbox"), now=NOW)
    assert client.delete(
        f"/api/v1/vision/watch-folders/{other.id}").status_code == 404
    assert w.WatchStore(tmp_path).get_watch(other.id) is not None


def test_http_reregister_after_delete_scans_fresh(tmp_path, monkeypatch):
    client, chat_id, watch, url, att_ids = _scanned_watch(
        tmp_path, monkeypatch, files=("a.png",))
    res = client.delete(url)
    assert res.json()["ingested_records_removed"] == 1
    # the same folder for the same chat registers cleanly again,
    # and its first scan honestly re-ingests: the reported
    # loss of dedupe memory was real, not a bookkeeping fiction
    folder = tmp_path / "inbox"
    watch2 = _http_watch(client, chat_id, folder)
    scan = client.post(f"/api/v1/vision/watch-folders/{watch2['id']}/scan")
    assert len(scan.json()["ingested"]) == 1
    assert scan.json()["ingested"][0] != att_ids[0]


# --------------------------------------------------------- migration


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
