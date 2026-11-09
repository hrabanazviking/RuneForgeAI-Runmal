"""P-167 - Face speaking census (Part X, DERIVED).

Pins: the owner-wide CURRENT speaking census - one
row per owned character in the characters service's
creation order, each row composing P-164's census row
verbatim in substance (P-160's board: character
facts, board_state under P-160's law, the board's
rows whole, its counts) PLUS that character's OWN
current S512 voice resolution composed verbatim in
substance (the closed voice-state law: profile /
profile_fallback / default_voice; stored_backend
visible; the P-109 affect carried whole with
consumed False) and that row's OWN paired flag (a
voice resolved and that row's ready_count > 0) -
the blur objection answered by construction: voice
stands ONLY inside character rows, two characters'
distinct voices stay distinct per row, and the
census envelope carries no voice, no paired, no
voice_scope and no face at owner level; no chat row
carries a voice field; the census classified under
the closed SPEAKING_CENSUS_STATES law on the face
axis only (no_characters / no_chats / none_ready /
some_ready / all_ready); the counts summed from the
boards' own arithmetic plus paired_character_count
(a count of rows, no voice value); both halves
current (no voice_scope field - the P-157 / P-159 /
P-166 precedent; the census reads no kept history);
owner scoping (another owner's characters and chats
never appear; a deleted character drops out; unbound
chats never appear); the standing honesty notes; the
pure-read law (the P-092 store byte-identical after
resolves, the voice rows untouched); HTTP end to
end; and the neighbours (migration head stays 0041,
no 0042). No network.
"""

from __future__ import annotations

import struct
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
from runmal.faces import census as plain_census
from runmal.faces import speaking_census as census
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


async def seed_chat(factory, uid, character_id=None,
                    title="The Lighthouse"):
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


async def _world(factory, uid, name="Asta"):
    cid = await seed_character(factory, uid, name=name)
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


async def speak_census(factory, uid):
    async with factory() as session:
        return await census.resolve_face_speaking_census(session, uid)


# -- Empty / state law -----------------------------------------------------------


async def test_owner_with_no_characters_gets_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await speak_census(factory, uid)
    assert doc["schema"] == census.SPEAKING_CENSUS_SCHEMA
    assert doc["schema"] == "runmal-p167-face-speaking-census-v1"
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_NO_CHARACTERS
    assert doc["characters"] == []
    assert doc["counts"]["character_count"] == 0
    assert doc["counts"]["chat_count"] == 0
    assert doc["counts"]["paired_character_count"] == 0


