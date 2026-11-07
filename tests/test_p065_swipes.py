"""P-065 message swipes battery (TESTER).

Pins the swipe contract: the pure deck module (deck_for defensive
reads, clamped navigation, strict index selection, strict regen
settings, copy-merge param resolution, session adaptation), the
chat service (deck seeding on append, unlimited alternates, add /
select / delete semantics, edit-the-active-alternate, the
content == swipes[swipe_id] invariant after every mutation,
owner scoping, metadata-only events, per-chat swipe settings,
preset-aware param resolution, generation-session import), the
REST API, PROVISIONAL migration 0036, legacy-row reads, and the
chat export document.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.chats.service import chat_to_dict, event_to_dict, message_to_dict
from runmal.chats.swipes import (
    SwipeRegenSettings,
    deck_for,
    navigate,
    resolve_params,
    select_index,
    settings_from_data,
    settings_to_data,
    swipes_from_session,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.generation.modes import GenerationSession
from runmal.presets import service as presets_svc

DEFAULT_SETTINGS = {"enabled": True, "params": {}}
SECRET = "ZqxSwipeSecret65"
PROMPT = [{"role": "user", "content": "Tell me of the sea."}]

# ---------------- pure: settings defaults + round-trip ----------------

def test_settings_defaults():
    assert SwipeRegenSettings() == SwipeRegenSettings(enabled=True, params={})
    assert settings_from_data(None) == SwipeRegenSettings()
    assert settings_from_data({}) == SwipeRegenSettings()
    assert settings_to_data(SwipeRegenSettings()) == DEFAULT_SETTINGS
    assert settings_to_data(settings_from_data(None)) == DEFAULT_SETTINGS


def test_settings_round_trip_full_and_partial():
    data = {"enabled": False, "params": {"temperature": 0.5, "top_k": 10}}
    settings = settings_from_data(data)
    assert settings_to_data(settings) == data
    assert settings_from_data(settings_to_data(settings)) == settings
    assert settings_from_data(json.loads(json.dumps(data))) == settings
    partial = settings_from_data({"enabled": False})
    assert (partial.enabled, partial.params) == (False, {})
    partial = settings_from_data({"params": {"seed": 7}})
    assert (partial.enabled, partial.params) == (True, {"seed": 7})


@pytest.mark.parametrize("bad", [
    {"bogus": 1},
    {"enabled": True, "params": {}, "extra": None},
    {"enabled": 1},
    {"enabled": 0},
    {"enabled": "yes"},
    {"enabled": None},
    {"params": []},
    {"params": "x"},
    {"params": None},
    {"params": {"temperature": -1}},
    {"params": {"temperature": "hot"}},
    {"params": {"top_p": 2}},
    {"params": {"top_p": 0}},
])
def test_settings_from_data_rejects(bad):
    with pytest.raises(ValueError):
        settings_from_data(bad)


@pytest.mark.parametrize("bad", ["x", 42, 3.5, ["enabled"], True])
def test_settings_from_data_rejects_non_dict(bad):
    with pytest.raises(ValueError):
        settings_from_data(bad)


def test_settings_direct_construction_rejects():
    with pytest.raises(ValueError):
        SwipeRegenSettings(enabled=1)
    with pytest.raises(ValueError):
        SwipeRegenSettings(enabled="yes")
    with pytest.raises(ValueError):
        SwipeRegenSettings(params={"temperature": -1})
    with pytest.raises(ValueError):
        SwipeRegenSettings(params="nope")

# ---------------- pure: deck_for ----------------

def test_deck_for_consistent_row():
    raw = json.dumps(["a", "b", "c"])
    assert deck_for("b", raw, 1) == (["a", "b", "c"], 1)
    deck, idx = deck_for("a", raw, 0)
    deck.append("mutant")  # returned deck is a copy
    assert deck_for("a", raw, 0) == (["a", "b", "c"], 0)


@pytest.mark.parametrize("raw,swipe_id", [
    ("[]", 0),            # legacy default: never swiped
    (None, 0),
    ("", 0),
    ("{not json", 0),     # corrupt JSON
    ('"just a string"', 0),  # non-list JSON
    (json.dumps({"a": 1}), 0),  # non-list JSON object
    (json.dumps(["a", ""]), 0),   # empty-string entry
    (json.dumps(["a", 42]), 1),    # non-string entry
    (json.dumps([]), 0),
    (json.dumps(["a", "b"]), 2),   # swipe_id == len
    (json.dumps(["a", "b"]), 5),   # swipe_id out of range
    (json.dumps(["a", "b"]), -1),  # negative swipe_id
    (json.dumps(["a", "b"]), True),  # bool swipe_id
    (json.dumps(["a", "b"]), "1"),   # non-int swipe_id
])
def test_deck_for_defensive_fallback(raw, swipe_id):
    assert deck_for("content", raw, swipe_id) == (["content"], 0)


def test_deck_for_content_mismatch_falls_back():
    raw = json.dumps(["a", "b"])
    assert deck_for("other", raw, 0) == (["other"], 0)
    assert deck_for("other", raw, 1) == (["other"], 0)

# ---------------- pure: navigate / select_index ----------------

DECK = ["a", "b", "c"]

def test_navigate_next_prev_clamp_both_ends():
    assert navigate(DECK, 0, "next") == 1
    assert navigate(DECK, 1, "next") == 2
    assert navigate(DECK, 2, "next") == 2  # clamped at last
    assert navigate(DECK, 2, "prev") == 1
    assert navigate(DECK, 1, "prev") == 0
    assert navigate(DECK, 0, "prev") == 0  # clamped at first


def test_navigate_first_last():
    assert navigate(DECK, 2, "first") == 0
    assert navigate(DECK, 0, "last") == 2
    assert navigate(DECK, 1, "first") == 0
    assert navigate(DECK, 1, "last") == 2


def test_navigate_goto_clamps_both_ends():
    assert navigate(DECK, 0, "goto", target=1) == 1
    assert navigate(DECK, 0, "goto", target=99) == 2
    assert navigate(DECK, 2, "goto", target=-5) == 0


def test_navigate_rejects():
    with pytest.raises(ValueError):
        navigate(DECK, 0, "goto")  # no target
    with pytest.raises(ValueError):
        navigate(DECK, 0, "spin")  # unknown action
    with pytest.raises(ValueError):
        navigate([], 0, "next")  # empty deck


def test_select_index_strict():
    assert select_index(DECK, 0) == 0
    assert select_index(DECK, 2) == 2
    for bad in (-1, 3, 99, True, False, "1", 1.0, None):
        with pytest.raises(ValueError):
            select_index(DECK, bad)

# ---------------- pure: resolve_params ----------------

def test_resolve_params_disabled_returns_unmutated_copy():
    base = {"temperature": 0.7, "top_p": 0.9}
    settings = SwipeRegenSettings(enabled=False, params={"temperature": 0.1})
    resolved = resolve_params(base, settings)
    assert resolved == base
    assert resolved is not base
    resolved["temperature"] = 9.9
    assert base == {"temperature": 0.7, "top_p": 0.9}


def test_resolve_params_enabled_override_wins_untouched_survive():
    base = {"temperature": 0.7, "top_p": 0.9}
    settings = SwipeRegenSettings(enabled=True, params={"temperature": 0.2, "seed": 3})
    resolved = resolve_params(base, settings)
    assert resolved == {"temperature": 0.2, "top_p": 0.9, "seed": 3}
    assert base == {"temperature": 0.7, "top_p": 0.9}  # base not mutated
    assert settings.params == {"temperature": 0.2, "seed": 3}


def test_resolve_params_base_none():
    settings = SwipeRegenSettings(enabled=True, params={"seed": 3})
    assert resolve_params(None, settings) == {"seed": 3}
    disabled = SwipeRegenSettings(enabled=False, params={"seed": 3})
    assert resolve_params(None, disabled) == {}

# ---------------- pure: swipes_from_session ----------------

def _driven_session(contents):
    session = GenerationSession()
    session.compose(PROMPT)
    for i, text in enumerate(contents):
        session.begin()
        session.complete(text)
        if i < len(contents) - 1:
            session.regenerate(PROMPT)
    return session


def test_swipes_from_session_pure():
    session = _driven_session(["c1", "c2", "c3"])
    assert swipes_from_session(session) == (["c1", "c2", "c3"], 2)
    session.swipe(-1)
    assert swipes_from_session(session) == (["c1", "c2", "c3"], 1)
    assert swipes_from_session(GenerationSession()) == ([], 0)

# ---------------- service harness ----------------

def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def setup_chat_msg(factory, user_id, content="original"):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, "Hall")
        msg = await svc.append_message(session, user_id, chat.id, "assistant", content)
        return chat.id, msg.id


async def setup_deck(factory, user_id, contents):
    chat_id, msg_id = await setup_chat_msg(factory, user_id, contents[0])
    for extra in contents[1:]:
        async with factory() as session:
            await svc.add_swipe(session, user_id, chat_id, msg_id, extra)
    return chat_id, msg_id


async def deck_state(factory, user_id, chat_id, msg_id):
    """Fresh dict for a message; asserts the deck invariant."""
    async with factory() as session:
        history = await svc.get_history(session, user_id, chat_id)
        assert history is not None
        match = [m for m in history if m.id == msg_id]
        assert len(match) == 1
        state = message_to_dict(match[0])
    assert state["content"] == state["swipes"][state["swipe_id"]]
    assert state["swipe_count"] == len(state["swipes"])
    return state


async def event_dicts(factory, user_id, chat_id):
    async with factory() as session:
        events = await svc.list_events(session, user_id, chat_id)
        assert events is not None
        return [event_to_dict(e) for e in events]

# ---------------- service: append + add ----------------

async def test_append_seeds_deck(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "original")
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipes"] == ["original"]
    assert state["swipe_id"] == 0
    assert state["swipe_count"] == 1
    assert state["content"] == "original"


async def test_add_swipe_unlimited_alternates_ordered(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "alt-0")
    for i in range(1, 31):
        async with factory() as session:
            msg = await svc.add_swipe(session, user, chat_id, msg_id, f"alt-{i}")
            assert msg is not None
            state = message_to_dict(msg)
        assert state["swipe_id"] == i  # add activates the new alternate
        assert state["content"] == f"alt-{i}"
        assert state["content"] == state["swipes"][state["swipe_id"]]
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipe_count"] == 31
    assert state["swipes"] == [f"alt-{i}" for i in range(31)]


async def test_add_swipe_rejects_bad_content(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user)
    for bad in ("", None, 42):
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.add_swipe(session, user, chat_id, msg_id, bad)
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipe_count"] == 1

# ---------------- service: select ----------------

async def test_select_swipe_actions_and_index(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c", "d"])
    # deck active starts at last (3, "d")
    async def select(**kw):
        async with factory() as session:
            msg = await svc.select_swipe(session, user, chat_id, msg_id, **kw)
            assert msg is not None
            return message_to_dict(msg)
    state = await select(action="first")
    assert (state["swipe_id"], state["content"]) == (0, "a")
    state = await select(action="next")
    assert (state["swipe_id"], state["content"]) == (1, "b")
    state = await select(action="last")
    assert (state["swipe_id"], state["content"]) == (3, "d")
    state = await select(action="next")  # clamped at last
    assert (state["swipe_id"], state["content"]) == (3, "d")
    state = await select(action="prev")
    assert (state["swipe_id"], state["content"]) == (2, "c")
    state = await select(index=0)
    assert (state["swipe_id"], state["content"]) == (0, "a")
    state = await select(action="prev")  # clamped at first
    assert (state["swipe_id"], state["content"]) == (0, "a")
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipe_id"] == 0


async def test_select_swipe_no_change_records_no_event(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b"])  # active 1
    before = await event_dicts(factory, user, chat_id)
    async with factory() as session:
        msg = await svc.select_swipe(session, user, chat_id, msg_id, index=1)
        assert msg is not None
    async with factory() as session:
        msg = await svc.select_swipe(session, user, chat_id, msg_id, action="next")
        assert msg is not None  # already last: clamped no-change
    after = await event_dicts(factory, user, chat_id)
    assert len(after) == len(before)
    assert not [e for e in after if e["kind"] == "message.swipe_selected"]
    # A real change DOES record exactly one event.
    async with factory() as session:
        await svc.select_swipe(session, user, chat_id, msg_id, action="prev")
    after = await event_dicts(factory, user, chat_id)
    selected = [e for e in after if e["kind"] == "message.swipe_selected"]
    assert len(selected) == 1
    assert selected[0]["data"] == {"swipe_id": 0, "swipe_count": 2}


async def test_select_swipe_rejects(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c"])
    bad_calls = [
        dict(action="next", index=1),  # both
        dict(),                          # neither
        dict(index=3),                   # out of range
        dict(index=-1),                  # negative
        dict(index=True),                # bool
        dict(action="goto"),             # goto is not a service action
        dict(action="spin"),             # unknown action
    ]
    for kw in bad_calls:
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.select_swipe(session, user, chat_id, msg_id, **kw)
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipe_id"] == 2  # nothing moved

# ---------------- service: delete ----------------

async def _select(factory, user, chat_id, msg_id, index):
    async with factory() as session:
        await svc.select_swipe(session, user, chat_id, msg_id, index=index)


async def _delete(factory, user, chat_id, msg_id, index):
    async with factory() as session:
        msg = await svc.delete_swipe(session, user, chat_id, msg_id, index)
        assert msg is not None
        return message_to_dict(msg)


async def test_delete_active_middle_next_becomes_active(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c", "d"])
    await _select(factory, user, chat_id, msg_id, 1)
    state = await _delete(factory, user, chat_id, msg_id, 1)
    assert state["swipes"] == ["a", "c", "d"]
    assert (state["swipe_id"], state["content"]) == (1, "c")
    assert state["content"] == state["swipes"][state["swipe_id"]]
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipes"] == ["a", "c", "d"]


async def test_delete_active_last_prev_becomes_active(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c", "d"])
    state = await _delete(factory, user, chat_id, msg_id, 3)  # active is last
    assert state["swipes"] == ["a", "b", "c"]
    assert (state["swipe_id"], state["content"]) == (2, "c")
    await deck_state(factory, user, chat_id, msg_id)


async def test_delete_inactive_before_active_id_decrements(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c", "d"])
    state = await _delete(factory, user, chat_id, msg_id, 0)  # active was 3 ("d")
    assert state["swipes"] == ["b", "c", "d"]
    assert (state["swipe_id"], state["content"]) == (2, "d")
    await deck_state(factory, user, chat_id, msg_id)


async def test_delete_inactive_after_active_id_unchanged(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c", "d"])
    await _select(factory, user, chat_id, msg_id, 0)
    state = await _delete(factory, user, chat_id, msg_id, 2)
    assert state["swipes"] == ["a", "b", "d"]
    assert (state["swipe_id"], state["content"]) == (0, "a")
    await deck_state(factory, user, chat_id, msg_id)


async def test_delete_swipe_rejects(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "only")
    async with factory() as session:
        with pytest.raises(ValueError):
            await svc.delete_swipe(session, user, chat_id, msg_id, 0)  # the only one
    chat2, msg2 = await setup_deck(factory, user, ["a", "b", "c"])
    for bad in (3, 99, -1, True):
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.delete_swipe(session, user, chat2, msg2, bad)
    state = await deck_state(factory, user, chat2, msg2)
    assert state["swipes"] == ["a", "b", "c"]

# ---------------- service: edit edits the active alternate ----------------

async def test_edit_message_edits_active_alternate_only(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c"])
    await _select(factory, user, chat_id, msg_id, 1)
    async with factory() as session:
        msg = await svc.edit_message(session, user, chat_id, msg_id, "b-edited")
        assert msg is not None
        state = message_to_dict(msg)
    assert state["swipes"] == ["a", "b-edited", "c"]  # others untouched
    assert (state["swipe_id"], state["content"]) == (1, "b-edited")
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipes"] == ["a", "b-edited", "c"]
    await _select(factory, user, chat_id, msg_id, 0)
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["content"] == "a"

# ---------------- service: owner scoping ----------------

async def test_swipe_ops_owner_scoping_returns_none(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b"])
    chat2, _msg2 = await setup_chat_msg(factory, user, "elsewhere")
    gen = _driven_session(["x", "y"])
    async with factory() as session:
        # cross-chat message id
        assert await svc.add_swipe(session, user, chat2, msg_id, "z") is None
        assert await svc.select_swipe(session, user, chat2, msg_id, index=0) is None
        assert await svc.delete_swipe(session, user, chat2, msg_id, 0) is None
        assert await svc.edit_message(session, user, chat2, msg_id, "z") is None
        # foreign user
        assert await svc.add_swipe(session, other, chat_id, msg_id, "z") is None
        assert await svc.select_swipe(session, other, chat_id, msg_id, index=0) is None
        assert await svc.delete_swipe(session, other, chat_id, msg_id, 0) is None
        assert await svc.import_session_swipes(session, other, chat_id, msg_id, gen) is None
        # missing chat / message
        assert await svc.add_swipe(session, user, "missing", msg_id, "z") is None
        assert await svc.add_swipe(session, user, chat_id, "missing", "z") is None
        assert await svc.select_swipe(session, user, chat_id, "missing", index=0) is None
        assert await svc.delete_swipe(session, user, chat_id, "missing", 0) is None
        assert await svc.get_chat_swipe_settings(session, user, "missing") is None
        assert await svc.set_chat_swipe_settings(session, user, "missing", {}) is None
        assert await svc.resolve_swipe_params(session, user, "missing") is None
        assert await svc.import_session_swipes(session, user, chat_id, "missing", gen) is None
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipes"] == ["a", "b"]  # untouched by all of it

# ---------------- service: events carry no alternate text ----------------

async def test_events_contain_no_alternate_text(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "plain start")
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, msg_id, SECRET + " alternate")
        await svc.select_swipe(session, user, chat_id, msg_id, action="prev")
        await svc.select_swipe(session, user, chat_id, msg_id, action="next")
        await svc.delete_swipe(session, user, chat_id, msg_id, 0)
        await svc.set_chat_swipe_settings(
            session, user, chat_id,
            {"enabled": True, "params": {"my_knob": SECRET}},
        )
    events = await event_dicts(factory, user, chat_id)
    kinds = [e["kind"] for e in events]
    assert "message.swipe_added" in kinds
    assert "message.swipe_selected" in kinds
    assert "message.swipe_deleted" in kinds
    assert "swipe_settings.changed" in kinds
    assert SECRET not in json.dumps(events)

# ---------------- service: swipe settings ----------------

async def test_settings_service_default_and_round_trip(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _msg = await setup_chat_msg(factory, user)
    async with factory() as session:
        settings = await svc.get_chat_swipe_settings(session, user, chat_id)
        assert settings == SwipeRegenSettings()  # default on create
    payload = {"enabled": False, "params": {"temperature": 0.4, "seed": 11}}
    async with factory() as session:
        chat = await svc.set_chat_swipe_settings(session, user, chat_id, payload)
        assert chat is not None
        assert chat_to_dict(chat)["swipe_settings"] == payload
    async with factory() as session:
        settings = await svc.get_chat_swipe_settings(session, user, chat_id)
        assert settings is not None
        assert settings_to_data(settings) == payload


async def test_settings_invalid_set_stores_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _msg = await setup_chat_msg(factory, user)
    good = {"enabled": True, "params": {"temperature": 0.4}}
    async with factory() as session:
        await svc.set_chat_swipe_settings(session, user, chat_id, good)
    for bad in ({"enabled": "yes"}, {"params": {"top_p": 2}}, {"bogus": 1}):
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.set_chat_swipe_settings(session, user, chat_id, bad)
    async with factory() as session:
        settings = await svc.get_chat_swipe_settings(session, user, chat_id)
        assert settings is not None
        assert settings_to_data(settings) == good


async def test_settings_corrupt_stored_reads_as_default(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _msg = await setup_chat_msg(factory, user)
    for corrupt in ("{not json", json.dumps({"enabled": "yes"}), json.dumps([1])):
        async with factory() as session:
            chat = await svc.get_chat(session, user, chat_id)
            assert chat is not None
            chat.swipe_settings_json = corrupt
            await session.commit()
        async with factory() as session:
            settings = await svc.get_chat_swipe_settings(session, user, chat_id)
            assert settings == SwipeRegenSettings()
            chat = await svc.get_chat(session, user, chat_id)
            assert chat_to_dict(chat)["swipe_settings"] == DEFAULT_SETTINGS

# ---------------- service: resolve_swipe_params ----------------

async def test_resolve_params_service_no_preset(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _msg = await setup_chat_msg(factory, user)
    async with factory() as session:
        assert await svc.resolve_swipe_params(session, user, chat_id) == {}
        await svc.set_chat_swipe_settings(
            session, user, chat_id,
            {"enabled": True, "params": {"temperature": 0.5}},
        )
    async with factory() as session:
        resolved = await svc.resolve_swipe_params(session, user, chat_id)
        assert resolved == {"temperature": 0.5}  # settings only


async def test_resolve_params_service_with_preset(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _msg = await setup_chat_msg(factory, user)
    preset_params = {"temperature": 0.7, "top_p": 0.9}
    async with factory() as session:
        preset = await presets_svc.create_preset(
            session, user, "base-preset", params=preset_params
        )
        chat = await svc.set_chat_preset(session, user, chat_id, preset.id)
        assert chat is not None
    async with factory() as session:
        resolved = await svc.resolve_swipe_params(session, user, chat_id)
        assert resolved == preset_params  # no overrides yet
        await svc.set_chat_swipe_settings(
            session, user, chat_id,
            {"enabled": True, "params": {"temperature": 0.3}},
        )
    async with factory() as session:
        resolved = await svc.resolve_swipe_params(session, user, chat_id)
        assert resolved == {"temperature": 0.3, "top_p": 0.9}  # merged override
        await svc.set_chat_swipe_settings(
            session, user, chat_id,
            {"enabled": False, "params": {"temperature": 0.1}},
        )
    async with factory() as session:
        resolved = await svc.resolve_swipe_params(session, user, chat_id)
        assert resolved == preset_params  # disabled: preset unchanged

# ---------------- service: import_session_swipes ----------------

async def test_import_session_swipes_preserves_candidates_and_active(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "placeholder")
    session_obj = _driven_session(["c1", "c2", "c3"])
    session_obj.swipe(-1)  # active index 1
    async with factory() as session:
        msg = await svc.import_session_swipes(session, user, chat_id, msg_id, session_obj)
        assert msg is not None
        state = message_to_dict(msg)
    assert state["swipes"] == ["c1", "c2", "c3"]
    assert (state["swipe_id"], state["content"]) == (1, "c2")
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipes"] == ["c1", "c2", "c3"]
    assert state["swipe_id"] == 1


async def test_import_session_swipes_empty_raises(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user)
    async with factory() as session:
        with pytest.raises(ValueError):
            await svc.import_session_swipes(
                session, user, chat_id, msg_id, GenerationSession()
            )
    state = await deck_state(factory, user, chat_id, msg_id)
    assert state["swipe_count"] == 1  # untouched

# ---------------- service: legacy row + export ----------------

async def test_legacy_row_reads_as_one_card_deck(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_chat_msg(factory, user, "original")
    async with factory() as session:
        msg = (await session.execute(
            select(Message).where(Message.id == msg_id)
        )).scalar_one()
        msg.swipes_json = "[]"  # pre-0036 shape, set by hand
        msg.swipe_id = 0
        await session.commit()
        state = message_to_dict(msg)
    assert state["swipes"] == ["original"]
    assert state["swipe_id"] == 0
    assert state["swipe_count"] == 1


async def test_export_chat_carries_swipes(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, msg_id = await setup_deck(factory, user, ["a", "b", "c"])
    await _select(factory, user, chat_id, msg_id, 1)
    async with factory() as session:
        document = await svc.export_chat(session, user, chat_id)
    assert document is not None
    assert len(document["messages"]) == 1
    exported = document["messages"][0]
    assert exported["swipes"] == ["a", "b", "c"]
    assert exported["swipe_id"] == 1
    assert exported["content"] == "b"
    assert exported["swipes"][exported["swipe_id"]] == exported["content"]

# ---------------- API harness ----------------

@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _api_chat(client, title="Hall"):
    resp = client.post("/api/v1/chats", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _api_msg(client, chat_id, content="original"):
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": content},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _api_add_swipe(client, chat_id, msg_id, content):
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages/{msg_id}/swipes",
        json={"content": content},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()

# ---------------- API: swipe flow ----------------

def test_api_swipe_flow(app_client):
    chat = _api_chat(app_client)
    chat_id = chat["id"]
    assert chat["swipe_settings"] == DEFAULT_SETTINGS
    msg = _api_msg(app_client, chat_id, "original")
    assert msg["swipes"] == ["original"]
    assert msg["swipe_id"] == 0
    assert msg["swipe_count"] == 1
    added = _api_add_swipe(app_client, chat_id, msg["id"], "alternate")
    assert added["swipes"] == ["original", "alternate"]
    assert added["swipe_id"] == 1
    assert added["swipe_count"] == 2
    assert added["content"] == "alternate"
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/select",
        json={"action": "prev"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["swipe_id"] == 0
    assert resp.json()["content"] == "original"
    history = app_client.get(f"/api/v1/chats/{chat_id}/messages")
    assert history.status_code == 200, history.text
    shown = history.json()[0]
    assert shown["swipes"] == ["original", "alternate"]
    assert shown["swipe_id"] == 0
    assert shown["swipe_count"] == 2
    fetched = app_client.get(f"/api/v1/chats/{chat_id}")
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["swipe_settings"] == DEFAULT_SETTINGS
    assert body["messages"][0]["swipes"] == ["original", "alternate"]


def test_api_select_by_index_zero(app_client):
    chat_id = _api_chat(app_client)["id"]
    msg = _api_msg(app_client, chat_id, "original")
    _api_add_swipe(app_client, chat_id, msg["id"], "alternate")  # active 1
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/select",
        json={"index": 0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["swipe_id"] == 0
    assert resp.json()["content"] == "original"
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/select",
        json={"action": "last"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["swipe_id"] == 1


def test_api_select_both_or_neither_422(app_client):
    chat_id = _api_chat(app_client)["id"]
    msg = _api_msg(app_client, chat_id)
    _api_add_swipe(app_client, chat_id, msg["id"], "alternate")
    url = f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/select"
    resp = app_client.post(url, json={"action": "next", "index": 0})
    assert resp.status_code == 422, resp.text
    resp = app_client.post(url, json={})
    assert resp.status_code == 422, resp.text
    resp = app_client.post(url, json={"index": 5})
    assert resp.status_code == 422, resp.text
    resp = app_client.post(url, json={"action": "goto"})
    assert resp.status_code == 422, resp.text


def test_api_delete_swipe_and_delete_only_422(app_client):
    chat_id = _api_chat(app_client)["id"]
    msg = _api_msg(app_client, chat_id, "original")
    _api_add_swipe(app_client, chat_id, msg["id"], "alternate")
    resp = app_client.delete(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/1"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["swipes"] == ["original"]
    assert body["swipe_id"] == 0
    assert body["content"] == "original"
    resp = app_client.delete(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/0"
    )
    assert resp.status_code == 422, resp.text  # the only alternate
    resp = app_client.delete(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/swipes/9"
    )
    assert resp.status_code == 422, resp.text  # out of range


def test_api_swipe_missing_and_cross_chat_404(app_client):
    chat_id = _api_chat(app_client, "One")["id"]
    other_id = _api_chat(app_client, "Two")["id"]
    msg = _api_msg(app_client, chat_id)
    resp = app_client.post(
        f"/api/v1/chats/missing/messages/{msg['id']}/swipes",
        json={"content": "x"},
    )
    assert resp.status_code == 404, resp.text
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/messages/missing/swipes",
        json={"content": "x"},
    )
    assert resp.status_code == 404, resp.text
    resp = app_client.post(  # cross-chat message id
        f"/api/v1/chats/{other_id}/messages/{msg['id']}/swipes",
        json={"content": "x"},
    )
    assert resp.status_code == 404, resp.text
    resp = app_client.post(
        f"/api/v1/chats/{other_id}/messages/{msg['id']}/swipes/select",
        json={"index": 0},
    )
    assert resp.status_code == 404, resp.text
    resp = app_client.delete(
        f"/api/v1/chats/{other_id}/messages/{msg['id']}/swipes/0"
    )
    assert resp.status_code == 404, resp.text

# ---------------- API: swipe settings + regen params ----------------

def test_api_swipe_settings_round_trip(app_client):
    chat_id = _api_chat(app_client)["id"]
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-settings")
    assert resp.status_code == 200, resp.text
    assert resp.json() == DEFAULT_SETTINGS
    payload = {"enabled": False, "params": {"temperature": 0.4, "seed": 11}}
    resp = app_client.post(f"/api/v1/chats/{chat_id}/swipe-settings", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["swipe_settings"] == payload
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-settings")
    assert resp.json() == payload
    fetched = app_client.get(f"/api/v1/chats/{chat_id}")
    assert fetched.json()["swipe_settings"] == payload


def test_api_swipe_settings_invalid_422_stores_nothing(app_client):
    chat_id = _api_chat(app_client)["id"]
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/swipe-settings",
        json={"enabled": True, "params": {"temperature": -1}},
    )
    assert resp.status_code == 422, resp.text
    resp = app_client.post(
        f"/api/v1/chats/{chat_id}/swipe-settings",
        json={"enabled": True, "params": {"top_p": 2}},
    )
    assert resp.status_code == 422, resp.text
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-settings")
    assert resp.json() == DEFAULT_SETTINGS
    resp = app_client.get("/api/v1/chats/missing/swipe-settings")
    assert resp.status_code == 404, resp.text
    resp = app_client.post("/api/v1/chats/missing/swipe-settings", json={})
    assert resp.status_code == 404, resp.text


def test_api_swipe_regen_params_reflects_merge(app_client):
    chat_id = _api_chat(app_client)["id"]
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-regen-params")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"chat_id": chat_id, "params": {}}
    app_client.post(
        f"/api/v1/chats/{chat_id}/swipe-settings",
        json={"enabled": True, "params": {"temperature": 0.4}},
    )
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-regen-params")
    assert resp.json() == {"chat_id": chat_id, "params": {"temperature": 0.4}}
    app_client.post(
        f"/api/v1/chats/{chat_id}/swipe-settings",
        json={"enabled": False, "params": {"temperature": 0.4}},
    )
    resp = app_client.get(f"/api/v1/chats/{chat_id}/swipe-regen-params")
    assert resp.json() == {"chat_id": chat_id, "params": {}}
    resp = app_client.get("/api/v1/chats/missing/swipe-regen-params")
    assert resp.status_code == 404, resp.text

# ---------------- migration: PROVISIONAL 0036 ----------------

def _apply_up_to(db_path, revision):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for rev, _desc, module in MIGRATIONS:
            if rev > revision:
                break
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (rev, "test"),
            )
            conn.commit()
    finally:
        conn.close()


def test_migration_head_is_0036_provisional(tmp_path):
    assert MIGRATIONS[-1][0] == "0036"
    assert "PROVISIONAL" in MIGRATIONS[-1][1]
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0036"
    assert current_revision(db_path) == "0036"
    assert migrate_to_head(db_path) == []  # idempotent


def test_migration_0036_applies_exactly_and_adds_columns(tmp_path):
    db_path = tmp_path / "m.db"
    _apply_up_to(db_path, "0035")
    assert current_revision(db_path) == "0035"
    assert migrate_to_head(db_path) == ["0036"]
    assert current_revision(db_path) == "0036"
    conn = sqlite3.connect(db_path)
    try:
        message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    finally:
        conn.close()
    assert "swipes_json" in message_columns
    assert "swipe_id" in message_columns
    assert "swipe_settings_json" in chat_columns
