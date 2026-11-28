"""FIX-AVATAR: filename sanitisation contract.

Ordinary realistic photo names LAND (sanitised); traversal shapes
and unsupported extensions are refused in plain words; the 16 MiB
cap still answers 413. Repro base: the 2026-11-27 live matrix in
which \"IMG 20251127 1205.jpg\" and kin got HTTP 400 \"bad filename\".
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import (
    IMAGE_EXTENSIONS,
    MAX_FILENAME_LEN,
    UnsafeFilenameError,
    validate_asset_filename,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415478da626001000000ffff03000006000557bfabd40000000049454e44ae426082")


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# -- sanitiser unit contract -------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("IMG 20251127 1205.jpg", "IMG_20251127_1205.jpg"),
    ("photo (1).jpg", "photo__1_.jpg"),
    ("volmarr's photo.jpg", "volmarr_s_photo.jpg"),
    ("mynd_\u00fe.jpg", "mynd__.jpg"),
    ("avatar.png", "avatar.png"),
    ("My Photo.JPG", "My_Photo.jpg"),
    ("clean-camera_01.jpeg", "clean-camera_01.jpeg"),
])
def test_ordinary_names_land_sanitised(raw, expected):
    assert validate_asset_filename(raw, IMAGE_EXTENSIONS) == expected
    # idempotent: a stored name re-validates to itself (read road)
    assert validate_asset_filename(expected, IMAGE_EXTENSIONS) == expected


def test_long_name_truncated_to_cap_with_extension():
    safe = validate_asset_filename("a" * 136 + ".jpg", IMAGE_EXTENSIONS)
    assert len(safe) == MAX_FILENAME_LEN
    assert safe.endswith(".jpg")


@pytest.mark.parametrize("raw", [
    "../../evil.png", "..\\evil.png", "/abs.png", "a/b.png",
    "..", ".", "", "   ", "evil\\.png",
])
def test_traversal_and_empty_names_refused(raw):
    with pytest.raises(UnsafeFilenameError):
        validate_asset_filename(raw, IMAGE_EXTENSIONS)


@pytest.mark.parametrize("raw", ["!!!.jpg", ".png", "---.jpg"])
def test_name_sanitising_to_nothing_refused(raw):
    with pytest.raises(UnsafeFilenameError):
        validate_asset_filename(raw, IMAGE_EXTENSIONS)


def test_heic_refused_with_display_words():
    with pytest.raises(UnsafeFilenameError) as exc:
        validate_asset_filename("photo.heic", IMAGE_EXTENSIONS)
    words = str(exc.value).lower()
    assert "heic" in words and "browsers cannot display" in words
    assert "jpg" in words and "png" in words


@pytest.mark.parametrize("raw", ["evil.exe", "photo.bmp", "noext", "x" * 200])
def test_unsupported_extension_refused_with_words(raw):
    with pytest.raises(UnsafeFilenameError) as exc:
        validate_asset_filename(raw, IMAGE_EXTENSIONS)
    assert "accepted" in str(exc.value)


# -- API level: avatar + asset roads inherit the contract ---------------

def _char(app_client):
    return app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]


@pytest.mark.parametrize("raw,expected", [
    ("IMG 20251127 1205.jpg", "IMG_20251127_1205.jpg"),
    ("photo (1).jpg", "photo__1_.jpg"),
    ("volmarr's photo.jpg", "volmarr_s_photo.jpg"),
    ("mynd_\u00fe.jpg", "mynd__.jpg"),
])
def test_avatar_upload_with_realistic_name_lands(app_client, raw, expected):
    char_id = _char(app_client)
    resp = app_client.post(f"/api/v1/characters/{char_id}/avatar",
                           files={"file": (raw, PNG, "image/png")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == expected
    got = app_client.get(f"/api/v1/characters/{char_id}/avatar")
    assert got.status_code == 200 and got.content == PNG


def test_avatar_upload_long_name_lands(app_client):
    char_id = _char(app_client)
    resp = app_client.post(f"/api/v1/characters/{char_id}/avatar",
                           files={"file": ("a" * 136 + ".jpg", PNG, "image/jpeg")})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["filename"]) == MAX_FILENAME_LEN


def test_avatar_heic_refusal_words_over_api(app_client):
    char_id = _char(app_client)
    resp = app_client.post(f"/api/v1/characters/{char_id}/avatar",
                           files={"file": ("photo.heic", b"data", "image/heic")})
    assert resp.status_code == 400
    assert "browsers cannot display" in resp.json()["detail"]


def test_avatar_traversal_still_refused_over_api(app_client):
    char_id = _char(app_client)
    resp = app_client.post(f"/api/v1/characters/{char_id}/avatar",
                           files={"file": ("../../evil.png", PNG, "image/png")})
    assert resp.status_code == 400


def test_asset_upload_with_spaced_name_lands(app_client):
    char_id = _char(app_client)
    resp = app_client.post(f"/api/v1/characters/{char_id}/assets",
                           files={"file": ("my photo.jpg", PNG, "image/jpeg")},
                           data={"kind": "embedded", "name": "my photo"})
    assert resp.status_code == 201, resp.text
