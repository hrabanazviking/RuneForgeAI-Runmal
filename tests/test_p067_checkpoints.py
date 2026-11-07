"""P-067 Checkpoints battery (BUILDER C).

Pins the checkpoint contract from hidden_files/P067_DESIGN.md:
named chat snapshots (bookmarks) stored as self-contained,
checksum-sealed JSON files (no DB rows, NO new migration -- head
stays PROVISIONAL 0037), and restore-as-new (restoring NEVER
writes into the source chat; it creates a brand-new root chat
carrying the snapshot's settings and messages, swipe decks
included).

Areas (design section 7): A create/list/get round-trip,
B payload fidelity (archive member shape + checksum),
C restore-as-new correctness, D source untouched + events,
E delete, F isolation (foreign user / foreign checkpoint),
G refusals and edges, H pins (migration head, archive parity,
chat-deletion interplay).
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import checkpoints
from runmal.chats import service as svc
from runmal.chats.checkpoints import CheckpointError
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.portable.archive import export_archive, row_to_dict

DEFAULT_NAME_RE = re.compile(r"^Checkpoint \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$")
META_KEYS = {"id", "chat_id", "name", "created_at", "message_count", "chat_title"}
UNKNOWN_ID = "12345678-1234-4234-9234-1234567890ab"


# ---------------- REST harness (copied from test_p066_branches) ----------------


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


def _chat(client, title="Saga"):
    r = client.post("/api/v1/chats", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _get_chat(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _msg(client, chat_id, content, role="user"):
    r = client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": role, "content": content}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _history(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert r.status_code == 200, r.text
    return r.json()


def _contents(client, chat_id):
    return [m["content"] for m in _history(client, chat_id)]


def _events(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/events")
    assert r.status_code == 200, r.text
    return r.json()


def _ckpt_events(client, chat_id):
    return [e for e in _events(client, chat_id) if e["kind"].startswith("checkpoint.")]


def _seed_chat(client, title="Saga", contents=("one", "two", "three")):
    chat = _chat(client, title)
    msgs = [_msg(client, chat["id"], c) for c in contents]
    return chat, msgs


def _create_cp(client, chat_id, **body):
    return client.post(f"/api/v1/chats/{chat_id}/checkpoints", json=body)


def _create_cp_ok(client, chat_id, **body):
    r = _create_cp(client, chat_id, **body)
    assert r.status_code == 201, r.text
    return r.json()


def _list_cp(client, chat_id):
    return client.get(f"/api/v1/chats/{chat_id}/checkpoints")


def _get_cp(client, chat_id, checkpoint_id):
    return client.get(f"/api/v1/chats/{chat_id}/checkpoints/{checkpoint_id}")


def _restore_cp(client, chat_id, checkpoint_id, **body):
    return client.post(
        f"/api/v1/chats/{chat_id}/checkpoints/{checkpoint_id}/restore", json=body
    )


def _delete_cp(client, chat_id, checkpoint_id):
    return client.delete(f"/api/v1/chats/{chat_id}/checkpoints/{checkpoint_id}")


def _cp_file(tmp_path, chat_id, checkpoint_id) -> Path:
    matches = list(
        (tmp_path / "checkpoints").glob(f"*/{chat_id}/{checkpoint_id}.json")
    )
    assert len(matches) == 1, matches
    return matches[0]


def _cp_doc(tmp_path, chat_id, checkpoint_id) -> dict:
    return json.loads(_cp_file(tmp_path, chat_id, checkpoint_id).read_text("utf-8"))


def _rewrite_cp_file(tmp_path, chat_id, checkpoint_id, doc_or_text) -> Path:
    path = _cp_file(tmp_path, chat_id, checkpoint_id)
    text = doc_or_text if isinstance(doc_or_text, str) else json.dumps(doc_or_text)
    path.write_text(text, encoding="utf-8")
    return path


def _canonical(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal(doc: dict) -> dict:
    """Recompute a document's checksum in-test (for hand-edited payloads)."""
    doc["checksum"] = hashlib.sha256(
        _canonical({"chat": doc["chat"], "messages": doc["messages"]})
    ).hexdigest()
    return doc


# ---------------- service harness (copied from test_p065_swipes) ----------------


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def _svc_chat(factory, user_id, title="Hall", contents=("one", "two")):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, title)
        for content in contents:
            await svc.append_message(session, user_id, chat.id, "user", content)
        return chat.id


