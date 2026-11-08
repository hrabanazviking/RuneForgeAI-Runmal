"""P-123 — Attachment thumbnails for vision surfaces (DERIVED).

Pins: the derived-on-read thumbnail service riding the P-023
PNG engine (a real downscale that itself sniffs as PNG, a
custom max_dim honoured, nothing stored by a derivation),
the plain total refusals (non-PNG format naming the PNG-only
bound and never substituting the full bytes, an undecodable
PNG, missing byte files, max_dim outside the supported
range), the record carrying NO thumbnail claim (availability
is a request-time fact), the owner-scoped HTTP road
(200 image/png, 404 unknown/foreign, 422 refusals), and the
migration head staying 0041 (NO migration; provisional 0042
not taken). No network: fixtures only.
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.imaging import sniff_image
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.vision import attachments as att

NOW = "2026-11-08T14:00:00+00:00"


def _chunk(ctype, data):
    raw = ctype + data
    return struct.pack(">I", len(data)) + raw + struct.pack(
        ">I", zlib.crc32(raw) & 0xFFFFFFFF)


def make_png_bytes(width=6, height=4, color=(30, 30, 200), interlace=0):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, interlace)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def make_jpeg_bytes(width=8, height=6):
    sof = struct.pack(">H", 8 + 3 * 3) + bytes([8]) + struct.pack(
        ">HH", height, width) + bytes([3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    return b"\xff\xd8" + b"\xff\xc0" + sof + b"\xff\xd9"


def make_gif_bytes(width=8, height=6):
    return (
        b"GIF89a" + struct.pack("<HH", width, height)
        + bytes([0x70, 0, 0]) + b"\x3b"
    )


BIG_PNG = make_png_bytes(512, 256)
SMALL_PNG = make_png_bytes(6, 4)
INTERLACED_PNG = make_png_bytes(6, 4, interlace=1)
JPEG = make_jpeg_bytes()
GIF = make_gif_bytes()


def _store(tmp_path):
    return att.AttachmentStore(tmp_path)


def _attach(store, data, filename="img.png"):
    return att.attach_image(
        store, chat_id="c1", owner_id="u1", data=data,
        filename=filename, now=NOW)


# --------------------------------------------------------- service


def test_thumbnail_downscales_and_sniffs_as_png(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, BIG_PNG, "big.png")
    thumb = att.thumbnail_bytes(store, rec)
    info = sniff_image(thumb)
    assert info.format == "png"
    assert (info.width, info.height) == (256, 128)
    assert thumb != BIG_PNG


def test_thumbnail_small_source_reencoded_at_native_size(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, SMALL_PNG, "small.png")
    thumb = att.thumbnail_bytes(store, rec)
    info = sniff_image(thumb)
    assert info.format == "png"
    assert (info.width, info.height) == (6, 4)


def test_thumbnail_custom_max_dim(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, BIG_PNG, "big.png")
    info = sniff_image(att.thumbnail_bytes(store, rec, max_dim=64))
    assert (info.width, info.height) == (64, 32)
    info = sniff_image(att.thumbnail_bytes(store, rec, max_dim=1024))
    assert (info.width, info.height) == (512, 256)


def test_thumbnail_max_dim_out_of_range_refused(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, BIG_PNG, "big.png")
    for bad in (0, -1, att.THUMBNAIL_MAX_DIM_LIMIT + 1):
        with pytest.raises(att.AttachmentError, match="max_dim"):
            att.thumbnail_bytes(store, rec, max_dim=bad)


def test_thumbnail_non_png_refused_never_substituted(tmp_path):
    store = _store(tmp_path)
    for data, name in ((JPEG, "a.jpg"), (GIF, "a.gif")):
        rec = _attach(store, data, name)
        with pytest.raises(att.AttachmentError, match="PNG-only"):
            att.thumbnail_bytes(store, rec)


def test_thumbnail_missing_bytes_refused_as_not_found(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, SMALL_PNG, "small.png")
    store.bytes_path(rec).unlink()
    with pytest.raises(att.AttachmentError, match="bytes not found"):
        att.thumbnail_bytes(store, rec)


def test_thumbnail_undecodable_png_refused(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, INTERLACED_PNG, "interlaced.png")
    assert rec.image_format == "png"
    with pytest.raises(att.AttachmentError, match="decodable subset"):
        att.thumbnail_bytes(store, rec)


def test_thumbnail_derivation_stores_nothing(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, BIG_PNG, "big.png")
    before = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    index_before = store.index_path.read_bytes()
    att.thumbnail_bytes(store, rec)
    att.thumbnail_bytes(store, rec, max_dim=32)
    after = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert after == before
    assert store.index_path.read_bytes() == index_before


def test_record_carries_no_thumbnail_claim(tmp_path):
    store = _store(tmp_path)
    rec = _attach(store, SMALL_PNG, "small.png")
    assert "thumbnail" not in rec.to_dict()


# ------------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def _chat(client):
    return client.post("/api/v1/chats", json={}).json()["id"]


def _attach_http(client, chat_id, data, filename="img.png"):
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": filename,
        "image_b64": base64.b64encode(data).decode()})
    assert res.status_code == 201
    return res.json()["id"]


def test_http_thumbnail_road_serves_derived_png(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    att_id = _attach_http(client, _chat(client), BIG_PNG, "big.png")
    res = client.get(f"/api/v1/vision/attachments/{att_id}/thumbnail")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    info = sniff_image(res.content)
    assert (info.width, info.height) == (256, 128)
    res = client.get(
        f"/api/v1/vision/attachments/{att_id}/thumbnail?max_dim=64")
    assert res.status_code == 200
    info = sniff_image(res.content)
    assert (info.width, info.height) == (64, 32)


def test_http_thumbnail_unknown_and_foreign_are_404(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/vision/attachments/nope/thumbnail")
    assert res.status_code == 404
    store = att.AttachmentStore(Path(tmp_path))
    foreign = att.attach_image(
        store, chat_id="cX", owner_id="someone-else", data=SMALL_PNG,
        filename="f.png", now=NOW)
    res = client.get(f"/api/v1/vision/attachments/{foreign.id}/thumbnail")
    assert res.status_code == 404


def test_http_thumbnail_non_png_is_422_and_not_the_full_image(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    att_id = _attach_http(client, _chat(client), JPEG, "a.jpg")
    res = client.get(f"/api/v1/vision/attachments/{att_id}/thumbnail")
    assert res.status_code == 422
    assert "PNG-only" in res.json()["detail"]
    assert res.content != JPEG


def test_http_thumbnail_bad_max_dim_and_undecodable_are_422(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    att_id = _attach_http(client, chat_id, BIG_PNG, "big.png")
    for bad in ("0", "1025"):
        res = client.get(
            f"/api/v1/vision/attachments/{att_id}/thumbnail"
            f"?max_dim={bad}")
        assert res.status_code == 422
    odd_id = _attach_http(client, chat_id, INTERLACED_PNG, "i.png")
    res = client.get(f"/api/v1/vision/attachments/{odd_id}/thumbnail")
    assert res.status_code == 422
    assert "decodable subset" in res.json()["detail"]


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _, db_path = make_client(tmp_path, monkeypatch)
    assert current_revision(db_path) == "0041"
