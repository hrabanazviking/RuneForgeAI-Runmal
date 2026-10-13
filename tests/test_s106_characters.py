"""S106 acceptance: character service + /api/v1/characters."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


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


def test_migration_0002_applied(tmp_path) -> None:
    # NOTE (S107/S201/S203/S207/S211/S303): fresh DBs apply 0003 through 0013;
    # the 0002 assertions check the revision lands in the chain, upgrade
    # ordering holds.
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert "0002" in applied and applied.index("0002") < applied.index("0003")
    assert current_revision(db_path) == "0016"


def test_character_crud(app_client) -> None:
    created = app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()
    assert created["name"] == "Test V2"
    assert created["has_avatar"] is False
    char_id = created["id"]

    listed = app_client.get("/api/v1/characters").json()
    assert [c["id"] for c in listed] == [char_id]

    fetched = app_client.get(f"/api/v1/characters/{char_id}").json()
    assert fetched["name"] == "Test V2"

    renamed = app_client.patch(f"/api/v1/characters/{char_id}", json={"name": "Renamed"}).json()
    assert renamed["name"] == "Renamed"

    assert app_client.get("/api/v1/characters/missing").status_code == 404

    deleted = app_client.delete(f"/api/v1/characters/{char_id}").json()
    assert deleted["deleted"] is True
    assert app_client.get(f"/api/v1/characters/{char_id}").status_code == 404
    assert app_client.get("/api/v1/characters").json() == []


def test_character_create_rejects_bad_card(app_client) -> None:
    resp = app_client.post("/api/v1/characters", json={"card": {"no": "name"}})
    assert resp.status_code == 422


def test_avatar_upload_download(app_client) -> None:
    char_id = app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c4944415478da626001000000ffff03000006000557bfabd40000000049454e44ae426082"
    )
    uploaded = app_client.post(
        f"/api/v1/characters/{char_id}/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
    ).json()
    assert uploaded["filename"] == "avatar.png"
    assert app_client.get(f"/api/v1/characters/{char_id}").json()["has_avatar"] is True

    resp = app_client.get(f"/api/v1/characters/{char_id}/avatar")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == png_bytes


@pytest.mark.parametrize(
    "evil_name", ["../../evil.png", "..\\evil.png", "/abs.png", "a/b.png", "", "x" * 200]
)
def test_avatar_rejects_unsafe_filenames(app_client, evil_name) -> None:
    char_id = app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]
    resp = app_client.post(
        f"/api/v1/characters/{char_id}/avatar",
        files={"file": (evil_name or "unnamed", b"data", "image/png")},
    )
    assert resp.status_code == 400, evil_name


def test_avatar_rejects_bad_extension(app_client) -> None:
    char_id = app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]
    resp = app_client.post(
        f"/api/v1/characters/{char_id}/avatar",
        files={"file": ("evil.exe", b"data", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_characters_require_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    assert client.get("/api/v1/characters").status_code == 401
    assert client.post("/api/v1/characters", json={"card": V2_CARD}).status_code == 401