# ---------------- H. migration pin (NO new migration) ----------------


def test_migration_head_is_0037_provisional(tmp_path):
    # Banking heal (P-068 banking): this slice took NO migration --
    # 0037 was the head when the battery was written; in the merged
    # tree 0037 stands at [-2] and the head is P-068's 0038 (the only
    # 0038 in the registry, landed after this slice). Pins reworked
    # to merged truth at the merged positions.
    assert MIGRATIONS[-2][0] == "0037"
    assert "PROVISIONAL" in MIGRATIONS[-2][1]
    assert MIGRATIONS[-1][0] == "0038"
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-2] == "0037"
    assert applied[-1] == "0038"
    assert current_revision(db_path) == "0038"


# ---------------- A. create / list / get round-trip ----------------


def test_create_named_roundtrip(app_client, tmp_path):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="  Mark  ")
    assert set(created) == META_KEYS
    assert created["chat_id"] == chat["id"]
    assert created["name"] == "Mark"  # explicit name honoured and stripped
    assert created["message_count"] == 3
    assert created["chat_title"] == "Saga"
    assert created["id"]

    # the file on disk is the design 1.3 document
    doc = _cp_doc(tmp_path, chat["id"], created["id"])
    assert doc["format"] == "runmal-checkpoint"
    assert doc["format_version"] == 1
    assert doc["id"] == created["id"]
    assert doc["chat_id"] == chat["id"]
    assert doc["name"] == "Mark"
    assert doc["created_at"] == created["created_at"]
    assert doc["message_count"] == 3
    assert doc["chat"]["title"] == "Saga"
    assert [m["content"] for m in doc["messages"]] == ["one", "two", "three"]
    assert isinstance(doc["checksum"], str) and len(doc["checksum"]) == 64
    assert doc["user_id"]

    listed = _list_cp(app_client, chat["id"])
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]
    got = _get_cp(app_client, chat["id"], created["id"])
    assert got.status_code == 200, got.text
    assert got.json() == created


def test_create_default_name_is_timestamp(app_client):
    chat, _msgs = _seed_chat(app_client, contents=("one",))
    created = _create_cp_ok(app_client, chat["id"])
    assert DEFAULT_NAME_RE.match(created["name"]), created["name"]
    # an explicitly null name also takes the default
    created2 = _create_cp_ok(app_client, chat["id"], name=None)
    assert DEFAULT_NAME_RE.match(created2["name"]), created2["name"]


def test_list_ordering_oldest_first(app_client):
    chat, _msgs = _seed_chat(app_client)
    first = _create_cp_ok(app_client, chat["id"], name="First")
    second = _create_cp_ok(app_client, chat["id"], name="Second")
    listed = _list_cp(app_client, chat["id"]).json()
    assert [c["id"] for c in listed] == [first["id"], second["id"]]
    assert [c["name"] for c in listed] == ["First", "Second"]


def test_list_empty_for_fresh_chat(app_client):
    chat = _chat(app_client, "Fresh")
    r = _list_cp(app_client, chat["id"])
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_chat_title_is_snapshot_title_not_live(app_client):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    r = app_client.patch(f"/api/v1/chats/{chat['id']}", json={"title": "Renamed"})
    assert r.status_code == 200, r.text
    got = _get_cp(app_client, chat["id"], created["id"]).json()
    assert got["chat_title"] == "Saga"  # title AT SNAPSHOT TIME
    assert _list_cp(app_client, chat["id"]).json()[0]["chat_title"] == "Saga"


# ---------------- B. payload fidelity ----------------


async def test_payload_equals_row_to_dict_and_checksum_verifies(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Hall")
        await svc.append_message(session, user, chat.id, "user", "hello")
        await svc.append_message(
            session, user, chat.id, "assistant", "reply",
            speaker_id="sp-1", speaker_name="Saga Teller",
        )
        chat_id = chat.id
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
    assert meta is not None
    doc = _cp_doc(tmp_path, chat_id, meta["id"])
    async with factory() as session:
        chat_row = await svc.get_chat(session, user, chat_id)
        result = await session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at, Message.id)
        )
        rows = list(result.scalars().all())
        expected_chat = row_to_dict(chat_row)
        expected_messages = [row_to_dict(m) for m in rows]
    # the on-disk payload IS the archive member shape for the same chat
    assert doc["chat"] == expected_chat
    assert doc["messages"] == expected_messages
    assert doc["message_count"] == len(expected_messages) == 2
    # speaker fields ride along verbatim
    assert doc["messages"][1]["speaker_id"] == "sp-1"
    assert doc["messages"][1]["speaker_name"] == "Saga Teller"
    # checksum verifies: sha256 of the canonical bytes of {chat, messages}
    digest = hashlib.sha256(
        _canonical({"chat": doc["chat"], "messages": doc["messages"]})
    ).hexdigest()
    assert doc["checksum"] == digest


