"""S410 (roadmap): memory browser UI.

Acceptance: UI tests — inspect/search plus provenance/witness/status
display over the API and the server-rendered page.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.owners import get_or_create_owner
from runmal.memory import service


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def seed(factory):
    async def go():
        async with factory() as session:
            owner = await get_or_create_owner(session)
            await service.create_memory(
                session, owner.id, content="Volmarr lives in Schenectady.",
                subject="Volmarr", predicate="lives_in", scope="witnesses",
                witnesses=("char-a",), extractor={"kind": "fake", "model": "fx"},
                sources=(("message", "m1", "chat-1"),))
            await service.create_memory(
                session, owner.id, content="An old disputed claim.",
                state="disputed")
            await session.commit()
            return owner.id
    return asyncio.run(go())


def test_browser_api_lists_with_provenance_witness_status(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    seed(factory)
    resp = client.get("/api/v1/memories")
    assert resp.status_code == 200
    memories = resp.json()["memories"]
    assert len(memories) == 2
    fact = next(m for m in memories if m["subject"] == "Volmarr")
    assert fact["state"] == "active"
    assert fact["witnesses"] == ["char-a"]
    assert fact["extractor"]["model"] == "fx"
    assert fact["sources"] == [
        {"memory_id": fact["id"], "source_kind": "message",
         "source_id": "m1", "chat_id": "chat-1"}]
    # Search + state filter.
    found = client.get("/api/v1/memories", params={"q": "schenectady"}).json()
    assert [m["id"] for m in found["memories"]] == [fact["id"]]
    disputed = client.get("/api/v1/memories", params={"state": "disputed"}).json()
    assert len(disputed["memories"]) == 1
    # Detail + 404.
    detail = client.get(f"/api/v1/memories/{fact['id']}")
    assert detail.status_code == 200
    assert client.get("/api/v1/memories/nope").status_code == 404


def test_browser_page_renders_status_and_scope(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    seed(factory)
    page = client.get("/memories")
    assert page.status_code == 200
    assert "Memory Browser" in page.text
    assert "Volmarr lives in Schenectady." in page.text
    assert "disputed" in page.text and "witnesses" in page.text


def test_browser_requires_auth(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    client.headers.pop("Authorization")
    assert client.get("/api/v1/memories").status_code == 401
