"""S201 acceptance: lorebook model + /api/v1/lorebooks CRUD + ownership."""

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.models import User
from runmal.lorebooks import service


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_migration_0004_reaches_head(tmp_path) -> None:
    # NOTE (S207/S211/S303/S306): 0006-0009 now follow 0005; HEAD is 0009.
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0010"
    assert current_revision(db_path) == "0010"


def test_lorebook_crud(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/lorebooks",
        json={"name": "Norse Lore", "description": "d", "scan_depth": 3},
    )
    assert created.status_code == 201
    book = created.json()
    book_id = book["id"]
    assert book["name"] == "Norse Lore"
    assert book["scan_depth"] == 3
    assert book["entry_count"] == 0

    listed = client.get("/api/v1/lorebooks").json()
    assert [b["id"] for b in listed] == [book_id]

    renamed = client.patch(f"/api/v1/lorebooks/{book_id}", json={"name": "New Name"})
    assert renamed.json()["name"] == "New Name"

    assert client.delete(f"/api/v1/lorebooks/{book_id}").json()["deleted"] is True
    assert client.get(f"/api/v1/lorebooks/{book_id}").status_code == 404


def test_entry_crud(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    created = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={
            "name": "Fjord",
            "content": "Cold water.",
            "keys": ["fjord", "water"],
            "secondary_keys": ["cold"],
            "priority": 50,
            "position": "after_char",
            "constant": True,
        },
    )
    assert created.status_code == 201
    entry = created.json()
    entry_id = entry["id"]
    assert entry["keys"] == ["fjord", "water"]
    assert entry["secondary_keys"] == ["cold"]
    assert entry["priority"] == 50
    assert entry["position"] == "after_char"
    assert entry["constant"] is True
    assert entry["enabled"] is True

    # Detail view nests entries.
    detail = client.get(f"/api/v1/lorebooks/{book_id}").json()
    assert detail["entry_count"] == 1
    assert detail["entries"][0]["id"] == entry_id

    updated = client.patch(
        f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
        json={"content": "Icy water.", "enabled": False},
    ).json()
    assert updated["content"] == "Icy water."
    assert updated["enabled"] is False
    assert updated["updated_at"] is not None

    assert (
        client.delete(f"/api/v1/lorebooks/{book_id}/entries/{entry_id}").json()["deleted"] is True
    )
    assert client.get(f"/api/v1/lorebooks/{book_id}/entries/{entry_id}").status_code == 404


def test_entry_activation_timing_fields(tmp_path, monkeypatch) -> None:
    # S203: sticky/cooldown/delay knobs round-trip through the API.
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    created = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={
            "name": "Echo",
            "content": "Echoes.",
            "keys": ["echo"],
            "sticky_prompts": 2,
            "cooldown_prompts": 3,
            "delay_prompts": 1,
        },
    )
    assert created.status_code == 201
    entry = created.json()
    entry_id = entry["id"]
    assert entry["sticky_prompts"] == 2
    assert entry["cooldown_prompts"] == 3
    assert entry["delay_prompts"] == 1

    updated = client.patch(
        f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
        json={"sticky_prompts": 5, "delay_prompts": 0},
    ).json()
    assert updated["sticky_prompts"] == 5
    assert updated["delay_prompts"] == 0
    assert updated["cooldown_prompts"] == 3

    bad = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={"name": "Bad", "keys": ["x"], "sticky_prompts": -1},
    )
    assert bad.status_code == 422


def test_entry_validation(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    bad = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={"name": "X", "position": "moon"},
    )
    assert bad.status_code == 422
    assert client.post("/api/v1/lorebooks/nope/entries", json={}).status_code == 404


def test_entries_ordered_by_priority(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    for name, priority in (("low", 10), ("high", 200), ("mid", 100)):
        client.post(
            f"/api/v1/lorebooks/{book_id}/entries",
            json={"name": name, "priority": priority},
        )
    names = [e["name"] for e in client.get(f"/api/v1/lorebooks/{book_id}/entries").json()]
    assert names == ["high", "mid", "low"]


def test_book_delete_cascades_entries(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    client.post(f"/api/v1/lorebooks/{book_id}/entries", json={"name": "E"})
    client.delete(f"/api/v1/lorebooks/{book_id}")
    assert client.get(f"/api/v1/lorebooks/{book_id}/entries").status_code == 404


def test_lorebook_api_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    anon = TestClient(client.app)
    assert anon.get("/api/v1/lorebooks").status_code == 401
    assert anon.post("/api/v1/lorebooks", json={"name": "B"}).status_code == 401


async def test_ownership_isolation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        user_a = User(name="A")
        user_b = User(name="B")
        session.add_all([user_a, user_b])
        await session.flush()
        book = await service.create_lorebook(session, user_a.id, "A's book")
        entry = await service.create_entry(session, user_a.id, book.id, name="E", keys=["x"])
        # B sees nothing of A's.
        assert await service.list_lorebooks(session, user_b.id) == []
        assert await service.get_lorebook(session, user_b.id, book.id) is None
        assert await service.list_entries(session, user_b.id, book.id) is None
        assert await service.get_entry(session, user_b.id, book.id, entry.id) is None
        assert await service.delete_lorebook(session, user_b.id, book.id) is False
        assert await service.delete_entry(session, user_b.id, book.id, entry.id) is False
        # B cannot plant entries in A's book either.
        with pytest.raises(KeyError):
            await service.create_entry(session, user_b.id, book.id, name="sneak")
        # A's data is untouched.
        assert (await service.get_lorebook(session, user_a.id, book.id)).name == "A's book"
    await engine.dispose()