async def test_payload_matches_archive_member(tmp_path):
    """Design 7H: the checkpoint pair deep-equals the .runmal member."""
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user, "Hall", ("one", "two", "three"))
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
        dest = tmp_path / "out.runmal"
        await export_archive(session, user, dest, base_dir=tmp_path)
    doc = _cp_doc(tmp_path, chat_id, meta["id"])
    with zipfile.ZipFile(dest) as zf:
        member = json.loads(zf.read(f"chats/{chat_id}.json"))
    assert {"chat": doc["chat"], "messages": doc["messages"]} == {
        "chat": member["chat"],
        "messages": member["messages"],
    }


def test_swipe_deck_survives_checkpoint_and_restore(app_client, tmp_path):
    chat = _chat(app_client, "Swipes")
    msg = _msg(app_client, chat["id"], "original", role="assistant")
    base = f"/api/v1/chats/{chat['id']}/messages/{msg['id']}/swipes"
    r = app_client.post(base, json={"content": "alt-one"})
    assert r.status_code == 201, r.text
    r = app_client.post(base, json={"content": "alt-two"})
    assert r.status_code == 201, r.text
    r = app_client.post(base + "/select", json={"index": 1})
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "alt-one"
    assert r.json()["swipe_id"] == 1

    created = _create_cp_ok(app_client, chat["id"], name="Deck")
    doc = _cp_doc(tmp_path, chat["id"], created["id"])
    (payload_msg,) = doc["messages"]
    assert json.loads(payload_msg["swipes_json"]) == ["original", "alt-one", "alt-two"]
    assert payload_msg["swipe_id"] == 1
    assert payload_msg["content"] == "alt-one"

    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored = r.json()
    (restored_msg,) = _history(app_client, restored["id"])
    assert restored_msg["swipes"] == ["original", "alt-one", "alt-two"]
    assert restored_msg["swipe_id"] == 1
    assert restored_msg["content"] == "alt-one"
    # the content == swipes[swipe_id] invariant holds in the restored chat
    assert restored_msg["content"] == restored_msg["swipes"][restored_msg["swipe_id"]]


# ---------------- C/D. restore-as-new, source untouched, events ----------------


def test_restore_as_new_chat(app_client):
    chat, msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    snapshot = _history(app_client, chat["id"])

    # the snapshot is frozen: later appends and edits stay out of it
    _msg(app_client, chat["id"], "four-after")
    r = app_client.patch(
        f"/api/v1/chats/{chat['id']}/messages/{msgs[0]['id']}",
        json={"content": "one-edited"},
    )
    assert r.status_code == 200, r.text

    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored = r.json()
    assert restored["id"] != chat["id"]
    assert restored["message_count"] == 3
    assert restored["title"] == "Saga (checkpoint: Mark)"
    assert restored["branch"]["kind"] == "root"
    assert restored["branch"]["is_branch"] is False

    restored_history = _history(app_client, restored["id"])
    assert [m["content"] for m in restored_history] == ["one", "two", "three"]
    assert [m["role"] for m in restored_history] == [m["role"] for m in snapshot]
    assert [m["created_at"] for m in restored_history] == [
        m["created_at"] for m in snapshot
    ]
    source_ids = {m["id"] for m in snapshot}
    assert all(m["id"] not in source_ids for m in restored_history)  # fresh ids

    # source chat completely unchanged by the restore
    assert _contents(app_client, chat["id"]) == [
        "one-edited", "two", "three", "four-after",
    ]
    assert _get_chat(app_client, chat["id"])["title"] == "Saga"


def test_restore_with_explicit_name_uses_it_as_title(app_client):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    r = _restore_cp(app_client, chat["id"], created["id"], name="Rewound")
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Rewound"


