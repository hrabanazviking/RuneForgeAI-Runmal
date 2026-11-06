"""P-023 acceptance: character card assets — migration 0020, image
sniffing + PNG thumbnails, asset plan/ingest classification, CHARX +
PNG container art, the /assets HTTP surface, unknown-field
preservation, duplicate / soft-delete cloning, bulk-import notes,
cleanup referenced-set, portable archive round trip, corrupt +
oversize degradation, traversal safety and storage-name collisions.

Style mirrors tests/test_p022_bulk_library_import.py (make_factory /
make_user helpers) and test_s106_characters.py (TestClient patterns).
"""

from __future__ import annotations

import base64
import json
import sqlite3
import struct
import zipfile
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.assets import service as asset_service
from runmal.assets.imaging import make_png_thumbnail, sniff_image
from runmal.assets.models import asset_to_dict
from runmal.assets.service import build_asset_plan
from runmal.auth import data_dir, get_or_create_credential
from runmal.cards import import_card
from runmal.cards.exporter import export_png
from runmal.cards.models import CharacterCard
from runmal.cards.parser import MAX_ASSET_BYTES
from runmal.characters import service as character_service
from runmal.characters.service import create_character_from_card
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, CharacterAsset, User
from runmal.diagnostics.cleanup import (
    UNREFERENCED_CHARACTER_FILES,
    scan_cleanup,
)
from runmal.library import import_library_folder
from runmal.portable.archive import export_archive
from runmal.portable.restore import import_archive

FIXTURES = Path(__file__).parent / "fixtures"
CARDS = FIXTURES / "cards"
INTEROP = FIXTURES / "interop"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------- helpers

@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + ctype
        + data
        + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
    )


def make_png_bytes(width, height, color=(200, 30, 30), *, interlace=0) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, interlace))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def v2_card_obj(name="Png Card", **over) -> dict:
    data = {
        "name": name,
        "description": "A PNG-carried card.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": "forge",
        "extensions": {},
    }
    data.update(over)
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def make_png_card_bytes(width, height, card_obj, color=(10, 20, 30)) -> bytes:
    payload = base64.b64encode(json.dumps(card_obj).encode())
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"tEXt", b"chara\x00" + payload)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def make_jpeg_bytes(width, height) -> bytes:
    return (
        b"\xff\xd8\xff\xc0"
        + struct.pack(">H", 11)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x01\x01"
    )


def make_gif_bytes(width, height) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


def make_webp_bytes(width, height) -> bytes:
    return (
        b"RIFF"
        + struct.pack("<I", 22)
        + b"WEBP"
        + b"VP8X"
        + struct.pack("<I", 10)
        + b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )


async def create_char(factory, user_id, card, **kw) -> str:
    async with factory() as session:
        character = await create_character_from_card(session, user_id, card, **kw)
        return character.id


async def fetch_rows(factory, user_id, character_id):
    async with factory() as session:
        return await asset_service.list_assets(session, user_id, character_id)


async def fetch_dicts(factory, user_id, character_id):
    rows = await fetch_rows(factory, user_id, character_id)
    if rows is None:
        return None
    return [asset_to_dict(r) for r in rows]


async def fetch_contents(factory, user_id, character_id) -> dict:
    """{row name: content bytes or None} for every asset row."""
    rows = await fetch_rows(factory, user_id, character_id)
    out = {}
    for row in rows or []:
        found = asset_service.read_asset_content(character_id, row)
        out[row.name] = found[0] if found else None
    return out


def write(folder: Path, relpath: str, data: bytes) -> Path:
    path = folder / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- migration

EXPECTED_ASSET_COLUMNS = {
    "id", "character_id", "user_id", "kind", "name", "source_type",
    "source_uri", "source_ext", "status", "detail", "format", "media_type",
    "width", "height", "byte_size", "sha256", "storage_relpath",
    "thumbnail_relpath", "thumbnail_status", "created_at",
}


def test_migration_0020_present_and_applied(tmp_path):
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert "0020" in [m[0] for m in MIGRATIONS]
    assert "0020" in applied
    assert applied[-1] == "0031"  # head pin moved by P-036 (0027 reserved for P-035)
    assert current_revision(db_path) == "0031"


