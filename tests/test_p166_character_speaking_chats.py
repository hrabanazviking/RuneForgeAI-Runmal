"""P-166 - Character speaking chats (Part X, DERIVED).

Pins: the per-character board of that character's CURRENT
faces across all of its chats, paired with the character's
CURRENT voice resolution - P-160's face-chats board
composed whole (list_chats order, the chats service's
title and message count, other characters' and unbound
chats never appearing; each row P-155's presentation truth
verbatim - presentation_state, current, current_problem,
face named only when ready), the board classified under
the closed SPEAKING_CHATS_STATES law (no_chats /
none_ready / some_ready / all_ready - P-160's own
judgement carried), the counts carried from P-160's own
arithmetic, the S512 voice half composed verbatim in
substance exactly as P-157 / P-159 / P-161 / P-163 compose
it (the closed voice-state law: profile /
profile_fallback for a legacy removed backend /
default_voice; stored_backend visible; the P-109 affect
carried whole with consumed False), the voice stated ONCE
at board level (no row carries a voice field of any
kind), both halves current (no voice_scope field - the
P-157 / P-159 precedent for current pairings; the board
reads no kept history, so a voice set after a selection
is simply the voice the document names), ``paired`` true
exactly when a voice resolved and at least one chat
shows a ready face, owner scoping (unknown/foreign/
deleted character -> None / 404), the pure-read law (the
P-092 store byte-identical, the voice row untouched, no
history written beyond the selections themselves), the
HTTP road, and the neighbours (migration head stays
0041, no 0042). No network.
"""

from __future__ import annotations

import struct
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets import service as assets_svc
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import CharacterVoiceProfile, User
from runmal.faces import chats as plain_board
from runmal.faces import speaking_chats as board
from runmal.plugins import expressions as ex
from runmal.plugins import service as plugin_service
from runmal.plugins.image_generation import render_deterministic_png
from runmal.voice import profiles as voice_profiles

PNG_BYTES = render_deterministic_png("sprite seed", "", 1, 32)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def card_dict(name="Asta"):
    return {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A keeper of the northern lighthouse.",
        "personality": "Steady.", "scenario": "A test hall.",
        "first_mes": "Hail!", "mes_example": "", "creator_notes": "",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "forge",
        "character_version": "1.0",
    }


async def seed_character(factory, uid, name="Asta"):
    async with factory() as session:
        character = await characters_svc.create_character(
            session, uid, card_dict(name))
        await session.commit()
        return character.id


async def seed_chat(factory, uid, character_id=None, title="The Lighthouse"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title,
            character_id=character_id,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def _add_asset(factory, uid, cid, *, kind, name):
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=f"{name.replace(' ', '_')}.png", data=PNG_BYTES)
        return asset.id


async def _world(factory, uid):
    """Character + set: neutral (no asset), amused (bound
    sprite), wrong (wrong-kind asset); default is amused.
    No chats yet - each test seeds the chats it judges."""
    cid = await seed_character(factory, uid)
    bound_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    bg_id = await _add_asset(factory, uid, cid, kind="background",
                             name="stairs")
    ex.create_set(uid, {
        "character_id": cid,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused", "asset_id": bound_id},
            {"name": "wrong", "label": "Wrong", "asset_id": bg_id},
        ],
        "default": "amused",
    })
    return cid, bound_id, bg_id


async def speak_board(factory, uid, cid):
    async with factory() as session:
        return await board.resolve_character_speaking_chats(
            session, uid, cid)


# -- Existence / owner scoping ---------------------------------


async def test_missing_and_foreign_character_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await board.resolve_character_speaking_chats(
            session, uid, str(uuid.uuid4())) is None
        assert await board.resolve_character_speaking_chats(
            session, other, cid) is None


async def test_deleted_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await characters_svc.delete_character(
            session, uid, cid) is True
        assert await board.resolve_character_speaking_chats(
            session, uid, cid) is None


# -- Empty boards: the voice is stated, never upgraded ---------