def test_restore_carries_snapshot_authors_note(app_client):
    chat, _msgs = _seed_chat(app_client)
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/authors-note",
        json={"text": "Old note", "depth": 2, "frequency": 1,
              "enabled": True, "role": "system"},
    )
    assert r.status_code == 200, r.text
    created = _create_cp_ok(app_client, chat["id"], name="Noted")
    # mutate the LIVE chat after the checkpoint
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/authors-note",
        json={"text": "New note", "depth": 2, "frequency": 1,
              "enabled": True, "role": "system"},
    )
    assert r.status_code == 200, r.text
    r = app_client.patch(f"/api/v1/chats/{chat['id']}", json={"title": "Renamed"})
    assert r.status_code == 200, r.text

    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored = r.json()
    assert restored["authors_note"]["text"] == "Old note"  # snapshot-time value
    assert restored["title"] == "Saga (checkpoint: Noted)"  # snapshot title too
    # ... while the live chat keeps its new values, untouched
    live = _get_chat(app_client, chat["id"])
    assert live["authors_note"]["text"] == "New note"
    assert live["title"] == "Renamed"


async def test_restore_carries_all_snapshot_settings_service(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user, "Hall", ("one",))
    async with factory() as session:
        await svc.set_chat_authors_note(
            session, user, chat_id,
            {"text": "Old note", "depth": 2, "frequency": 1,
             "enabled": True, "role": "system"},
        )
        await svc.set_chat_post_history(
            session, user, chat_id,
            {"text": "Old PH", "enabled": True, "role": "system"},
        )
        await svc.set_chat_swipe_settings(
            session, user, chat_id,
            {"enabled": False, "params": {"temperature": 0.5}},
        )
        chat_row = await svc.get_chat(session, user, chat_id)
        chat_row.preset_id = "preset-x"
        chat_row.backend_profile_id = "profile-y"
        await session.commit()
        snapshot = {
            "authors_note_json": chat_row.authors_note_json,
            "post_history_json": chat_row.post_history_json,
            "swipe_settings_json": chat_row.swipe_settings_json,
        }
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Settings", base_dir=tmp_path
        )
    # mutate every live setting after the checkpoint
    async with factory() as session:
        await svc.set_chat_authors_note(
            session, user, chat_id,
            {"text": "New note", "depth": 2, "frequency": 1,
             "enabled": True, "role": "system"},
        )
        live = await svc.get_chat(session, user, chat_id)
        live.preset_id = "preset-z"
        live.backend_profile_id = "profile-w"
        await session.commit()
    async with factory() as session:
        restored = await checkpoints.restore_checkpoint(
            session, user, chat_id, meta["id"], base_dir=tmp_path
        )
        assert restored is not None
        assert restored.preset_id == "preset-x"
        assert restored.backend_profile_id == "profile-y"
        assert restored.authors_note_json == snapshot["authors_note_json"]
        assert restored.post_history_json == snapshot["post_history_json"]
        assert restored.swipe_settings_json == snapshot["swipe_settings_json"]
        assert restored.group_id is None
        assert restored.branch_kind == "root"
        assert restored.branch_parent_id is None
        live = await svc.get_chat(session, user, chat_id)
        assert live.preset_id == "preset-z"  # source untouched


async def test_group_id_not_carried_service(tmp_path):
    """A payload whose chat row holds a group link restores standalone."""
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user, "Room", ("one",))
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "RoomMark", base_dir=tmp_path
        )
    doc = _cp_doc(tmp_path, chat_id, meta["id"])
    doc["chat"]["group_id"] = "99999999-8888-4777-8666-555555555555"
    _rewrite_cp_file(tmp_path, chat_id, meta["id"], _seal(doc))
    async with factory() as session:
        restored = await checkpoints.restore_checkpoint(
            session, user, chat_id, meta["id"], base_dir=tmp_path
        )
        assert restored is not None
        assert restored.group_id is None


