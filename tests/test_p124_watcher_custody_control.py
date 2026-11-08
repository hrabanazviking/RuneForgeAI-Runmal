"""P-124 — Watcher custody & control completion (Part VIII, DERIVED).

Pins: WatchStore.forget_attachment (an attachment's death
forgets its ingested records across watches; an empty id
forgets nothing; a no-match forget leaves the store file
byte-untouched), WatchStore.set_enabled (the enabled flag's
first handle: round-trip, preservation of every other field
and of the ingested records, unknown watch = None and no
write), the scan consequence (without forget an unchanged
file skips as already-ingested forever; after forget the
same file ingests anew), the HTTP roads (GET single watch,
PATCH enabled — owner-scoped 404s, a disabled watch's scan
refused 422 end to end), custody end to end (deleting a
watcher-ingested attachment over HTTP forgets its record
and a rescan re-ingests the file; deleting a message
forgets the records naming its attachments), the additive
watch_records_forgotten count on attachment delete, and
the migration head staying 0041 (NO migration). No
network, no daemon: fakes/fixtures only.
"""

from __future__ import annotations

import base64
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

NOW = "2026-11-08T15:00:00+00:00"


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
PNG_B64 = base64.b64encode(PNG).decode()


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


# ------------------------------------------------- store: forget


def test_forget_removes_only_naming_records_across_watches(tmp_path):
    store = _store(tmp_path)
    a = _register(store, tmp_path / "inbox")
    b = _register(store, tmp_path / "inbox2", chat_id="c2")
    _ingested(store, a.id, "att-1")
    _ingested(store, a.id, "att-2", path="/inbox/b.png")
    _ingested(store, b.id, "att-1", path="/inbox2/a.png")
    assert store.forget_attachment("att-1") == 2
    fresh = _store(tmp_path)
    assert [r.attachment_id for r in fresh.list_ingested(a.id)] == ["att-2"]
    assert fresh.list_ingested(b.id) == []
    # the watches themselves are untouched
    assert fresh.get_watch(a.id) is not None
    assert fresh.get_watch(b.id) is not None


def test_forget_unknown_is_noop_and_byte_untouched(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "inbox")
    _ingested(store, watch.id, "att-1")
    before = store.index_path.read_bytes()
    assert store.forget_attachment("att-nope") == 0
    assert store.index_path.read_bytes() == before


def test_forget_empty_id_and_absent_store(tmp_path):
    store = _store(tmp_path)
    assert store.forget_attachment("") == 0
    assert not store.index_path.exists()
    watch = _register(store, tmp_path / "inbox")
    _ingested(store, watch.id, "att-1")
    assert store.forget_attachment("") == 0
    assert len(store.list_ingested(watch.id)) == 1


# ------------------------------------------------ store: enabled


def test_set_enabled_round_trip_preserves_everything(tmp_path):
    store = _store(tmp_path)
    watch = _register(store, tmp_path / "inbox", recursive=True)
    _ingested(store, watch.id, "att-1")
    updated = store.set_enabled(watch.id, False)
    assert updated.enabled is False
    assert updated.path == watch.path
    assert updated.recursive is True
    assert updated.chat_id == watch.chat_id
    assert updated.created_at == watch.created_at
    fresh = _store(tmp_path)
    assert fresh.get_watch(watch.id).enabled is False
    assert len(fresh.list_ingested(watch.id)) == 1
    assert fresh.set_enabled(watch.id, True).enabled is True
    assert _store(tmp_path).get_watch(watch.id).enabled is True


def test_set_enabled_unknown_returns_none_and_writes_nothing(tmp_path):
    store = _store(tmp_path)
    _register(store, tmp_path / "inbox")
    before = store.index_path.read_bytes()
    assert store.set_enabled("nope", False) is None
    assert store.index_path.read_bytes() == before


# --------------------------------------------- scan consequence


