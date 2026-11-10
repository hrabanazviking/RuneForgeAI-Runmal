"""P-204 acceptance: the Inspector events document -
Part XIII second slice (Assistant View, Inspector &
Bots, DERIVED scope).

Contract under test:
- ONE schema-versioned document (runmal-p204-inspector-
  events-v1) per owned chat, composing the banked S107
  durable chat event log by CALLING the banked
  chats-service read (list_events).
- The census (total, by_kind, first_at / last_at,
  latest) agrees EXACTLY with the rows the banked raw
  road (GET /chats/{chat_id}/events) returns for the
  same chat; stored kind strings are counted verbatim,
  legacy kinds included.
- No-payload law: no event data payload and no message
  content anywhere in the document; no "data" key at
  any depth. Payloads stay on the raw road, which the
  document points at.
- A chat with no recorded rows reads events status
  empty, total 0, by_kind {} - never a faked census.
  An upstream read failure reads unavailable + reason.
- The actions section counts the five action kinds from
  the SAME census; the flags section reads
  not_applicable (bind-time bool seeds) with pointers;
  not_recorded names exactly three families (generation
  events, plugin dispatches, chat.deleted), each
  not_applicable + reason.
- Unknown and unowned chats are refused in the house
  404 idiom; the P-203 overview document shape is
  unchanged; the app route set grows by exactly one
  road; no migration (head stays 0041, no m0042).
Fixtures mirror test_p203_inspector_overview.py.
"""

from __future__ import annotations

import asyncio
import copy
import json

from fastapi.testclient import TestClient
from sqlalchemy import delete

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, ChatEvent, User
from runmal.inspector import EVENTS_SCHEMA, OVERVIEW_SCHEMA
from runmal.inspector import events as events_mod

MARKER = "ZqxP204UnmistakablePayload"

ACTION_KINDS = [
    "message.edited",
    "message.pinned_to_memory",
    "message.unpinned_from_memory",
    "message.moved",
    "message.copied_to_branch",
]


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


def post_message(client, chat_id, role, content):
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": role, "content": content},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_events_doc(client, chat_id):
    resp = client.get(f"/api/v1/inspector/chats/{chat_id}/events")
    assert resp.status_code == 200, resp.text
    return resp.json()


