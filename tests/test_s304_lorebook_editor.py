"""S304 acceptance: lorebook editor UI + import/export integration.

Import of fixture books in 2 formats (native + world-info), export
round-trip, editor CRUD through the API the UI drives, and page wiring.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.lorebooks.transfer import parse_import

FIXTURES = Path(__file__).parent / "fixtures" / "lorebooks"
NATIVE = json.loads((FIXTURES / "native.json").read_text())
WORLDINFO = json.loads((FIXTURES / "worldinfo.json").read_text())


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_import_native_fixture(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/lorebooks/import", json=NATIVE)
    assert resp.status_code == 201, resp.text
    book = resp.json()
    assert book["name"] == "Fixture Native Book"
    assert book["entry_count"] == 2
    entries = client.get(f"/api/v1/lorebooks/{book['id']}/entries").json()
    harbor = next(e for e in entries if e["name"] == "Harbor")
    assert harbor["keys"] == ["harbor", "port"]
    assert harbor["secondary_keys"] == ["winter"]
    assert harbor["sticky_prompts"] == 1
    tide = next(e for e in entries if e["name"] == "Tide")
    assert tide["constant"] is True and tide["position"] == "after_char"


def test_import_worldinfo_fixture(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/lorebooks/import", json=WORLDINFO)
    assert resp.status_code == 201, resp.text
    book = resp.json()
    assert book["name"] == "Fixture World Info"
    entries = client.get(f"/api/v1/lorebooks/{book['id']}/entries").json()
    dragon = next(e for e in entries if e["name"] == "Dragon")
    assert dragon["keys"] == ["dragon", "wyrm"]
    assert dragon["secondary_keys"] == ["mountain"]
    assert dragon["priority"] == 200  # order -> priority
    assert dragon["position"] == "before_char"  # position 0
    ale = next(e for e in entries if e["name"] == "Ale")
    assert ale["enabled"] is False  # disable -> not enabled
    assert ale["constant"] is True
    assert ale["position"] == "after_char"  # position 1


def test_export_import_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks/import", json=NATIVE).json()
    exported = client.get(f"/api/v1/lorebooks/{book['id']}/export")
    assert exported.status_code == 200
    shape = exported.json()
    assert shape["format"] == "runmal-lorebook"
    again = client.post("/api/v1/lorebooks/import", json=shape)
    assert again.status_code == 201
    entries = client.get(f"/api/v1/lorebooks/{again.json()['id']}/entries").json()
    assert {e["name"] for e in entries} == {"Harbor", "Tide"}


def test_parse_import_rejects_garbage() -> None:
    for bad in ({"nope": 1}, {"entries": 42}, {"entries": []}, ["x"]):
        try:
            parse_import(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted garbage: {bad!r}")


def test_editor_crud_flow(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "Editorial"}).json()
    entry = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Keep", "content": "v1", "keys": ["keep"]},
    )
    assert entry.status_code == 201
    entry = entry.json()
    patched = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{entry['id']}",
        json={"keys": ["keep", "hold"], "sticky_prompts": 3},
    )
    assert patched.status_code == 200
    assert patched.json()["keys"] == ["keep", "hold"]
    assert patched.json()["sticky_prompts"] == 3
    assert client.delete(
        f"/api/v1/lorebooks/{book['id']}/entries/{entry['id']}"
    ).status_code == 200
    assert client.get(f"/api/v1/lorebooks/{book['id']}/entries").json() == []


def test_lorebooks_ui_page(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/lorebooks")
    assert page.status_code == 200
    for marker in ('id="book-select"', 'id="entry-table"', 'id="entry-form"',
                   'id="e-keys"', 'id="import-file"', 'id="export-link"',
                   "lorebooks.js"):
        assert marker in page.text, marker
    js = client.get("/static/lorebooks.js")
    assert js.status_code == 200
    assert "/api/v1/lorebooks/import" in js.text
    assert "/export" in js.text
