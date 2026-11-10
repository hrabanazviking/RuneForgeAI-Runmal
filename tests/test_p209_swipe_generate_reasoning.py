"""P-209 acceptance: reasoning wiring for swipes and the web
/generate road (Part XIII, DERIVED).

Contract under test (P209_DESIGN.md):
- Swipe half: chats/service.add_swipe gains a keyword-only
  reasoning= param. A caller landing a GENERATED alternate
  may attach that generation's strict P-205 record; it is
  stored as the new swipe's record. No param -> the standing
  byte-identical not_recorded stamp (P-205 d4/d5 and P-208
  test_16 exercise that path and run UNHEALED in the fence).
  A lying record raises ValueError BEFORE any store: deck
  and reasoning document byte-unchanged.
- REST half: MessageCreate / SwipeCreate gain an optional
  ReasoningIn body ({status, text}); the router strict-builds
  it with reasoning.build_record, so shape lies answer 422
  and are never stored. No new route: the census stays
  354 paths / 437 operations; migration head stays 0042.
- Web half: app.js streamGeneration collects the stream's
  {"type": "reasoning"} dicts in arrival order and attaches
  the built record (recorded with the verbatim joined text,
  else not_present) to the ONE append POST that persists the
  reply. KEEPER RULING (this tick): the P-206 stored-only
  ruling governs RENDERING -- transient collection for
  storage only, with nothing rendered live and the panel
  reading only the stored record, sits INSIDE the ruling.
  P-206 test_16 is the ONE named heal, restated to assert
  the collector's presence AND no live rendering in the
  stream path.
- D1 (stateless groupchat reasoning error-swallowing) is
  FENCED: no behaviour change, no pin here blesses it;
  src/runmal/groupchat/router.py is byte-untouched.
Fixtures mirror test_p205_reasoning_record.py.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User

REPO = Path(__file__).parent.parent
APP_JS = REPO / "src" / "runmal" / "web" / "static" / "app.js"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def seed_chat(factory, user, turns):
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Saga")
        chat_id = chat.id
        for role, content in turns:
            await svc.append_message(session, user, chat_id, role, content)
    return chat_id


async def _seed_message(factory, user, chat_id, reasoning=None):
    async with factory() as session:
        message = await svc.append_message(
            session, user, chat_id, "assistant", "Answer.",
            reasoning=reasoning)
        return message.id


# -- Service half: swipes -------------------------------------------------


async def test_01_add_swipe_with_recorded_record_stores_it(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    message_id = await _seed_message(factory, user, chat_id)
    record = rsn.build_record(status="recorded", text="second thought")
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.",
            reasoning=record)
        doc = rsn.parse_document(updated.reasoning_json)
        view = svc.message_to_dict(updated)["reasoning"]
        active = rsn.active_view(updated, 1)
    assert doc["swipes"] == {
        "0": {"status": "not_recorded"},
        "1": {"status": "recorded", "text": "second thought"}}
    assert active["status"] == "recorded"
    assert active["text"] == "second thought"
    assert view["status"] == "recorded"
    assert view["text"] == "second thought"


async def test_02_add_swipe_with_not_present_record(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    first = rsn.build_record(status="recorded", text="first thought")
    message_id = await _seed_message(factory, user, chat_id, reasoning=first)
    record = rsn.build_record(status="not_present")
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.",
            reasoning=record)
        doc = rsn.parse_document(updated.reasoning_json)
        view = rsn.active_view(updated, 1)
    assert doc["swipes"]["0"] == {
        "status": "recorded", "text": "first thought"}  # untouched
    assert doc["swipes"]["1"] == {"status": "not_present"}
    assert view["status"] == "not_present"
    assert "text" not in view


async def test_03_add_swipe_without_record_stays_not_recorded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    message_id = await _seed_message(factory, user, chat_id)
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.")
        doc = rsn.parse_document(updated.reasoning_json)
    assert doc["swipes"]["1"] == {"status": "not_recorded"}


async def test_04_add_swipe_with_lying_record_refused(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    message_id = await _seed_message(factory, user, chat_id)
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        stored = [m for m in history if m.id == message_id][0]
        before_reasoning = stored.reasoning_json
        before_swipes = stored.swipes_json
    lying_records = (
        {"status": "recorded"},                        # no text
        {"status": "not_present", "text": "smuggled"},  # text on non-recorded
        {"status": "recorded", "text": "ok", "bogus": 1},  # unknown keys
        {"status": "sideways"},                         # out of vocabulary
    )
    for lying in lying_records:
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.add_swipe(
                    session, user, chat_id, message_id, "Answer two.",
                    reasoning=lying)
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        stored = [m for m in history if m.id == message_id][0]
    assert stored.reasoning_json == before_reasoning  # byte-unchanged
    assert stored.swipes_json == before_swipes


async def test_05_wired_swipe_lifecycle_delete_and_branch_copy(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    first = rsn.build_record(status="recorded", text="original thought")
    second = rsn.build_record(status="recorded", text="second thought")
    message_id = await _seed_message(factory, user, chat_id, reasoning=first)
    async with factory() as session:
        await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.",
            reasoning=second)
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer three.")
        doc = rsn.parse_document(updated.reasoning_json)
        assert doc["swipes"] == {
            "0": {"status": "recorded", "text": "original thought"},
            "1": {"status": "recorded", "text": "second thought"},
            "2": {"status": "not_recorded"}}
        updated = await svc.delete_swipe(
            session, user, chat_id, message_id, 1)
        doc = rsn.parse_document(updated.reasoning_json)
        assert doc["swipes"] == {
            "0": {"status": "recorded", "text": "original thought"},
            "1": {"status": "not_recorded"}}  # renumbered down
        result = await svc.copy_message_to_branch(
            session, user, chat_id, message_id)
        copied_doc = rsn.parse_document(
            result["copied_message"].reasoning_json)
    assert copied_doc["swipes"] == doc["swipes"]


# -- REST half: both endpoints ---------------------------------------------


def _http_message(client):
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    posted = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "Answer."})
    assert posted.status_code == 201, posted.text
    return chat_id, posted.json()["id"]


def test_06_post_swipe_with_reasoning_stores_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, message_id = _http_message(client)
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes",
        json={"content": "Answer two.",
              "reasoning": {"status": "recorded", "text": "alt thinking"}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["reasoning"]["status"] == "recorded"
    assert resp.json()["reasoning"]["text"] == "alt thinking"
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.status_code == 200, road.text
    assert road.json()["swipes"] == {
        "0": {"status": "not_recorded"},
        "1": {"status": "recorded", "text": "alt thinking"}}


def test_07_post_swipe_with_lying_reasoning_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, message_id = _http_message(client)
    for lying in ({"status": "recorded"},               # no text
                  {"status": "not_present", "text": "lie"},
                  {"status": "sideways"}):               # out of vocabulary
        resp = client.post(
            f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes",
            json={"content": "Answer two.", "reasoning": lying})
        assert resp.status_code == 422, resp.text
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.json()["swipes"] == {"0": {"status": "not_recorded"}}
    history = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert history[0]["swipes"] == ["Answer."]  # deck unchanged
    assert history[0]["swipe_count"] == 1


def test_08_post_message_with_reasoning_stores_swipe0(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    chat_id = created.json()["id"]
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "Answer.",
              "reasoning": {"status": "recorded", "text": "web thinking"}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["reasoning"]["status"] == "recorded"
    assert resp.json()["reasoning"]["text"] == "web thinking"
    message_id = resp.json()["id"]
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.status_code == 200, road.text
    assert road.json()["swipes"] == {
        "0": {"status": "recorded", "text": "web thinking"}}


def test_09_post_message_with_not_present_reasoning(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    chat_id = created.json()["id"]
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "Answer.",
              "reasoning": {"status": "not_present"}})
    assert resp.status_code == 201, resp.text
    view = resp.json()["reasoning"]
    assert view["status"] == "not_present"
    assert "text" not in view  # distinct from test_10's not_recorded
    message_id = resp.json()["id"]
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.json()["swipes"] == {"0": {"status": "not_present"}}


def test_10_post_message_without_reasoning_stays_not_recorded(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, message_id = _http_message(client)
    history = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert history[0]["reasoning"]["status"] == "not_recorded"
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.json()["swipes"] == {"0": {"status": "not_recorded"}}


def test_11_post_message_text_on_not_present_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    chat_id = created.json()["id"]
    ok = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": "Hail."})
    assert ok.status_code == 201, ok.text
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "Answer.",
              "reasoning": {"status": "not_present", "text": "lie"}})
    assert resp.status_code == 422, resp.text
    history = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert len(history) == 1  # nothing stored
    assert history[0]["role"] == "user"


# -- Web half: app.js (the P-206 source-inspection method) ------------------


def _stream_source():
    source = APP_JS.read_text()
    return source.split("async function streamGeneration", 1)[1].split(
        "async function sendMessage", 1)[0]


def test_12_stream_generation_collects_reasoning_for_the_append():
    stream = _stream_source()
    assert 'event.type === "token"' in stream
    assert 'event.type === "done"' in stream
    assert 'event.type === "reasoning"' in stream  # handled, not discarded
    assert "reasoningParts.push(event.text)" in stream  # arrival order
    assert "reasoning: reasoningParts.length" in stream
    assert "reasoningParts.join(\"\")" in stream  # verbatim concatenation
    assert 'status: "recorded"' in stream
    assert 'status: "not_present"' in stream  # the seam ran, no thinking
    assert stream.count("state.allMessages.push") == 1  # one append only


def test_13_stream_generation_renders_nothing_live():
    stream = _stream_source()
    assert "reasoningView" not in stream  # P-206 stored-only rendering
    assert "reasoningPanel" not in stream
    assert "bubble.textContent = full" in stream
    assert stream.count("full +=") == 1  # only token text joins the answer


# -- Fences ------------------------------------------------------------------


def test_14_migration_head_stays_0042():
    assert MIGRATIONS[-1][0] == "0042"
    migrations_dir = REPO / "src" / "runmal" / "db" / "migrations"
    assert not [p.name for p in migrations_dir.glob("m0043*")]


def test_15_route_census_stays_354_437(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # P-210 heal: 355 / 438 - exactly one new road since
    # this pin was written (P-210's Inspector reasoning
    # road); P-209 itself added no road.
    assert len(paths) == 355
    assert operations == 438


async def test_16_content_law_on_both_new_seams(tmp_path, monkeypatch):
    marker = "THINKING-MARKER-P209"
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    message_id = await _seed_message(factory, user, chat_id)
    record = rsn.build_record(status="recorded", text=marker)
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.",
            reasoning=record)
        deck = json.loads(updated.swipes_json)
        doc = rsn.parse_document(updated.reasoning_json)
    assert marker not in updated.content
    assert all(marker not in alt for alt in deck)
    assert doc["swipes"]["1"]["text"] == marker
    assert "Answer two." not in doc["swipes"]["1"]["text"]
    client = make_client(tmp_path / "http", monkeypatch)
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    http_chat = created.json()["id"]
    resp = client.post(
        f"/api/v1/chats/{http_chat}/messages",
        json={"role": "assistant", "content": "Web answer.",
              "reasoning": {"status": "recorded", "text": marker}})
    assert resp.status_code == 201, resp.text
    assert marker not in resp.json()["content"]
    http_message = resp.json()["id"]
    road = client.get(
        f"/api/v1/chats/{http_chat}/messages/{http_message}/reasoning")
    assert road.json()["swipes"]["0"] == {
        "status": "recorded", "text": marker}
    assert "Web answer." not in road.json()["swipes"]["0"]["text"]
