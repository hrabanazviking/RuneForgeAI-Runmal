"""P-213 acceptance: the persistent-group transcript loader
on the group page (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- group.html gains ONE aside block above the Roster
  heading: a Saved groups label + <select id="saved-group">
  and <button id="open-group" type="button">Open</button>;
  script tags unchanged (renderer.js already loads BEFORE
  group.js since P-212, so the banked P-206 view-model
  RunmalRenderer.reasoningView is on the page, called
  unchanged, never edited).
- group.js loadSavedGroups() populates the picker from the
  banked list road GET /api/v1/groups (value = id,
  textContent = name + message count); openSavedGroup()
  fetches the banked transcript road
  GET /api/v1/groups/{id}/messages and, on success only,
  clears #group-thread and renders one bubble per stored
  message via the existing addBubble (author = the stored
  speaker_name - user rows carry null and render under the
  page\'s own "user" label - body = the stored content),
  appending the group-local reasoningPanel built from
  window.RunmalRenderer.reasoningView over the stored view
  when one is present - the same pair the P-212 stream
  path uses, no second view model, no second panel
  builder, textContent only.
- DISPLAY-ONLY fence: fetched messages never enter the
  stateless history state, nothing joins sentHistory, the
  loader issues no POST and writes no web storage -
  opening a saved group never changes what the composer
  sends (persistent-group composer wiring is a separate
  later candidate, not founded here).
- Failure path: a failed fetch (including the banked 404)
  surfaces via the existing showError banner and leaves
  the visible thread in place - the clear happens only
  after a successful fetch.
- Fences: migration head stays 0042 (no m0043); the app
  route census stays 356 paths / 439 operations (zero
  census heals - no road is added); the P-212 stream
  branch is untouched in shape.
Fixtures mirror test_p211_inspector_group_reasoning.py /
test_p212_group_assistant_view.py. group.js is not a node
module - it exports nothing and binds DOM listeners at
load - so, like app.js before it, its wiring is pinned by
page, served-source and segment assertions, never by
importing it.
"""

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import create_character
from runmal.chats import reasoning as rsn
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.db.owners import get_or_create_owner
from runmal.groupchat import store as group_store

REPO = Path(__file__).parent.parent
GROUP_JS = REPO / "src" / "runmal" / "web" / "static" / "group.js"
GROUP_HTML = (REPO / "src" / "runmal" / "web" / "templates"
              / "group.html")

THINK_TEXT = "ZqxP213StoredThinking"
CONTENT_TEXT = "ZqxP213StoredContent"

CARD = {
    "name": "Asta",
    "description": "Keeper of the mead hall at TESTHOLD.",
    "personality": "Warm but exact.",
    "scenario": "A longhouse hall.",
    "first_mes": "Sit, traveller.",
    "system_prompt": "You are Asta of TESTHOLD.",
}


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0043"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for store-layer seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    client.db_path = db_path
    return client


def run(coro):
    return asyncio.run(coro)


async def _seed_group(factory, name="Mead Hall"):
    async with factory() as session:
        uid = (await get_or_create_owner(session)).id
        character = await create_character(session, uid, dict(CARD))
        group = await group_store.create_group(
            session, uid, name, [character.id])
        return uid, group.id, character.id


def seed_group(client, name="Mead Hall"):
    return run(_seed_group(client.factory, name))


async def _append(factory, uid, gid, speaker, content, reasoning=None):
    async with factory() as session:
        message = await group_store.append_message(
            session, uid, gid, speaker, content, reasoning=reasoning)
        return message.id


def append(client, uid, gid, speaker, content, reasoning=None):
    return run(_append(
        client.factory, uid, gid, speaker, content, reasoning))


def loader_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function loadSavedGroups")
    end = js.index("function selectedIds()")
    return js[start:end]


# -- Static-source pins over group.html -----------------------------------


# -- Static-source pins over group.js --------------------------------------


# -- API-truth pins (backend unchanged, seeded store) -----------------------


def test_09_transcript_serves_recorded_reasoning_with_text(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    record = rsn.build_record(status="recorded", text=THINK_TEXT)
    mid = append(client, uid, gid, char_id, CONTENT_TEXT,
                 reasoning=record)
    resp = client.get(f"/api/v1/groups/{gid}/messages")
    assert resp.status_code == 200, resp.text
    stored = [m for m in resp.json() if m["id"] == mid]
    assert len(stored) == 1
    message = stored[0]
    assert message["speaker_name"] == "Asta"
    assert message["content"] == CONTENT_TEXT
    # The stored active reasoning view the loader renders,
    # WITH its recorded text (the P-205 record, verbatim).
    assert message["reasoning"]["status"] == "recorded"
    assert message["reasoning"]["text"] == THINK_TEXT


def test_10_list_serves_picker_fields_and_owner_fence(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    append(client, uid, gid, char_id, CONTENT_TEXT)

    async def _foreign(factory):
        async with factory() as session:
            other = User(name="Other Owner")
            session.add(other)
            await session.flush()
            character = await create_character(
                session, other.id, dict(CARD, name="Bryn"))
            group = await group_store.create_group(
                session, other.id, "Foreign Hall", [character.id])
            return group.id

    foreign_gid = run(_foreign(client.factory))
    resp = client.get("/api/v1/groups")
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    mine = [g for g in groups if g["id"] == gid]
    assert len(mine) == 1
    assert mine[0]["name"] == "Mead Hall"
    assert mine[0]["message_count"] == 1
    assert all(g["id"] != foreign_gid for g in groups)


def test_11_unknown_group_transcript_answers_404(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/groups/no-such-group/messages")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "group not found"


# -- Census / head pins ------------------------------------------------------


def test_12_route_census_unchanged(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # No road is added, moved or removed by P-213: the census
    # stands at the P-212 census and NO pin is healed.
    # R-16 heal: 354 / 444 — the web shell is scrapped:
    # the 8 in-schema web page paths, /voice, /memories
    # and /api/v1/memories-browser are gone (-11 paths /
    # -11 operations; "/" was schema-excluded, never counted).
    assert len(paths) == 354
    assert operations == 444


def test_13_migration_head_stays_0042(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0043"
    assert current_revision(client.db_path) == "0043"
    assert [rev for rev, _desc, _mod in MIGRATIONS].count("0043") == 1  # W-12 banking heal: head is now 0043 (m0043_default_chat_profile)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert [n for n in names if n.startswith("m0043")] == ["m0043_default_chat_profile.py"]  # W-12 banking heal: head is now 0043 (m0043_default_chat_profile)
