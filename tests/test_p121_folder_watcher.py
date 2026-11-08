"""P-121 — Folder watcher: watched folders ingest as
attachments (DERIVED).

Pins: registration refusals and round-trip, the tolerant
store, scan ingestion through an INJECTED attacher shaped
like P-120's attach_image (new files ingest as chat-level
attachments; non-images, oversize and unreadable files skip
with named reasons and store nothing; an unchanged file never
duplicates; a changed file at the same path ingests anew;
recursion and the per-scan cap behave as stated), the
disabled/missing-folder plain refusals, the lazy-attacher
honesty in a tree without P-120 (a scan with no injected
attacher refuses plainly naming the absence — skipped when
the attachments module IS present), custody purge, the HTTP
roads + 404/422 shapes, and the migration head pin (0041).
No network, no daemon: fakes/fixtures only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import struct
import zlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.imaging import sniff_image
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.vision import watcher as w

NOW = "2026-11-08T14:00:00+00:00"


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
PNG2 = make_png_bytes(2, 2, (10, 200, 10))


def _store(tmp_path):
    return w.WatchStore(tmp_path / "data")


def _fake_attacher():
    """An attacher with P-120's shape and refusal discipline."""
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


def _register(store, folder, chat_id="c1", owner="u1", **kw):
    return w.register_watch(
        store, owner_id=owner, chat_id=chat_id,
        path=str(folder), now=NOW, **kw)


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


# ------------------------------------------------------- registration


def test_register_round_trip(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "inbox")
    assert watch.enabled is True
    assert watch.recursive is False
    again = _store(tmp_path)
    assert again.get_watch(watch.id).chat_id == "c1"
    assert [r.id for r in again.list_for_chat("c1")] == [watch.id]
    assert [r.id for r in again.list_for_owner("u1")] == [watch.id]
    assert again.list_for_chat("other") == []


