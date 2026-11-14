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
import re
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


def test_01_open_group_state_declared_null():
    js = GROUP_JS.read_text()
    assert "let openGroupId = null;" in js


def test_02_loader_sets_open_group_on_success_only():
    segment = loader_segment()
    assert "openGroupId = groupId;" in segment
    set_at = segment.index("openGroupId = groupId;")
    assert segment.index('"/messages"') < set_at
    assert segment.index("addBubble(m.speaker_name") < set_at
    assert set_at < segment.index("} catch (err)")


def test_03_loader_fence_restated_in_true_form():
    segment = loader_segment()
    assert "history.push" not in segment
    assert "sentHistory" not in segment
    assert "localStorage" not in segment
    assert "sessionStorage" not in segment


def test_04_submit_branches_before_stateless_state():
    segment = submit_segment()
    branch_at = segment.index("if (openGroupId)")
    assert branch_at < segment.index("const sentHistory")
    assert "await sendPersistent(text);" in segment
    assert segment.index("await sendPersistent(text);") \
        < segment.index("const sentHistory")


def test_05_persistent_branch_posts_the_banked_next_road():
    segment = persistent_segment()
    assert '"/api/v1/groups/" + openGroupId + "/next"' in segment
    assert 'method: "POST"' in segment
    assert "user_text: text" in segment
    assert "generate: true" in segment


def test_06_persistent_branch_touches_no_stateless_state():
    segment = persistent_segment()
    for fenced in ("history", "sentHistory", "rrCursor",
                   "selectedIds", "strategy", "localStorage",
                   "sessionStorage", "/api/v1/group/turn"):
        assert fenced not in segment, fenced


def test_07_reply_renders_via_the_p213_pair():
    segment = persistent_segment()
    assert "const m = result.message;" in segment
    assert 'addBubble(m.speaker_name || "user", m.content)' in segment
    assert "reasoningPanel(" in segment
    assert ("window.RunmalRenderer.reasoningView(m.reasoning)"
            in segment)


def test_08_null_message_renders_nothing():
    # P-217 heal (named in advance in the P-217 design,
    # section 5): the early-return form this pin asserted
    # is replaced BY DESIGN with the guarded render, so a
    # null message renders nothing AND reaches the P-217
    # picker-refresh tail - the same null-message truth,
    # restated at equal-or-greater strength in its true
    # P-217 form; the P-217 battery pin 7 asserts exactly
    # this form.
    segment = persistent_segment()
    assert "if (!m) return;" not in segment
    guard_at = segment.index("if (m) {")
    assert guard_at < segment.index("addBubble(m.speaker_name")
    assert segment.index("addBubble(m.speaker_name") \
        < segment.index("await loadSavedGroups();")


def test_09_stateless_body_intact():
    segment = submit_segment()
    assert 'api("/api/v1/group/turn"' in segment
    assert "participant_ids: selectedIds()" in segment
    assert "history: sentHistory" in segment
    assert "strategy:" in segment
    assert "rr_cursor: rrCursor" in segment


def test_10_textcontent_only_no_innerhtml():
    assert "innerHTML" not in GROUP_JS.read_text()


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
    assert len(paths) == 365
    assert operations == 455
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(client.db_path) == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)
    # P-215 heal (named in advance in the P-215 design,
    # section 5): group.html now carries exactly the
    # P-213/P-214 control set PLUS the two ids P-215 adds
    # by design (close-group, group-mode) and no others -
    # the same exact-census assertion, restated at equal
    # strength in its true P-215 form; the P-215 battery
    # pin 14 asserts this same census.
    # P-216 heal (named in advance in the P-216 design,
    # section 5): group.html now carries exactly that set
    # PLUS the two ids P-216 adds by design (new-group-name,
    # create-group) and no others - the same exact-census
    # assertion, restated at equal strength in its true
    # P-216 form; the P-216 battery pin 14 asserts this
    # same census.
    html = GROUP_HTML.read_text()
    assert '<select id="saved-group"' in html
    assert 'id="open-group" type="button">Open</button>' in html
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert ids == {
        "group-main", "error-banner", "error-text",
        "error-dismiss", "group-layout", "saved-group",
        "open-group", "close-group", "group-mode",
        "new-group-name", "create-group", "roster",
        "strategy", "group-thread",
        "group-form", "group-input", "palette",
        "palette-card", "palette-input", "palette-list",
    }
    assert (html.index('/static/renderer.js')
            < html.index('/static/group.js'))