def test_scan_forget_rescan_reingests(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    store = _store(tmp_path)
    watch = _register(store, folder)
    attacher = _fake_attacher()
    first = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert first.ingested == ["att-1"]
    # without forget: the unchanged file skips forever
    second = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert second.ingested == []
    assert second.skipped[0]["reason"] == "already_ingested"
    # the attachment dies; its record is forgotten; rescan lands it anew
    assert store.forget_attachment("att-1") == 1
    third = w.scan_watch(store, watch, attacher=attacher, now=NOW)
    assert third.ingested == ["att-2"]
    assert [r.attachment_id for r in store.list_ingested(watch.id)] == ["att-2"]


# --------------------------------------------------------- HTTP


def _http_watch(client, chat_id, folder):
    res = client.post("/api/v1/vision/watch-folders",
                      json={"chat_id": chat_id, "path": str(folder)})
    assert res.status_code == 201
    return res.json()


def test_http_get_single_watch_and_404s(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    res = client.get(f"/api/v1/vision/watch-folders/{watch['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == watch["id"]
    assert res.json()["enabled"] is True
    assert client.get("/api/v1/vision/watch-folders/nope").status_code == 404
    # a foreign owner's registration is invisible
    foreign = w.WatchStore(tmp_path)
    other = w.register_watch(foreign, owner_id="other", chat_id=chat_id,
                             path=str(tmp_path / "inbox"), now=NOW)
    assert client.get(
        f"/api/v1/vision/watch-folders/{other.id}").status_code == 404


def test_http_patch_toggles_enabled_and_scan_follows(tmp_path, monkeypatch):
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, folder)
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    res = client.patch(url, json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    # the P-121 scan refusal is now reachable end to end
    res = client.post(f"{url}/scan")
    assert res.status_code == 422
    assert "disabled" in res.json()["detail"]
    res = client.patch(url, json={"enabled": True})
    assert res.json()["enabled"] is True
    res = client.post(f"{url}/scan")
    assert res.status_code == 200
    assert len(res.json()["ingested"]) == 1


def test_http_patch_unknown_foreign_and_shape(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    assert client.patch("/api/v1/vision/watch-folders/nope",
                        json={"enabled": False}).status_code == 404
    assert client.patch(url, json={}).status_code == 422
    foreign = w.WatchStore(tmp_path)
    other = w.register_watch(foreign, owner_id="other", chat_id=chat_id,
                             path=str(tmp_path / "inbox"), now=NOW)
    res = client.patch(f"/api/v1/vision/watch-folders/{other.id}",
                       json={"enabled": False})
    assert res.status_code == 404
    # the refused patch changed nothing
    assert w.WatchStore(tmp_path).get_watch(other.id).enabled is True
    assert client.get(url).json()["enabled"] is True


# ------------------------------------------------- custody E2E


def test_http_ingested_attachment_delete_forgets_and_rescan_reingests(
        tmp_path, monkeypatch):
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    watch = _http_watch(client, chat_id, folder)
    wurl = f"/api/v1/vision/watch-folders/{watch['id']}"
    scan = client.post(f"{wurl}/scan")
    assert scan.status_code == 200
    att_id = scan.json()["ingested"][0]
    assert len(client.get(f"{wurl}/ingested").json()["ingested"]) == 1
    res = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert res.json()["descriptions_purged"] == 0
    assert res.json()["watch_records_forgotten"] == 1
    assert client.get(f"{wurl}/ingested").json()["ingested"] == []
    # the file itself was never touched; a rescan ingests it anew
    assert (folder / "a.png").read_bytes() == PNG
    scan2 = client.post(f"{wurl}/scan")
    assert len(scan2.json()["ingested"]) == 1
    assert scan2.json()["ingested"][0] != att_id


def test_http_plain_attachment_delete_reports_zero_forgotten(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "a.png", "image_b64": PNG_B64})
    assert res.status_code == 201
    att_id = res.json()["id"]
    res = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert res.status_code == 200
    assert res.json()["watch_records_forgotten"] == 0


def test_message_delete_forgets_ingested_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    msg = client.post(f"/api/v1/chats/{chat_id}/messages",
                      json={"role": "user", "content": "look"})
    assert msg.status_code == 201
    message_id = msg.json()["id"]
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": message_id,
        "filename": "a.png", "image_b64": PNG_B64})
    assert res.status_code == 201
    att_id = res.json()["id"]
    watch = _http_watch(client, chat_id, tmp_path / "inbox")
    store = w.WatchStore(tmp_path)
    _ingested(store, watch["id"], att_id)
    assert len(store.list_ingested(watch["id"])) == 1
    res = client.delete(f"/api/v1/chats/{chat_id}/messages/{message_id}")
    assert res.status_code == 200
    assert w.WatchStore(tmp_path).list_ingested(watch["id"]) == []
    assert client.get(
        f"/api/v1/vision/attachments/{att_id}").status_code == 404


# --------------------------------------------------------- pin


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
