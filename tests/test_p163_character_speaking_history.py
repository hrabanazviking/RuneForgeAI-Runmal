"""P-163 - Character speaking history (Part X, DERIVED).

Pins: the per-character board of that character's kept
face history across all of its chats, paired with the
character's CURRENT voice resolution - P-160's / P-162's
chat enumeration (list_chats order, the chats service's
title and message count, other characters' and unbound
chats never appearing) composed with P-158's history
document verbatim per chat (events whole with
provenance, entry_state / problem_now / descriptor, the
counts, the kept window), events never merged across
chats, the board classified under the closed
SPEAKING_BOARD_STATES law (no_chats / no_history /
some_history / all_history), the totals summed from
P-158's own arithmetic, the S512 voice half composed
verbatim in substance exactly as P-157 / P-159 / P-161
compose it (the closed voice-state law: profile /
profile_fallback for a legacy removed backend /
default_voice; stored_backend visible; the P-109 affect
carried whole with consumed False), the voice stated
ONCE at board level (no row and no event carries a
voice field of any kind), the voice honesty law as data
(voice_scope is current_only on every document; S512
stores no voice history, so a voice set after the
selections is the voice the document names - today's,
never a claim about the past), ``paired`` true exactly
when a voice resolved and the board's kept history
holds at least one selection, owner scoping
(unknown/foreign/deleted character -> None / 404), the
pure-read law (the P-092 store byte-identical, the
voice row untouched, no history written), the HTTP
road, and the neighbours (migration head stays 0041,
no 0042). No network.
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
from runmal.faces import character_speaking_history as board
from runmal.faces import history as hist
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
        return await board.resolve_character_speaking_history(
            session, uid, cid)


# -- Existence / owner scoping ---------------------------------


async def test_missing_and_foreign_character_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await board.resolve_character_speaking_history(
            session, uid, str(uuid.uuid4())) is None
        assert await board.resolve_character_speaking_history(
            session, other, cid) is None


async def test_deleted_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await characters_svc.delete_character(
            session, uid, cid) is True
        assert await board.resolve_character_speaking_history(
            session, uid, cid) is None


# -- Empty boards: the voice is stated, never upgraded ---------


async def test_character_with_no_chats_is_an_empty_unpaired_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    doc = await speak_board(factory, uid, cid)
    assert doc["schema"] == board.CHARACTER_SPEAKING_HISTORY_SCHEMA
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["state"] == board.SPEAKING_BOARD_STATE_NO_CHATS
    assert doc["chats"] == []
    assert doc["chat_count"] == 0
    assert doc["chats_with_history_count"] == 0
    assert doc["event_count"] == 0
    assert doc["selection_count"] == 0
    assert doc["cleared_count"] == 0
    assert doc["still_ready_count"] == 0
    assert doc["chats_at_kept_limit"] == 0
    assert doc["kept_limit"] == ex.MAX_HISTORY_KEPT
    voice = doc["voice"]
    assert voice is not None
    assert voice["state"] == board.VOICE_DEFAULT
    assert voice["profile_exists"] is False
    assert voice["stored_backend"] is None
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert doc["voice_scope"] == "current_only"
    # A voice beside an empty history is stated, never upgraded.
    assert doc["paired"] is False


async def test_chats_without_events_are_a_no_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid, title="First")
    await seed_chat(factory, uid, cid, title="Second")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_BOARD_STATE_NO_HISTORY
    assert doc["chat_count"] == 2
    assert doc["chats_with_history_count"] == 0
    assert doc["event_count"] == 0
    for row in doc["chats"]:
        assert row["events"] == []
        assert row["event_count"] == 0
        assert row["at_kept_limit"] is False
        assert row["kept_limit"] == ex.MAX_HISTORY_KEPT
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
    assert doc["event_count"] == 1
    assert doc["paired"] is True


# -- The board half rides P-158 whole, per chat ------------------


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


async def test_row_composes_p158_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused",
                                 reason="a joke landed")
        await ex.select_for_chat(session, uid, second, "neutral",
                                 reason="the news turned grave")
        doc = await board.resolve_character_speaking_history(
            session, uid, cid)
        plains = {}
        for chat_id in (first, second):
            plains[chat_id] = await hist.resolve_face_history(
                session, uid, chat_id)
    for row in doc["chats"]:
        plain = plains[row["chat_id"]]
        for key in ("chat_id", "presentation_state", "current",
                    "events", "event_count", "selection_count",
                    "cleared_count", "still_ready_count",
                    "kept_limit", "at_kept_limit"):
            assert row[key] == plain[key], key
    assert doc["event_count"] == 2
    assert doc["selection_count"] == 2


async def test_still_ready_event_descriptor_rides_per_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, bound_id, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    doc = await speak_board(factory, uid, cid)
    (row,) = doc["chats"]
    (event,) = row["events"]
    assert event["expression"] == "amused"
    assert event["entry_state"] == "still_ready"
    assert event["descriptor"]["name"] == "amused"
    assert event["descriptor"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{bound_id}/content")
    assert doc["still_ready_count"] == 1


async def test_events_are_never_merged_across_chats(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "neutral")
        await ex.select_for_chat(session, uid, first, "neutral")
    doc = await speak_board(factory, uid, cid)
    # No board-level event stream exists at all.
    assert "events" not in doc
    by_title = {row["title"]: row for row in doc["chats"]}
    assert [e["expression"] for e in by_title["First"]["events"]] == [
        "neutral", "amused"]
    assert [e["expression"] for e in by_title["Second"]["events"]] == [
        "neutral"]
    for row in doc["chats"]:
        for event in row["events"]:
            assert event["chat_id"] == row["chat_id"]


async def test_cleared_event_counts_as_history_not_selection(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.clear_selection(uid, chat_id, reason="scene over") is True
    doc = await speak_board(factory, uid, cid)
    assert doc["event_count"] == 2
    assert doc["selection_count"] == 1 and doc["cleared_count"] == 1
    assert doc["state"] == board.SPEAKING_BOARD_STATE_ALL_HISTORY
    cleared = doc["chats"][0]["events"][0]
    assert cleared["entry_state"] == "cleared"
    assert cleared["descriptor"] is None
    # The kept selection still stands, so the pairing stands.
    assert doc["paired"] is True


async def test_some_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    busy = await seed_chat(factory, uid, cid, title="Busy")
    await seed_chat(factory, uid, cid, title="Quiet")
    async with factory() as session:
        await ex.select_for_chat(session, uid, busy, "amused")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_BOARD_STATE_SOME_HISTORY
    assert doc["chats_with_history_count"] == 1
    assert doc["paired"] is True


async def test_all_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "amused")
    doc = await speak_board(factory, uid, cid)
    assert doc["state"] == board.SPEAKING_BOARD_STATE_ALL_HISTORY
    assert doc["chats_with_history_count"] == 2
    assert doc["paired"] is True


async def test_totals_sum_p158_arithmetic_on_a_mixed_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    await seed_chat(factory, uid, cid, title="Quiet")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, first, "wrong")
        await ex.select_for_chat(session, uid, second, "neutral")
    doc = await speak_board(factory, uid, cid)
    assert doc["chat_count"] == 3
    assert doc["chats_with_history_count"] == 2
    assert doc["event_count"] == 3
    assert doc["selection_count"] == 3
    assert doc["cleared_count"] == 0
    assert doc["still_ready_count"] == 1
    assert doc["chats_at_kept_limit"] == 0
    assert doc["state"] == board.SPEAKING_BOARD_STATE_SOME_HISTORY
    by_title = {row["title"]: row for row in doc["chats"]}
    wrong_event = by_title["First"]["events"][0]
    assert wrong_event["expression"] == "wrong"
    assert wrong_event["entry_state"] == "declared_unbound"
    assert wrong_event["problem_now"] == "wrong_kind"
    neutral_event = by_title["Second"]["events"][0]
    assert neutral_event["entry_state"] == "declared_unbound"
    assert neutral_event["problem_now"] == "no_asset"
    assert by_title["Quiet"]["events"] == []


async def test_no_set_character_rows_are_empty_and_honest(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    await seed_chat(factory, uid, cid)
    doc = await speak_board(factory, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "no_set"
    assert row["events"] == [] and row["current"] is None
    assert doc["state"] == board.SPEAKING_BOARD_STATE_NO_HISTORY
    assert doc["voice"]["state"] == board.VOICE_DEFAULT
    assert doc["paired"] is False


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


# -- Voice honesty: today's resolution only, stated once ---------


async def test_voice_is_todays_resolution_only_and_stated_once(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        # The selections happen while NO profile exists...
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "neutral")
        before = await board.resolve_character_speaking_history(
            session, uid, cid)
        assert before["voice"]["state"] == board.VOICE_DEFAULT
        # ...and the profile is set only afterwards.
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="late-voice")
    doc = await speak_board(factory, uid, cid)
    # The document names the voice as it resolves TODAY...
    assert doc["voice"]["state"] == board.VOICE_PROFILE
    assert doc["voice"]["voice_id"] == "late-voice"
    assert doc["voice_scope"] == board.VOICE_SCOPE == "current_only"
    # ...and no row or event is dressed in it: the voice
    # lives exactly once, at board level.
    assert doc["chats"] == before["chats"]
    for row in doc["chats"]:
        assert "voice" not in row
        assert "voice_scope" not in row
        assert "paired" not in row
        for event in row["events"]:
            assert "voice" not in event
            assert "tts_backend" not in event
            assert "voice_id" not in event


async def test_document_keys_are_exactly_the_contract(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid)
    doc = await speak_board(factory, uid, cid)
    assert set(doc) == {
        "schema", "character_id", "character", "state",
        "chats", "chat_count", "chats_with_history_count",
        "event_count", "selection_count", "cleared_count",
        "still_ready_count", "chats_at_kept_limit",
        "kept_limit", "voice", "voice_scope", "paired",
        "notes"}
    assert set(doc["voice"]) == {
        "state", "profile_exists", "stored_backend",
        "tts_backend", "voice_id", "language", "params",
        "affect"}
    assert set(doc["chats"][0]) == {
        "chat_id", "title", "message_count",
        "presentation_state", "current", "events",
        "event_count", "selection_count", "cleared_count",
        "still_ready_count", "kept_limit", "at_kept_limit"}


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
    assert "current_only" in doc["notes"][1]
    assert "no voice history" in doc["notes"][1]
    assert "never merged" in doc["notes"][2]
    assert "kept window" in doc["notes"][3]
    assert "consumed" in doc["notes"][4]
    assert set(board.SPEAKING_BOARD_STATES) == {
        "no_chats", "no_history", "some_history", "all_history"}
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


def test_http_character_speaking_history_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    empty = client.get("/api/v1/faces/character-speaking-history",
                       params={"character_id": cid})
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_chats"
    assert empty.json()["chats"] == []
    assert empty.json()["voice"]["state"] == "default_voice"
    assert empty.json()["voice_scope"] == "current_only"
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
    before = client.get("/api/v1/faces/character-speaking-history",
                        params={"character_id": cid})
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "no_history"
    assert before.json()["chats"][0]["events"] == []
    assert before.json()["paired"] is False
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/character-speaking-history",
                       params={"character_id": cid})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p163-character-speaking-history-v1"
    assert doc["state"] == "all_history"
    assert doc["event_count"] == 1
    assert doc["voice_scope"] == "current_only"
    assert doc["voice"]["state"] == "default_voice"
    assert doc["paired"] is True
    event = doc["chats"][0]["events"][0]
    assert event["expression"] == "amused"
    assert event["entry_state"] == "still_ready"
    assert "voice" not in doc["chats"][0]
    assert "voice" not in event
    missing = client.get("/api/v1/faces/character-speaking-history",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/character-speaking-history" in paths


# -- Neighbours ------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