def test_restore_events_on_both_chats(app_client):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")

    src_events = _ckpt_events(app_client, chat["id"])
    assert [e["kind"] for e in src_events] == ["checkpoint.created"]
    assert src_events[0]["data"] == {
        "checkpoint_id": created["id"],
        "name": "Mark",
        "message_count": 3,
    }

    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored = r.json()

    src_events = _ckpt_events(app_client, chat["id"])
    assert [e["kind"] for e in src_events] == [
        "checkpoint.created", "checkpoint.restored",
    ]
    assert src_events[1]["data"] == {
        "checkpoint_id": created["id"],
        "name": "Mark",
        "restored_chat_id": restored["id"],
    }

    restored_events = _events(app_client, restored["id"])
    ckpt = [e for e in restored_events if e["kind"].startswith("checkpoint.")]
    assert [e["kind"] for e in ckpt] == ["checkpoint.restored"]
    assert ckpt[0]["data"] == {
        "source_chat_id": chat["id"],
        "checkpoint_id": created["id"],
        "name": "Mark",
        "restored_messages": 3,
    }

    # deleting a checkpoint records NO event (pinned decision, design 2.6)
    before = [e["kind"] for e in _events(app_client, chat["id"])]
    assert _delete_cp(app_client, chat["id"], created["id"]).status_code == 200
    assert [e["kind"] for e in _events(app_client, chat["id"])] == before


# ---------------- E. delete ----------------


def test_delete_flow(app_client, tmp_path):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored_id = r.json()["id"]
    path = _cp_file(tmp_path, chat["id"], created["id"])

    r = _delete_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": True, "id": created["id"]}
    assert not path.exists()
    assert _list_cp(app_client, chat["id"]).json() == []
    assert _get_cp(app_client, chat["id"], created["id"]).status_code == 404
    assert _restore_cp(app_client, chat["id"], created["id"]).status_code == 404
    assert _delete_cp(app_client, chat["id"], created["id"]).status_code == 404

    # a chat restored earlier from the deleted checkpoint is untouched
    assert _contents(app_client, restored_id) == ["one", "two", "three"]


# ---------------- F. isolation ----------------


async def test_foreign_user_gets_nothing_service(tmp_path):
    factory = make_factory(tmp_path)
    owner = await make_user(factory, "owner")
    other = await make_user(factory, "intruder")
    chat_id = await _svc_chat(factory, owner, "OwnerHall", ("secret-one",))
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, owner, chat_id, "Mine", base_dir=tmp_path
        )
    async with factory() as session:
        assert await checkpoints.create_checkpoint(
            session, other, chat_id, "Nope", base_dir=tmp_path
        ) is None
        assert await checkpoints.list_checkpoints(
            session, other, chat_id, base_dir=tmp_path
        ) is None
        assert await checkpoints.get_checkpoint(
            session, other, chat_id, meta["id"], base_dir=tmp_path
        ) is None
        assert await checkpoints.restore_checkpoint(
            session, other, chat_id, meta["id"], base_dir=tmp_path
        ) is None
        assert await checkpoints.delete_checkpoint(
            session, other, chat_id, meta["id"], base_dir=tmp_path
        ) is None
        # the refused foreign restore created no chat for anyone
        assert len(await svc.list_chats(session, other)) == 0
        assert len(await svc.list_chats(session, owner)) == 1
    # the foreign user's list on their OWN chat never sees the owner's
    other_chat = await _svc_chat(factory, other, "OtherHall", ("mine",))
    async with factory() as session:
        assert await checkpoints.list_checkpoints(
            session, other, other_chat, base_dir=tmp_path
        ) == []
        # and the owner's checkpoint still exists, unharmed
        assert await checkpoints.get_checkpoint(
            session, owner, chat_id, meta["id"], base_dir=tmp_path
        ) is not None


def test_checkpoint_id_under_wrong_chat_is_404(app_client):
    chat1, _ = _seed_chat(app_client, "One", ("a",))
    chat2, _ = _seed_chat(app_client, "Two", ("b",))
    created = _create_cp_ok(app_client, chat1["id"], name="Mark")
    assert _get_cp(app_client, chat2["id"], created["id"]).status_code == 404
    assert _restore_cp(app_client, chat2["id"], created["id"]).status_code == 404
    assert _delete_cp(app_client, chat2["id"], created["id"]).status_code == 404
    # the checkpoint itself is unharmed under its own chat
    assert _get_cp(app_client, chat1["id"], created["id"]).status_code == 200


def test_copied_foreign_file_is_refused(app_client, tmp_path):
    """Identity binding (design 5.4): a file copied into another
    chat's directory is foreign and refuses with 422, never served."""
    chat1, _ = _seed_chat(app_client, "One", ("a",))
    chat2, _ = _seed_chat(app_client, "Two", ("b",))
    created = _create_cp_ok(app_client, chat1["id"], name="Mark")
    src = _cp_file(tmp_path, chat1["id"], created["id"])
    dst_dir = src.parent.parent / chat2["id"]
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / src.name).write_bytes(src.read_bytes())
    assert _get_cp(app_client, chat2["id"], created["id"]).status_code == 422
    assert _restore_cp(app_client, chat2["id"], created["id"]).status_code == 422


