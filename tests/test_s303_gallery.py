"""S303 acceptance: character gallery + editor shell.

Duplicate creates an independent copy; delete is a soft delete that
retains a recoverable copy (restore = undo); the gallery page wires
search, duplicate, delete/undo, and the import dropzone.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def create_char(client):
    return client.post("/api/v1/characters", json={"card": V2_CARD}).json()


def test_duplicate_creates_independent_copy(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    original = create_char(client)
    dup = client.post(f"/api/v1/characters/{original['id']}/duplicate")
    assert dup.status_code == 201, dup.text
    copy = dup.json()
    assert copy["id"] != original["id"]
    assert copy["name"] == original["name"] + " (copy)"
    names = [c["name"] for c in client.get("/api/v1/characters").json()]
    assert original["name"] in names and copy["name"] in names
    # editing the copy does not touch the original
    client.patch(
        f"/api/v1/characters/{copy['id']}/editor",
        json={"personality": "Copy only."},
    )
    orig_view = client.get(f"/api/v1/characters/{original['id']}/editor").json()
    assert orig_view["personality"] == V2_CARD["personality"]
    assert client.post("/api/v1/characters/nope/duplicate").status_code == 404


def test_delete_is_soft_and_restorable(tmp_path, monkeypatch) -> None:
    client, db_path = make_client(tmp_path, monkeypatch)
    char = create_char(client)
    deleted = client.delete(f"/api/v1/characters/{char['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["undoable"] is True
    # hidden everywhere...
    assert client.get("/api/v1/characters").json() == []
    assert client.get(f"/api/v1/characters/{char['id']}").status_code == 404
    # ...but the row (the recoverable copy) is retained
    import sqlite3

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT deleted_at FROM characters WHERE id = ?", (char["id"],)
    ).fetchone()
    assert row is not None and row[0] is not None
    # second delete: already gone
    assert client.delete(f"/api/v1/characters/{char['id']}").status_code == 404
    # undo
    restored = client.post(f"/api/v1/characters/{char['id']}/restore")
    assert restored.status_code == 200
    assert [c["id"] for c in client.get("/api/v1/characters").json()] == [char["id"]]
    # restoring a live character conflicts; restoring a ghost 404s
    assert client.post(f"/api/v1/characters/{char['id']}/restore").status_code == 409
    assert client.post("/api/v1/characters/ghost/restore").status_code == 404


def test_gallery_ui_page(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    page = client.get("/gallery")
    assert page.status_code == 200
    for marker in ('id="gallery-grid"', 'id="search"', 'id="dropzone"',
                   'id="import-file"', 'id="undo-banner"', "gallery.js"):
        assert marker in page.text, marker
    js = client.get("/static/gallery.js")
    assert js.status_code == 200
    for needle in ("/duplicate", "/restore", "dataTransfer", "/api/v1/characters"):
        assert needle in js.text, needle
