"""P-217 acceptance: persistent-mode refinements on the
group page (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change, no markup change):
- On a successful open only, openSavedGroup disables the
  strategy select and every roster checkbox - the roster
  and strategy controls govern only the stateless room;
  in persistent mode speaker choice is the opened group's
  own stored policy. A failed open changes no control
  state (the catch still only calls showError).
- closeSavedGroup re-enables both controls among its
  P-215 reload-equivalent restatements; close stays
  network- and storage-free.
- After a SUCCESSFUL persistent send - a rendered reply
  or a null message alike - sendPersistent re-runs
  loadSavedGroups() (the banked list road, display-only)
  and re-sets select#saved-group's value to openGroupId,
  so the picker's stored message_count labels track the
  server truth. On failure there is no refresh: the catch
  keeps its showError-only shape. The P-214 early return
  is replaced by a guarded render so the null path reaches
  the refresh tail having rendered nothing.
- The P-213 loader fence, both composer branches, the
  P-215 mode strings, the P-216 creation truth and the
  textContent-only rule stand restated.
- API truth over the banked roads the refinements rely
  on: /next with generate=false stores the user turn
  server-side (the list count rises 0 -> 1 -> 2) and
  returns a null message; an unknown group answers 404;
  the list road serves the picker fields for an owned
  group and nothing for another owner's.
- Route census unchanged 356 paths / 439 operations;
  migration head stays 0042; group.html's control census
  is exact (the build-base set, NO new ids - this slice
  changes no markup).
Fixtures mirror test_p216_group_creation.py. group.js is
not a node module, so its wiring is pinned by served-
source and segment assertions, never by importing it.
"""

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import create_character
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

USER_TEXT = "ZqxP217UserTurn"

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
    assert applied[-1] == "0042"
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


def open_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function openSavedGroup")
    end = js.index("function closeSavedGroup()")
    return js[start:end]


def close_segment():
    js = GROUP_JS.read_text()
    start = js.index("function closeSavedGroup()")
    end = js.index("function selectedIds()")
    return js[start:end]


def create_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function createGroup()")
    end = js.index("async function sendPersistent")
    return js[start:end]


def persistent_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function sendPersistent")
    end = js.index('$("group-form").addEventListener')
    return js[start:end]


def submit_segment():
    js = GROUP_JS.read_text()
    start = js.index('$("group-form").addEventListener')
    end = js.index("loadRoster().catch")
    return js[start:end]


# -- Static-source pins over group.js --------------------------------------


# -- API-truth pins (backend unchanged, seeded store) -----------------------


def _listed_count(client, gid):
    resp = client.get("/api/v1/groups")
    assert resp.status_code == 200, resp.text
    mine = [g for g in resp.json() if g["id"] == gid]
    assert len(mine) == 1
    return mine[0]["message_count"]


def test_12_count_truth_rises_with_stored_user_turns(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    assert _listed_count(client, gid) == 0
    first = client.post(
        f"/api/v1/groups/{gid}/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert first.status_code == 200, first.text
    assert first.json()["message"] is None
    assert _listed_count(client, gid) == 1
    second = client.post(
        f"/api/v1/groups/{gid}/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert second.status_code == 200, second.text
    assert second.json()["message"] is None
    assert _listed_count(client, gid) == 2


def test_13_next_unknown_404_and_list_owner_fence(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    unknown = client.post(
        "/api/v1/groups/no-such-group/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert unknown.status_code == 404, unknown.text

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
    for key in ("id", "name", "message_count"):
        assert key in mine[0], key
    assert mine[0]["name"] == "Mead Hall"
    assert all(g["id"] != foreign_gid for g in groups)


# -- Census / integrity pin ---------------------------------------------------


def test_14_census_head_and_exact_control_census(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # R-16 heal: 354 / 444 — the web shell is scrapped:
    # the 8 in-schema web page paths, /voice, /memories
    # and /api/v1/memories-browser are gone (-11 paths /
    # -11 operations; "/" was schema-excluded, never counted).
    assert len(paths) == 354
    assert operations == 444
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(client.db_path) == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)
    # R-16: the group.html control census leg is scrapped
    # with the web shell; census + head fences above stand.