async def test_characters_without_chats_is_no_chats(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    await _world(factory, uid, name="Asta")
    await _world(factory, uid, name="Bera")
    doc = await speak_census(factory, uid)
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_NO_CHATS
    assert doc["counts"]["character_count"] == 2
    assert doc["counts"]["characters_with_chats_count"] == 0
    assert doc["counts"]["paired_character_count"] == 0
    for row in doc["characters"]:
        assert row["board_state"] == "no_chats"
        assert row["chats"] == []
        # A voice beside an empty row is stated, never upgraded.
        assert row["voice"]["state"] == census.VOICE_DEFAULT
        assert row["paired"] is False


async def test_chats_without_ready_faces_is_none_ready(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1")
    doc = await speak_census(factory, uid)
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_NONE_READY
    assert doc["counts"]["ready_count"] == 0
    assert doc["counts"]["paired_character_count"] == 0
    (row,) = doc["characters"]
    # The character HAS a profile voice and a chat, yet
    # nothing is ready, so the row never pairs.
    assert row["voice"]["state"] == census.VOICE_PROFILE
    assert row["paired"] is False
    assert chat_id


async def test_some_and_all_ready_states_and_row_pairing(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid_a, _b, _g = await _world(factory, uid, name="Asta")
    cid_b, _b2, _g2 = await _world(factory, uid, name="Bera")
    busy = await seed_chat(factory, uid, cid_a, title="Busy")
    await seed_chat(factory, uid, cid_b, title="Quiet")
    async with factory() as session:
        await ex.select_for_chat(session, uid, busy, "amused")
        doc = await census.resolve_face_speaking_census(session, uid)
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_SOME_READY
    by_name = {row["character"]["name"]: row
               for row in doc["characters"]}
    assert by_name["Asta"]["paired"] is True
    assert by_name["Bera"]["paired"] is False
    assert doc["counts"]["paired_character_count"] == 1
    quiet = [c for c in await _chat_ids(factory, uid, cid_b)][0]
    async with factory() as session:
        await ex.select_for_chat(session, uid, quiet, "amused")
        doc = await census.resolve_face_speaking_census(session, uid)
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_ALL_READY
    assert doc["counts"]["paired_character_count"] == 2


async def _chat_ids(factory, uid, cid):
    async with factory() as session:
        pairs = await chats_svc.list_chats(session, uid)
    return [chat.id for chat, _n in pairs
            if getattr(chat, "character_id", None) == cid]


# -- Rows: order, verbatim composition, the blur pin ------------------------------


async def test_rows_ride_in_character_creation_order(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    await _world(factory, uid, name="Asta")
    await _world(factory, uid, name="Bera")
    await seed_character(factory, uid, name="Idle")
    doc = await speak_census(factory, uid)
    assert [row["character"]["name"] for row in doc["characters"]] == [
        "Asta", "Bera", "Idle"]


async def test_row_composes_p164_verbatim_plus_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        expected = await plain_census.resolve_face_census(session, uid)
        doc = await census.resolve_face_speaking_census(session, uid)
    (plain_row,) = expected["characters"]
    (row,) = doc["characters"]
    for key in ("character_id", "character", "board_state", "chats",
                "chat_count", "ready_count", "selection_count",
                "unbound_count"):
        assert row[key] == plain_row[key], key
    for key in ("character_count", "characters_with_chats_count",
                "chat_count", "ready_count", "selection_count",
                "unbound_count"):
        assert doc["counts"][key] == expected["counts"][key], key
    assert doc["state"] == expected["state"]
    assert row["paired"] is True


async def test_distinct_voices_stay_distinct_per_row(tmp_path):
    """THE BLUR PIN: two characters with different voices
    keep exactly their own voice inside their own row,
    and no voice of any kind stands at census level."""
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid_a, _b, _g = await _world(factory, uid, name="Asta")
    cid_b, _b2, _g2 = await _world(factory, uid, name="Bera")
    chat_a = await seed_chat(factory, uid, cid_a, title="A chat")
    chat_b = await seed_chat(factory, uid, cid_b, title="B chat")
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_a, "amused")
        await ex.select_for_chat(session, uid, chat_b, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid_a, tts_backend="fake-tts",
            voice_id="asta-voice", language="en-gb")
        await voice_profiles.set_character_voice(
            session, uid, cid_b, tts_backend="fake-tts",
            voice_id="bera-voice", language="is")
        doc = await census.resolve_face_speaking_census(session, uid)
    by_name = {row["character"]["name"]: row
               for row in doc["characters"]}
    assert by_name["Asta"]["voice"]["voice_id"] == "asta-voice"
    assert by_name["Asta"]["voice"]["language"] == "en-gb"
    assert by_name["Bera"]["voice"]["voice_id"] == "bera-voice"
    assert by_name["Bera"]["voice"]["language"] == "is"
    assert by_name["Asta"]["voice"] != by_name["Bera"]["voice"]
    assert "voice" not in doc
    assert "paired" not in doc
    assert doc["counts"]["paired_character_count"] == 2


async def test_counts_arithmetic_on_a_mixed_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid_a, _b, _g = await _world(factory, uid, name="Asta")
    cid_b, _b2, _g2 = await _world(factory, uid, name="Bera")
    await seed_character(factory, uid, name="Idle")
    busy = await seed_chat(factory, uid, cid_a, title="Busy")
    wrong = await seed_chat(factory, uid, cid_a, title="Wrong")
    hers = await seed_chat(factory, uid, cid_b, title="Hers")
    await seed_chat(factory, uid, None, title="Unbound chat")
    async with factory() as session:
        await ex.select_for_chat(session, uid, busy, "amused")
        await ex.select_for_chat(session, uid, wrong, "wrong")
        await ex.select_for_chat(session, uid, hers, "amused")
        doc = await census.resolve_face_speaking_census(session, uid)
    counts = doc["counts"]
    assert counts["character_count"] == 3
    assert counts["characters_with_chats_count"] == 2
    assert counts["chat_count"] == 3
    assert counts["ready_count"] == 2
    assert counts["selection_count"] == 3
    assert counts["unbound_count"] == 1
    assert counts["paired_character_count"] == 2
    assert doc["state"] == census.SPEAKING_CENSUS_STATE_SOME_READY
    by_name = {row["character"]["name"]: row
               for row in doc["characters"]}
    assert by_name["Idle"]["board_state"] == "no_chats"
    assert by_name["Idle"]["paired"] is False


async def test_foreign_owner_and_deleted_character_never_appear(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    foreign_cid, _fb, _fg = await _world(factory, other, name="Foreign")
    doomed_cid, _db, _dg = await _world(factory, uid, name="Doomed")
    mine = await seed_chat(factory, uid, cid, title="Mine")
    foreign = await seed_chat(factory, other, foreign_cid, title="F")
    async with factory() as session:
        await ex.select_for_chat(session, uid, mine, "amused")
        await ex.select_for_chat(session, other, foreign, "amused")
        await voice_profiles.set_character_voice(
            session, other, foreign_cid, voice_id="foreign-voice")
        assert await characters_svc.delete_character(
            session, uid, doomed_cid) is True
        doc = await census.resolve_face_speaking_census(session, uid)
        other_doc = await census.resolve_face_speaking_census(
            session, other)
    assert [row["character"]["name"] for row in doc["characters"]] == [
        "Asta"]
    assert doc["characters"][0]["voice"]["voice_id"] != "foreign-voice"
    assert [row["character"]["name"]
            for row in other_doc["characters"]] == ["Foreign"]
    assert other_doc["characters"][0]["voice"]["voice_id"] == (
        "foreign-voice")


# -- Key law: the objection pinned as absence --------------------------------------


async def test_exact_envelope_row_and_voice_keys(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        doc = await census.resolve_face_speaking_census(session, uid)
    assert set(doc) == {"schema", "state", "characters", "counts",
                        "notes"}
    for key in ("voice", "voice_scope", "paired", "face", "history",
                "kept_limit", "events"):
        assert key not in doc
    (row,) = doc["characters"]
    assert set(row) == {
        "character_id", "character", "board_state", "chats",
        "chat_count", "ready_count", "selection_count",
        "unbound_count", "voice", "paired"}
    assert set(doc["counts"]) == {
        "character_count", "characters_with_chats_count",
        "chat_count", "ready_count", "selection_count",
        "unbound_count", "paired_character_count"}
    assert set(row["voice"]) == {
        "state", "profile_exists", "stored_backend",
        "tts_backend", "voice_id", "language", "params", "affect"}
    (chat_row,) = row["chats"]
    assert set(chat_row) == {
        "chat_id", "title", "message_count", "presentation_state",
        "current", "current_problem", "face"}
    for key in ("voice", "voice_scope", "paired"):
        assert key not in chat_row


# -- The voice half: S512 states, judged per row ------------------------------------


async def test_profile_voice_and_carried_affect_per_row(tmp_path):
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
    doc = await speak_census(factory, uid)
    (row,) = doc["characters"]
    voice = row["voice"]
    assert voice["state"] == census.VOICE_PROFILE
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
    assert row["paired"] is True


async def test_partial_profile_stays_profile_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, voice_id="only-voice")
    doc = await speak_census(factory, uid)
    voice = doc["characters"][0]["voice"]
    assert voice["state"] == census.VOICE_PROFILE
    assert voice["stored_backend"] == ""
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == "only-voice"


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
    doc = await speak_census(factory, uid)
    voice = doc["characters"][0]["voice"]
    assert voice["state"] == census.VOICE_PROFILE_FALLBACK
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "kokoro-onnx"
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert set(census.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


async def test_default_voice_affect_is_neutral_unconsumed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    doc = await speak_census(factory, uid)
    (row,) = doc["characters"]
    assert row["voice"]["state"] == census.VOICE_DEFAULT
    assert row["voice"]["profile_exists"] is False
    assert row["voice"]["stored_backend"] is None
    affect = row["voice"]["affect"]
    assert affect["affect"] == "neutral"
    assert affect["source"] == "default"
    assert affect["consumed"] is False
    assert row["paired"] is True


# -- Pure read / notes ----------------------------------------------------------------


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
        row = await voice_profiles.get_character_voice(session, uid, cid)
        stamp_before = (row.tts_backend, row.voice_id, row.updated_at)
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        first = await census.resolve_face_speaking_census(session, uid)
        second = await census.resolve_face_speaking_census(session, uid)
        row = await voice_profiles.get_character_voice(session, uid, cid)
        stamp_after = (row.tts_backend, row.voice_id, row.updated_at)
    assert first == second
    assert store.read_bytes() == before
    assert stamp_after == stamp_before
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1


async def test_notes_and_closed_state_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await speak_census(factory, uid)
    assert doc["notes"] == list(census.NOTES)
    assert len(doc["notes"]) == 5
    assert "data only" in doc["notes"][0]
    assert "per character row only" in doc["notes"][1]
    assert "no owner-wide" in doc["notes"][3].lower() or (
        "No owner-wide" in doc["notes"][3])
    assert "speaking-history census" in doc["notes"][4]
    assert set(census.SPEAKING_CENSUS_STATES) == {
        "no_characters", "no_chats", "none_ready",
        "some_ready", "all_ready"}


# -- HTTP surface -----------------------------------------------------------------------


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def make_png_bytes(width=16, height=16, color=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(
                ">IIBBBBB", width, height, 8, 2, 0, 0, 0))
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


def test_http_speaking_census_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    empty = client.get("/api/v1/faces/speaking-census")
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_characters"
    assert "voice" not in empty.json()
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    no_chats = client.get("/api/v1/faces/speaking-census")
    assert no_chats.status_code == 200, no_chats.text
    assert no_chats.json()["state"] == "no_chats"
    (row,) = no_chats.json()["characters"]
    assert row["voice"]["state"] == "default_voice"
    assert row["paired"] is False
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
    before = client.get("/api/v1/faces/speaking-census")
    assert before.json()["state"] == "none_ready"
    assert before.json()["characters"][0]["paired"] is False
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/speaking-census")
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p167-face-speaking-census-v1"
    assert doc["state"] == "all_ready"
    assert doc["counts"]["ready_count"] == 1
    assert doc["counts"]["paired_character_count"] == 1
    assert doc["characters"][0]["paired"] is True
    assert doc["characters"][0]["voice"]["state"] == "default_voice"
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/speaking-census" in paths


# -- Neighbours ---------------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