# ---------------- G. refusals and edges ----------------


def test_missing_chat_404_on_all_five_routes(app_client):
    missing = "missing-chat"
    assert _create_cp(app_client, missing, name="x").status_code == 404
    assert _list_cp(app_client, missing).status_code == 404
    assert _get_cp(app_client, missing, UNKNOWN_ID).status_code == 404
    assert _restore_cp(app_client, missing, UNKNOWN_ID).status_code == 404
    assert _delete_cp(app_client, missing, UNKNOWN_ID).status_code == 404


def test_unknown_checkpoint_id_404(app_client):
    chat, _msgs = _seed_chat(app_client)
    assert _get_cp(app_client, chat["id"], UNKNOWN_ID).status_code == 404
    assert _restore_cp(app_client, chat["id"], UNKNOWN_ID).status_code == 404
    assert _delete_cp(app_client, chat["id"], UNKNOWN_ID).status_code == 404


def test_blank_name_refused_rest(app_client):
    chat, _msgs = _seed_chat(app_client)
    assert _create_cp(app_client, chat["id"], name="   ").status_code == 422
    assert _create_cp(app_client, chat["id"], name="").status_code == 422
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    r = _restore_cp(app_client, chat["id"], created["id"], name="  ")
    assert r.status_code == 422, r.text


async def test_blank_name_and_unknown_refused_service(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user)
    async with factory() as session:
        with pytest.raises(ValueError):
            await checkpoints.create_checkpoint(
                session, user, chat_id, "   ", base_dir=tmp_path
            )
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
        with pytest.raises(ValueError):
            await checkpoints.restore_checkpoint(
                session, user, chat_id, meta["id"], " ", base_dir=tmp_path
            )
        # unknown well-formed id: None / False, never an exception
        assert await checkpoints.get_checkpoint(
            session, user, chat_id, UNKNOWN_ID, base_dir=tmp_path
        ) is None
        assert await checkpoints.restore_checkpoint(
            session, user, chat_id, UNKNOWN_ID, base_dir=tmp_path
        ) is None
        assert await checkpoints.delete_checkpoint(
            session, user, chat_id, UNKNOWN_ID, base_dir=tmp_path
        ) is False


@pytest.mark.parametrize("bad_id", ["../x", "..", "a/b", "a\\b", "../secret", "."])
async def test_traversal_ids_refused_service(tmp_path, bad_id):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user)
    async with factory() as session:
        await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
        with pytest.raises(ValueError):
            await checkpoints.get_checkpoint(
                session, user, chat_id, bad_id, base_dir=tmp_path
            )
        with pytest.raises(ValueError):
            await checkpoints.restore_checkpoint(
                session, user, chat_id, bad_id, base_dir=tmp_path
            )
        with pytest.raises(ValueError):
            await checkpoints.delete_checkpoint(
                session, user, chat_id, bad_id, base_dir=tmp_path
            )


@pytest.mark.parametrize("bad_id", [".hidden", "a.b", "a b"])
def test_malformed_ids_422_rest(app_client, bad_id):
    chat, _msgs = _seed_chat(app_client)
    assert _get_cp(app_client, chat["id"], bad_id).status_code == 422
    assert _restore_cp(app_client, chat["id"], bad_id).status_code == 422
    assert _delete_cp(app_client, chat["id"], bad_id).status_code == 422


def test_tampered_message_content_refused(app_client, tmp_path):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    doc = _cp_doc(tmp_path, chat["id"], created["id"])
    doc["messages"][0]["content"] = "forged"
    _rewrite_cp_file(tmp_path, chat["id"], created["id"], doc)

    assert _get_cp(app_client, chat["id"], created["id"]).status_code == 422
    chats_before = len(app_client.get("/api/v1/chats").json())
    assert _restore_cp(app_client, chat["id"], created["id"]).status_code == 422
    # a refused restore creates NO chat
    assert len(app_client.get("/api/v1/chats").json()) == chats_before


def test_corrupted_checksum_field_refused(app_client, tmp_path):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    doc = _cp_doc(tmp_path, chat["id"], created["id"])
    doc["checksum"] = "0" * 64
    _rewrite_cp_file(tmp_path, chat["id"], created["id"], doc)
    assert _get_cp(app_client, chat["id"], created["id"]).status_code == 422
    assert _restore_cp(app_client, chat["id"], created["id"]).status_code == 422


