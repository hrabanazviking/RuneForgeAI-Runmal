"""P-207 acceptance: reasoning wiring for continue / impersonate
(Part XIII, DERIVED).

Contract under test (P207_DESIGN.md):
- The ONE shared generation seam of the P-069 pair,
  ``continue_impersonate._generate_text``, collects the
  generation service's reasoning dicts in arrival order and
  returns a strict P-205 record beside the text (recorded with
  the verbatim joined thinking, else not_present). Reasoning is
  never merged into the answer text. The failure contract is
  unchanged: a failed generation raises GenerationFailedError
  and continue_chat stores nothing.
- Continue NEXT lands the record via append_message's
  reasoning= param (the bridge producer's pattern).
- Continue EXTEND combines the new record with the active
  swipe's existing record ONLY when that record is seam-owned
  (recorded / not_present), per the design's combination
  table; a legacy not_recorded swipe's reasoning_json stays
  byte-untouched while its text and provenance amendment land.
- Impersonate carries the record TRANSIENTLY on the draft
  document only; accept never attaches it (the landed text is
  user-supplied, so its message reads not_recorded).
- Fences: migration head stays 0042 (no m0043), the app route
  census is the P-206 census, and the declined family
  (groupchat manual append, chats add_swipe) still reads
  not_recorded.
Fixtures mirror test_p205_reasoning_record.py / test_p069.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.errors import BackendUnavailable
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.characters.service import create_character
from runmal.chats import continue_impersonate as ci
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.groupchat import store as group_store

CARD = {
    "name": "Bridge Warden",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are the Bridge Warden of TESTHOLD.",
}

MSGS = [ChatMessage("user", "hi")]


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


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


async def seed_extend_chat(factory, user, record):
    """A chat whose last assistant message carries ``record``
    as its swipe-0 reasoning record (or the append default
    not_recorded when ``record`` is None)."""
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Saga")
        chat_id = chat.id
        await svc.append_message(session, user, chat_id, "user", "Hail.")
        if record is None:
            await svc.append_message(
                session, user, chat_id, "assistant", "Well met")
        else:
            await svc.append_message(
                session, user, chat_id, "assistant", "Well met",
                reasoning=record)
    return chat_id


async def last_message(factory, user, chat_id):
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        return history[-1]


# -- Seam (pins 1-3) ------------------------------------------------------


async def test_01_seam_collects_reasoning_in_order_never_merged():
    backend = FakeChatBackend(
        chunks=("The ", "answer."),
        reasoning_chunks=("weigh ", "the toll"))
    text, record = await ci._generate_text(backend, MSGS)
    assert text == "The answer."
    assert "weigh" not in text and "toll" not in text
    assert record == {"status": "recorded", "text": "weigh the toll"}


async def test_02_seam_without_reasoning_reads_not_present():
    backend = FakeChatBackend(chunks=("Plain answer.",))
    text, record = await ci._generate_text(backend, MSGS)
    assert text == "Plain answer."
    assert record == {"status": "not_present"}
    assert "text" not in record


async def test_03_failing_backend_raises_and_continue_stores_nothing(
        tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    before = await last_message(factory, user, chat_id)
    before_json = before.reasoning_json
    failing = FakeChatBackend(fail_with=BackendUnavailable("down"))
    async with factory() as session:
        with pytest.raises(ci.GenerationFailedError):
            await ci.continue_chat(session, user, chat_id, backend=failing)
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert len(history) == 1
    assert history[-1].reasoning_json == before_json


# -- Continue NEXT (pins 4-5) ----------------------------------------------


async def test_04_continue_next_lands_recorded_reasoning(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(
        chunks=("Well met, traveller.",),
        reasoning_chunks=("first thought", " second thought"))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    assert result["mode"] == "next"
    view = result["message"]["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == "first thought second thought"
    message = await last_message(factory, user, chat_id)
    assert svc.message_to_dict(message)["reasoning"]["status"] == "recorded"
    assert svc.message_to_dict(message)["reasoning"]["text"] == (
        "first thought second thought")
    async with factory() as session:
        document = await svc.get_message_reasoning(
            session, user, chat_id, message.id)
    assert document["swipes"]["0"] == {
        "status": "recorded", "text": "first thought second thought"}


async def test_05_continue_next_without_reasoning_reads_not_present(
        tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(chunks=("Well met, traveller.",))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    view = result["message"]["reasoning"]
    assert view["status"] == "not_present"
    assert view["status"] != "not_recorded"
    assert "text" not in view


# -- Continue EXTEND (pins 6-10) --------------------------------------------


async def test_06_extend_recorded_plus_recorded_concatenates(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    record = rsn.build_record(status="recorded", text="part one ")
    chat_id = await seed_extend_chat(factory, user, record)
    backend = FakeChatBackend(
        chunks=(" more.",), reasoning_chunks=("part two",))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    assert result["mode"] == "extend"
    message = await last_message(factory, user, chat_id)
    assert message.content == "Well met" + " more."
    view = svc.message_to_dict(message)["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == "part one part two"


async def test_07_extend_not_present_plus_recorded_becomes_recorded(
        tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    record = rsn.build_record(status="not_present")
    chat_id = await seed_extend_chat(factory, user, record)
    backend = FakeChatBackend(
        chunks=(" more.",), reasoning_chunks=("new thought",))
    async with factory() as session:
        await ci.continue_chat(session, user, chat_id, backend=backend)
    message = await last_message(factory, user, chat_id)
    assert message.content == "Well met more."
    view = svc.message_to_dict(message)["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == "new thought"


async def test_08_extend_recorded_plus_not_present_keeps_text(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    record = rsn.build_record(status="recorded", text="orig thought")
    chat_id = await seed_extend_chat(factory, user, record)
    backend = FakeChatBackend(chunks=(" more.",))
    async with factory() as session:
        await ci.continue_chat(session, user, chat_id, backend=backend)
    message = await last_message(factory, user, chat_id)
    assert message.content == "Well met more."
    view = svc.message_to_dict(message)["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == "orig thought"


async def test_09_extend_not_present_plus_not_present_stays(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    record = rsn.build_record(status="not_present")
    chat_id = await seed_extend_chat(factory, user, record)
    backend = FakeChatBackend(chunks=(" more.",))
    async with factory() as session:
        await ci.continue_chat(session, user, chat_id, backend=backend)
    message = await last_message(factory, user, chat_id)
    view = svc.message_to_dict(message)["reasoning"]
    assert view["status"] == "not_present"
    assert "text" not in view


async def test_10_extend_legacy_not_recorded_bytes_untouched(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_extend_chat(factory, user, None)
    before = await last_message(factory, user, chat_id)
    before_json = before.reasoning_json
    assert rsn.active_view(before)["status"] == "not_recorded"
    backend = FakeChatBackend(
        chunks=(" more.",), reasoning_chunks=("lost thought",))
    async with factory() as session:
        await ci.continue_chat(session, user, chat_id, backend=backend)
    message = await last_message(factory, user, chat_id)
    assert message.reasoning_json == before_json
    assert rsn.active_view(message)["status"] == "not_recorded"
    assert message.content == "Well met more."
    prov_doc = json.loads(message.provenance_json)
    amendments = prov_doc["swipes"]["0"]["amendments"]
    assert any(a.get("kind") == "continuation" for a in amendments)


# -- Impersonate (pins 11-13) ------------------------------------------------


async def test_11_impersonate_draft_carries_reasoning_transiently(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met")])
    before = await last_message(factory, user, chat_id)
    before_json = before.reasoning_json
    backend = FakeChatBackend(
        chunks=("I will go.",), reasoning_chunks=("draft thought",))
    async with factory() as session:
        draft = await ci.impersonate_draft(
            session, user, chat_id, backend=backend)
    assert draft["reasoning"] == {
        "status": "recorded", "text": "draft thought"}
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert len(history) == 2
    assert history[-1].reasoning_json == before_json


async def test_12_impersonate_draft_without_reasoning_not_present(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met")])
    backend = FakeChatBackend(chunks=("I will go.",))
    async with factory() as session:
        draft = await ci.impersonate_draft(
            session, user, chat_id, backend=backend)
    assert draft["reasoning"] == {"status": "not_present"}
    assert "text" not in draft["reasoning"]


async def test_13_accept_never_attaches_draft_reasoning(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met")])
    backend = FakeChatBackend(
        chunks=("I will go.",), reasoning_chunks=("draft thought",))
    async with factory() as session:
        draft = await ci.impersonate_draft(
            session, user, chat_id, backend=backend)
    async with factory() as session:
        discarded = await ci.discard_impersonate(
            session, user, chat_id, draft_id=draft["id"])
    assert discarded is True
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert len(history) == 2  # discard stored nothing
    async with factory() as session:
        message = await ci.accept_impersonate(
            session, user, chat_id, draft["content"],
            draft_id=draft["id"])
    assert message.role == "user"
    assert rsn.active_view(message)["status"] == "not_recorded"


# -- Fences (pins 14-16) ------------------------------------------------------


def test_14_migration_head_stays_0042_no_m0043(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    applied = migrate_to_head(tmp_path / "m.db")
    assert applied[-1] == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)


def test_15_route_census_equals_p206_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # R-03 heal: 365 / 455 — R-02's backend-profile roads
    # (+7 paths / +12 operations) landed without healing this
    # pin, and R-03 adds /chats/{id}/persona (GET+POST) and
    # /user-name (GET+PUT): +2 paths / +4 operations.
    # (P-211 heal: 356 / 439 since P-211's one new road;
    # P-210 heal: 355 / 438 since P-210's one new road;
    # the P-206 census this pin was written against was
    # 354 / 437; P-207 itself added no road.)
    assert len(paths) == 365
    assert operations == 455


async def test_16_declined_family_still_not_recorded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    # groupchat manual append: the declined family's store road.
    async with factory() as session:
        character = await create_character(session, user, CARD)
        group = await group_store.create_group(
            session, user, "Mead Hall", [character.id])
        gmessage = await group_store.append_message(
            session, user, group.id, "user", "Hail all.")
    assert rsn.active_view(gmessage)["status"] == "not_recorded"
    # chats add_swipe: a caller-supplied manual swipe.
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met")])
    message = await last_message(factory, user, chat_id)
    async with factory() as session:
        updated = await svc.add_swipe(
            session, user, chat_id, message.id, "An alternate telling.")
    view = rsn.active_view(updated, updated.swipe_id)
    assert view["status"] == "not_recorded"
