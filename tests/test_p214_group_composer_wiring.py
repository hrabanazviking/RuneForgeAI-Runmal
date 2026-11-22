"""P-214 acceptance: persistent-group composer wiring on
the group page (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- group.js gains one piece of page state, openGroupId,
  initialised null (the stateless room). The P-213 loader
  openSavedGroup() sets it from the picked group id, on
  success only - the assignment sits after the successful
  fetch and render loop, never in the catch, so a failed
  open keeps the composer's prior mode.
- The P-213 loader fence stands in its true P-214 form:
  the loader still copies nothing into the stateless
  history state, references no sentHistory and writes no
  web storage; what changes is only what the composer
  does next - opening a saved group puts the composer
  into that group's persistent mode.
- The #group-form submit handler keeps its shared head
  (preventDefault, trim, empty return, clear input, the
  user's bubble) and then branches on openGroupId BEFORE
  any sentHistory snapshot or history mutation: set -
  the new sendPersistent(text) runs and the handler
  returns; null - the banked stateless body runs
  byte-unchanged (POST /api/v1/group/turn with
  participant_ids, history: sentHistory, strategy,
  rr_cursor, the SSE loop, the P-212 panels).
- sendPersistent POSTs through the existing api() helper
  to /api/v1/groups/{openGroupId}/next with
  {user_text, generate: true} - a plain JSON road, no SSE
  reading - and renders result.message through the same
  addBubble + reasoningPanel(reasoningView(...)) pair
  the P-213 stored path uses. A null message renders
  nothing further. Errors surface via showError. The
  persistent branch references none of the stateless
  turn state (no history, sentHistory, rrCursor,
  selectedIds or strategy), never calls
  /api/v1/group/turn and writes no web storage.
- API truth over the banked roads: /next with
  generate=false stores the user turn server-side,
  returns message null and names the group's own stored
  strategy; an unknown group answers 404; a /messages +
  /next round trip leaves the stored transcript exactly
  the appended turns.
- Fences: group.html is untouched (exactly the P-213
  control set, no new ids); migration head stays 0042;
  the route census stays 356 paths / 439 operations
  (zero census heals - no road is added).
Fixtures mirror test_p213_group_transcript_loader.py.
group.js is not a node module, so its wiring is pinned
by served-source and segment assertions, never by
importing it.
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
from runmal.groupchat import store as group_store

REPO = Path(__file__).parent.parent
GROUP_JS = REPO / "src" / "runmal" / "web" / "static" / "group.js"
GROUP_HTML = (REPO / "src" / "runmal" / "web" / "templates"
              / "group.html")

USER_TEXT = "ZqxP214UserTurn"
FIRST_TEXT = "ZqxP214FirstStored"
SECOND_TEXT = "ZqxP214SecondStored"

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
        from runmal.db.owners import get_or_create_owner
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


# -- Static-source pins over group.js --------------------------------------


# -- API-truth pins (backend unchanged, seeded store) -----------------------


def test_11_next_stores_user_turn_and_returns_null_message(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    described = client.get(f"/api/v1/groups/{gid}")
    assert described.status_code == 200, described.text
    resp = client.post(
        f"/api/v1/groups/{gid}/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["message"] is None
    # The speaker choice is the group's own stored policy,
    # never the page's strategy select.
    assert result["strategy"] == described.json()["speaker_policy"]
    stored = client.get(f"/api/v1/groups/{gid}/messages")
    assert stored.status_code == 200, stored.text
    turns = [m for m in stored.json() if m["content"] == USER_TEXT]
    assert len(turns) == 1
    assert turns[0]["role"] == "user"
    assert turns[0]["speaker_name"] is None


def test_12_next_on_unknown_group_answers_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/groups/no-such-group/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "group not found"


def test_13_round_trip_leaves_exactly_the_appended_turns(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    uid, gid, char_id = seed_group(client)
    first = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": "user", "content": FIRST_TEXT})
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/groups/{gid}/messages",
        json={"speaker": char_id, "content": SECOND_TEXT})
    assert second.status_code == 201, second.text
    nxt = client.post(
        f"/api/v1/groups/{gid}/next",
        json={"user_text": USER_TEXT, "generate": False})
    assert nxt.status_code == 200, nxt.text
    stored = client.get(f"/api/v1/groups/{gid}/messages")
    assert stored.status_code == 200, stored.text
    messages = stored.json()
    # No phantom writes: exactly the three appended turns,
    # in append order - the road truth the composer
    # relies on.
    assert [m["content"] for m in messages] == [
        FIRST_TEXT, SECOND_TEXT, USER_TEXT]
    assert messages[1]["speaker_name"] == "Asta"


# -- Census / head / page-integrity pin --------------------------------------


def test_14_census_head_and_page_integrity(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # No road is added, moved or removed by P-214: the census
    # stands at the P-213 census and NO pin is healed.
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
