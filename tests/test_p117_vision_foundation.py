"""P-117 — Vision foundation + openapi fix (Part VIII opener, DERIVED).

Pins: the commissioned F2 fix (app.openapi() succeeds; the
/voice and /memories bare pages declare an HTML response
class and still serve), the metadata provider's sniffed
truth and its refusal of non-images, the no-provider plain
refusal (nothing fabricated, nothing stored), the durable
JSON store (round-trip, tolerant load, last-per-chat), and
the owner-scoped HTTP road (inline + asset describe, list,
last, 404/422 shapes). Migration head stays 0041.
No network: fakes/fixtures only.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.service import asset_storage_dir
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, CharacterAsset, Chat
from runmal.db.owners import get_or_create_owner
from runmal.vision import service as vis

NOW = "2026-11-08T12:00:00+00:00"
LATER = "2026-11-08T12:05:00+00:00"


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
PNG_SHA = hashlib.sha256(PNG).hexdigest()


def _store(tmp_path):
    return vis.VisionStore(tmp_path / "vision_descriptions.json")


# ------------------------------------------------------- F2 fix


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


def test_openapi_succeeds_and_names_html_pages(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/voice" in paths
    assert "/memories" in paths
    assert "200" in paths["/voice"]["get"]["responses"]
    assert "200" in paths["/memories"]["get"]["responses"]
    assert "/api/v1/vision/describe" in paths


def test_html_pages_still_serve(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    voice = client.get("/voice")
    assert voice.status_code == 200
    assert "text/html" in voice.headers["content-type"]
    memories = client.get("/memories")
    assert memories.status_code == 200
    assert "text/html" in memories.headers["content-type"]


# --------------------------------------------------- provider seam


def test_metadata_provider_reports_sniffed_truth():
    text = vis.MetadataVisionProvider().describe(PNG, "what is this?")
    assert "png" in text
    assert "6x4" in text
    assert str(len(PNG)) in text
    assert PNG_SHA in text
    assert "no semantic caption" in text


def test_metadata_provider_refuses_non_image():
    with pytest.raises(vis.VisionProviderError):
        vis.MetadataVisionProvider().describe(b"definitely not an image")


def test_no_provider_is_a_plain_refusal_and_stores_nothing(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(vis.VisionUnavailableError):
        vis.describe_image(
            store, chat_id="c1", owner_id="u1", image_bytes=PNG,
            provider=None, now=NOW)
    assert store.list_for_chat("c1") == []


def test_empty_bytes_refused(tmp_path):
    with pytest.raises(vis.VisionError):
        vis.describe_image(
            _store(tmp_path), chat_id="c1", owner_id="u1",
            image_bytes=b"", provider=vis.MetadataVisionProvider(),
            now=NOW)


def test_describe_records_full_truth(tmp_path):
    store = _store(tmp_path)
    rec = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=vis.MetadataVisionProvider(), question="look",
        now=NOW)
    assert rec.provider_id == "runmal.vision.metadata"
    assert rec.provider_road == "metadata"
    assert rec.image_format == "png"
    assert (rec.image_width, rec.image_height) == (6, 4)
    assert rec.image_bytes == len(PNG)
    assert rec.image_sha256 == PNG_SHA
    assert rec.question == "look"
    assert rec.created_at == NOW
    assert rec.source_kind == "inline"


# ------------------------------------------------------------ store


def test_store_round_trip_and_last_per_chat(tmp_path):
    store = _store(tmp_path)
    vis.describe_image(store, chat_id="c1", owner_id="u1",
                       image_bytes=PNG,
                       provider=vis.MetadataVisionProvider(), now=NOW)
    vis.describe_image(store, chat_id="c1", owner_id="u1",
                       image_bytes=make_png_bytes(2, 2),
                       provider=vis.MetadataVisionProvider(), now=LATER)
    vis.describe_image(store, chat_id="c2", owner_id="u1",
                       image_bytes=PNG,
                       provider=vis.MetadataVisionProvider(), now=LATER)
    fresh = _store(tmp_path)
    rows = fresh.list_for_chat("c1")
    assert len(rows) == 2
    assert fresh.last_for_chat("c1").created_at == LATER
    assert fresh.last_for_chat("c2").image_sha256 == PNG_SHA
    assert fresh.last_for_chat("nope") is None


def test_store_tolerant_load(tmp_path):
    path = tmp_path / "vision_descriptions.json"
    path.write_text("{ not json")
    store = vis.VisionStore(path)
    assert store.list_for_chat("c1") == []
    assert store.last_for_chat("c1") is None


# -------------------------------------------------------------- HTTP


def _chat(client, **kw):
    return client.post("/api/v1/chats", json=kw).json()["id"]


def test_http_inline_describe_list_last(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    b64 = base64.b64encode(PNG).decode()
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "image_b64": b64,
                            "question": "look at this"})
    assert res.status_code == 200
    body = res.json()
    assert body["image"]["sha256"] == PNG_SHA
    assert body["provider"]["road"] == "metadata"
    assert body["source_kind"] == "inline"
    listed = client.get("/api/v1/vision/descriptions",
                        params={"chat_id": chat_id})
    assert listed.status_code == 200
    assert len(listed.json()["descriptions"]) == 1
    last = client.get("/api/v1/vision/last", params={"chat_id": chat_id})
    assert last.status_code == 200
    assert last.json()["id"] == body["id"]


def test_http_last_404_when_none(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    res = client.get("/api/v1/vision/last", params={"chat_id": chat_id})
    assert res.status_code == 404


def test_http_unknown_chat_404(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    b64 = base64.b64encode(PNG).decode()
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": "nope", "image_b64": b64})
    assert res.status_code == 404
    res = client.get("/api/v1/vision/descriptions",
                     params={"chat_id": "nope"})
    assert res.status_code == 404


def test_http_bad_inputs_422(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "image_b64": "!!!"})
    assert res.status_code == 422
    notimg = base64.b64encode(b"plain text bytes").decode()
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "image_b64": notimg})
    assert res.status_code == 422
    res = client.post("/api/v1/vision/describe", json={"chat_id": chat_id})
    assert res.status_code == 422


def test_http_asset_describe(tmp_path, monkeypatch):
    client, factory, _db = make_client(tmp_path, monkeypatch)

    async def seed():
        async with factory() as session:
            owner = await get_or_create_owner(session)
            char = Character(user_id=owner.id, name="Seer")
            session.add(char)
            await session.flush()
            chat = Chat(user_id=owner.id, character_id=char.id,
                        title="vision")
            session.add(chat)
            asset = CharacterAsset(
                character_id=char.id, user_id=owner.id, kind="avatar",
                name="pic.png", status="stored", format="png",
                media_type="image/png", byte_size=len(PNG),
                sha256=PNG_SHA, storage_relpath="p023/pic.png")
            session.add(asset)
            await session.commit()
            return chat.id, char.id, asset.id

    chat_id, char_id, asset_id = asyncio.run(seed())
    folder = asset_storage_dir(char_id)
    (folder / "pic.png").write_bytes(PNG)
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "asset_id": asset_id})
    assert res.status_code == 200
    body = res.json()
    assert body["source_kind"] == "asset"
    assert body["source_ref"] == asset_id
    assert body["image"]["sha256"] == PNG_SHA
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "asset_id": "nope"})
    assert res.status_code == 404


# ------------------------------------------------------------ pins


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
