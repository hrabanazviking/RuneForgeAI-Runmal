"""P-211 acceptance: the Inspector group reasoning census
(Part XIII, DERIVED).

Contract under test (P211_DESIGN.md):
- ONE new read-only, schema-versioned document
  (runmal-p211-inspector-group-reasoning-v1) per owned
  group on GET /inspector/groups/{group_id}/reasoning,
  built by the Inspector package from the new
  groupchat-store read list_group_reasoning (mirroring
  list_chat_reasoning; the owned fence is list_messages
  itself) over the banked P-205 record's active and
  full views, aggregating through the banked
  summarise_reasoning unchanged.
- The census reports the P-210 summary shape verbatim,
  a per-speaker roll-up in first-appearance order, and
  per-message entries in the P-210 shape plus
  speaker_id / speaker_name - with NO thinking text
  and NO message content anywhere (the P-204 no-text
  law, as P-210 applied it). One document-level
  raw_road points at the banked transcript road
  GET /groups/{group_id}/messages.
- Honesty fences: missing / foreign groups answer the
  house 404 ("group not found") and the service read
  returns None; a transcript whose messages all read
  not_recorded is AVAILABLE; malformed stored
  reasoning censuses as unknown and never raises; the
  build is a pure read. Migration head stays 0042
  (no m0043); the route census grows by exactly one
  road to 356 paths / 439 operations; the P-210 chat
  document is byte-shaped exactly as banked.
Fixtures mirror test_p208_groupchat_reasoning.py /
test_p210_inspector_reasoning.py: a real group driven
through the groupchat store and the persistent
deepening road with a scripted reasoning backend, plus
direct store appends carrying strict P-205 records.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.fake import FakeChatBackend
from runmal.characters.service import create_character
from runmal.chats import reasoning as rsn
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import ChatEvent, Message, User
from runmal.db.owners import get_or_create_owner
from runmal.generation import service as gen_service
from runmal.groupchat import deepening
from runmal.groupchat import store as group_store
from runmal.inspector import GROUP_REASONING_SCHEMA, REASONING_SCHEMA
from runmal.inspector import group_reasoning as inspector_group_reasoning
from runmal.inspector import reasoning as inspector_reasoning

REPO = Path(__file__).parent.parent

THINK_MARKER = "ZqxP211UnmistakableThinking"
CONTENT_MARKER = "ZqxP211UnmistakableContent"

CARD = {
    "name": "Asta",
    "description": "Keeper of the mead hall at TESTHOLD.",
    "personality": "Warm but exact.",
    "scenario": "A longhouse hall.",
    "first_mes": "Sit, traveller.",
    "system_prompt": "You are Asta of TESTHOLD.",
}

STATUSES = ("recorded", "not_present", "not_recorded", "unknown")

TOP_KEYS = {
    "schema", "group_id", "room_chat_id", "coverage",
    "summary", "speakers", "messages", "raw_road",
}
SUMMARY_KEYS = {
    "messages_total",
    "active_by_status",
    "messages_with_recorded",
    "swipes_total",
    "swipes_recorded",
    "swipes_by_status",
}
SPEAKER_KEYS = {
    "speaker_id", "speaker_name", "messages_total",
    "active_by_status", "messages_with_recorded",
}
ENTRY_KEYS = {
    "message_id", "role", "speaker_id", "speaker_name",
    "active_status", "recorded", "recorded_at",
    "swipes_recorded",
}
READ_ENTRY_KEYS = {
    "message_id", "role", "speaker_id", "speaker_name",
    "active", "full",
}
P210_TOP_KEYS = {"schema", "chat_id", "coverage", "summary", "messages"}
P210_ENTRY_KEYS = {
    "message_id", "role", "active_status", "recorded",
    "recorded_at", "swipes_recorded", "raw_road",
}

THINK = ("weigh ", "the toll")
THINK_TEXT = "weigh the toll"
ANSWER = ("The ", "answer.")


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for service-layer seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    return client


def run(coro):
    return asyncio.run(coro)


def get_doc(client, group_id):
    resp = client.get(f"/api/v1/inspector/groups/{group_id}/reasoning")
    assert resp.status_code == 200, resp.text
    return resp.json()


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


async def _seed_group(factory, names=("Asta", "Bryn")):
    async with factory() as session:
        uid = (await get_or_create_owner(session)).id
        ids = []
        for name in names:
            character = await create_character(
                session, uid, dict(CARD, name=name))
            ids.append(character.id)
        group = await group_store.create_group(
            session, uid, "Mead Hall", ids)
        described = await group_store.describe_group(
            session, uid, group.id)
        return uid, group.id, ids, described["chat_id"]


def seed_group(client, names=("Asta", "Bryn")):
    return run(_seed_group(client.factory, names))


async def _append(factory, uid, gid, speaker, content, reasoning=None):
    async with factory() as session:
        message = await group_store.append_message(
            session, uid, gid, speaker, content, reasoning=reasoning)
        return message.id


def append(client, uid, gid, speaker, content, reasoning=None):
    return run(_append(
        client.factory, uid, gid, speaker, content, reasoning))


def zero_counts():
    return {status: 0 for status in STATUSES}


# -- Pin 1: schema and shape ----------------------------------------------


def test_01_schema_shape_and_exact_keys(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, room_chat_id = seed_group(client)
    record = rsn.build_record(status="recorded", text="a thought")
    append(client, uid, gid, ids[0], "An answer.", reasoning=record)
    doc = get_doc(client, gid)
    assert GROUP_REASONING_SCHEMA == (
        "runmal-p211-inspector-group-reasoning-v1")
    assert rsn.REASONING_SCHEMA == "runmal-p205-message-reasoning-v1"
    assert doc["schema"] == GROUP_REASONING_SCHEMA
    assert doc["group_id"] == gid
    # room_chat_id names the room transcript Chat exactly
    # as describe_group reports it for the same group.
    assert doc["room_chat_id"] == room_chat_id
    assert set(doc) == TOP_KEYS
    assert set(doc["coverage"]) == {"status", "reason"}
    assert set(doc["summary"]) == SUMMARY_KEYS
    assert set(doc["summary"]["active_by_status"]) == set(STATUSES)
    assert set(doc["summary"]["swipes_by_status"]) == set(STATUSES)
    assert len(doc["speakers"]) == 1
    assert set(doc["speakers"][0]) == SPEAKER_KEYS
    assert set(doc["speakers"][0]["active_by_status"]) == set(STATUSES)
    assert len(doc["messages"]) == 1
    assert set(doc["messages"][0]) == ENTRY_KEYS
    # The truth layer's own shape, pinned at the read.
    async def probe():
        async with client.factory() as session:
            return await group_store.list_group_reasoning(
                session, uid, gid)
    read = run(probe())
    assert read["group_id"] == gid
    assert read["room_chat_id"] == room_chat_id
    assert len(read["messages"]) == 1
    assert set(read["messages"][0]) == READ_ENTRY_KEYS


# -- Pins 2-3: generated truth through the deepening road ------------------


async def _generated_turn(factory, uid, gid, ids):
    async with factory() as session:
        await group_store.update_group(
            session, uid, gid, speaker_policy="list",
            speaker_config={"order": list(ids)})
    async with factory() as session:
        return await deepening.next_turn(
            session, uid, gid, user_text="Speak, friends.",
            generate=True)


def test_02_recorded_truth_from_a_generated_turn(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    monkeypatch.setattr(
        gen_service, "default_backend",
        lambda: FakeChatBackend(chunks=ANSWER, reasoning_chunks=THINK))
    result = run(_generated_turn(client.factory, uid, gid, ids))
    assert result["speaker_id"] == ids[0]
    generated_id = result["message"]["id"]
    doc = get_doc(client, gid)
    entry = next(
        e for e in doc["messages"] if e["message_id"] == generated_id)
    assert entry["role"] == "assistant"
    assert entry["speaker_id"] == ids[0]
    assert entry["speaker_name"] == "Asta"
    assert entry["active_status"] == "recorded"
    assert entry["recorded"] is True
    assert entry["swipes_recorded"] == [0]
    # recorded_at carried verbatim from the full document.
    async def full_recorded_at():
        async with client.factory() as session:
            messages = await group_store.list_messages(session, uid, gid)
            stored = next(m for m in messages if m.id == generated_id)
            return rsn.full_view(stored)["recorded_at"]
    assert entry["recorded_at"] is not None
    assert entry["recorded_at"] == run(full_recorded_at())
    speaker = next(
        s for s in doc["speakers"] if s["speaker_id"] == ids[0])
    assert speaker["speaker_name"] == "Asta"
    assert speaker["messages_total"] == 1
    assert speaker["active_by_status"]["recorded"] == 1
    assert speaker["messages_with_recorded"] == 1
    assert doc["summary"]["active_by_status"]["recorded"] == 1
    # messages_with_recorded counts full documents whose
    # recorded flag is set - the generated turn's AND the
    # user turn's explicit document (banked vocabulary,
    # see pin 3's note).
    assert doc["summary"]["messages_with_recorded"] == 2


def test_03_not_present_truth_from_a_generated_turn(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    monkeypatch.setattr(
        gen_service, "default_backend",
        lambda: FakeChatBackend(chunks=ANSWER))
    result = run(_generated_turn(client.factory, uid, gid, ids))
    generated_id = result["message"]["id"]
    doc = get_doc(client, gid)
    entry = next(
        e for e in doc["messages"] if e["message_id"] == generated_id)
    # not_present is a positive fact about that generation,
    # distinct from recorded and from not_recorded in all
    # three sections of the document.
    assert entry["active_status"] == "not_present"
    # The entry's recorded flag is the FULL document's
    # own flag, carried verbatim (the P-210 shape): an
    # explicitly built document is recorded as a
    # document even when its swipe produced no thinking
    # - the banked P-205 vocabulary, identical in the
    # chats store. The swipe-level truth is the status
    # and the empty recorded-index list.
    assert entry["recorded"] is True
    assert entry["swipes_recorded"] == []
    speaker = next(
        s for s in doc["speakers"] if s["speaker_id"] == ids[0])
    assert speaker["active_by_status"]["not_present"] == 1
    assert speaker["active_by_status"]["recorded"] == 0
    assert speaker["messages_with_recorded"] == 1
    summary = doc["summary"]
    assert summary["active_by_status"]["not_present"] == 1
    assert summary["active_by_status"]["recorded"] == 0
    # The user turn the road appended reads not_recorded:
    # the two unrecorded states are never blurred.
    assert summary["active_by_status"]["not_recorded"] == 1


# -- Pin 4: manual honesty ---------------------------------------------------


def test_04_manual_and_user_appends_read_not_recorded(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    append(client, uid, gid, ids[0], "A declared line.")
    append(client, uid, gid, "user", "Hail all.")
    doc = get_doc(client, gid)
    assert doc["summary"]["messages_total"] == 2
    assert doc["summary"]["active_by_status"] == {
        "recorded": 0, "not_present": 0,
        "not_recorded": 2, "unknown": 0,
    }
    # Both appends carry an explicit not_recorded
    # document (the P-208 store pin), so the banked
    # document-level count is 2 - while no swipe record
    # anywhere reads as thinking.
    assert doc["summary"]["messages_with_recorded"] == 2
    assert doc["summary"]["swipes_recorded"] == 0
    for entry in doc["messages"]:
        # Never upgraded, never dropped.
        assert entry["active_status"] == "not_recorded"
        assert entry["swipes_recorded"] == []
    by_id = {e["message_id"]: e for e in doc["messages"]}
    assert len(by_id) == 2
    speakers = {(s["speaker_id"], s["speaker_name"]): s
                for s in doc["speakers"]}
    # The store's own speaker identity, carried verbatim:
    # the character's id + name snapshot, and null / null
    # for the user turn - never invented.
    assert speakers[(ids[0], "Asta")]["active_by_status"] == {
        "recorded": 0, "not_present": 0,
        "not_recorded": 1, "unknown": 0,
    }
    assert speakers[(None, None)]["messages_total"] == 1
    assert speakers[(None, None)]["active_by_status"]["not_recorded"] == 1


# -- Pin 5: the two count families are never confused ------------------------


def test_05_active_and_swipe_families_never_confused(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    message_id = append(client, uid, gid, ids[0], "A two-swipe line.")

    async def craft_two_swipes():
        # A stored document whose ACTIVE swipe (0) reads
        # not_present while swipe 1 is recorded, written
        # straight to the row with the banked builders.
        async with client.factory() as session:
            row = (
                await session.execute(
                    select(Message).where(Message.id == message_id))
            ).scalar_one()
            document = rsn.build_document(
                rsn.build_record(status="not_present"))
            document = rsn.with_record_for_swipe(
                document, 1,
                rsn.build_record(status="recorded", text="second thought"))
            row.reasoning_json = rsn.dump_document(document)
            await session.commit()

    run(craft_two_swipes())
    doc = get_doc(client, gid)
    summary = doc["summary"]
    # The active family sees only the active swipe...
    assert summary["active_by_status"] == {
        "recorded": 0, "not_present": 1,
        "not_recorded": 0, "unknown": 0,
    }
    # ...the swipe family sees every record in the document.
    assert summary["swipes_by_status"] == {
        "recorded": 1, "not_present": 1,
        "not_recorded": 0, "unknown": 0,
    }
    assert summary["swipes_total"] == 2
    assert summary["swipes_recorded"] == 1
    assert summary["messages_with_recorded"] == 1
    entry = doc["messages"][0]
    assert entry["active_status"] == "not_present"
    assert entry["recorded"] is True
    assert entry["swipes_recorded"] == [1]


# -- Pin 6: the per-speaker roll-up -------------------------------------------


def test_06_speaker_rollup_first_appearance_and_sums(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    append(client, uid, gid, ids[1], "Bryn opens.",
           reasoning=rsn.build_record(status="not_present"))
    append(client, uid, gid, ids[0], "Asta answers.",
           reasoning=rsn.build_record(status="recorded", text="a thought"))
    append(client, uid, gid, ids[1], "Bryn again.")
    doc = get_doc(client, gid)
    speakers = doc["speakers"]
    # First-appearance transcript order: Bryn spoke first.
    assert [s["speaker_id"] for s in speakers] == [ids[1], ids[0]]
    assert [s["speaker_name"] for s in speakers] == ["Bryn", "Asta"]
    bryn, asta = speakers
    assert bryn["messages_total"] == 2
    assert bryn["active_by_status"] == {
        "recorded": 0, "not_present": 1,
        "not_recorded": 1, "unknown": 0,
    }
    assert bryn["messages_with_recorded"] == 2
    assert asta["messages_total"] == 1
    assert asta["active_by_status"]["recorded"] == 1
    assert asta["messages_with_recorded"] == 1
    # The roll-up sums to the summary exactly.
    summary = doc["summary"]
    assert sum(s["messages_total"] for s in speakers) == (
        summary["messages_total"])
    for status in STATUSES:
        assert sum(
            s["active_by_status"][status] for s in speakers) == (
            summary["active_by_status"][status])
    assert sum(s["messages_with_recorded"] for s in speakers) == (
        summary["messages_with_recorded"])


# -- Pins 7-8: honest coverage -------------------------------------------------


def test_07_empty_group_reads_empty_never_an_error(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _uid, gid, _ids, room_chat_id = seed_group(client)
    doc = get_doc(client, gid)
    assert doc["group_id"] == gid
    assert doc["room_chat_id"] == room_chat_id
    assert doc["coverage"]["status"] == "empty"
    assert doc["coverage"]["reason"]
    summary = doc["summary"]
    assert summary["messages_total"] == 0
    assert summary["messages_with_recorded"] == 0
    assert summary["swipes_total"] == 0
    assert summary["swipes_recorded"] == 0
    assert summary["active_by_status"] == zero_counts()
    assert summary["swipes_by_status"] == zero_counts()
    assert doc["speakers"] == []
    assert doc["messages"] == []
    assert doc["raw_road"] == f"/groups/{gid}/messages"


def test_08_all_not_recorded_group_reads_available(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    append(client, uid, gid, "user", "Hail all.")
    append(client, uid, gid, ids[0], "A declared line.")
    doc = get_doc(client, gid)
    # The census is the fact: an all-not_recorded
    # transcript is AVAILABLE, per the P-210 idiom.
    assert doc["coverage"] == {"status": "available", "reason": None}
    assert doc["summary"]["active_by_status"]["not_recorded"] == 2


# -- Pin 9: refusal --------------------------------------------------------------


def test_09_unknown_and_foreign_group_404_and_service_none(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, _ids, _chat = seed_group(client)
    missing = client.get("/api/v1/inspector/groups/no-such-group/reasoning")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "group not found"

    async def probe():
        async with client.factory() as session:
            stranger = User(name="stranger")
            session.add(stranger)
            await session.commit()
            foreign_read = await group_store.list_group_reasoning(
                session, stranger.id, gid)
            foreign_doc = (
                await inspector_group_reasoning
                .build_group_reasoning_document(session, stranger.id, gid))
            missing_read = await group_store.list_group_reasoning(
                session, stranger.id, "no-such-group")
            missing_doc = (
                await inspector_group_reasoning
                .build_group_reasoning_document(
                    session, uid, "no-such-group"))
        return foreign_read, foreign_doc, missing_read, missing_doc

    foreign_read, foreign_doc, missing_read, missing_doc = run(probe())
    assert foreign_read is None
    assert foreign_doc is None
    assert missing_read is None
    assert missing_doc is None


# -- Pin 10: malformed stored reasoning -------------------------------------------


def test_10_malformed_stored_reasoning_censuses_unknown(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    message_id = append(
        client, uid, gid, ids[0], "An answer.",
        reasoning=rsn.build_record(status="recorded", text="a thought"))

    async def corrupt():
        # Hand-corrupt the stored record inside an otherwise
        # valid document: a recorded record whose text is not
        # a string. The banked tolerant readers read it as
        # unknown; the census joins that, never raises.
        async with client.factory() as session:
            row = (
                await session.execute(
                    select(Message).where(Message.id == message_id))
            ).scalar_one()
            row.reasoning_json = json.dumps(
                {
                    "schema": rsn.REASONING_SCHEMA,
                    "recorded": True,
                    "recorded_at": "2026-11-10T00:00:00+00:00",
                    "swipes": {
                        "0": {"status": "recorded", "text": 42}
                    },
                }
            )
            await session.commit()

    run(corrupt())
    doc = get_doc(client, gid)  # answers 200, never raises
    entry = doc["messages"][0]
    assert entry["active_status"] == "unknown"
    assert doc["summary"]["active_by_status"]["unknown"] == 1
    assert doc["summary"]["swipes_by_status"]["unknown"] == 1
    speaker = doc["speakers"][0]
    assert speaker["active_by_status"]["unknown"] == 1


# -- Pin 11: the no-text law --------------------------------------------------------


def test_11_no_thinking_text_and_no_message_content(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    append(client, uid, gid, ids[0], f"{CONTENT_MARKER} answer.",
           reasoning=rsn.build_record(
               status="recorded", text=THINK_MARKER))
    doc = get_doc(client, gid)
    blob = json.dumps(doc)
    assert THINK_MARKER not in blob
    assert CONTENT_MARKER not in blob
    assert "text" not in set(walk_keys(doc))
    assert set(doc) == TOP_KEYS
    assert set(doc["messages"][0]) == ENTRY_KEYS
    assert set(doc["speakers"][0]) == SPEAKER_KEYS


# -- Pin 12: pure read, fresh assembly ------------------------------------------------


def test_12_pure_read_and_assembled_fresh(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, room_chat_id = seed_group(client)
    append(client, uid, gid, ids[0], "An answer.",
           reasoning=rsn.build_record(status="recorded", text="a thought"))

    async def snapshot():
        async with client.factory() as session:
            messages = await session.execute(
                select(func.count(Message.id)).where(
                    Message.chat_id == room_chat_id))
            events = await session.execute(
                select(func.count(ChatEvent.id)).where(
                    ChatEvent.chat_id == room_chat_id))
            return int(messages.scalar_one()), int(events.scalar_one())

    before = run(snapshot())
    first = client.get(f"/api/v1/inspector/groups/{gid}/reasoning")
    second = client.get(f"/api/v1/inspector/groups/{gid}/reasoning")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # Two consecutive GETs are byte-identical...
    assert first.text == second.text
    # ...and the store's message and event counts are
    # unchanged across them: the read persists nothing.
    assert run(snapshot()) == before
    # The document is assembled fresh: a record appended
    # between reads appears in the next read's census.
    new_id = append(client, uid, gid, ids[1], "A later line.",
                    reasoning=rsn.build_record(status="not_present"))
    doc = get_doc(client, gid)
    assert doc["summary"]["messages_total"] == 2
    assert new_id in {e["message_id"] for e in doc["messages"]}


# -- Pin 13: one source of truth ---------------------------------------------------------


def test_13_summary_is_the_banked_summariser_applied(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    append(client, uid, gid, ids[0], "Recorded.",
           reasoning=rsn.build_record(status="recorded", text="a thought"))
    append(client, uid, gid, ids[1], "Plain.",
           reasoning=rsn.build_record(status="not_present"))
    append(client, uid, gid, "user", "Hail all.")
    doc = get_doc(client, gid)

    async def expected_summary():
        async with client.factory() as session:
            read = await group_store.list_group_reasoning(session, uid, gid)
            return inspector_reasoning.summarise_reasoning(read["messages"])

    # The document's summary equals summarise_reasoning
    # applied to the store read's entries, computed
    # independently here: the aggregator is shared, not
    # copied.
    assert doc["summary"] == run(expected_summary())


# -- Pin 14: the raw-road pointer is true ---------------------------------------------------


def test_14_raw_road_pointer_is_the_banked_transcript_road(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, ids, _chat = seed_group(client)
    message_id = append(
        client, uid, gid, ids[0], "An answer.",
        reasoning=rsn.build_record(status="recorded", text=THINK_TEXT))
    doc = get_doc(client, gid)
    assert doc["raw_road"] == f"/groups/{gid}/messages"
    resp = client.get(f"/api/v1/groups/{gid}/messages")
    assert resp.status_code == 200, resp.text
    stored = next(m for m in resp.json() if m["id"] == message_id)
    # The pointed-at road really serves the recorded
    # message's active reasoning view, text included:
    # the pointer is true.
    assert stored["reasoning"]["status"] == "recorded"
    assert stored["reasoning"]["text"] == THINK_TEXT


# -- Pin 15: census and fences restated --------------------------------------------------------


def test_15_census_migration_and_p210_document_unmoved(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    # Route census: exactly +1/+1 on the P-210 census.
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len(
            [
                k
                for k in methods
                if k in ("get", "post", "put", "delete", "patch")
            ]
        )
        for methods in paths.values()
    )
    assert len(paths) == 365
    assert operations == 455
    assert "/api/v1/inspector/groups/{group_id}/reasoning" in paths
    assert "/api/v1/inspector/chats/{chat_id}/reasoning" in paths
    # Migration head stays 0042; no 0043 file exists.
    assert MIGRATIONS[-1][0] == "0042"
    migrations_dir = REPO / "src" / "runmal" / "db" / "migrations"
    assert not [p.name for p in migrations_dir.glob("m0043*")]
    # The P-210 chat document for a one-to-one fixture
    # chat is byte-shaped exactly as banked: the group
    # join moved nothing it did not own.
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    posted = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={
            "role": "assistant",
            "content": "An answer.",
            "reasoning": {"status": "recorded", "text": "a thought"},
        },
    )
    assert posted.status_code == 201, posted.text
    resp = client.get(f"/api/v1/inspector/chats/{chat_id}/reasoning")
    assert resp.status_code == 200, resp.text
    chat_doc = resp.json()
    assert chat_doc["schema"] == REASONING_SCHEMA
    assert REASONING_SCHEMA == "runmal-p210-inspector-reasoning-v1"
    assert set(chat_doc) == P210_TOP_KEYS
    assert set(chat_doc["summary"]) == SUMMARY_KEYS
    assert len(chat_doc["messages"]) == 1
    entry = chat_doc["messages"][0]
    assert set(entry) == P210_ENTRY_KEYS
    assert entry["raw_road"] == (
        f"/chats/{chat_id}/messages/{posted.json()['id']}/reasoning")
