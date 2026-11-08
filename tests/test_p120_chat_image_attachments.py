"""P-120 — Image attachments on chat messages (Part VIII, DERIVED).

Pins: the attachment truth layer (sniffed truth only, the
user filename kept as data and never as a path), the plain
total refusals (empty / oversize / non-image store NOTHING),
the durable JSON-index + byte-file store (round-trip,
tolerant load, delete and purge remove BOTH row and bytes),
the owner-scoped HTTP roads (attach / list / get / content /
delete, 404 + 422 shapes), describe-from-attachment through
the P-117 road, the additive attachments view on message
history, custody on message delete and chat delete, and the
migration head staying 0041 (NO migration; provisional 0042
not taken). No network: fixtures only.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.vision import attachments as att

NOW = "2026-11-08T13:00:00+00:00"
LATER = "2026-11-08T13:05:00+00:00"


def make_png_bytes(width=6, height=4, color=(30, 30, 200)) -> bytes:
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
PNG_SHA = hashlib.sha256(PNG).hexdigest()
PNG_B64 = base64.b64encode(PNG).decode()


def _store(tmp_path):
    return att.AttachmentStore(tmp_path)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory, db_path


def _chat(client, **kw):
    return client.post("/api/v1/chats", json=kw).json()["id"]


def _message(client, chat_id, content="look at this"):
    res = client.post(f"/api/v1/chats/{chat_id}/messages",
                      json={"role": "user", "content": content})
    assert res.status_code == 201
    return res.json()["id"]


# --------------------------------------------------------- service


def test_attach_records_sniffed_truth_and_round_trips(tmp_path):
    store = _store(tmp_path)
    rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=PNG,
        message_id="m1", filename="sunset.png", now=NOW)
    assert rec.image_format == "png"
    assert (rec.image_width, rec.image_height) == (6, 4)
    assert rec.image_bytes == len(PNG)
    assert rec.image_sha256 == PNG_SHA
    assert rec.filename == "sunset.png"
    assert rec.message_id == "m1"
    assert rec.created_at == NOW
    assert rec.media_type == "image/png"
    assert store.read_bytes(rec) == PNG
    fresh = _store(tmp_path)
    rows = fresh.list_for_chat("c1")
    assert [r.id for r in rows] == [rec.id]
    assert fresh.list_for_message("m1")[0].id == rec.id
    assert fresh.list_for_message("other") == []
    assert fresh.get(rec.id).image_sha256 == PNG_SHA
    assert fresh.get("nope") is None


def test_attach_chat_level_has_no_message(tmp_path):
    rec = att.attach_image(
        _store(tmp_path), chat_id="c1", owner_id="u1", data=PNG, now=NOW)
    assert rec.message_id is None
    assert rec.to_dict()["message_id"] is None


def test_filename_is_data_never_a_path(tmp_path):
    store = _store(tmp_path)
    rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=PNG,
        filename="../../evil.png", now=NOW)
    assert rec.filename == "../../evil.png"
    path = store.bytes_path(rec)
    assert path.parent == store.bytes_dir
    assert path.name.startswith(rec.id)
    assert store.read_bytes(rec) == PNG


def test_refusals_store_nothing(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(att.AttachmentError):
        att.attach_image(store, chat_id="c1", owner_id="u1", data=b"")
    with pytest.raises(att.AttachmentError):
        att.attach_image(
            store, chat_id="c1", owner_id="u1", data=b"plain text bytes")
    with pytest.raises(att.AttachmentError) as exc:
        att.attach_image(
            store, chat_id="c1", owner_id="u1",
            data=b"x" * (att.MAX_ATTACHMENT_BYTES + 1))
    assert "cap" in str(exc.value)
    assert store.list_for_chat("c1") == []
    assert not store.index_path.exists()
    assert not store.bytes_dir.exists()


def test_store_tolerant_load(tmp_path):
    (tmp_path / att.ATTACHMENTS_FILENAME).write_text("{ not json")
    store = _store(tmp_path)
    assert store.list_for_chat("c1") == []
    assert store.get("x") is None


def test_remove_deletes_row_and_bytes(tmp_path):
    store = _store(tmp_path)
    rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=PNG, now=NOW)
    path = store.bytes_path(rec)
    assert path.exists()
    removed = store.remove(rec.id)
    assert removed is not None and removed.id == rec.id
    assert store.get(rec.id) is None
    assert not path.exists()
    assert store.remove(rec.id) is None


def test_purges_are_scoped_and_remove_bytes(tmp_path):
    store = _store(tmp_path)
    a = att.attach_image(store, chat_id="c1", owner_id="u1", data=PNG,
                         message_id="m1", now=NOW)
    b = att.attach_image(store, chat_id="c1", owner_id="u1", data=PNG,
                         now=LATER)
    c = att.attach_image(store, chat_id="c2", owner_id="u1", data=PNG,
                         message_id="m9", now=LATER)
    assert store.purge_message("m1") == 1
    assert not store.bytes_path(a).exists()
    assert store.get(b.id) is not None
    assert store.purge_message("m1") == 0
    assert store.purge_chat("c1") == 1
    assert not store.bytes_path(b).exists()
    assert store.get(c.id) is not None
    assert store.read_bytes(c) == PNG
    assert store.purge_chat("nope") == 0


def test_missing_byte_file_reads_as_none(tmp_path):
    store = _store(tmp_path)
    rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=PNG, now=NOW)
    store.bytes_path(rec).unlink()
    assert store.read_bytes(rec) is None


# -------------------------------------------------------------- HTTP


def test_http_attach_list_get_content_delete(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "sunset.png",
        "image_b64": PNG_B64})
    assert res.status_code == 201
    body = res.json()
    assert body["image"]["sha256"] == PNG_SHA
    assert body["image"]["format"] == "png"
    assert body["filename"] == "sunset.png"
    assert body["message_id"] is None
    assert body["media_type"] == "image/png"
    att_id = body["id"]
    listed = client.get("/api/v1/vision/attachments",
                        params={"chat_id": chat_id})
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()["attachments"]] == [att_id]
    got = client.get(f"/api/v1/vision/attachments/{att_id}")
    assert got.status_code == 200
    assert got.json()["id"] == att_id
    content = client.get(f"/api/v1/vision/attachments/{att_id}/content")
    assert content.status_code == 200
    assert content.content == PNG
    assert content.headers["content-type"].startswith("image/png")
    deleted = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(
        f"/api/v1/vision/attachments/{att_id}").status_code == 404
    assert client.get(
        f"/api/v1/vision/attachments/{att_id}/content").status_code == 404


def test_http_attach_to_message_and_history_view(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    msg_id = _message(client, chat_id)
    other_id = _message(client, chat_id, "no picture here")
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": msg_id,
        "filename": "evidence.png", "image_b64": PNG_B64})
    assert res.status_code == 201
    assert res.json()["message_id"] == msg_id
    history = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert history.status_code == 200
    by_id = {m["id"]: m for m in history.json()}
    assert by_id[msg_id]["attachments"][0]["id"] == res.json()["id"]
    assert by_id[msg_id]["attachments"][0]["image"]["sha256"] == PNG_SHA
    assert "attachments" not in by_id[other_id]
    detail = client.get(f"/api/v1/chats/{chat_id}")
    by_id = {m["id"]: m for m in detail.json()["messages"]}
    assert by_id[msg_id]["attachments"][0]["filename"] == "evidence.png"


def test_http_attach_404_and_422_shapes(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": "nope", "image_b64": PNG_B64})
    assert res.status_code == 404
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": "nope", "image_b64": PNG_B64})
    assert res.status_code == 404
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": "!!!"})
    assert res.status_code == 422
    notimg = base64.b64encode(b"plain text bytes").decode()
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": notimg})
    assert res.status_code == 422
    res = client.get("/api/v1/vision/attachments",
                     params={"chat_id": "nope"})
    assert res.status_code == 404
    res = client.get("/api/v1/vision/attachments/nope")
    assert res.status_code == 404
    res = client.delete("/api/v1/vision/attachments/nope")
    assert res.status_code == 404


def test_http_describe_from_attachment(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    other_chat = _chat(client, title="other")
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64})
    att_id = res.json()["id"]
    described = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "attachment_id": att_id,
        "question": "what is attached?"})
    assert described.status_code == 200
    body = described.json()
    assert body["source_kind"] == "attachment"
    assert body["source_ref"] == att_id
    assert body["provider"]["road"] == "metadata"
    assert body["image"]["sha256"] == PNG_SHA
    cross = client.post("/api/v1/vision/describe", json={
        "chat_id": other_chat, "attachment_id": att_id})
    assert cross.status_code == 404
    missing = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "attachment_id": "nope"})
    assert missing.status_code == 404


# ----------------------------------------------------------- custody


def test_message_delete_purges_its_attachments(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    msg_id = _message(client, chat_id)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": msg_id, "image_b64": PNG_B64})
    att_id = res.json()["id"]
    store = _store(tmp_path)
    byte_path = store.bytes_path(store.get(att_id))
    assert byte_path.exists()
    deleted = client.delete(f"/api/v1/chats/{chat_id}/messages/{msg_id}")
    assert deleted.status_code in (200, 204)
    assert _store(tmp_path).list_for_chat(chat_id) == []
    assert not byte_path.exists()


def test_chat_delete_purges_attachments(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="pics")
    keep_chat = _chat(client, title="keep")
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64})
    att_id = res.json()["id"]
    client.post("/api/v1/vision/attachments", json={
        "chat_id": keep_chat, "image_b64": PNG_B64})
    store = _store(tmp_path)
    byte_path = store.bytes_path(store.get(att_id))
    deleted = client.delete(f"/api/v1/chats/{chat_id}")
    assert deleted.status_code in (200, 204)
    fresh = _store(tmp_path)
    assert fresh.list_for_chat(chat_id) == []
    assert not byte_path.exists()
    assert len(fresh.list_for_chat(keep_chat)) == 1


# ------------------------------------------------------------ pins


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
