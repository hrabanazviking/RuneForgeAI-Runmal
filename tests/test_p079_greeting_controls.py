"""P-079 quiet/greeting controls battery.

Pins the greeting contract: the pure deck + choice module
(ordered deck with kinds/source indexes, blank filtering, strict
choice decode, strict index resolution, seeded-random honesty,
quiet mode), the chat service (greeting seeded as the first
message with the whole deck as swipes, per-alternate P-075
provenance, metadata-only events, owner scoping, seed-into-empty
for quiet/persona-late chats), the REST API (deck view, create
controls, seed endpoint, error mapping), and the neighbours
(no migration, export/fork inheritance, undo of a seed).
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import create_character
from runmal.chats import greetings as gm
from runmal.chats import service as svc
from runmal.chats.branches import fork_chat
from runmal.chats.greetings import GreetingChoice, choice_from_data, choice_to_data
from runmal.chats.provenance import active_view, parse_provenance
from runmal.chats.service import event_to_dict, message_to_dict
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, User
from runmal.groupchat.store import create_group

FIRST = "Hail, wanderer."
ALTS = ["The fire is lit; sit.", "You look half-frozen. Come in."]
DECK = [FIRST] + ALTS
SECRET = "ZqxGreetingSecret79"


def card_dict(name="Brynn", first=FIRST, alternates=ALTS, **over):
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A hall-keeper.",
        "personality": "Warm, blunt.",
        "scenario": "A hall at dusk.",
        "first_mes": first,
        "alternate_greetings": list(alternates),
    }
    card.update(over)
    return card


# ---------------- pure: deck ----------------

def test_deck_orders_first_then_alternates():
    assert gm.greeting_deck(FIRST, ALTS) == DECK
    entries = gm.greeting_entries(FIRST, ALTS)
    assert [(e["kind"], e["source_index"]) for e in entries] == [
        ("first", 0), ("alternate", 0), ("alternate", 1)]
    assert [e["text"] for e in entries] == DECK


def test_deck_filters_blank_and_nonstring_entries():
    entries = gm.greeting_entries("", ["", "  ", "Real.", None, 42, "Also real."])
    assert [(e["kind"], e["source_index"], e["text"]) for e in entries] == [
        ("alternate", 2, "Real."), ("alternate", 5, "Also real.")]
    assert gm.greeting_deck("   ", []) == []
    assert gm.greeting_deck(None, None) == []
    assert gm.greeting_deck(FIRST, "not-a-list") == [FIRST]


def test_deck_keeps_duplicates_and_text_verbatim():
    assert gm.greeting_deck("Same.", ["Same.", " padded "]) == ["Same.", "Same.", " padded "]


# ---------------- pure: choice ----------------

def test_choice_defaults_and_round_trip():
    assert GreetingChoice() == GreetingChoice(mode="first", index=None, seed=None)
    assert choice_from_data(None) == GreetingChoice()
    assert choice_from_data({}) == GreetingChoice()
    for data in ({"mode": "quiet"}, {"mode": "index", "index": 2},
                 {"mode": "random", "seed": 7}, {"mode": "random"}):
        choice = choice_from_data(data)
        assert choice_to_data(choice) == {
            "mode": choice.mode, "index": choice.index, "seed": choice.seed}
        assert choice_from_data(choice_to_data(choice)) == choice


@pytest.mark.parametrize("bad", [
    {"bogus": 1}, {"mode": "sideways"}, {"mode": 3}, {"mode": None},
    {"mode": "index"}, {"mode": "index", "index": -1},
    {"mode": "index", "index": True}, {"mode": "index", "index": "1"},
    {"mode": "first", "index": 0}, {"mode": "quiet", "seed": 3},
    {"mode": "random", "seed": True}, {"mode": "random", "seed": "7"},
    "first", ["first"], 42,
])
def test_choice_rejects_bad_documents(bad):
    with pytest.raises(ValueError):
        choice_from_data(bad)


def test_choice_resolve_modes():
    assert GreetingChoice().resolve(DECK) == 0
    assert GreetingChoice(mode="quiet").resolve(DECK) is None
    assert GreetingChoice(mode="index", index=2).resolve(DECK) == 2
    with pytest.raises(ValueError):
        GreetingChoice(mode="index", index=3).resolve(DECK)
    with pytest.raises(ValueError):
        GreetingChoice(mode="index", index=0).resolve([])
    assert GreetingChoice().resolve([]) is None
    assert GreetingChoice(mode="quiet").resolve([]) is None
    assert GreetingChoice(mode="random", seed=5).resolve([]) is None


def test_choice_random_is_seeded_and_honest():
    expected = random.Random(99).randrange(len(DECK))
    assert GreetingChoice(mode="random", seed=99).resolve(DECK) == expected
    assert GreetingChoice(mode="random", seed=99).resolve(DECK) == expected
    rolled = GreetingChoice(mode="random").resolve(DECK, rng=random.Random(3))
    assert rolled == random.Random(3).randrange(len(DECK))
    for seed in range(25):
        assert 0 <= GreetingChoice(mode="random", seed=seed).resolve(DECK) < len(DECK)


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


async def make_char(factory, user_id, **over):
    async with factory() as session:
        char = await create_character(session, user_id, card_dict(**over))
        return char.id


async def history(factory, user_id, chat_id):
    async with factory() as session:
        rows = await svc.get_history(session, user_id, chat_id)
        assert rows is not None
        return [message_to_dict(m) for m in rows]


async def events(factory, user_id, chat_id):
    async with factory() as session:
        rows = await svc.list_events(session, user_id, chat_id)
        assert rows is not None
        return [event_to_dict(e) for e in rows]


async def seeded_chat(factory, user_id, choice=None, **card_over):
    char_id = await make_char(factory, user_id, **card_over)
    async with factory() as session:
        chat = await svc.create_chat(
            session, user_id, "Hall", char_id, greeting=choice)
        return chat.id, char_id


# ---------------- service: seeding on create ----------------

async def test_create_seeds_first_greeting_with_full_deck(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, char_id = await seeded_chat(factory, user)
    rows = await history(factory, user, chat_id)
    assert len(rows) == 1
    msg = rows[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == FIRST
    assert msg["swipes"] == DECK
    assert msg["swipe_id"] == 0
    assert msg["swipe_count"] == 3
    assert msg["position"] == 0
    assert msg["speaker_id"] == char_id
    assert msg["speaker_name"] == "Brynn"
    assert msg["content"] == msg["swipes"][msg["swipe_id"]]


async def test_create_index_mode_opens_on_chosen_alternate(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, GreetingChoice(mode="index", index=2))
    rows = await history(factory, user, chat_id)
    assert rows[0]["swipe_id"] == 2
    assert rows[0]["content"] == ALTS[1]
    assert rows[0]["swipes"] == DECK


async def test_create_quiet_mode_seeds_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, GreetingChoice(mode="quiet"))
    assert await history(factory, user, chat_id) == []
    kinds = [e["kind"] for e in await events(factory, user, chat_id)]
    assert kinds == ["chat.created"]


async def test_create_random_mode_records_resolved_index(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    expected = random.Random(99).randrange(len(DECK))
    chat_id, _ = await seeded_chat(
        factory, user, GreetingChoice(mode="random", seed=99))
    rows = await history(factory, user, chat_id)
    assert rows[0]["swipe_id"] == expected
    assert rows[0]["content"] == DECK[expected]
    ev = [e for e in await events(factory, user, chat_id)
          if e["kind"] == "message.appended"]
    assert len(ev) == 1
    assert ev[0]["data"]["greeting_mode"] == "random"
    assert ev[0]["data"]["swipe_id"] == expected


async def test_create_greetingless_card_seeds_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, first="", alternates=["", "  "])
    assert await history(factory, user, chat_id) == []


async def test_create_without_character_unchanged(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Solo")
    assert await history(factory, user, chat.id) == []
    ev = await events(factory, user, chat.id)
    assert [e["kind"] for e in ev] == ["chat.created"]
    assert ev[0]["data"]["greeting_mode"] == "first"


async def test_create_foreign_character_raises_keyerror(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    char_id = await make_char(factory, other)
    async with factory() as session:
        with pytest.raises(KeyError):
            await svc.create_chat(session, user, "Hall", char_id)


async def test_create_index_out_of_range_raises_and_creates_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    char_id = await make_char(factory, user)
    async with factory() as session:
        with pytest.raises(ValueError):
            await svc.create_chat(session, user, "Hall", char_id,
                                  greeting=GreetingChoice(mode="index", index=9))
    async with factory() as session:
        assert await svc.list_chats(session, user) == []


# ---------------- service: provenance + events ----------------

async def test_greeting_provenance_per_alternate(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, char_id = await seeded_chat(
        factory, user, GreetingChoice(mode="index", index=1))
    async with factory() as session:
        rows = await svc.get_history(session, user, chat_id)
        doc = parse_provenance(rows[0])
    assert set(doc["swipes"].keys()) == {"0", "1", "2"}
    active = active_view(rows[0], 1)
    assert active["origin"]["kind"] == "manual"
    assert active["origin"]["source"] == "card_greeting"
    assert active["origin"]["greeting_kind"] == "alternate"
    assert active["origin"]["greeting_index"] == 0
    assert active["model"]["status"] == "not_applicable"
    assert active["speaker"]["speaker_id"] == char_id
    first = doc["swipes"]["0"]
    assert first["origin"]["greeting_kind"] == "first"
    assert first["origin"]["greeting_index"] == 0


async def test_greeting_events_carry_metadata_only(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user)
    ev = await events(factory, user, chat_id)
    assert [e["kind"] for e in ev] == ["chat.created", "message.appended"]
    assert ev[0]["data"]["greeting_mode"] == "first"
    data = ev[1]["data"]
    assert data["greeting"] is True
    assert data["greeting_kind"] == "first"
    assert data["swipe_count"] == 3
    for event in ev:
        blob = str(event["data"])
        assert FIRST not in blob and ALTS[0] not in blob and SECRET not in blob


# ---------------- service: the seeded deck is a real swipe deck ----------------

async def test_seeded_greeting_swipes_like_any_message(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user)
    async with factory() as session:
        rows = await svc.get_history(session, user, chat_id)
        msg_id = rows[0].id
    async with factory() as session:
        moved = await svc.select_swipe(session, user, chat_id, msg_id, action="next")
        assert moved.content == ALTS[0]
    async with factory() as session:
        grown = await svc.add_swipe(session, user, chat_id, msg_id, "A fourth opening.")
        assert grown.swipe_id == 3
    state = (await history(factory, user, chat_id))[0]
    assert state["swipes"] == DECK + ["A fourth opening."]
    assert state["content"] == state["swipes"][state["swipe_id"]]


async def test_append_after_greeting_takes_next_position(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user)
    async with factory() as session:
        await svc.append_message(session, user, chat_id, "user", "Hail and well met.")
    rows = await history(factory, user, chat_id)
    assert [r["position"] for r in rows] == [0, 1]
    assert rows[1]["role"] == "user"


# ---------------- service: seed into an existing empty chat ----------------

async def test_seed_greeting_after_quiet_create(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, GreetingChoice(mode="quiet"))
    async with factory() as session:
        msg = await svc.seed_greeting(
            session, user, chat_id, GreetingChoice(mode="index", index=1))
        assert msg is not None
        assert msg.content == ALTS[0]
    rows = await history(factory, user, chat_id)
    assert rows[0]["swipes"] == DECK and rows[0]["swipe_id"] == 1


async def test_seed_greeting_after_persona_bound_late(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    char_id = await make_char(factory, user)
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Late")
        chat_id = chat.id
    async with factory() as session:
        await svc.set_chat_persona(session, user, chat_id, char_id)
    async with factory() as session:
        msg = await svc.seed_greeting(session, user, chat_id)
        assert msg is not None and msg.content == FIRST


async def test_seed_greeting_refusals(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    chat_id, _ = await seeded_chat(factory, user)
    async with factory() as session:
        with pytest.raises(ValueError):  # already has the greeting
            await svc.seed_greeting(session, user, chat_id)
        with pytest.raises(KeyError):  # missing chat
            await svc.seed_greeting(session, user, "missing")
        with pytest.raises(KeyError):  # foreign chat
            await svc.seed_greeting(session, other, chat_id)
    async with factory() as session:
        bare = await svc.create_chat(session, user, "Bare")
        bare_id = bare.id
    async with factory() as session:
        with pytest.raises(ValueError):  # no character bound
            await svc.seed_greeting(session, user, bare_id)


async def test_seed_greeting_quiet_and_bad_index(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, GreetingChoice(mode="quiet"))
    async with factory() as session:
        assert await svc.seed_greeting(
            session, user, chat_id, GreetingChoice(mode="quiet")) is None
        with pytest.raises(ValueError):
            await svc.seed_greeting(
                session, user, chat_id, GreetingChoice(mode="index", index=9))
    assert await history(factory, user, chat_id) == []
    kinds = [e["kind"] for e in await events(factory, user, chat_id)]
    assert kinds == ["chat.created"]


# ---------------- service: deck view ----------------

async def test_get_character_greetings_view(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    char_id = await make_char(factory, user, first="", alternates=["", "Only this."])
    async with factory() as session:
        view = await svc.get_character_greetings(session, user, char_id)
        assert view["count"] == 1
        assert view["greetings"] == [{
            "index": 0, "kind": "alternate", "source_index": 1, "text": "Only this."}]
        assert view["character_name"] == "Brynn"
        assert await svc.get_character_greetings(session, other, char_id) is None
        assert await svc.get_character_greetings(session, user, "missing") is None


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


def _api_char(client, **over):
    resp = client.post("/api/v1/characters", json={"card": card_dict(**over)})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _api_chat(client, char_id=None, **kw):
    body = {"title": "Hall"}
    if char_id is not None:
        body["character_id"] = char_id
    body.update(kw)
    resp = client.post("/api/v1/chats", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _api_messages(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------- API: deck view + create controls ----------------

def test_api_greeting_deck_view(app_client):
    char_id = _api_char(app_client)
    resp = app_client.get(f"/api/v1/characters/{char_id}/greetings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert [g["text"] for g in body["greetings"]] == DECK
    assert [g["kind"] for g in body["greetings"]] == ["first", "alternate", "alternate"]
    assert app_client.get("/api/v1/characters/missing/greetings").status_code == 404


def test_api_create_seeds_and_quiet(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id)
    rows = _api_messages(app_client, chat["id"])
    assert len(rows) == 1 and rows[0]["swipes"] == DECK and rows[0]["swipe_id"] == 0
    quiet = _api_chat(app_client, char_id, greeting_mode="quiet")
    assert _api_messages(app_client, quiet["id"]) == []


def test_api_create_index_and_random_seed(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id, greeting_mode="index", greeting_index=2)
    rows = _api_messages(app_client, chat["id"])
    assert rows[0]["swipe_id"] == 2 and rows[0]["content"] == ALTS[1]
    expected = random.Random(99).randrange(len(DECK))
    rolled = _api_chat(app_client, char_id, greeting_mode="random", greeting_seed=99)
    rows = _api_messages(app_client, rolled["id"])
    assert rows[0]["swipe_id"] == expected


def test_api_create_bad_controls_422(app_client):
    char_id = _api_char(app_client)
    for body in (
        {"character_id": char_id, "greeting_mode": "sideways"},
        {"character_id": char_id, "greeting_mode": "index"},
        {"character_id": char_id, "greeting_mode": "index", "greeting_index": 9},
        {"character_id": char_id, "greeting_mode": "index", "greeting_index": True},
        {"character_id": char_id, "greeting_mode": "first", "greeting_seed": 3},
        {"character_id": "missing"},
    ):
        resp = app_client.post("/api/v1/chats", json=body)
        assert resp.status_code in (404, 422), (body, resp.status_code)
        if body.get("character_id") == "missing":
            assert resp.status_code == 404
        else:
            assert resp.status_code == 422


def test_api_seed_endpoint_flow(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id, greeting_mode="quiet")
    resp = app_client.post(f"/api/v1/chats/{chat['id']}/greeting", json={"mode": "index", "index": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seeded"] is True
    assert body["message"]["content"] == ALTS[0]
    assert body["message"]["swipes"] == DECK
    again = app_client.post(f"/api/v1/chats/{chat['id']}/greeting", json={})
    assert again.status_code == 422  # no longer empty
    assert app_client.post("/api/v1/chats/missing/greeting", json={}).status_code == 404
    bare = _api_chat(app_client)
    resp = app_client.post(f"/api/v1/chats/{bare['id']}/greeting", json={})
    assert resp.status_code == 422  # no character bound


def test_api_seed_quiet_reports_not_seeded(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id, greeting_mode="quiet")
    resp = app_client.post(f"/api/v1/chats/{chat['id']}/greeting", json={"mode": "quiet"})
    assert resp.status_code == 200
    assert resp.json() == {"seeded": False, "message": None}
    assert _api_messages(app_client, chat["id"]) == []


def test_api_greeting_swipe_via_existing_routes(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id)
    msg = _api_messages(app_client, chat["id"])[0]
    resp = app_client.post(
        f"/api/v1/chats/{chat['id']}/messages/{msg['id']}/swipes/select",
        json={"action": "next"})
    assert resp.status_code == 200
    assert resp.json()["content"] == ALTS[0]


def test_api_editor_update_changes_deck_view(app_client):
    char_id = _api_char(app_client)
    resp = app_client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={"first_mes": "A new opening.", "alternate_greetings": ["Second."]})
    assert resp.status_code == 200, resp.text
    body = app_client.get(f"/api/v1/characters/{char_id}/greetings").json()
    assert [g["text"] for g in body["greetings"]] == ["A new opening.", "Second."]
    chat = _api_chat(app_client, char_id)
    rows = _api_messages(app_client, chat["id"])
    assert rows[0]["swipes"] == ["A new opening.", "Second."]


def test_api_requires_auth(app_client):
    app_client.headers.pop("Authorization")
    assert app_client.get("/api/v1/characters/x/greetings").status_code in (401, 403)
    assert app_client.post("/api/v1/chats/x/greeting", json={}).status_code in (401, 403)


# ---------------- neighbours ----------------

def test_no_new_migration(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert "0042" not in MIGRATIONS


async def test_export_full_deck_and_fork_active_line(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await seeded_chat(factory, user, GreetingChoice(mode="index", index=1))
    async with factory() as session:
        document = await svc.export_chat(session, user, chat_id)
    exported = document["messages"][0]
    assert exported["swipes"] == DECK and exported["swipe_id"] == 1
    async with factory() as session:
        fork = await fork_chat(session, user, chat_id)
        assert fork is not None
        rows = await svc.get_history(session, user, fork.id)
        state = message_to_dict(rows[0])
    # P-078 fixed branches._copy_message to carry the whole deck
    # (the old active-only copy silently destroyed swipe decks on
    # fork): the greeting's full deck and active index ride along.
    assert state["content"] == ALTS[0]
    assert state["swipes"] == DECK and state["swipe_id"] == 1


def test_api_undo_removes_seeded_greeting(app_client):
    char_id = _api_char(app_client)
    chat = _api_chat(app_client, char_id, greeting_mode="quiet")
    resp = app_client.post(f"/api/v1/chats/{chat['id']}/greeting", json={})
    assert resp.json()["seeded"] is True
    assert len(_api_messages(app_client, chat["id"])) == 1
    undone = app_client.post(f"/api/v1/chats/{chat['id']}/undo", json={})
    assert undone.status_code == 200, undone.text
    assert _api_messages(app_client, chat["id"]) == []


# ---------------- banking heal: group rooms refuse explicitly ----------------

async def test_seed_greeting_refuses_group_room_with_bound_character(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    char_id = await make_char(factory, user)
    async with factory() as session:
        group = await create_group(session, user, "Mead Hall", [char_id])
        group_id = group.id
    async with factory() as session:
        room = (await session.execute(
            select(Chat).where(Chat.group_id == group_id))).scalar_one()
        room_id = room.id
        assert room.character_id is None  # rooms bind no greeter at birth
    async with factory() as session:
        await svc.set_chat_persona(session, user, room_id, char_id)
    async with factory() as session:
        # Even with a character bound, a room has no single greeter:
        # the refusal is the explicit group guard, not the incidental
        # no-character refusal a room used to fall through to.
        with pytest.raises(ValueError, match="group room"):
            await svc.seed_greeting(session, user, room_id)
    assert await history(factory, user, room_id) == []
