"""S207 acceptance: sampling presets CRUD + round-trip tests.

Named variable-shape canonical parameter bags with a prompt-template
reference: create/read/update/delete, name uniqueness, canonical field
validation, unknown-field passthrough, and JSON round-trip fidelity.
"""

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.presets.service import validate_params


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


BAG = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_tokens": 512,
    "frequency_penalty": 0.2,
    "stop": ["<|end|>", "User:"],
    "seed": 42,
    "my_backend_knob": {"nested": [1, 2]},  # unknown field: rides along
}


def test_crud_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/presets",
        json={"name": "creative", "params": BAG, "template_ref": "chat-v1"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    preset_id = body["id"]
    assert body["name"] == "creative"
    assert body["params"] == BAG  # exact round trip, unknowns included
    assert body["template_ref"] == "chat-v1"

    listed = client.get("/api/v1/presets")
    assert [p["id"] for p in listed.json()] == [preset_id]

    fetched = client.get(f"/api/v1/presets/{preset_id}")
    assert fetched.json()["params"] == BAG

    patched = client.patch(
        f"/api/v1/presets/{preset_id}",
        json={"params": {"temperature": 1.2}, "template_ref": "chat-v2"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["params"] == {"temperature": 1.2}
    assert patched.json()["template_ref"] == "chat-v2"

    deleted = client.delete(f"/api/v1/presets/{preset_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/presets/{preset_id}").status_code == 404
    assert client.get("/api/v1/presets").json() == []


def test_duplicate_name_conflicts(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.post("/api/v1/presets", json={"name": "x"}).status_code == 201
    dup = client.post("/api/v1/presets", json={"name": "x"})
    assert dup.status_code == 409


def test_invalid_bags_rejected(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bad_bags = [
        {"temperature": -0.1},
        {"top_p": 1.5},
        {"top_p": 0},
        {"top_k": True},  # bool is not an int
        {"max_tokens": 0},
        {"stop": ["ok", 7]},
        {"seed": -1},
    ]
    for bag in bad_bags:
        resp = client.post("/api/v1/presets", json={"name": "n", "params": bag})
        assert resp.status_code == 422, bag
    # non-JSON-serializable values fail service-side validation (the HTTP
    # layer can't transport them at all)
    with pytest.raises(ValueError):
        validate_params({"mystery": object()})
    with pytest.raises(ValueError):
        validate_params([1, 2])  # not an object


def test_validate_params_normalizes(tmp_path, monkeypatch) -> None:
    assert validate_params(None) == {}
    assert validate_params({}) == {}
    # canonical fields pass through with types intact
    assert validate_params({"temperature": 1, "top_k": 0}) == {
        "temperature": 1,
        "top_k": 0,
    }


def test_rename_to_taken_name_conflicts(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    a = client.post("/api/v1/presets", json={"name": "a"}).json()["id"]
    client.post("/api/v1/presets", json={"name": "b"})
    resp = client.patch(f"/api/v1/presets/{a}", json={"name": "b"})
    assert resp.status_code == 409


def test_presets_require_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    anon = TestClient(client.app)
    assert anon.get("/api/v1/presets").status_code in (401, 403)
    assert anon.post("/api/v1/presets", json={"name": "z"}).status_code in (401, 403)
