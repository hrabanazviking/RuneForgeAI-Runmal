"""Roadmap S210 acceptance: group chats — room / members / per-message
speaker, with API + data tests.

The persistent layer beneath the in-memory turn core: a group room is
created with a roster of member characters, owns a transcript chat, and
every posted message records who spoke (character id + name snapshot).
Membership changes never rewrite historical speaker identity.
"""

import copy
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
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0016"  # bridge-credentials migration is the head
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_group(client, name="Mead Hall", members=()):
    resp = client.post("/api/v1/groups", json={"name": name, "member_character_ids": list(members)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_group_requires_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    client.headers.pop("Authorization")
    assert client.get("/api/v1/groups").status_code == 401
    assert client.post("/api/v1/groups", json={"name": "x"}).status_code == 401


def test_create_group_with_roster(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    assert group["name"] == "Mead Hall"
    assert group["chat_id"]  # the room owns a transcript chat
    assert group["member_count"] == 2
    assert group["message_count"] == 0
    # Roster order is the order members were supplied in.
    assert [m["character_id"] for m in group["members"]] == [bryn, una]
    assert [m["name"] for m in group["members"]] == ["Bryn", "Una"]
    assert [m["position"] for m in group["members"]] == [0, 1]

    listed = client.get("/api/v1/groups").json()
    assert [g["id"] for g in listed] == [group["id"]]
    fetched = client.get(f"/api/v1/groups/{group['id']}").json()
    assert fetched["members"] == group["members"]


def test_create_group_rejects_unknown_member(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/groups", json={"name": "x", "member_character_ids": ["nope"]})
    assert resp.status_code == 422
    assert client.get("/api/v1/groups").json() == []  # nothing half-created


def test_group_unknown_404(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/groups/nope").status_code == 404
    assert client.delete("/api/v1/groups/nope").status_code == 404
    assert client.get("/api/v1/groups/nope/messages").status_code == 404


def test_member_add_remove(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn])

    added = client.post(f"/api/v1/groups/{group['id']}/members", json={"character_id": una})
    assert added.status_code == 201, added.text
    assert added.json() == {"character_id": una, "name": "Una", "position": 1,
                            "talkativeness": 0.5, "muted": False}

    dup = client.post(f"/api/v1/groups/{group['id']}/members", json={"character_id": una})
    assert dup.status_code == 422

    removed = client.delete(f"/api/v1/groups/{group['id']}/members/{una}")
    assert removed.status_code == 200
    fetched = client.get(f"/api/v1/groups/{group['id']}").json()
    assert [m["character_id"] for m in fetched["members"]] == [bryn]
    assert client.delete(f"/api/v1/groups/{group['id']}/members/{una}").status_code == 404


def test_messages_carry_per_message_speaker(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    kol = make_character(client, "Kol")  # not a member
    group = make_group(client, members=[bryn, una])
    gid = group["id"]

    r1 = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": "user", "content": "Speak, friends."},
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["role"] == "user"
    assert r1.json()["speaker_id"] is None

    r2 = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": bryn, "content": "The road is long."},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["role"] == "assistant"
    assert r2.json()["speaker_id"] == bryn
    assert r2.json()["speaker_name"] == "Bryn"

    # A character who is not a member cannot speak in the room.
    r3 = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": kol, "content": "Let me in!"},
    )
    assert r3.status_code == 422

    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    assert [m["content"] for m in transcript] == ["Speak, friends.", "The road is long."]
    assert [m["speaker_name"] for m in transcript] == [None, "Bryn"]
    fetched = client.get(f"/api/v1/groups/{gid}").json()
    assert fetched["message_count"] == 2


def test_speaker_snapshot_survives_member_removal(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    group = make_group(client, members=[bryn])
    gid = group["id"]
    client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": bryn, "content": "I was here."},
    )
    assert client.delete(f"/api/v1/groups/{gid}/members/{bryn}").status_code == 200

    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    assert len(transcript) == 1
    # History is not rewritten: Bryn still shows as the speaker.
    assert transcript[0]["speaker_id"] == bryn
    assert transcript[0]["speaker_name"] == "Bryn"
    # ...but Bryn can no longer speak.
    resp = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": bryn, "content": "Again!"},
    )
    assert resp.status_code == 422


def test_delete_group_removes_room_and_transcript(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    group = make_group(client, members=[bryn])
    gid, chat_id = group["id"], group["chat_id"]
    client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": "user", "content": "Hello."},
    )
    assert client.delete(f"/api/v1/groups/{gid}").status_code == 200
    assert client.get(f"/api/v1/groups/{gid}").status_code == 404
    assert client.get("/api/v1/groups").json() == []
    # The room transcript went with the group (FK cascade).
    assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
    assert client.get(f"/api/v1/chats/{chat_id}/messages").status_code == 404
