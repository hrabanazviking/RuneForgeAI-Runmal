"""P-210 acceptance: the Inspector reasoning join
(Part XIII, DERIVED).

Contract under test (P210_DESIGN.md):
- ONE new read-only, schema-versioned document
  (runmal-p210-inspector-reasoning-v1) per owned chat on
  GET /inspector/chats/{chat_id}/reasoning, built by the
  Inspector package from the new chats-service read
  list_chat_reasoning (mirroring list_chat_provenance),
  over the banked P-205 record's active and full views.
- The census reports per message (active status, the
  full document's recorded bool + recorded_at, recorded
  swipe indexes, a raw_road pointer) and in aggregate
  (per-status counts over active views AND over all
  swipe documents) - with NO thinking text and NO
  message content anywhere (the P-204 no-payload
  discipline applied to the one content-class record).
- Honesty fences: missing / foreign chats answer the
  house 404 and the service read returns None; a chat
  whose messages all read not_recorded is AVAILABLE;
  groupchat records (separate store) never appear in a
  chat's census; malformed stored reasoning censuses as
  unknown and never raises; the build is a pure read.
- The P-203 overview and P-204 events documents are
  unchanged by the join; migration head stays 0042
  (no m0043); the route census grows by exactly one
  road to 355 paths / 438 operations (P-211 heal: the
  census has since grown by P-211's one road to
  356 paths / 439 operations; this slice's own growth
  statement stands as written).
Fixtures mirror test_p204_inspector_events.py /
test_p209_swipe_generate_reasoning.py.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import create_character
from runmal.chats import reasoning as rsn
from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.db.owners import get_or_create_owner
from runmal.groupchat import store as group_store
from runmal.inspector import (
    EVENTS_SCHEMA,
    OVERVIEW_SCHEMA,
    REASONING_SCHEMA,
)
from runmal.inspector import reasoning as inspector_reasoning

REPO = Path(__file__).parent.parent

THINK_MARKER = "ZqxP210UnmistakableThinking"
CONTENT_MARKER = "ZqxP210UnmistakableContent"

CARD = {
    "name": "Asta",
    "description": "Keeper of the mead hall at TESTHOLD.",
    "personality": "Warm but exact.",
    "scenario": "A longhouse hall.",
    "first_mes": "Sit, traveller.",
    "system_prompt": "You are Asta of TESTHOLD.",
}

STATUSES = ("recorded", "not_present", "not_recorded", "unknown")

TOP_KEYS = {"schema", "chat_id", "coverage", "summary", "messages"}
SUMMARY_KEYS = {
    "messages_total",
    "active_by_status",
    "messages_with_recorded",
    "swipes_total",
    "swipes_recorded",
    "swipes_by_status",
}
ENTRY_KEYS = {
    "message_id",
    "role",
    "active_status",
    "recorded",
    "recorded_at",
    "swipes_recorded",
    "raw_road",
}


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


def make_chat(client, title="Saga"):
    created = client.post("/api/v1/chats", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def post_message(client, chat_id, role, content, reasoning=None):
    body = {"role": role, "content": content}
    if reasoning is not None:
        body["reasoning"] = reasoning
    resp = client.post(f"/api/v1/chats/{chat_id}/messages", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_doc(client, chat_id):
    resp = client.get(f"/api/v1/inspector/chats/{chat_id}/reasoning")
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


async def owner_id(factory):
    async with factory() as session:
        return (await get_or_create_owner(session)).id


# -- Shape and roads ------------------------------------------------------


def test_01_shape_schema_and_exact_keys(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    posted = post_message(
        client, chat_id, "assistant", "An answer.",
        reasoning={"status": "recorded", "text": "a thought"},
    )
    doc = get_doc(client, chat_id)
    # Both schema strings pinned verbatim: the inspector
    # document's and the P-205 record's are different
    # strings for different documents.
    assert REASONING_SCHEMA == "runmal-p210-inspector-reasoning-v1"
    assert rsn.REASONING_SCHEMA == "runmal-p205-message-reasoning-v1"
    assert doc["schema"] == REASONING_SCHEMA
    assert doc["chat_id"] == chat_id
    assert set(doc) == TOP_KEYS
    assert set(doc["coverage"]) == {"status", "reason"}
    assert set(doc["summary"]) == SUMMARY_KEYS
    assert set(doc["summary"]["active_by_status"]) == set(STATUSES)
    assert set(doc["summary"]["swipes_by_status"]) == set(STATUSES)
    assert len(doc["messages"]) == 1
    entry = doc["messages"][0]
    assert set(entry) == ENTRY_KEYS
    assert entry["message_id"] == posted["id"]
    assert entry["raw_road"] == (
        f"/chats/{chat_id}/messages/{posted['id']}/reasoning"
    )


def test_02_missing_and_foreign_chat_404_and_service_none(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    missing = client.get("/api/v1/inspector/chats/no-such-chat/reasoning")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    factory = client.factory

    async def probe():
        async with factory() as session:
            stranger = User(name="stranger")
            session.add(stranger)
            await session.commit()
            foreign_list = await chats_service.list_chat_reasoning(
                session, stranger.id, chat_id
            )
            foreign_doc = await inspector_reasoning.build_reasoning_document(
                session, stranger.id, chat_id
            )
            missing_list = await chats_service.list_chat_reasoning(
                session, stranger.id, "no-such-chat"
            )
        return foreign_list, foreign_doc, missing_list

    foreign_list, foreign_doc, missing_list = run(probe())
    assert foreign_list is None
    assert foreign_doc is None
    assert missing_list is None


# -- Census correctness ---------------------------------------------------


def test_03_active_counts_one_of_each_status(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(
        client, chat_id, "assistant", "Recorded answer.",
        reasoning={"status": "recorded", "text": "thought one"},
    )
    post_message(
        client, chat_id, "assistant", "Plain answer.",
        reasoning={"status": "not_present"},
    )
    post_message(client, chat_id, "user", "Never wired.")
    doc = get_doc(client, chat_id)
    assert doc["coverage"] == {"status": "available", "reason": None}
    summary = doc["summary"]
    assert summary["messages_total"] == 3
    assert summary["active_by_status"] == {
        "recorded": 1,
        "not_present": 1,
        "not_recorded": 1,
        "unknown": 0,
    }


def test_04_multi_swipe_full_census_vs_active(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    posted = post_message(
        client, chat_id, "assistant", "First answer.",
        reasoning={"status": "recorded", "text": "first thought"},
    )
    added = client.post(
        f"/api/v1/chats/{chat_id}/messages/{posted['id']}/swipes",
        json={"content": "Second answer."},
    )
    assert added.status_code == 201, added.text
    doc = get_doc(client, chat_id)
    summary = doc["summary"]
    # Both swipes are in the full-document census...
    assert summary["swipes_by_status"] == {
        "recorded": 1,
        "not_present": 0,
        "not_recorded": 1,
        "unknown": 0,
    }
    assert summary["swipes_total"] == 2
    # ...while the active family reflects only the active
    # swipe (the newly added alternate, not_recorded).
    assert summary["active_by_status"] == {
        "recorded": 0,
        "not_present": 0,
        "not_recorded": 1,
        "unknown": 0,
    }
    entry = doc["messages"][0]
    assert entry["active_status"] == "not_recorded"
    assert entry["swipes_recorded"] == [0]
    assert summary["swipes_recorded"] == 1
    assert summary["messages_with_recorded"] == 1


def test_05_recorded_at_carried_and_order_is_chat_order(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    recorded = post_message(
        client, chat_id, "assistant", "Recorded answer.",
        reasoning={"status": "recorded", "text": "a thought"},
    )
    legacy = post_message(client, chat_id, "assistant", "Legacy answer.")
    factory = client.factory

    async def make_legacy():
        # A pre-0042 legacy row: the stored document is the
        # "{}" default, read tolerantly as unrecorded.
        async with factory() as session:
            row = (
                await session.execute(
                    select(Message).where(Message.id == legacy["id"])
                )
            ).scalar_one()
            row.reasoning_json = "{}"
            await session.commit()

    run(make_legacy())
    doc = get_doc(client, chat_id)
    assert [e["message_id"] for e in doc["messages"]] == [
        recorded["id"],
        legacy["id"],
    ]
    first, second = doc["messages"]
    raw = client.get(
        f"/api/v1/chats/{chat_id}/messages/{recorded['id']}/reasoning"
    )
    assert raw.status_code == 200, raw.text
    assert first["recorded"] is True
    assert first["recorded_at"] is not None
    assert first["recorded_at"] == raw.json()["recorded_at"]
    assert second["recorded"] is False
    assert second["recorded_at"] is None
    assert second["active_status"] == "not_recorded"


def test_06_empty_chat_honest_emptiness(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    doc = get_doc(client, chat_id)
    assert doc["coverage"]["status"] == "empty"
    assert doc["coverage"]["reason"]
    summary = doc["summary"]
    assert summary["messages_total"] == 0
    assert summary["messages_with_recorded"] == 0
    assert summary["swipes_total"] == 0
    assert summary["swipes_recorded"] == 0
    zero = {status: 0 for status in STATUSES}
    assert summary["active_by_status"] == zero
    assert summary["swipes_by_status"] == zero
    assert doc["messages"] == []


# -- Consistency with the banked surfaces ---------------------------------


def test_07_census_agrees_with_raw_road_per_message(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    first = post_message(
        client, chat_id, "assistant", "First answer.",
        reasoning={"status": "recorded", "text": "first thought"},
    )
    client.post(
        f"/api/v1/chats/{chat_id}/messages/{first['id']}/swipes",
        json={
            "content": "Second answer.",
            "reasoning": {"status": "not_present"},
        },
    )
    post_message(
        client, chat_id, "assistant", "Plain answer.",
        reasoning={"status": "not_present"},
    )
    post_message(client, chat_id, "user", "A question.")
    doc = get_doc(client, chat_id)
    assert len(doc["messages"]) == 3
    for entry in doc["messages"]:
        raw_resp = client.get(
            f"/api/v1/chats/{chat_id}/messages/"
            f"{entry['message_id']}/reasoning"
        )
        assert raw_resp.status_code == 200, raw_resp.text
        raw = raw_resp.json()
        active_record = raw["swipes"].get(
            str(raw["active_swipe_id"]), {"status": "not_recorded"}
        )
        assert entry["active_status"] == active_record["status"]
        assert entry["recorded"] == raw["recorded"]
        assert entry["swipes_recorded"] == sorted(
            int(index)
            for index, record in raw["swipes"].items()
            if record["status"] == "recorded"
        )


def test_08_overview_and_events_documents_unmoved(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(
        client, chat_id, "assistant", "An answer.",
        reasoning={"status": "recorded", "text": "a thought"},
    )
    overview_before = client.get(f"/api/v1/inspector/chats/{chat_id}")
    events_before = client.get(
        f"/api/v1/inspector/chats/{chat_id}/events"
    )
    assert overview_before.status_code == 200, overview_before.text
    assert events_before.status_code == 200, events_before.text
    get_doc(client, chat_id)  # the join exists and is read
    overview_after = client.get(f"/api/v1/inspector/chats/{chat_id}")
    events_after = client.get(f"/api/v1/inspector/chats/{chat_id}/events")
    assert overview_after.json() == overview_before.json()
    assert events_after.json() == events_before.json()
    assert overview_after.json()["schema"] == OVERVIEW_SCHEMA
    assert events_after.json()["schema"] == EVENTS_SCHEMA
    assert OVERVIEW_SCHEMA == "runmal-p203-inspector-overview-v1"
    assert EVENTS_SCHEMA == "runmal-p204-inspector-events-v1"


# -- Honesty fences ---------------------------------------------------------


def test_09_no_thinking_text_and_no_text_key(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(
        client, chat_id, "assistant", f"{CONTENT_MARKER} answer.",
        reasoning={"status": "recorded", "text": THINK_MARKER},
    )
    doc = get_doc(client, chat_id)
    blob = json.dumps(doc)
    assert THINK_MARKER not in blob
    assert CONTENT_MARKER not in blob
    assert "text" not in set(walk_keys(doc))


def test_10_read_only_two_gets_identical_nothing_written(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(
        client, chat_id, "assistant", "An answer.",
        reasoning={"status": "recorded", "text": "a thought"},
    )
    post_message(client, chat_id, "user", "A question.")
    factory = client.factory

    async def snapshot():
        async with factory() as session:
            uid = (await get_or_create_owner(session)).id
            history = await chats_service.get_history(session, uid, chat_id)
            events = await chats_service.list_events(session, uid, chat_id)
        return (
            [(m.id, m.content, m.reasoning_json) for m in history],
            len(events),
        )

    before = run(snapshot())
    first = get_doc(client, chat_id)
    second = get_doc(client, chat_id)
    after = run(snapshot())
    assert first == second
    assert after == before


def test_11_group_transcript_never_in_a_chat_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", "A lone question.")
    factory = client.factory

    async def seed_group():
        async with factory() as session:
            uid = (await get_or_create_owner(session)).id
            character = await create_character(session, uid, dict(CARD))
            group = await group_store.create_group(
                session, uid, "Mead Hall", [character.id]
            )
            record = rsn.build_record(
                status="recorded", text=THINK_MARKER
            )
            message = await group_store.append_message(
                session, uid, group.id, character.id,
                "A group answer.", reasoning=record,
            )
            return group.id, message.id

    group_id, group_message_id = run(seed_group())
    doc = get_doc(client, chat_id)
    assert doc["summary"]["messages_total"] == 1
    assert group_message_id not in {
        e["message_id"] for e in doc["messages"]
    }
    assert THINK_MARKER not in json.dumps(doc)
    # A group id is not a chat id on this road either.
    resp = client.get(f"/api/v1/inspector/chats/{group_id}/reasoning")
    assert resp.status_code == 404


# -- Migration and census fences ------------------------------------------


def test_12_migration_head_still_0042():
    assert MIGRATIONS[-1][0] == "0042"
    migrations_dir = REPO / "src" / "runmal" / "db" / "migrations"
    assert not [p.name for p in migrations_dir.glob("m0043*")]


def test_13_route_census_grows_by_exactly_one_road(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
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
    # P-211 heal: 356 / 439 since P-211's one new road
    # (the Inspector group reasoning road).
    assert len(paths) == 365  # 354 at P-209 + P-210/P-211 roads
    assert operations == 455
    assert "/api/v1/inspector/chats/{chat_id}/reasoning" in paths


def test_14_malformed_stored_reasoning_censuses_unknown(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    posted = post_message(
        client, chat_id, "assistant", "An answer.",
        reasoning={"status": "recorded", "text": "a thought"},
    )
    factory = client.factory

    async def corrupt():
        # Hand-corrupt the stored record inside an otherwise
        # valid document: a recorded record whose text is not
        # a string. The banked tolerant readers read it as
        # unknown; the census joins that, never raises.
        async with factory() as session:
            row = (
                await session.execute(
                    select(Message).where(Message.id == posted["id"])
                )
            ).scalar_one()
            row.reasoning_json = json.dumps(
                {
                    "schema": rsn.REASONING_SCHEMA,
                    "recorded": True,
                    "recorded_at": "2026-11-09T00:00:00+00:00",
                    "swipes": {
                        "0": {"status": "recorded", "text": 42}
                    },
                }
            )
            await session.commit()

    run(corrupt())
    doc = get_doc(client, chat_id)
    entry = doc["messages"][0]
    assert entry["active_status"] == "unknown"
    assert doc["summary"]["active_by_status"]["unknown"] == 1
    assert doc["summary"]["swipes_by_status"]["unknown"] == 1
