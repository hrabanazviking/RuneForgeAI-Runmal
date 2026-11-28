"""P-216 acceptance: saved-group creation on the group
page (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- group.html gains, in the aside's Saved groups block
  directly after the P-215 group-mode line, exactly two
  elements: a labelled text input
  <input id="new-group-name" type="text"> and
  <button id="create-group" type="button">Create
  group</button>.
- group.js gains createGroup(): the trimmed name is the
  creation name, the members are selectedIds() (the
  roster boxes ticked at click time, in page order). A
  trimmed-empty name creates NOTHING - no POST, only
  showError. Otherwise it POSTs the banked creation road
  POST /api/v1/groups via the existing api() helper; on
  success ONLY it clears the name input, re-runs
  loadSavedGroups() and sets select#saved-group's value
  to the returned group id. The new group is SELECTED,
  never opened: createGroup calls no openSavedGroup,
  sets no openGroupId and fetches no transcript. On
  failure the catch surfaces showError and leaves the
  input, the picker, the thread and every mode/composer
  state exactly as they were.
- The P-213 loader fence, the P-215 close fence, both
  P-214 composer branches, the P-215 mode strings and
  the textContent-only rule stand restated.
- API truth over the banked creation road (S210
  contract): create-with-roster answers 201 with the
  describe shape and the group then lists; an unknown
  member answers 422 and nothing is half-created.
- Route census unchanged 356 paths / 439 operations;
  migration head stays 0042; group.html's control census
  is exact (every prior id plus exactly new-group-name
  and create-group).
Fixtures mirror test_p215_group_mode_toggle.py. group.js
is not a node module, so its wiring is pinned by
served-source and segment assertions, never by importing
it. Segment note (P-216 design section 5 placement
contingency): createGroup sits directly after
selectedIds() and before sendPersistent, so the banked
loader / close / persistent segments stay literally true
of their own blocks and the slice's one POST lives only
inside createGroup's block.
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
from runmal.db.owners import get_or_create_owner

REPO = Path(__file__).parent.parent
GROUP_JS = REPO / "src" / "runmal" / "web" / "static" / "group.js"
GROUP_HTML = (REPO / "src" / "runmal" / "web" / "templates"
              / "group.html")

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
    client.factory = factory  # same DB, for service seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    client.db_path = db_path
    return client


def run(coro):
    return asyncio.run(coro)


async def _seed_characters(factory):
    async with factory() as session:
        uid = (await get_or_create_owner(session)).id
        first = await create_character(session, uid, dict(CARD))
        second = await create_character(
            session, uid, dict(CARD, name="Bryn"))
        return uid, first.id, second.id


def seed_characters(client):
    return run(_seed_characters(client.factory))


def create_segment():
    js = GROUP_JS.read_text()
    start = js.index("async function createGroup()")
    end = js.index("async function sendPersistent")
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


def test_11_create_with_roster_describes_and_lists(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, first_id, second_id = seed_characters(client)
    resp = client.post(
        "/api/v1/groups",
        json={"name": "Mead Hall",
              "member_character_ids": [first_id, second_id]})
    assert resp.status_code == 201, resp.text
    created = resp.json()
    for key in ("id", "name", "chat_id", "members",
                "member_count", "message_count"):
        assert key in created, key
    assert created["name"] == "Mead Hall"
    assert created["member_count"] == 2
    assert created["message_count"] == 0
    assert len(created["members"]) == 2
    listed = client.get("/api/v1/groups")
    assert listed.status_code == 200, listed.text
    mine = [g for g in listed.json() if g["id"] == created["id"]]
    assert len(mine) == 1
    assert mine[0]["name"] == "Mead Hall"
    assert mine[0]["member_count"] == 2


def test_12_unknown_member_422_and_nothing_created(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    seed_characters(client)
    resp = client.post(
        "/api/v1/groups",
        json={"name": "Mead Hall",
              "member_character_ids": ["no-such-character"]})
    assert resp.status_code == 422, resp.text
    listed = client.get("/api/v1/groups")
    assert listed.status_code == 200, listed.text
    assert listed.json() == []


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
    assert MIGRATIONS[-1][0] == "0043"
    assert current_revision(client.db_path) == "0043"
    assert [rev for rev, _desc, _mod in MIGRATIONS].count("0043") == 1  # W-12 banking heal: head is now 0043 (m0043_default_chat_profile)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert [n for n in names if n.startswith("m0043")] == ["m0043_default_chat_profile.py"]  # W-12 banking heal: head is now 0043 (m0043_default_chat_profile)
    # R-16: the group.html control census leg is scrapped
    # with the web shell; census + head fences above stand.
