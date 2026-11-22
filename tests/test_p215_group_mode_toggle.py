"""P-215 acceptance: explicit composer mode toggle /
close-group control on the group page (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- group.html gains, in the aside's Saved groups block
  directly under the Open button, exactly two elements:
  <button id="close-group" type="button" disabled> and
  <p id="group-mode"> whose initial text is exactly
  "Stateless room".
- group.js: openSavedGroup's SUCCESS path (the P-214
  path) also restates the mode - the mode line becomes
  exactly "Saved group mode" and the close control is
  enabled, both after the openGroupId set, never in the
  catch, so a failed open changes neither.
- New closeSavedGroup(): the in-page equivalent of the
  P-214 reload exit, minus the re-fetch. Guarded by
  if (!openGroupId) return; it sets openGroupId = null,
  clears #group-thread, resets history = [] and
  rrCursor = 0, restores the mode line to "Stateless
  room" and disables the close control. It issues no
  fetch or POST, writes no web storage and deletes
  nothing - the stored group is untouched and can be
  re-opened at once.
- The P-213 loader fence, both P-214 composer branches
  and the textContent-only rule stand restated.
- API truth over the banked roads the two modes rely
  on; route census unchanged 356 paths / 439
  operations; migration head stays 0042; group.html's
  control census is exact (every prior id plus exactly
  close-group and group-mode).
Fixtures mirror test_p213_group_transcript_loader.py /
test_p214_group_composer_wiring.py. group.js is not a
node module, so its wiring is pinned by served-source
and segment assertions, never by importing it.
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

USER_TEXT = "ZqxP215UserTurn"
FIRST_TEXT = "ZqxP215FirstStored"

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


def loader_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function loadSavedGroups")
    end = js.index("function closeSavedGroup()")
    return js[start:end]


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


def submit_segment():
    js = GROUP_JS.read_text()
    start = js.index('$("group-form").addEventListener')
    end = js.index("loadRoster().catch")
    return js[start:end]


def persistent_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function sendPersistent")
    end = js.index('$("group-form").addEventListener')
    return js[start:end]


# -- Static-source pins over group.html / group.js --------------------------


# -- API-truth pins (backend unchanged, seeded store) -----------------------


def test_11_list_serves_picker_fields_and_owner_fence(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    first = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": "user", "content": FIRST_TEXT})
    assert first.status_code == 201, first.text

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


def test_12_next_stores_turn_and_unknown_messages_404(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    resp = client.post(
        f"/api/v1/groups/{gid}/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] is None
    stored = client.get(f"/api/v1/groups/{gid}/messages")
    assert stored.status_code == 200, stored.text
    turns = [m for m in stored.json() if m["content"] == USER_TEXT]
    assert len(turns) == 1
    assert turns[0]["role"] == "user"
    unknown = client.get("/api/v1/groups/no-such-group/messages")
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["detail"] == "group not found"


# -- Census / integrity pins --------------------------------------------------


def test_13_route_census_unchanged(tmp_path, monkeypatch):
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


def test_14_head_and_exact_control_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(client.db_path) == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)
    # R-16: the group.html control census leg is scrapped
    # with the web shell; census + head fences above stand.