def get_raw_events(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/events")
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


def drive_chat(client):
    """A chat driven through the banked service paths:
    create, append x2, edit, swipe add + select, pin,
    rename - one occurrence of each driven kind."""
    chat_id = make_chat(client)
    first = post_message(client, chat_id, "user", "First line.")
    post_message(client, chat_id, "assistant", "Second line.")
    edited = client.patch(
        f"/api/v1/chats/{chat_id}/messages/{first['id']}",
        json={"content": "First line, revised."},
    )
    assert edited.status_code == 200, edited.text
    added = client.post(
        f"/api/v1/chats/{chat_id}/messages/{first['id']}/swipes",
        json={"content": "An alternate first line."},
    )
    assert added.status_code == 201, added.text
    # add_swipe activates the new alternate, so selecting
    # index 0 is the real change that records the event.
    selected = client.post(
        f"/api/v1/chats/{chat_id}/messages/{first['id']}/swipes/select",
        json={"index": 0},
    )
    assert selected.status_code == 200, selected.text
    pinned = client.post(
        f"/api/v1/chats/{chat_id}/messages/{first['id']}/pin"
    )
    assert pinned.status_code == 201, pinned.text
    renamed = client.patch(
        f"/api/v1/chats/{chat_id}", json={"title": "Saga Renewed"}
    )
    assert renamed.status_code == 200, renamed.text
    return chat_id


# -- Schema + shape -------------------------------------------------------


def test_schema_pinned_and_no_migration(tmp_path, monkeypatch):
    make_client(tmp_path, monkeypatch)
    assert EVENTS_SCHEMA == "runmal-p204-inspector-events-v1"
    assert OVERVIEW_SCHEMA == "runmal-p203-inspector-overview-v1"
    assert MIGRATIONS[-1][0] == "0042"
    assert [rev for rev, _name, _mod in MIGRATIONS].count("0042") == 1  # P-205 banking heal: 0042 taken once, by P-205 m0042


def test_document_shape_and_section_statuses(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    doc = get_events_doc(client, chat_id)
    assert doc["schema"] == "runmal-p204-inspector-events-v1"
    assert doc["chat_id"] == chat_id
    assert doc["generated_from"] == ["S107 chat event log"]
    assert set(doc["sections"]) == {
        "events", "actions", "flags", "not_recorded"}
    for section in doc["sections"].values():
        assert section["status"] in events_mod.SECTION_STATUSES
        assert "reason" in section
    events = doc["sections"]["events"]
    assert events["status"] == "available"
    assert events["reason"] is None
    assert events["raw_road"] == {
        "method": "GET", "path": f"/api/v1/chats/{chat_id}/events"}


# -- Census exactness -------------------------------------------------------


def test_census_matches_raw_road_exactly(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = drive_chat(client)
    raw = get_raw_events(client, chat_id)
    expected_by_kind = {}
    for row in raw:
        expected_by_kind[row["kind"]] = expected_by_kind.get(row["kind"], 0) + 1
    # The driven operations each recorded exactly once.
    for kind in (
        "chat.created", "message.edited", "message.swipe_added",
        "message.swipe_selected", "message.pinned_to_memory",
        "chat.renamed",
    ):
        assert expected_by_kind[kind] == 1, expected_by_kind
    assert expected_by_kind["message.appended"] == 2
    doc = get_events_doc(client, chat_id)
    events = doc["sections"]["events"]
    assert events["status"] == "available"
    assert events["total"] == len(raw)
    assert events["by_kind"] == expected_by_kind
    assert events["first_at"] == raw[0]["created_at"]
    assert events["last_at"] == raw[-1]["created_at"]
    assert events["latest"] == {
        "kind": raw[-1]["kind"], "created_at": raw[-1]["created_at"]}


def test_legacy_kind_counted_verbatim(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def seed_legacy():
        async with factory() as session:
            session.add(ChatEvent(
                chat_id=chat_id, kind="legacy.unknown_kind", data="{}"))
            await session.commit()

    run(seed_legacy())
    doc = get_events_doc(client, chat_id)
    events = doc["sections"]["events"]
    # Counted under its own stored string, never renamed
    # or dropped against the 20-kind catalogue.
    assert events["by_kind"]["legacy.unknown_kind"] == 1
    assert events["total"] == 2


# -- No-payload law ---------------------------------------------------------


def test_no_payload_marker_and_no_data_key(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", f"{MARKER} in a message")
    # The rename path stores the title in the event's data
    # payload: the marker rides the payload verbatim.
    renamed = client.patch(
        f"/api/v1/chats/{chat_id}", json={"title": MARKER})
    assert renamed.status_code == 200, renamed.text
    factory = client.factory

    async def seed_payload():
        async with factory() as session:
            session.add(ChatEvent(
                chat_id=chat_id, kind="message.appended",
                data=json.dumps({"note": MARKER})))
            await session.commit()

    run(seed_payload())
    raw = get_raw_events(client, chat_id)
    assert MARKER in json.dumps(raw)  # the payload really is there
    doc = get_events_doc(client, chat_id)
    blob = json.dumps(doc)
    assert MARKER not in blob
    keys = set(walk_keys(doc))
    assert "data" not in keys
    assert "content" not in keys


# -- Empty + unavailable honesty ---------------------------------------------


def test_empty_chat_honesty(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def clear_log():
        async with factory() as session:
            await session.execute(
                delete(ChatEvent).where(ChatEvent.chat_id == chat_id))
            await session.commit()

    run(clear_log())
    assert get_raw_events(client, chat_id) == []
    doc = get_events_doc(client, chat_id)
    events = doc["sections"]["events"]
    assert events["status"] == "empty"
    assert events["reason"]
    assert events["total"] == 0
    assert events["by_kind"] == {}
    assert events["first_at"] is None
    assert events["last_at"] is None
    assert events["latest"] is None
    actions = doc["sections"]["actions"]
    assert actions["status"] == "empty"
    assert actions["counts"] == {kind: 0 for kind in ACTION_KINDS}
    assert actions["total"] == 0


def test_upstream_failure_reads_unavailable(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def broken(session, user_id, cid):
        raise RuntimeError("log store exploded")

    monkeypatch.setattr(chats_service, "list_events", broken)

    async def probe():
        async with factory() as session:
            chat = await session.get(Chat, chat_id)
            return await events_mod.build_events_document(
                session, chat.user_id, chat_id)

    doc = run(probe())
    assert doc is not None
    events = doc["sections"]["events"]
    assert events["status"] == "unavailable"
    assert "log store exploded" in events["reason"]
    assert events["total"] is None
    actions = doc["sections"]["actions"]
    assert actions["status"] == "unavailable"
    assert actions["counts"] == {}
    # The fixed sections are unaffected by the failed read.
    assert doc["sections"]["flags"]["status"] == "not_applicable"
    assert len(doc["sections"]["not_recorded"]["entries"]) == 3


# -- Actions + flags + not_recorded ------------------------------------------


def test_actions_counts_equal_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = drive_chat(client)
    doc = get_events_doc(client, chat_id)
    events = doc["sections"]["events"]
    actions = doc["sections"]["actions"]
    assert actions["status"] == "available"
    assert actions["kinds"] == ACTION_KINDS
    for kind in ACTION_KINDS:
        assert actions["counts"][kind] == events["by_kind"].get(kind, 0)
    assert actions["total"] == sum(actions["counts"].values())
    assert actions["counts"]["message.edited"] == 1
    assert actions["counts"]["message.pinned_to_memory"] == 1
    assert actions["counts"]["message.moved"] == 0
    pointer = actions["pointer"]
    assert pointer["method"] == "GET"
    assert pointer["path"] == f"/api/v1/chats/{chat_id}/messages"
    assert "m0038" in pointer["note"]


SCENARIO_BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "impersonation_name": "Ash",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.",
         "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def test_flags_not_applicable_bound_and_unbound(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client, title="Harbour")
    doc = get_events_doc(client, chat_id)
    flags = doc["sections"]["flags"]
    assert flags["status"] == "not_applicable"
    assert "bind-time" in flags["reason"]
    assert "bool" in flags["reason"]
    pointer = flags["pointers"]["overview_scenario"]
    assert pointer == {
        "method": "GET", "path": f"/api/v1/inspector/chats/{chat_id}"}
    definition = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(SCENARIO_BODY))
    assert definition.status_code == 201, definition.text
    bound = client.post(
        f"/api/v1/scenarios/{definition.json()['id']}/bind",
        json={"chat_id": chat_id},
    )
    assert bound.status_code == 201, bound.text
    doc = get_events_doc(client, chat_id)
    flags = doc["sections"]["flags"]
    # Bound or not, flags remain bind-time seeds: no stream.
    assert flags["status"] == "not_applicable"
    assert "met_maera" not in json.dumps(doc)


def test_not_recorded_exactly_three_families(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    doc = get_events_doc(client, chat_id)
    section = doc["sections"]["not_recorded"]
    assert section["status"] == "not_applicable"
    assert section["reason"]
    entries = section["entries"]
    assert [e["name"] for e in entries] == [
        "generation events", "plugin dispatches", "chat.deleted"]
    for entry in entries:
        assert entry["status"] == "not_applicable"
        assert entry["reason"]


# -- Refusals, P-203 stability, route set, purity ---------------------------


def test_unknown_chat_refused(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/inspector/chats/no-such-chat/events")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "chat not found"


def test_unowned_chat_refused_at_service_layer(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def probe():
        async with factory() as session:
            stranger = User(name="stranger")
            session.add(stranger)
            await session.commit()
            return await events_mod.build_events_document(
                session, stranger.id, chat_id)

    assert run(probe()) is None


def test_overview_shape_unchanged(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = drive_chat(client)
    resp = client.get(f"/api/v1/inspector/chats/{chat_id}")
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["schema"] == "runmal-p203-inspector-overview-v1"
    assert doc["generated_from"] == [
        "P-043", "P-059", "P-075", "scenario bindings"]
    assert set(doc["sections"]) == {
        "provenance", "prompt", "lore_activation", "scenario"}


def test_route_set_grows_by_exactly_one(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    spec = client.get("/openapi.json")
    assert spec.status_code == 200, spec.text
    paths = spec.json()["paths"]
    inspector_paths = {
        path for path in paths if path.startswith("/api/v1/inspector")}
    # P-203 banked exactly one inspector road; P-204 adds
    # exactly the events road beside it - no more.
    # P-210 heal: P-210 adds exactly the reasoning road
    # beside those two in its own slice; the set is still
    # exact - no more.
    # P-211 heal: P-211 adds exactly the group reasoning
    # road beside those three in its own slice; the set
    # is still exact - no more.
    assert inspector_paths == {
        "/api/v1/inspector/chats/{chat_id}",
        "/api/v1/inspector/chats/{chat_id}/events",
        "/api/v1/inspector/chats/{chat_id}/reasoning",
        "/api/v1/inspector/groups/{group_id}/reasoning",
    }
    assert "get" in paths["/api/v1/inspector/chats/{chat_id}/events"]
    from runmal.inspector.router import router as inspector_router

    assert len(inspector_router.routes) == 4


def test_events_document_is_a_pure_read(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = drive_chat(client)
    before = get_raw_events(client, chat_id)
    first = get_events_doc(client, chat_id)
    second = get_events_doc(client, chat_id)
    assert first == second
    assert get_raw_events(client, chat_id) == before
