"""P-208 acceptance: groupchat reasoning wiring (Part XIII, DERIVED).

Contract under test (P208_DESIGN.md):
- Persistent road: groupchat/deepening._generate collects the
  generation service's reasoning dicts in arrival order and
  returns a strict P-205 record beside the text (recorded with
  the verbatim joined thinking, else not_present); reasoning is
  never merged into the answer text. The collector adopts the
  P-207 failure contract whole (the D2 fix): an error dict, a
  finish of None / cancelled / error, or empty text raises
  GenerationFailedError, no record is built, nothing is stored.
- next_turn lands the record through the group store's new
  reasoning= param beside provenance; the transcript read and
  the chats full-document road carry it. Manual and user
  appends on the same store pass nothing and keep reading
  not_recorded (P-205 E3 / P-207 pin 16 group halves, no heal).
- Stateless road: POST /group/turn forwards reasoning live as
  per-speaker {"type": "reasoning", "author": ...} events in
  arrival order and stores NOTHING. Defect D1 (stateless
  error-swallowing) is FENCED: no pin here blesses it.
- Fences: migration head stays 0042 (no m0043), the route
  census stays the P-207 census (354 paths / 437 operations),
  chats add_swipe still reads not_recorded, the P-071 presence
  digest never sees reasoning text, and prompt text never
  enters a stored reasoning record.
Fixtures mirror test_p070_group_deepening.py (client helpers)
and test_p207 (factory helpers). Backend injection:
monkeypatch runmal.generation.service.default_backend -- both
groupchat seams call generate_events(backend=None), which
resolves default_backend in the service module at call time.
"""

import asyncio
import copy
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.errors import BackendUnavailable
from runmal.backends.events import Done, ReasoningDelta, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.characters.service import create_character
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.generation import service as gen_service
from runmal.groupchat import deepening, presence
from runmal.groupchat import store as group_store

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())

CARD = {
    "name": "Bridge Warden",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are the Bridge Warden of TESTHOLD.",
}

THINK = ("weigh ", "the toll")
THINK_TEXT = "weigh the toll"
ANSWER = ("The ", "answer.")
ANSWER_TEXT = "The answer."


def patch_backend(monkeypatch, factory):
    monkeypatch.setattr(gen_service, "default_backend", factory)


def reasoning_fake():
    return FakeChatBackend(chunks=ANSWER, reasoning_chunks=THINK)


def plain_fake():
    return FakeChatBackend(chunks=ANSWER)


class CancelledBackend(FakeChatBackend):
    """Stub backend: partial output, then Done('cancelled')."""

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        yield ReasoningDelta("partial thought")
        yield TextDelta("Partial answer")
        yield Done("cancelled")


# -- client fixtures (mirror test_p070) -----------------------------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_group(client, members, policy=None):
    resp = client.post(
        "/api/v1/groups", json={"name": "Mead Hall", "member_character_ids": list(members)}
    )
    assert resp.status_code == 201, resp.text
    group = resp.json()
    if policy:
        upd = client.patch(f"/api/v1/groups/{group['id']}", json={"speaker_policy": policy})
        assert upd.status_code == 200, upd.text
    return group