async def test_tamper_raises_checkpoint_error_service(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user)
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
    doc = _cp_doc(tmp_path, chat_id, meta["id"])
    doc["messages"][0]["content"] = "forged"
    _rewrite_cp_file(tmp_path, chat_id, meta["id"], doc)
    async with factory() as session:
        with pytest.raises(CheckpointError):
            await checkpoints.get_checkpoint(
                session, user, chat_id, meta["id"], base_dir=tmp_path
            )
        with pytest.raises(CheckpointError):
            await checkpoints.restore_checkpoint(
                session, user, chat_id, meta["id"], base_dir=tmp_path
            )
        assert len(await svc.list_chats(session, user)) == 1  # no partial chat


def test_non_json_file_surfaces_loudly(app_client, tmp_path):
    """Design 2.3/5: list raises on an unparseable file (422), never
    silently drops the corrupt checkpoint."""
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    _rewrite_cp_file(tmp_path, chat["id"], created["id"], "this is not json {{{")
    assert _list_cp(app_client, chat["id"]).status_code == 422
    assert _get_cp(app_client, chat["id"], created["id"]).status_code == 422
    assert _restore_cp(app_client, chat["id"], created["id"]).status_code == 422
    # ... but deletion stays possible even for a corrupt file (design 2.6)
    assert _delete_cp(app_client, chat["id"], created["id"]).status_code == 200


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc.update(format="other-format"),
        lambda doc: doc.update(format_version=2),
        lambda doc: doc.update(message_count=99),
        lambda doc: doc.update(user_id="someone-else"),
        lambda doc: doc.update(chat_id="another-chat"),
    ],
)
async def test_envelope_tamper_raises_service(tmp_path, mutate):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _svc_chat(factory, user)
    async with factory() as session:
        meta = await checkpoints.create_checkpoint(
            session, user, chat_id, "Mark", base_dir=tmp_path
        )
    doc = _cp_doc(tmp_path, chat_id, meta["id"])
    mutate(doc)
    _rewrite_cp_file(tmp_path, chat_id, meta["id"], doc)
    async with factory() as session:
        with pytest.raises(CheckpointError):
            await checkpoints.get_checkpoint(
                session, user, chat_id, meta["id"], base_dir=tmp_path
            )
        with pytest.raises(CheckpointError):
            await checkpoints.restore_checkpoint(
                session, user, chat_id, meta["id"], base_dir=tmp_path
            )


def test_empty_chat_checkpoint_roundtrip(app_client):
    chat = _chat(app_client, "Empty")
    created = _create_cp_ok(app_client, chat["id"], name="Blank")
    assert created["message_count"] == 0
    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored = r.json()
    assert restored["id"] != chat["id"]
    assert restored["message_count"] == 0
    assert _history(app_client, restored["id"]) == []


# ---------------- H. chat-deletion interplay ----------------


def test_chat_deletion_removes_checkpoints(app_client, tmp_path):
    chat, _msgs = _seed_chat(app_client)
    created = _create_cp_ok(app_client, chat["id"], name="Mark")
    r = _restore_cp(app_client, chat["id"], created["id"])
    assert r.status_code == 201, r.text
    restored_id = r.json()["id"]
    cp_dir = _cp_file(tmp_path, chat["id"], created["id"]).parent
    assert cp_dir.is_dir()

    r = app_client.delete(f"/api/v1/chats/{chat['id']}")
    assert r.status_code == 200, r.text
    assert not cp_dir.exists()  # the checkpoint directory dies with the chat

    # the restored-from chat survives, independent, with its history
    assert _contents(app_client, restored_id) == ["one", "two", "three"]


def test_remove_chat_checkpoints_never_existed_is_true(tmp_path):
    assert checkpoints.remove_chat_checkpoints(
        "user-x", "chat-never", base_dir=tmp_path
    ) is True
    # and removing a real directory works and reports True
    chat_id = "chat-real"
    user_id = "user-x"
    directory = tmp_path / "checkpoints" / user_id / chat_id
    directory.mkdir(parents=True)
    (directory / "cp.json").write_text("{}", encoding="utf-8")
    assert checkpoints.remove_chat_checkpoints(
        user_id, chat_id, base_dir=tmp_path
    ) is True
    assert not directory.exists()
