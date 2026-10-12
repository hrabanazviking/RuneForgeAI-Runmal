"""S111 acceptance: chat export endpoint + management API surface."""

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def seed_chat(client, title="Export me"):
    chat_id = client.post("/api/v1/chats", json={"title": title}).json()["id"]
    client.post(f"/api/v1/chats/{chat_id}/messages", json={"role": "user", "content": "hi"})
    client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "hello"},
    )
    return chat_id


def test_export_document_shape(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    chat_id = seed_chat(client)
    doc = client.get(f"/api/v1/chats/{chat_id}/export").json()
    assert doc["format"] == "runmal-chat-export"
    assert doc["version"] == 1
    assert doc["exported_at"]
    assert doc["chat"]["id"] == chat_id
    assert doc["chat"]["title"] == "Export me"
    assert [m["content"] for m in doc["messages"]] == ["hi", "hello"]
    assert [m["role"] for m in doc["messages"]] == ["user", "assistant"]


def test_export_is_non_destructive(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    chat_id = seed_chat(client)
    client.get(f"/api/v1/chats/{chat_id}/export")
    assert client.get(f"/api/v1/chats/{chat_id}").status_code == 200
    assert len(client.get(f"/api/v1/chats/{chat_id}/messages").json()) == 2


def test_export_404_and_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/chats/missing/export").status_code == 404
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    anon = TestClient(create_app(create_session_factory(engine)))
    assert anon.get("/api/v1/chats/x/export").status_code == 401


def test_management_api_surface(tmp_path, monkeypatch) -> None:
    """Rename + delete endpoints the UI drives (S107 API, S111 UI)."""
    client = make_client(tmp_path, monkeypatch)
    chat_id = seed_chat(client, title="Old")
    renamed = client.patch(f"/api/v1/chats/{chat_id}", json={"title": "New"}).json()
    assert renamed["title"] == "New"
    assert client.delete(f"/api/v1/chats/{chat_id}").json()["deleted"] is True
    assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