def next_turn(client, gid, **kw):
    resp = client.post(f"/api/v1/groups/{gid}/next", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def list_group(client, members):
    group = make_group(client, members, policy="list")
    gid = group["id"]
    upd = client.patch(
        f"/api/v1/groups/{gid}", json={"speaker_config": {"order": list(members)}})
    assert upd.status_code == 200, upd.text
    return group


# -- factory fixtures (mirror test_p207) -----------------------------------


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


async def make_factory_group(factory, user, names=("Asta",)):
    async with factory() as session:
        ids = []
        for name in names:
            character = await create_character(session, user, dict(CARD, name=name))
            ids.append(character.id)
        group = await group_store.create_group(session, user, "Mead Hall", ids)
        return group.id, ids


# -- A. Persistent seam (pins 1-4) ------------------------------------------


async def test_01_generate_collects_reasoning_in_order_never_merged(monkeypatch):
    patch_backend(monkeypatch, reasoning_fake)
    text, record = await deepening._generate([{"role": "user", "content": "hi"}])
    assert text == ANSWER_TEXT
    assert "weigh" not in text and "toll" not in text
    assert record == {"status": "recorded", "text": THINK_TEXT}


async def test_02_generate_without_reasoning_reads_not_present(monkeypatch):
    patch_backend(monkeypatch, plain_fake)
    text, record = await deepening._generate([{"role": "user", "content": "hi"}])
    assert text == ANSWER_TEXT
    assert record == {"status": "not_present"}
    assert "text" not in record


async def test_03_failing_backend_next_turn_stores_nothing(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, _ids = await make_factory_group(factory, user)
    async with factory() as session:
        await group_store.append_message(session, user, gid, "user", "Hail all.")
    async with factory() as session:
        before = await group_store.list_messages(session, user, gid)
    assert len(before) == 1
    patch_backend(monkeypatch, lambda: FakeChatBackend(fail_with=BackendUnavailable("down")))
    async with factory() as session:
        with pytest.raises(deepening.GenerationFailedError):
            await deepening.next_turn(session, user, gid, generate=True)
    async with factory() as session:
        after = await group_store.list_messages(session, user, gid)
    assert len(after) == 1
    assert after[-1].id == before[-1].id
    assert after[-1].content == "Hail all."


async def test_04_cancelled_finish_stores_nothing(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, _ids = await make_factory_group(factory, user)
    async with factory() as session:
        await group_store.append_message(session, user, gid, "user", "Hail all.")
    patch_backend(monkeypatch, lambda: CancelledBackend())
    async with factory() as session:
        with pytest.raises(deepening.GenerationFailedError):
            await deepening.next_turn(session, user, gid, generate=True)
    async with factory() as session:
        after = await group_store.list_messages(session, user, gid)
    # The D2 pin: partial text is never landed as a complete turn.
    assert len(after) == 1
    assert all(m.content != "Partial answer" for m in after)


# -- B. Persistent landing (pins 5-9) ----------------------------------------


def test_05_next_turn_lands_recorded_reasoning(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = list_group(client, [a, b])
    gid = group["id"]
    patch_backend(monkeypatch, reasoning_fake)
    result = next_turn(client, gid, user_text="Speak, friends.", generate=True)
    assert result["speaker_id"] == a
    message = result["message"]
    assert message["content"] == ANSWER_TEXT
    assert THINK_TEXT not in message["content"]
    view = message["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == THINK_TEXT
    prov = message["provenance"]
    assert prov["provenance_status"] == "recorded"
    assert "group_generated" in json.dumps(prov)
    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    stored = [m for m in transcript if m["id"] == message["id"]][0]
    assert stored["reasoning"]["status"] == "recorded"
    assert stored["reasoning"]["text"] == THINK_TEXT
    assert stored["content"] == ANSWER_TEXT


def test_06_next_turn_without_reasoning_reads_not_present(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = list_group(client, [a, b])
    gid = group["id"]
    patch_backend(monkeypatch, plain_fake)
    result = next_turn(client, gid, user_text="Speak, friends.", generate=True)
    view = result["message"]["reasoning"]
    assert view["status"] == "not_present"
    assert view["status"] != "not_recorded"
    assert "text" not in view
    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    stored = [m for m in transcript if m["id"] == result["message"]["id"]][0]
    assert stored["reasoning"]["status"] == "not_present"


async def test_07_run_turns_each_turn_own_record(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, ids = await make_factory_group(factory, user, ("Asta", "Bryn"))
    async with factory() as session:
        await group_store.update_group(
            session, user, gid, speaker_policy="list",
            speaker_config={"order": list(ids)})
    patch_backend(monkeypatch, reasoning_fake)
    async with factory() as session:
        result = await deepening.run_turns(session, user, gid, turns=2, generate=True)
    assert result["turns_run"] == 2
    assert [r["speaker_id"] for r in result["results"]] == list(ids)
    for turn in result["results"]:
        view = turn["message"]["reasoning"]
        assert view["status"] == "recorded"
        # Exactly ONE production's script: no cross-turn concatenation.
        assert view["text"] == THINK_TEXT
    async with factory() as session:
        messages = await group_store.list_messages(session, user, gid)
    generated = [m for m in messages if m.role == "assistant"]
    assert len(generated) == 2
    for message in generated:
        assert rsn.active_view(message)["text"] == THINK_TEXT


async def test_08_store_honesty_unwired_appends_stay_not_recorded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, ids = await make_factory_group(factory, user)
    record = rsn.build_record(status="recorded", text="stored thought")
    async with factory() as session:
        landed = await group_store.append_message(
            session, user, gid, ids[0], "A generated line.", reasoning=record)
        manual = await group_store.append_message(
            session, user, gid, ids[0], "A declared line.")
        usermsg = await group_store.append_message(
            session, user, gid, "user", "Hail all.")
    view = rsn.active_view(landed)
    assert view["status"] == "recorded" and view["text"] == "stored thought"
    for message in (manual, usermsg):
        assert rsn.active_view(message)["status"] == "not_recorded"
        # An EXPLICIT not_recorded document at swipe 0, never the
        # "{}" column default the store used to rely on.
        assert message.reasoning_json != "{}"
        doc = rsn.parse_document(message.reasoning_json)
        assert doc["swipes"] == {"0": {"status": "not_recorded"}}
        as_dict = group_store.message_to_dict(message)
        assert as_dict["reasoning"]["status"] == "not_recorded"
        assert as_dict["reasoning"]["reasoning_status"] == "not_recorded"
        assert "provenance" in as_dict
    # next_turn's user_text append passes nothing on the same store.
    async with factory() as session:
        result = await deepening.next_turn(
            session, user, gid, user_text="A fresh user line.", generate=False)
    assert result["message"] is None
    async with factory() as session:
        messages = await group_store.list_messages(session, user, gid)
    fresh = [m for m in messages if m.content == "A fresh user line."][0]
    assert rsn.active_view(fresh)["status"] == "not_recorded"
    assert group_store.message_to_dict(fresh)["reasoning"]["status"] == "not_recorded"


def test_09_full_document_road_resolves_group_message(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = list_group(client, [a, b])
    gid = group["id"]
    patch_backend(monkeypatch, reasoning_fake)
    result = next_turn(client, gid, user_text="Speak, friends.", generate=True)
    message_id = result["message"]["id"]
    resp = client.get(
        f"/api/v1/chats/{group['chat_id']}/messages/{message_id}/reasoning")
    assert resp.status_code == 200, resp.text
    assert resp.json()["swipes"]["0"] == {"status": "recorded", "text": THINK_TEXT}


# -- C. Stateless road (pins 10-13) -------------------------------------------


def run_stateless_turn(client, ids, user_text, strategy="mention"):
    with client.stream(
        "POST",
        "/api/v1/group/turn",
        json={
            "participant_ids": list(ids),
            "history": [],
            "user_text": user_text,
            "strategy": strategy,
            "rr_cursor": 0,
        },
    ) as resp:
        assert resp.status_code == 200, resp.status
        raw = "".join(resp.iter_text())
    events = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def make_stateless_characters(client):
    ids = {}
    for name in ("Bryn", "Una", "Kol"):
        ids[name] = make_character(client, name)
    return ids


def test_10_stateless_forwards_reasoning_per_speaker(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    patch_backend(monkeypatch, lambda: FakeChatBackend(
        chunks=("Hello ", "there."), reasoning_chunks=THINK))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert reasoning == [
        {"type": "reasoning", "author": "Una", "text": "weigh "},
        {"type": "reasoning", "author": "Una", "text": "the toll"},
    ]
    message_idx = next(i for i, e in enumerate(events) if e["type"] == "message")
    assert all(
        i < message_idx for i, e in enumerate(events) if e["type"] == "reasoning")


def test_11_stateless_sequence_otherwise_unchanged(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    patch_backend(monkeypatch, lambda: FakeChatBackend(
        chunks=("Hello ", "there."), reasoning_chunks=THINK))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    assert [e["type"] for e in events] == [
        "typing", "reasoning", "reasoning", "token", "token",
        "message", "turn_end"]
    message = next(e for e in events if e["type"] == "message")
    assert message["content"] == "Hello there."
    assert "weigh" not in message["content"] and "toll" not in message["content"]


def test_12_stateless_without_reasoning_is_banked_shape(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    patch_backend(monkeypatch, lambda: FakeChatBackend(chunks=("Hello ", "there.")))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    assert [e for e in events if e["type"] == "reasoning"] == []
    assert [e["type"] for e in events] == [
        "typing", "token", "token", "message", "turn_end"]


def _message_count(db_path):
    async def _count():
        engine = create_db_engine(db_path)
        factory = create_session_factory(engine)
        async with factory() as session:
            result = await session.execute(select(func.count(Message.id)))
            return int(result.scalar_one())
    return asyncio.run(_count())


def test_13_stateless_road_stores_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    db_path = tmp_path / "test.db"
    before = _message_count(db_path)
    patch_backend(monkeypatch, lambda: FakeChatBackend(
        chunks=("Hello ", "there."), reasoning_chunks=THINK))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    assert any(e["type"] == "reasoning" for e in events)  # it really streamed
    assert _message_count(db_path) == before


# -- D. Fences and honesty (pins 14-18) ----------------------------------------


def test_14_migration_head_stays_0042_no_m0043(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    applied = migrate_to_head(tmp_path / "m.db")
    assert applied[-1] == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)


def test_15_route_census_equals_p207_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    assert len(paths) == 354  # the P-207 census: no new road
    assert operations == 437


async def test_16_add_swipe_still_not_recorded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Saga")
        chat_id = chat.id
        await svc.append_message(session, user, chat_id, "user", "Hail.")
        message = await svc.append_message(
            session, user, chat_id, "assistant", "Well met")
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message.id, "An alternate telling.")
    view = rsn.active_view(updated, updated.swipe_id)
    assert view["status"] == "not_recorded"


async def test_17_presence_digest_never_sees_reasoning(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, ids = await make_factory_group(factory, user, ("Asta", "Bryn"))
    async with factory() as session:
        await group_store.update_group(
            session, user, gid, speaker_policy="list",
            speaker_config={"order": list(ids)})
        await presence.mark_absent(session, user, gid, ids[1])
    patch_backend(monkeypatch, reasoning_fake)
    async with factory() as session:
        result = await deepening.next_turn(session, user, gid, generate=True)
    assert result["speaker_id"] == ids[0]
    async with factory() as session:
        digest = await presence.missed_digest(session, user, gid, ids[1])
    blob = json.dumps(digest)
    assert ANSWER_TEXT in blob  # sanity: the content excerpt IS there
    assert THINK_TEXT not in blob and "weigh" not in blob and "toll" not in blob
    prompt_message = presence.digest_prompt_message(digest)
    assert ANSWER_TEXT in prompt_message["content"]
    assert THINK_TEXT not in prompt_message["content"]


async def test_18_prompt_marker_never_in_stored_reasoning(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, _ids = await make_factory_group(factory, user)
    patch_backend(monkeypatch, reasoning_fake)
    marker = "ZqxPromptMarker208"
    async with factory() as session:
        result = await deepening.next_turn(
            session, user, gid, user_text=f"{marker} speak now.", generate=True)
    assert result["message"]["reasoning"]["text"] == THINK_TEXT
    async with factory() as session:
        messages = await group_store.list_messages(session, user, gid)
    # Sanity: the marker really travelled the prompt path (user act).
    assert any(marker in m.content for m in messages)
    generated = [m for m in messages if m.role == "assistant"][0]
    assert marker not in (generated.reasoning_json or "")
    assert rsn.active_view(generated)["text"] == THINK_TEXT