async def test_character_with_no_chats_is_an_empty_unpaired_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    doc = await speak_board(factory, uid, cid)
    assert doc["schema"] == board.SPEAKING_CHATS_SCHEMA
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["state"] == board.SPEAKING_CHATS_STATE_NO_CHATS
    assert doc["chats"] == []
    assert doc["chat_count"] == 0
    assert doc["ready_count"] == 0
    assert doc["selection_count"] == 0
    assert doc["unbound_count"] == 0
    voice = doc["voice"]
    assert voice is not None
    assert voice["state"] == board.VOICE_DEFAULT
    assert voice["profile_exists"] is False
    assert voice["stored_backend"] is None
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    # A voice beside an empty board is stated, never upgraded.
    assert doc["paired"] is False


async def test_chats_without_selections_are_a_none_ready_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid, title="First")
    await seed_chat(factory, uid, cid, title="Second")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_CHATS_STATE_NONE_READY
    assert doc["chat_count"] == 2
    assert doc["ready_count"] == 0
    for row in doc["chats"]:
        assert row["presentation_state"] == "no_selection"
        assert row["face"] is None
        assert row["current"] is None
    assert doc["voice"]["state"] == board.VOICE_DEFAULT
    assert doc["paired"] is False


async def test_unbound_and_other_character_chats_never_appear(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    other_cid = await seed_character(factory, uid, name="Bryn")
    mine = await seed_chat(factory, uid, cid, title="Mine")
    await seed_chat(factory, uid, other_cid, title="Theirs")
    await seed_chat(factory, uid, None, title="Unbound")
    async with factory() as session:
        await ex.select_for_chat(session, uid, mine, "amused")
    doc = await speak_board(factory, uid, cid)
    assert [row["chat_id"] for row in doc["chats"]] == [mine]
    assert doc["chat_count"] == 1
    assert doc["ready_count"] == 1
    assert doc["paired"] is True


# -- The board half rides P-160 whole ----------------------------


async def test_rows_ride_in_creation_order_with_chat_facts(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    doc = await speak_board(factory, uid, cid)
    assert [row["chat_id"] for row in doc["chats"]] == [first, second]
    assert [row["title"] for row in doc["chats"]] == ["First", "Second"]
    for row in doc["chats"]:
        assert row["message_count"] == 0


async def test_board_composes_p160_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused",
                                 reason="a joke landed")
        await ex.select_for_chat(session, uid, second, "neutral")
        doc = await board.resolve_character_speaking_chats(
            session, uid, cid)
        plain = await plain_board.resolve_character_face_chats(
            session, uid, cid)
    for key in ("character_id", "character", "state", "chats",
                "chat_count", "ready_count", "selection_count",
                "unbound_count"):
        assert doc[key] == plain[key], key
    assert doc["state"] in board.SPEAKING_CHATS_STATES
    assert doc["paired"] is True


async def test_ready_row_names_the_face_descriptor(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, bound_id, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
    doc = await speak_board(factory, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "ready"
    assert row["current"]["expression"] == "amused"
    assert row["current"]["provenance"]["reason"] == "a joke landed"
    assert row["current_problem"] is None
    face = row["face"]
    assert face["name"] == "amused"
    assert face["bound"] is True
    assert face["renderable"] is True
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert face["content_url"] == f"{base}/content"
    assert face["thumbnail_url"] == f"{base}/thumbnail"
    assert doc["state"] == board.SPEAKING_CHATS_STATE_ALL_READY
    assert doc["ready_count"] == 1 and doc["selection_count"] == 1
    assert doc["paired"] is True


async def test_unbound_current_row_states_its_problem_and_never_pairs(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "neutral")
    doc = await speak_board(factory, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "current_unbound"
    assert row["current"]["expression"] == "neutral"
    assert row["current_problem"] == "no_asset"
    assert row["face"] is None
    assert doc["unbound_count"] == 1
    assert doc["state"] == board.SPEAKING_CHATS_STATE_NONE_READY
    assert doc["selection_count"] == 1 and doc["ready_count"] == 0
    # A selection that is not ready never pairs, voice or not.
    assert doc["paired"] is False


async def test_no_set_character_board_is_none_ready(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    await seed_chat(factory, uid, cid)
    doc = await speak_board(factory, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "no_set"
    assert row["face"] is None and row["current"] is None
    assert doc["state"] == board.SPEAKING_CHATS_STATE_NONE_READY
    assert doc["chat_count"] == 1 and doc["ready_count"] == 0
    assert doc["voice"]["state"] == board.VOICE_DEFAULT
    assert doc["paired"] is False


async def test_some_ready_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    ready_chat = await seed_chat(factory, uid, cid, title="Ready")
    await seed_chat(factory, uid, cid, title="Waiting")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready_chat, "amused")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_CHATS_STATE_SOME_READY
    assert doc["ready_count"] == 1 and doc["chat_count"] == 2
    assert doc["paired"] is True


async def test_all_ready_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "amused")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_CHATS_STATE_ALL_READY
    assert doc["ready_count"] == 2 and doc["chat_count"] == 2
    assert doc["paired"] is True


async def test_counts_arithmetic_on_a_mixed_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    ready_chat = await seed_chat(factory, uid, cid, title="Ready")
    unbound_chat = await seed_chat(factory, uid, cid, title="Unbound")
    await seed_chat(factory, uid, cid, title="Waiting")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready_chat, "amused")
        await ex.select_for_chat(session, uid, unbound_chat, "wrong")
    doc = await speak_board(factory, uid, cid)
    assert doc["chat_count"] == 3
    assert doc["ready_count"] == 1
    assert doc["selection_count"] == 2
    assert doc["unbound_count"] == 1
    assert doc["state"] == board.SPEAKING_CHATS_STATE_SOME_READY
    by_title = {row["title"]: row for row in doc["chats"]}
    assert by_title["Unbound"]["current_problem"] == "wrong_kind"
    assert by_title["Waiting"]["presentation_state"] == "no_selection"
    assert doc["paired"] is True


# -- The voice half: S512 states --------------------------------


async def test_profile_voice_and_carried_affect(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1", language="en-gb",
            params={"affect": "whispering", "prompt_text": "Hush."})
    doc = await speak_board(factory, uid, cid)
    voice = doc["voice"]
    assert voice["state"] == board.VOICE_PROFILE
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "fake-tts"
    assert voice["tts_backend"] == "fake-tts"
    assert voice["voice_id"] == "narrator-1"
    assert voice["language"] == "en-gb"
    assert voice["params"]["prompt_text"] == "Hush."
    affect = voice["affect"]
    assert affect["affect"] == "whispering"
    assert affect["source"] == "profile"
    assert affect["consumed"] is False
    assert doc["paired"] is True


async def test_partial_profile_stays_profile_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, voice_id="only-voice")
    doc = await speak_board(factory, uid, cid)
    voice = doc["voice"]
    assert voice["state"] == board.VOICE_PROFILE
    assert voice["stored_backend"] == ""
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == "only-voice"
    assert doc["paired"] is True


async def test_legacy_backend_is_profile_fallback(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        session.add(CharacterVoiceProfile(
            character_id=cid, user_id=uid,
            tts_backend="kokoro-onnx", voice_id="af_heart",
            language="en-us", params_json="{}"))
        await session.commit()
    doc = await speak_board(factory, uid, cid)
    voice = doc["voice"]
    assert voice["state"] == board.VOICE_PROFILE_FALLBACK
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "kokoro-onnx"
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert set(board.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


async def test_default_voice_affect_is_neutral_unconsumed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    doc = await speak_board(factory, uid, cid)
    affect = doc["voice"]["affect"]
    assert affect["affect"] == "neutral"
    assert affect["source"] == "default"
    assert affect["consumed"] is False
    assert doc["paired"] is True


# -- Voice stated once, both halves current ----------------------


async def test_voice_is_current_and_stated_once(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "neutral")
        before = await board.resolve_character_speaking_chats(
            session, uid, cid)
        assert before["voice"]["state"] == board.VOICE_DEFAULT
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="late-voice")
    doc = await speak_board(factory, uid, cid)
    # The document names the voice as it resolves NOW...
    assert doc["voice"]["state"] == board.VOICE_PROFILE
    assert doc["voice"]["voice_id"] == "late-voice"
    # ...the rows are untouched by it, and no row is dressed
    # in it: the voice lives exactly once, at board level.
    assert doc["chats"] == before["chats"]
    assert "voice_scope" not in doc
    for row in doc["chats"]:
        assert "voice" not in row
        assert "voice_scope" not in row
        assert "paired" not in row


async def test_document_keys_are_exactly_the_contract(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid)
    doc = await speak_board(factory, uid, cid)
    assert set(doc) == {
        "schema", "character_id", "character", "state",
        "chats", "chat_count", "ready_count",
        "selection_count", "unbound_count", "voice",
        "paired", "notes"}
    assert set(doc["voice"]) == {
        "state", "profile_exists", "stored_backend",
        "tts_backend", "voice_id", "language", "params",
        "affect"}
    assert set(doc["chats"][0]) == {
        "chat_id", "title", "message_count",
        "presentation_state", "current", "current_problem",
        "face"}


# -- Pure read / notes -------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1")
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        stamp_before = (row.tts_backend, row.voice_id, row.updated_at)
    store = ex.store_path(uid)
    before = store.read_bytes()
    first = await speak_board(factory, uid, cid)
    second = await speak_board(factory, uid, cid)
    assert first == second
    assert store.read_bytes() == before
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        assert (row.tts_backend, row.voice_id, row.updated_at) == stamp_before


async def test_notes_and_closed_state_laws(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    doc = await speak_board(factory, uid, cid)
    assert doc["notes"] == list(board.NOTES)
    assert len(doc["notes"]) == 5
    assert "synthesizes no" in doc["notes"][0]
    assert "lip-sync" in doc["notes"][0]
    assert "CURRENT" in doc["notes"][1]
    assert "never per chat" in doc["notes"][1]
    assert "verbatim" in doc["notes"][2]
    assert "no single current face" in doc["notes"][3]
    assert "consumed" in doc["notes"][4]
    assert set(board.SPEAKING_CHATS_STATES) == {
        "no_chats", "none_ready", "some_ready", "all_ready"}
    assert board.SPEAKING_CHATS_STATES == plain_board.BOARD_STATES
    assert set(board.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


# -- HTTP surface --------------------------------------------------


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def make_png_bytes(width=16, height=16, color=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw))
            + _png_chunk(b"IEND", b""))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_character_speaking_chats_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    empty = client.get("/api/v1/faces/speaking-chats",
                       params={"character_id": cid})
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_chats"
    assert empty.json()["chats"] == []
    assert empty.json()["voice"]["state"] == "default_voice"
    assert empty.json()["paired"] is False
    up = client.post(
        f"/api/v1/characters/{cid}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", make_png_bytes(), "image/png")})
    assert up.status_code == 201, up.text
    asset_id = up.json()["id"]
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "neutral"},
                    {"name": "amused", "asset_id": asset_id}],
        "default": "neutral"})
    assert made.status_code == 201, made.text
    chat = client.post("/api/v1/chats",
                       json={"title": "T", "character_id": cid})
    assert chat.status_code in (200, 201), chat.text
    chat_id = chat.json()["id"]
    before = client.get("/api/v1/faces/speaking-chats",
                        params={"character_id": cid})
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "none_ready"
    assert before.json()["chats"][0]["presentation_state"] == "no_selection"
    assert before.json()["paired"] is False
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/speaking-chats",
                       params={"character_id": cid})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p166-character-speaking-chats-v1"
    assert doc["state"] == "all_ready"
    assert doc["ready_count"] == 1
    assert doc["voice"]["state"] == "default_voice"
    assert doc["paired"] is True
    row = doc["chats"][0]
    assert row["face"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    assert "voice" not in row
    missing = client.get("/api/v1/faces/speaking-chats",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/speaking-chats" in paths


# -- Neighbours ------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
