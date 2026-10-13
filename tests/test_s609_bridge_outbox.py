"""S609 acceptance: durable bridge event outbox.

BRIDGE_PROTOCOL §5 + §14: ordered event ids, checkpoint/ack/replay —
a disconnect/reconnect cycle resumes without losing unacknowledged
events and without re-delivering acknowledged ones; checkpoints are
per-credential; retention is bounded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

CARD = {"name": "Warden", "system_prompt": "You are the WARDEN."}
FERRYMAN = {"name": "Ferryman", "system_prompt": "You are the FERRYMAN."}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    return client


def _bridge(client, scopes, name="outbox"):
    created = client.post(
        "/api/v1/bridge/credentials", json={"name": name, "scopes": scopes}
    ).json()
    return created, {"Authorization": f"Bearer {created['token']}"}


def _world(client):
    warden = client.post("/api/v1/characters", json={"card": CARD}).json()
    ferryman = client.post("/api/v1/characters", json={"card": FERRYMAN}).json()
    chat = client.post("/api/v1/chats", json={"title": "t", "character_id": warden["id"]}).json()
    return warden, ferryman, chat


def _full_scopes(chat, *personas):
    scopes = [
        f"chat:read:{chat['id']}",
        f"chat:write:{chat['id']}",
        f"events:read:{chat['id']}",
    ]
    return scopes + [f"persona:select:{p['id']}" for p in personas]


def _poll(client, headers, chat_id, **params):
    response = client.get(f"/api/v1/bridge/chats/{chat_id}/events", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_outbox_records_turn_and_generation_events(app_client) -> None:
    _, ferryman, chat = _world(app_client)
    _, headers = _bridge(app_client, _full_scopes(chat, ferryman))
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "user", "content": "Hail."},
    )
    app_client.post(f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={})
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=headers,
        json={"character_id": ferryman["id"]},
    )
    page = _poll(app_client, headers, chat["id"], after=0)
    kinds = [e["kind"] for e in page["events"]]
    assert kinds == ["turn_appended", "companion_turn_ready", "persona_changed"]
    ids = [e["id"] for e in page["events"]]
    assert ids == sorted(ids) and len(set(ids)) == 3  # strictly ordered, unique
    assert page["events"][1]["data"]["message_id"]
    assert page["events"][2]["data"]["to"] == ferryman["id"]
    assert page["latest"] == ids[-1]
    assert page["checkpoint"] == 0


def test_disconnect_reconnect_resumes_without_loss_or_duplication(app_client) -> None:
    _, _, chat = _world(app_client)
    _, headers = _bridge(app_client, _full_scopes(chat))
    for text in ("one", "two"):
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/turns",
            headers=headers,
            json={"speaker_kind": "user", "content": text},
        )
    first = _poll(app_client, headers, chat["id"])
    assert [e["id"] for e in first["events"]] == [1, 2]
    acked = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/events/ack",
        headers=headers,
        json={"event_id": 1},
    ).json()
    assert acked == {"chat_id": chat["id"], "checkpoint": 1}

    # "Disconnect." A third event lands while away.
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "user", "content": "three"},
    )
    # Reconnect: bare poll resumes from the checkpoint — event 1 is
    # NOT re-delivered, events 2 and 3 are NOT lost.
    resumed = _poll(app_client, headers, chat["id"])
    assert [e["id"] for e in resumed["events"]] == [2, 3]
    assert resumed["checkpoint"] == 1
    # Explicit after= replays from anywhere, regardless of checkpoint.
    replay = _poll(app_client, headers, chat["id"], after=0)
    assert [e["id"] for e in replay["events"]] == [1, 2, 3]
    # Ack is monotonic and clamps to what exists.
    assert (
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/events/ack",
            headers=headers,
            json={"event_id": 1},
        ).json()["checkpoint"]
        == 1
    )
    assert (
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/events/ack",
            headers=headers,
            json={"event_id": 9999},
        ).json()["checkpoint"]
        == 3
    )


def test_checkpoints_are_per_credential(app_client) -> None:
    _, _, chat = _world(app_client)
    _, headers_a = _bridge(app_client, _full_scopes(chat), name="a")
    _, headers_b = _bridge(app_client, _full_scopes(chat), name="b")
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers_a,
        json={"speaker_kind": "user", "content": "news"},
    )
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/events/ack",
        headers=headers_a,
        json={"event_id": 1},
    )
    assert _poll(app_client, headers_a, chat["id"])["events"] == []
    page_b = _poll(app_client, headers_b, chat["id"])
    assert [e["id"] for e in page_b["events"]] == [1]  # B has not acked
    assert page_b["checkpoint"] == 0


def test_events_scope_is_separate(app_client) -> None:
    _, _, chat = _world(app_client)
    _, reader = _bridge(app_client, [f"chat:read:{chat['id']}", f"chat:write:{chat['id']}"])
    response = app_client.get(f"/api/v1/bridge/chats/{chat['id']}/events", headers=reader)
    assert response.status_code == 403  # chat scopes do not imply events:read
    _, other = _bridge(app_client, ["events:read:another-chat"])
    response = app_client.get(f"/api/v1/bridge/chats/{chat['id']}/events", headers=other)
    assert response.status_code == 403


async def test_retention_is_bounded(tmp_path) -> None:
    from runmal.bridge import outbox
    from runmal.db.owners import get_or_create_owner

    db_path = tmp_path / "retention.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        await get_or_create_owner(session)
        for index in range(30):
            await outbox.record_event(
                session, "chat-x", "turn_appended", {"n": index}, keep_last=10
            )
        events = await outbox.list_events(session, "chat-x", after_id=0, limit=100)
    await engine.dispose()
    assert len(events) == 10
    assert events[0].data_json.find('"n": 20') >= 0  # newest window kept
    assert [e.id for e in events] == list(range(21, 31))