def test_register_refusals_store_nothing(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(w.WatchError):
        w.register_watch(store, owner_id="u1", chat_id="c1", path="  ")
    with pytest.raises(w.WatchError):
        w.register_watch(store, owner_id="u1", chat_id="", path="/x")
    _register(store, tmp_path / "inbox")
    with pytest.raises(w.WatchError):
        _register(store, tmp_path / "inbox")
    assert len(_store(tmp_path).list_for_owner("u1")) == 1


def test_tolerant_store_reads_corrupt_as_empty(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / w.WATCHER_FILENAME).write_text("{not json")
    store = w.WatchStore(data)
    assert store.list_for_owner("u1") == []
    assert store.list_ingested("any") == []


def test_remove_watch_drops_its_ingested_records(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    watch = _register(store, folder)
    w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    assert len(store.list_ingested(watch.id)) == 1
    assert store.remove_watch(watch.id).id == watch.id
    assert store.get_watch(watch.id) is None
    assert store.list_ingested(watch.id) == []
    assert store.remove_watch(watch.id) is None


# -------------------------------------------------------------- scan


def test_scan_ingests_new_images_as_chat_level(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    (folder / "b.png").write_bytes(PNG2)
    watch = _register(store, folder)
    attacher = _fake_attacher()
    report = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert report.scanned == 2
    assert len(report.ingested) == 2
    assert report.skipped == []
    assert report.truncated is False
    assert {c.filename for c in attacher.calls} == {"a.png", "b.png"}
    assert all(c.chat_id == "c1" for c in attacher.calls)
    rows = store.list_ingested(watch.id)
    assert {r.attachment_id for r in rows} == set(report.ingested)
    by_name = {r.source_path: r for r in rows}
    assert by_name[str(folder / "a.png")].sha256 == (
        hashlib.sha256(PNG).hexdigest())


def test_scan_skips_non_images_and_stores_nothing_for_them(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "note.txt").write_bytes(b"hello, not an image")
    (folder / "a.png").write_bytes(PNG)
    watch = _register(store, folder)
    report = w.scan_watch(
        store, watch, attacher=_fake_attacher(), now=NOW)
    assert len(report.ingested) == 1
    assert len(report.skipped) == 1
    assert report.skipped[0]["path"].endswith("note.txt")
    assert "refused" in report.skipped[0]["reason"]
    assert len(store.list_ingested(watch.id)) == 1


def test_scan_second_run_never_duplicates_unchanged(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    watch = _register(store, folder)
    first = w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    second = w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    assert len(first.ingested) == 1
    assert second.ingested == []
    assert second.skipped[0]["reason"] == "already_ingested"
    assert len(store.list_ingested(watch.id)) == 1


def test_scan_changed_file_at_same_path_ingests_anew(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    target = folder / "a.png"
    target.write_bytes(PNG)
    watch = _register(store, folder)
    w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    target.write_bytes(PNG2)
    report = w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    assert len(report.ingested) == 1
    assert len(store.list_ingested(watch.id)) == 2


def test_scan_oversize_is_a_named_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "MAX_WATCH_BYTES", 10)
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "big.png").write_bytes(PNG)
    watch = _register(store, folder)
    report = w.scan_watch(
        store, watch, attacher=_fake_attacher(), now=NOW)
    assert report.ingested == []
    assert "too_large" in report.skipped[0]["reason"]
    assert store.list_ingested(watch.id) == []


def test_scan_recursion_flag_controls_subfolders(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    sub = folder / "sub"
    sub.mkdir(parents=True)
    (folder / "top.png").write_bytes(PNG)
    (sub / "deep.png").write_bytes(PNG2)
    flat = _register(store, folder, chat_id="c-flat")
    report = w.scan_watch(store, flat, attacher=_fake_attacher(), now=NOW)
    assert report.scanned == 1
    deep = _register(store, folder, chat_id="c-deep", recursive=True)
    report = w.scan_watch(store, deep, attacher=_fake_attacher(), now=NOW)
    assert report.scanned == 2
    assert len(report.ingested) == 2


def test_scan_cap_truncates_and_names_it(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "MAX_FILES_PER_SCAN", 2)
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        (folder / name).write_bytes(PNG)
    watch = _register(store, folder)
    report = w.scan_watch(
        store, watch, attacher=_fake_attacher(), now=NOW)
    assert report.scanned == 2
    assert report.truncated is True


def test_scan_missing_folder_and_disabled_watch_refuse(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "does-not-exist")
    with pytest.raises(w.WatchError):
        w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    assert store.list_ingested(watch.id) == []
    folder = tmp_path / "inbox"
    folder.mkdir()
    live = _register(store, folder, chat_id="c2")
    disabled = w.WatchFolder(
        id=live.id, owner_id=live.owner_id, chat_id=live.chat_id,
        path=live.path, recursive=False, enabled=False,
        created_at=live.created_at)
    with pytest.raises(w.WatchError):
        w.scan_watch(store, disabled, attacher=_fake_attacher(), now=NOW)


def test_scan_without_attacher_names_absent_attachments(tmp_path):
    if importlib.util.find_spec("runmal.vision.attachments"):
        pytest.skip("attachments module present; absence case n/a")
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    watch = _register(store, folder)
    with pytest.raises(w.WatchError) as excinfo:
        w.scan_watch(store, watch, now=NOW)
    assert "P-120" in str(excinfo.value)
    assert store.list_ingested(watch.id) == []


def test_purge_chat_removes_watches_and_records(tmp_path):
    store = _store(tmp_path)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    watch = _register(store, folder)
    other = _register(store, folder, chat_id="c2")
    w.scan_watch(store, watch, attacher=_fake_attacher(), now=NOW)
    assert store.purge_chat("c1") == 1
    assert store.get_watch(watch.id) is None
    assert store.list_ingested(watch.id) == []
    assert store.get_watch(other.id) is not None
    assert store.purge_chat("c1") == 0


# -------------------------------------------------------------- HTTP


def test_http_watch_roads_round_trip(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="watcher")
    folder = tmp_path / "inbox"
    folder.mkdir()
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": str(folder)})
    assert res.status_code == 201
    watch = res.json()
    assert watch["chat_id"] == chat_id
    assert watch["path"] == str(folder)
    listed = client.get(
        "/api/v1/vision/watch-folders", params={"chat_id": chat_id})
    assert [r["id"] for r in listed.json()["watch_folders"]] == [
        watch["id"]]
    ingested = client.get(
        f"/api/v1/vision/watch-folders/{watch['id']}/ingested")
    assert ingested.status_code == 200
    assert ingested.json()["ingested"] == []
    deleted = client.delete(f"/api/v1/vision/watch-folders/{watch['id']}")
    assert deleted.status_code == 200
    listed = client.get(
        "/api/v1/vision/watch-folders", params={"chat_id": chat_id})
    assert listed.json()["watch_folders"] == []


def test_http_watch_404_and_422_shapes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="watcher")
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": "no-such-chat", "path": "/tmp/x"})
    assert res.status_code == 404
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": "   "})
    assert res.status_code == 422
    res = client.get(
        "/api/v1/vision/watch-folders", params={"chat_id": "nope"})
    assert res.status_code == 404
    res = client.delete("/api/v1/vision/watch-folders/nope")
    assert res.status_code == 404
    res = client.post("/api/v1/vision/watch-folders/nope/scan")
    assert res.status_code == 404


def test_http_scan_missing_folder_is_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="watcher")
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": str(tmp_path / "gone")})
    assert res.status_code == 201
    watch_id = res.json()["id"]
    res = client.post(f"/api/v1/vision/watch-folders/{watch_id}/scan")
    assert res.status_code == 422
    assert "missing" in res.json()["detail"]


def test_http_scan_with_injected_attacher(
        tmp_path, monkeypatch):
    from runmal.vision import router as vision_router

    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="watcher")
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": str(folder)})
    watch_id = res.json()["id"]
    attacher = _fake_attacher()
    monkeypatch.setattr(
        vision_router, "_scan_attacher",
        lambda: attacher, raising=False)
    res = client.post(f"/api/v1/vision/watch-folders/{watch_id}/scan")
    assert res.status_code == 200
    body = res.json()
    assert body["scanned"] == 1
    assert len(body["ingested"]) == 1
    ingested = client.get(
        f"/api/v1/vision/watch-folders/{watch_id}/ingested")
    rows = ingested.json()["ingested"]
    assert len(rows) == 1
    assert rows[0]["attachment_id"] == body["ingested"][0]
    assert rows[0]["sha256"] == hashlib.sha256(PNG).hexdigest()


# --------------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
