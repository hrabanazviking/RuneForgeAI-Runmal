"""S107 acceptance: chat service + /api/v1/chats."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS

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


def _apply_up_to(db_path, revision: str) -> None:
    """Test helper: apply migrations only up to (and including) `revision`."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for rev, _desc, module in MIGRATIONS:
            if rev > revision:
                break
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (rev, "test"),
            )
            conn.commit()
    finally:
        conn.close()


def test_migration_0003_upgrades_from_0002(tmp_path) -> None:
    # NOTE (S201/S203/S207/S211/S303): 0004-0009 now also apply after 0003;
    # the upgrade path under test is 0002 -> 0003, with HEAD reached after.
    db_path = tmp_path / "m.db"
    _apply_up_to(db_path, "0002")
    assert current_revision(db_path) == "0002"
    assert migrate_to_head(db_path) == ["0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011"]
    assert current_revision(db_path) == "0011"


def test_chat_crud(app_client) -> None:
    created = app_client.post("/api/v1/chats", json={"title": "First"}).json()
    assert created["title"] == "First"
    assert created["message_count"] == 0
    chat_id = created["id"]

    listed = app_client.get("/api/v1/chats").json()
    assert [c["id"] for c in listed] == [chat_id]

    fetched = app_client.get(f"/api/v1/chats/{chat_id}").json()
    assert fetched["messages"] == []

    renamed = app_client.patch(f"/api/v1/chats/{chat_id}", json={"title": "Renamed"}).json()
    assert renamed["title"] == "Renamed"

    assert app_client.get("/api/v1/chats/missing").status_code == 404

    deleted = app_client.delete(f"/api/v1/chats/{chat_id}").json()
    assert deleted["deleted"] is True
    assert app_client.get(f"/api/v1/chats/{chat_id}").status_code == 404
    assert app_client.get("/api/v1/chats").json() == []


def test_chat_with_character(app_client) -> None:
    char_id = app_client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]
    created = app_client.post("/api/v1/chats", json={"title": "RP", "character_id": char_id}).json()
    assert created["character_id"] == char_id

    resp = app_client.post("/api/v1/chats", json={"character_id": "no-such-char"})
    assert resp.status_code == 404


def test_message_append_and_history_order(app_client) -> None:
    chat_id = app_client.post("/api/v1/chats", json={}).json()["id"]
    m1 = app_client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": "Hail"}
    ).json()
    m2 = app_client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": "assistant", "content": "Hail back"}
    ).json()
    assert m1["updated_at"] is None
    history = app_client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert [m["id"] for m in history] == [m1["id"], m2["id"]]
    assert [m["content"] for m in history] == ["Hail", "Hail back"]
    assert app_client.get(f"/api/v1/chats/{chat_id}").json()["message_count"] == 2


def test_message_edit_keeps_stable_id_and_sets_mutation_timestamp(app_client) -> None:
    chat_id = app_client.post("/api/v1/chats", json={}).json()["id"]
    msg_id = app_client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": "before"}
    ).json()["id"]
    edited = app_client.patch(
        f"/api/v1/chats/{chat_id}/messages/{msg_id}", json={"content": "after"}
    ).json()
    assert edited["id"] == msg_id
    assert edited["content"] == "after"
    assert edited["updated_at"] is not None
    assert edited["updated_at"] >= edited["created_at"]
    history = app_client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert history[0]["content"] == "after"
    assert (
        app_client.patch(
            f"/api/v1/chats/{chat_id}/messages/missing", json={"content": "x"}
        ).status_code
        == 404
    )


def test_message_delete_reflected_in_history(app_client) -> None:
    chat_id = app_client.post("/api/v1/chats", json={}).json()["id"]
    msg_id = app_client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": "bye"}
    ).json()["id"]
    assert app_client.delete(f"/api/v1/chats/{chat_id}/messages/{msg_id}").json()["deleted"] is True
    assert app_client.get(f"/api/v1/chats/{chat_id}/messages").json() == []
    assert app_client.delete(f"/api/v1/chats/{chat_id}/messages/{msg_id}").status_code == 404


def test_mutation_events_emitted_for_memory_sync(app_client) -> None:
    chat_id = app_client.post("/api/v1/chats", json={"title": "E"}).json()["id"]
    msg_id = app_client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": "one"}
    ).json()["id"]
    app_client.patch(f"/api/v1/chats/{chat_id}", json={"title": "E2"})
    app_client.patch(f"/api/v1/chats/{chat_id}/messages/{msg_id}", json={"content": "two"})
    app_client.delete(f"/api/v1/chats/{chat_id}/messages/{msg_id}")
    events = app_client.get(f"/api/v1/chats/{chat_id}/events").json()
    kinds = [e["kind"] for e in events]
    assert kinds == [
        "chat.created",
        "message.appended",
        "chat.renamed",
        "message.edited",
        "message.deleted",
    ]
    assert all(e["chat_id"] == chat_id for e in events)
    assert events[1]["message_id"] == msg_id
    assert events[2]["data"] == {"title": "E2"}
    assert app_client.get("/api/v1/chats/missing/events").status_code == 404


def test_message_role_validation(app_client) -> None:
    chat_id = app_client.post("/api/v1/chats", json={}).json()["id"]
    assert (
        app_client.post(
            f"/api/v1/chats/{chat_id}/messages", json={"role": "hacker", "content": "x"}
        ).status_code
        == 422
    )
    assert (
        app_client.post(
            f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": ""}
        ).status_code
        == 422
    )


def test_chats_require_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    assert client.get("/api/v1/chats").status_code == 401
    assert client.post("/api/v1/chats", json={}).status_code == 401