def test_character_assets_table_exists_with_contracted_columns(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "character_assets" in tables
        columns = {
            r[1] for r in conn.execute("PRAGMA table_info(character_assets)")
        }
    finally:
        conn.close()
    assert columns == EXPECTED_ASSET_COLUMNS


# ---------------------------------------------------------------- imaging

def test_sniff_png_dimensions():
    info = sniff_image(make_png_bytes(17, 9))
    assert (info.format, info.width, info.height, info.error) == ("png", 17, 9, None)


def test_sniff_jpeg_dimensions():
    info = sniff_image(make_jpeg_bytes(640, 480))
    assert (info.format, info.width, info.height, info.error) == ("jpeg", 640, 480, None)


def test_sniff_gif_dimensions():
    info = sniff_image(make_gif_bytes(32, 24))
    assert (info.format, info.width, info.height, info.error) == ("gif", 32, 24, None)


def test_sniff_webp_dimensions():
    info = sniff_image(make_webp_bytes(300, 200))
    assert (info.format, info.width, info.height, info.error) == ("webp", 300, 200, None)


def test_sniff_truncated_png_is_corrupt():
    info = sniff_image(PNG_SIGNATURE + b"\x00\x00")
    assert info.format == "png"
    assert info.error == "corrupt"
    assert info.width is None and info.height is None


def test_sniff_random_bytes_are_unknown():
    info = sniff_image(b"\x00\x01\x02definitely not an image\xff\xfe")
    assert info.format == "unknown"
    assert info.error is None


def test_make_png_thumbnail_shrinks_512x256_to_256x128():
    thumb = make_png_thumbnail(make_png_bytes(512, 256, (12, 120, 200)))
    assert thumb is not None
    info = sniff_image(thumb)
    assert (info.format, info.width, info.height) == ("png", 256, 128)


def test_make_png_thumbnail_returns_none_for_jpeg_and_interlaced():
    assert make_png_thumbnail(make_jpeg_bytes(8, 8)) is None
    assert make_png_thumbnail(make_png_bytes(8, 8, interlace=1)) is None


# ------------------------------------------------------- plan / ingest (v3)

def load_v3_rich():
    return import_card((INTEROP / "card_v3_rich.json").read_bytes(), "card.json")


def test_build_asset_plan_classifies_v3_descriptors():
    plan = build_asset_plan(load_v3_rich(), has_container_art=False, source_bytes=None)
    assert [(p.kind, p.name, p.status) for p in plan] == [
        ("card_art", "main", "missing_bytes"),
        ("expression", "amused", "missing_bytes"),
        ("background", "stairs", "external_unfetched"),
    ]
    assert plan[0].detail == "embedded_uri_unresolved"
    assert plan[2].detail == "external_uri_not_fetched"


async def test_v3_descriptors_without_bytes_ingest_as_missing_or_external(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    char_id = await create_char(factory, user_id, load_v3_rich())
    rows = await fetch_dicts(factory, user_id, char_id)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"main", "amused", "stairs"}
    assert by_name["main"]["kind"] == "card_art"
    assert by_name["main"]["status"] == "missing_bytes"
    assert by_name["main"]["source_uri"] == "embeded://avatar.png"
    assert by_name["amused"]["kind"] == "expression"
    assert by_name["amused"]["status"] == "missing_bytes"
    assert by_name["stairs"]["kind"] == "background"
    assert by_name["stairs"]["status"] == "external_unfetched"
    assert by_name["stairs"]["storage_relpath"] is None


async def test_v3_descriptors_with_charx_bytes_are_stored_byte_identical(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = load_v3_rich()
    avatar_png = make_png_bytes(6, 4, (255, 0, 0))
    amused_png = make_png_bytes(5, 5, (0, 255, 0))
    card.assets = {"avatar.png": avatar_png, "expressions/amused.png": amused_png}
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    by_name = {r["name"]: r for r in rows}
    assert by_name["main"]["status"] == "stored"
    assert by_name["main"]["format"] == "png"
    assert by_name["amused"]["status"] == "stored"
    assert by_name["stairs"]["status"] == "external_unfetched"
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["main"] == avatar_png
    assert contents["amused"] == amused_png
    assert contents["stairs"] is None


# ---------------------------------------------------------------- CHARX full

async def test_card_full_charx_stores_two_embedded_assets(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = (CARDS / "card_full.charx").read_bytes()
    card = import_card(blob, "card_full.charx")
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 2
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"avatar.png", "lore/notes.txt"}
    assert all(r["status"] == "stored" for r in rows)
    assert all(r["kind"] == "embedded" for r in rows)
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["avatar.png"] == b"FAKEPNGDATA-FULL"
    assert contents["lore/notes.txt"] == b"fjord notes"
    assert by_name["lore/notes.txt"]["thumbnail_status"] == "not_applicable"


# ------------------------------------------------------------- PNG container

async def test_exporter_png_card_via_library_stores_card_art(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    v2 = import_card((CARDS / "v2.json").read_bytes(), "v2.json")
    png_blob = export_png(v2)
    folder = tmp_path / "library"
    write(folder, "card.png", png_blob)
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.created_id
    rows = await fetch_dicts(factory, user_id, entry.created_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "card_art"
    assert row["status"] == "stored"
    assert row["format"] == "png"
    assert row["thumbnail_status"] == "ready"
    contents = await fetch_contents(factory, user_id, entry.created_id)
    assert contents["card_art"] == png_blob
    raw_rows = await fetch_rows(factory, user_id, entry.created_id)
    thumb = asset_service.read_asset_thumbnail(entry.created_id, raw_rows[0])
    assert thumb is not None
    info = sniff_image(thumb[0])
    assert info.format == "png"
    assert info.width <= 256 and info.height <= 256


async def test_constructed_512x256_png_card_thumbnail_is_exactly_256x128(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = make_png_card_bytes(512, 256, v2_card_obj("Big Png Card"))
    folder = tmp_path / "library"
    write(folder, "big.png", blob)
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.created_id
    rows = await fetch_rows(factory, user_id, entry.created_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "card_art"
    assert row.format == "png"
    assert (row.width, row.height) == (512, 256)
    assert row.thumbnail_status == "ready"
    thumb = asset_service.read_asset_thumbnail(entry.created_id, row)
    assert thumb is not None
    info = sniff_image(thumb[0])
    assert (info.width, info.height) == (256, 128)


async def test_png_card_via_create_character_from_card_source_bytes(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = make_png_card_bytes(64, 32, v2_card_obj("Direct Png Card"))
    card = import_card(blob, "direct.png")
    assert card.source_format == "png"
    char_id = await create_char(factory, user_id, card, source_bytes=blob)
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 1
    assert rows[0]["kind"] == "card_art"
    assert rows[0]["source_type"] == "container"
    assert rows[0]["status"] == "stored"
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["card_art"] == blob


# ---------------------------------------------------------------- HTTP surface

@pytest.fixture()
def app_client(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


V2_CARD = json.loads((CARDS / "v2.json").read_text())


def http_character(client) -> str:
    resp = client.post("/api/v1/characters", json={"card": V2_CARD})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_http_assets_upload_list_get_content_thumbnail(app_client):
    char_id = http_character(app_client)
    assert app_client.get(f"/api/v1/characters/{char_id}/assets").json() == []
    png = make_png_bytes(512, 256, (9, 99, 199))
    up = app_client.post(
        f"/api/v1/characters/{char_id}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", png, "image/png")},
    )
    assert up.status_code == 201, up.text
    asset = up.json()
    assert asset["kind"] == "expression"
    assert asset["name"] == "amused"
    assert asset["status"] == "stored"
    assert asset["thumbnail_status"] == "ready"
    asset_id = asset["id"]
    listed = app_client.get(f"/api/v1/characters/{char_id}/assets")
    assert listed.status_code == 200
    assert [a["id"] for a in listed.json()] == [asset_id]
    got = app_client.get(f"/api/v1/characters/{char_id}/assets/{asset_id}")
    assert got.status_code == 200
    assert got.json()["id"] == asset_id
    content = app_client.get(f"/api/v1/characters/{char_id}/assets/{asset_id}/content")
    assert content.status_code == 200
    assert content.content == png
    assert content.headers["content-type"] == "image/png"
    thumb = app_client.get(f"/api/v1/characters/{char_id}/assets/{asset_id}/thumbnail")
    assert thumb.status_code == 200
    info = sniff_image(thumb.content)
    assert info.format == "png"
    assert (info.width, info.height) == (256, 128)


def test_http_unknown_character_is_404(app_client):
    assert app_client.get("/api/v1/characters/nope/assets").status_code == 404
    assert app_client.get("/api/v1/characters/nope/assets/x").status_code == 404
    assert app_client.get("/api/v1/characters/nope/assets/x/content").status_code == 404


def test_http_unknown_asset_is_404(app_client):
    char_id = http_character(app_client)
    base = f"/api/v1/characters/{char_id}/assets/nope"
    assert app_client.get(base).status_code == 404
    assert app_client.get(base + "/content").status_code == 404
    assert app_client.get(base + "/thumbnail").status_code == 404


def test_http_content_404_for_missing_bytes_row(app_client, tmp_path):
    char_id = http_character(app_client)
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO character_assets (id, character_id, user_id, kind, name, "
            "source_type, source_uri, source_ext, status, detail, format, media_type, "
            "width, height, byte_size, sha256, storage_relpath, thumbnail_relpath, "
            "thumbnail_status, created_at) VALUES (?, ?, ?, 'card_art', 'main', "
            "'icon', 'embeded://avatar.png', 'png', 'missing_bytes', "
            "'embedded_uri_unresolved', '', '', NULL, NULL, 0, '', NULL, NULL, "
            "'not_applicable', '2026-01-01T00:00:00+00:00')",
            ("missing-asset-1", char_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    listed = app_client.get(f"/api/v1/characters/{char_id}/assets").json()
    assert [a["id"] for a in listed] == ["missing-asset-1"]
    resp = app_client.get(
        f"/api/v1/characters/{char_id}/assets/missing-asset-1/content"
    )
    assert resp.status_code == 404


def test_http_thumbnail_404_detail_for_jpeg_upload(app_client):
    char_id = http_character(app_client)
    up = app_client.post(
        f"/api/v1/characters/{char_id}/assets",
        data={"kind": "card_art", "name": "photo"},
        files={"file": ("photo.jpg", make_jpeg_bytes(64, 48), "image/jpeg")},
    )
    assert up.status_code == 201, up.text
    asset = up.json()
    assert asset["format"] == "jpeg"
    assert asset["thumbnail_status"] == "unavailable_non_png"
    resp = app_client.get(
        f"/api/v1/characters/{char_id}/assets/{asset['id']}/thumbnail"
    )
    assert resp.status_code == 404
    assert resp.json()["detail"].startswith("thumbnail_unavailable:")


def test_http_upload_bad_kind_is_400(app_client):
    char_id = http_character(app_client)
    resp = app_client.post(
        f"/api/v1/characters/{char_id}/assets",
        data={"kind": "bogus", "name": "x"},
        files={"file": ("x.png", make_png_bytes(4, 4), "image/png")},
    )
    assert resp.status_code == 400


def test_http_upload_unsafe_filename_is_400(app_client):
    char_id = http_character(app_client)
    resp = app_client.post(
        f"/api/v1/characters/{char_id}/assets",
        data={"kind": "embedded", "name": "evil"},
        files={"file": ("../../evil.png", make_png_bytes(4, 4), "image/png")},
    )
    assert resp.status_code == 400


def test_http_upload_to_missing_character_is_404(app_client):
    resp = app_client.post(
        "/api/v1/characters/nope/assets",
        data={"kind": "embedded", "name": "x"},
        files={"file": ("x.png", make_png_bytes(4, 4), "image/png")},
    )
    assert resp.status_code == 404


def test_http_assets_require_auth(tmp_path):
    db_path = tmp_path / "auth.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    anon = TestClient(create_app(create_session_factory(engine)))
    assert anon.get("/api/v1/characters/any/assets").status_code == 401
    assert anon.post(
        "/api/v1/characters/any/assets",
        data={"kind": "embedded"},
        files={"file": ("x.png", make_png_bytes(4, 4), "image/png")},
    ).status_code == 401


# ------------------------------------------------------- unknown-field keeping

async def test_asset_descriptor_extra_key_survives_stored_card_json(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    obj = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": "Extra Key Card",
            "description": "d",
            "assets": [
                {"type": "icon", "uri": "embeded://avatar.png", "name": "main",
                 "ext": "png", "x_extra": "keep-me"}
            ],
        },
    }
    card = import_card(json.dumps(obj).encode(), "card.json")
    char_id = await create_char(factory, user_id, card)
    async with factory() as session:
        character = await session.get(Character, char_id)
        stored = json.loads(character.card_json)
    descriptors = stored["data"]["assets"]
    icon = [d for d in descriptors if d.get("type") == "icon"][0]
    assert icon["x_extra"] == "keep-me"
    assert icon["uri"] == "embeded://avatar.png"


async def test_card_level_unknown_survives_create_with_assets(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card((CARDS / "card_full.charx").read_bytes(), "card_full.charx")
    char_id = await create_char(factory, user_id, card)
    async with factory() as session:
        stmt = select(CharacterAsset).where(CharacterAsset.character_id == char_id)
        result = await session.execute(stmt)
        assert len(list(result.scalars().all())) == 2
        character = await session.get(Character, char_id)
        stored = json.loads(character.card_json)
    assert stored["data"]["x_custom_unknown"] == "must-survive-charx"


# ------------------------------------------------------------- duplicate / delete

async def test_duplicate_character_clones_asset_rows_and_bytes(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card((CARDS / "card_full.charx").read_bytes(), "card_full.charx")
    char_id = await create_char(factory, user_id, card)
    async with factory() as session:
        clone = await character_service.duplicate_character(session, user_id, char_id)
        clone_id = clone.id
    original = await fetch_dicts(factory, user_id, char_id)
    cloned = await fetch_dicts(factory, user_id, clone_id)
    assert len(cloned) == len(original) == 2
    assert {r["id"] for r in cloned}.isdisjoint({r["id"] for r in original})
    assert all(r["character_id"] == clone_id for r in cloned)
    orig_contents = await fetch_contents(factory, user_id, char_id)
    clone_contents = await fetch_contents(factory, user_id, clone_id)
    assert clone_contents == orig_contents
    assert clone_contents["lore/notes.txt"] == b"fjord notes"


async def test_soft_delete_hides_assets_and_restore_brings_them_back(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card((CARDS / "card_full.charx").read_bytes(), "card_full.charx")
    char_id = await create_char(factory, user_id, card)
    assert len(await fetch_dicts(factory, user_id, char_id)) == 2
    async with factory() as session:
        assert await character_service.delete_character(session, user_id, char_id) is True
    assert await fetch_rows(factory, user_id, char_id) is None
    async with factory() as session:
        restored = await character_service.restore_character(session, user_id, char_id)
        assert restored is not None
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 2
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["avatar.png"] == b"FAKEPNGDATA-FULL"


# ---------------------------------------------------------------- bulk import

async def test_bulk_charx_entry_notes_assets_stored(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card_full.charx", (CARDS / "card_full.charx").read_bytes())
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert "assets_stored_p023:2" in entry.notes
    assert entry.created_id
    assert len(await fetch_dicts(factory, user_id, entry.created_id)) == 2


async def test_bulk_dry_run_notes_assets_would_store_and_creates_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card_full.charx", (CARDS / "card_full.charx").read_bytes())
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder, dry_run=True)
    entry = report.entries[0]
    assert report.dry_run is True
    assert "assets_would_store_p023:2" in entry.notes
    async with factory() as session:
        chars = await character_service.list_characters(session, user_id)
    assert chars == []


async def test_bulk_png_card_notes_one_stored_card_art(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card.png", (CARDS / "card.png").read_bytes())
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert "assets_stored_p023:1" in entry.notes
    rows = await fetch_dicts(factory, user_id, entry.created_id)
    assert len(rows) == 1
    assert rows[0]["kind"] == "card_art"
    assert rows[0]["status"] == "stored"


# ---------------------------------------------------------------- cleanup

async def test_cleanup_keeps_referenced_files_but_lists_stray(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = load_v3_rich()
    card.asset_refs = [r for r in card.asset_refs if r.get("type") == "icon"]
    card.assets = {"avatar.png": make_png_bytes(6, 4, (1, 2, 3))}
    char_id = await create_char(factory, user_id, card)
    raw_rows = await fetch_rows(factory, user_id, char_id)
    stored = [r for r in raw_rows if r.status == "stored"]
    assert len(stored) == 1
    char_dir = tmp_path / "assets" / "characters" / char_id
    asset_file = char_dir / stored[0].storage_relpath
    thumb_file = char_dir / stored[0].thumbnail_relpath
    assert asset_file.is_file() and thumb_file.is_file()
    stray = char_dir / "stray.bin"
    stray.write_bytes(b"hand placed")
    report = scan_cleanup(db_path=tmp_path / "test.db", base_dir=tmp_path)
    listed_paths = {Path(i.path) for i in report.items if i.path}
    assert asset_file not in listed_paths
    assert thumb_file not in listed_paths
    unref_paths = {
        Path(i.path) for i in report.by_category(UNREFERENCED_CHARACTER_FILES)
    }
    assert stray in unref_paths


# ---------------------------------------------------------------- portable

async def _make_charx_character(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card((CARDS / "card_full.charx").read_bytes(), "card_full.charx")
    char_id = await create_char(factory, user_id, card)
    return factory, user_id, char_id


async def test_portable_export_includes_character_assets_and_file_members(tmp_path):
    factory, user_id, char_id = await _make_charx_character(tmp_path)
    rows = await fetch_dicts(factory, user_id, char_id)
    dest = tmp_path / "export.runmal"
    async with factory() as session:
        info = await export_archive(session, user_id, dest, base_dir=tmp_path)
    assert info.manifest["contents"]["character_assets"] == 2
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    asset_jsons = [n for n in names if n.startswith("character_assets/")]
    assert len(asset_jsons) == 2
    for row in rows:
        member = f"assets/characters/{char_id}/{row['storage_relpath']}"
        assert member in names


async def test_portable_import_restores_row_and_file_byte_identical(tmp_path):
    factory, user_id, char_id = await _make_charx_character(tmp_path)
    rows = await fetch_dicts(factory, user_id, char_id)
    dest = tmp_path / "export.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest, base_dir=tmp_path)
    staging = tmp_path / "staging"
    report = await import_archive(dest, staging)
    assert report.ok is True
    assert report.counts["character_assets"] == 2
    staged_factory = create_session_factory(create_db_engine(Path(report.staged_db)))
    async with staged_factory() as session:
        result = await session.execute(
            select(CharacterAsset).where(CharacterAsset.character_id == char_id)
        )
        staged_rows = list(result.scalars().all())
    assert len(staged_rows) == 2
    contents = await fetch_contents(factory, user_id, char_id)
    by_name = {r.name: r for r in staged_rows}
    for name, data in contents.items():
        staged_file = staging / "assets" / "characters" / char_id / by_name[name].storage_relpath
        assert staged_file.read_bytes() == data
    assert by_name["lore/notes.txt"].id in {r["id"] for r in rows}


# ------------------------------------------------------------- corrupt uploads

def _truncated_idat_png() -> bytes:
    raw = b"".join(b"\x00" + bytes((7, 8, 9)) * 4 for _ in range(4))
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw)[:5])
        + _chunk(b"IEND", b"")
    )


async def _plain_character(factory, user_id, name="Host") -> str:
    return await create_char(factory, user_id, CharacterCard(name=name))


async def test_upload_truncated_idat_png_stored_with_unavailable_decode(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    char_id = await _plain_character(factory, user_id)
    async with factory() as session:
        row = await asset_service.add_asset(
            session, user_id, char_id, kind="embedded", name="trunc",
            filename="trunc.png", data=_truncated_idat_png(),
        )
        row_id = row.id
    rows = await fetch_dicts(factory, user_id, char_id)
    mine = [r for r in rows if r["id"] == row_id][0]
    assert mine["status"] == "stored"
    assert mine["format"] == "png"
    assert mine["thumbnail_status"] == "unavailable_decode"


async def test_upload_garbage_ihdr_png_records_corrupt_image(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    char_id = await _plain_character(factory, user_id)
    garbage = PNG_SIGNATURE + b"\x00\x00\x00\x0dJUNK" + b"\x00" * 20
    assert sniff_image(garbage).error == "corrupt"
    async with factory() as session:
        row = await asset_service.add_asset(
            session, user_id, char_id, kind="embedded", name="garbage",
            filename="garbage.png", data=garbage,
        )
        row_id = row.id
    rows = await fetch_dicts(factory, user_id, char_id)
    mine = [r for r in rows if r["id"] == row_id][0]
    assert mine["status"] == "stored"
    assert mine["detail"] == "corrupt_image"
    assert mine["format"] == "png"


# ---------------------------------------------------------------- oversize

async def test_oversize_single_asset_degrades_to_missing_bytes(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    big = b"\x00" * (MAX_ASSET_BYTES + 1)
    card = CharacterCard(name="Big Asset Card", assets={"big.bin": big})
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "big.bin"
    assert row["status"] == "missing_bytes"
    assert row["detail"] == "oversize_not_stored"
    assert row["byte_size"] == MAX_ASSET_BYTES + 1
    assert row["storage_relpath"] is None
    async with factory() as session:
        chars = await character_service.list_characters(session, user_id)
    assert [c.id for c in chars] == [char_id]


# ------------------------------------------------------- traversal + collisions

async def test_traversal_descriptor_name_verbatim_and_storage_contained(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    png = make_png_bytes(5, 5, (3, 3, 3))
    card = CharacterCard(
        name="Traversal Card",
        asset_refs=[
            {"type": "emotion", "uri": "embeded://expressions/amused.png",
             "name": "../../evil", "ext": "png"}
        ],
        assets={"expressions/amused.png": png},
    )
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "../../evil"
    assert row["status"] == "stored"
    assert row["storage_relpath"].startswith("p023/")
    p023_dir = (data_dir() / "assets" / "characters" / char_id / "p023").resolve()
    stored_path = data_dir() / "assets" / "characters" / char_id / row["storage_relpath"]
    stored_file = stored_path.resolve()
    assert stored_file.is_relative_to(p023_dir)
    assert stored_file.is_file()
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["../../evil"] == png


async def test_storage_names_distinct_for_distinct_paths_and_bytes(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    png_a = make_png_bytes(4, 4, (255, 0, 0))
    png_b = make_png_bytes(4, 4, (0, 0, 255))
    card = CharacterCard(
        name="Collision Card",
        assets={"a/amused.png": png_a, "b/amused.png": png_b},
    )
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    by_name = {r["name"]: r for r in rows}
    assert by_name["a/amused.png"]["storage_relpath"] != by_name["b/amused.png"]["storage_relpath"]
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["a/amused.png"] == png_a
    assert contents["b/amused.png"] == png_b


async def test_identical_bytes_under_colliding_keys_share_storage_relpath(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    png = make_png_bytes(4, 4, (0, 200, 0))
    # Both keys flatten to the same storage name (c__amused.png); with
    # identical bytes the second store reuses the first file.
    card = CharacterCard(
        name="Dedup Card",
        assets={"c/amused.png": png, "c__amused.png": png},
    )
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    assert len(rows) == 2
    relpaths = {r["storage_relpath"] for r in rows}
    assert len(relpaths) == 1
    assert None not in relpaths
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["c/amused.png"] == png
    assert contents["c__amused.png"] == png


async def test_distinct_bytes_under_colliding_keys_get_distinct_storage(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    png_a = make_png_bytes(4, 4, (255, 255, 0))
    png_b = make_png_bytes(4, 4, (0, 255, 255))
    card = CharacterCard(
        name="Suffix Card",
        assets={"d/amused.png": png_a, "d__amused.png": png_b},
    )
    char_id = await create_char(factory, user_id, card)
    rows = await fetch_dicts(factory, user_id, char_id)
    by_name = {r["name"]: r for r in rows}
    assert by_name["d/amused.png"]["storage_relpath"] != by_name["d__amused.png"]["storage_relpath"]
    contents = await fetch_contents(factory, user_id, char_id)
    assert contents["d/amused.png"] == png_a
    assert contents["d__amused.png"] == png_b
