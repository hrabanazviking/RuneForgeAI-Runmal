"""P-161 - Speaking history (Part X, DERIVED).

Pins: one chat's kept face history paired with its
character's CURRENT voice resolution - P-158's history
document composed whole (every kept event verbatim with
provenance, newest first, entry states judged against
today, counts and the kept window riding whole) with
the S512 voice half composed verbatim in substance
exactly as P-157 / P-159 compose it (the closed
voice-state law: profile / profile_fallback for a legacy
removed backend / default_voice; stored_backend visible;
the P-109 affect carried whole with consumed False),
the voice honesty law as data (voice_scope is
current_only on every document; S512 stores no voice
history, so no event carries a voice field and a voice
changed after the selections is the voice the document
names - today's, never a claim about the past),
``paired`` true exactly when a voice resolved and the
kept history holds at least one selection, owner
scoping (unknown/foreign chat -> None / 404), the
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
from runmal.faces import history as hist
from runmal.faces import speaking_history as sh
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


async def seed_chat(factory, uid, character_id=None):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title="The Lighthouse",
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
    """Character + bound chat + set: neutral (no asset),
    amused (bound sprite), wrong (wrong-kind asset);
    default is the bound one. (P-158's world, verbatim.)"""
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
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
    return cid, chat_id, bound_id, bg_id


async def speak_hist(factory, uid, chat_id):
    async with factory() as session:
        return await sh.resolve_speaking_history(session, uid, chat_id)


# -- Existence / owner scoping ---------------------------------


async def test_missing_and_foreign_chat_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await sh.resolve_speaking_history(
            session, uid, str(uuid.uuid4())) is None
        assert await sh.resolve_speaking_history(
            session, other, chat_id) is None


async def test_no_character_chat_has_no_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    doc = await speak_hist(factory, uid, chat_id)
    assert doc["schema"] == sh.SPEAKING_HISTORY_SCHEMA
    assert doc["character_id"] is None
    assert doc["presentation_state"] == "no_character"
    assert doc["events"] == [] and doc["event_count"] == 0
    assert doc["voice"] is None
    # The scope law does not change when there is no voice.
    assert doc["voice_scope"] == "current_only"
    assert doc["paired"] is False


async def test_empty_history_still_resolves_todays_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    doc = await speak_hist(factory, uid, chat_id)
    assert doc["events"] == [] and doc["selection_count"] == 0
    assert doc["presentation_state"] == "no_selection"
    voice = doc["voice"]
    assert voice is not None
    assert voice["state"] == sh.VOICE_DEFAULT
    assert voice["profile_exists"] is False
    assert voice["stored_backend"] is None
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    # A voice beside an empty history is stated, never upgraded.
    assert doc["paired"] is False


# -- The history half rides P-158 whole -------------------------


async def test_history_half_is_p158_composed_whole(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
        await ex.select_for_chat(session, uid, chat_id, "neutral",
                                 reason="the news turned grave")
        doc = await sh.resolve_speaking_history(session, uid, chat_id)
        plain = await hist.resolve_face_history(session, uid, chat_id)
    for key in ("chat_id", "character_id", "presentation_state",
                "current", "events", "event_count",
                "selection_count", "cleared_count",
                "still_ready_count", "kept_limit", "at_kept_limit"):
        assert doc[key] == plain[key], key
    assert doc["event_count"] == 2
    newest, oldest = doc["events"]
    assert newest["expression"] == "neutral"
    assert newest["entry_state"] == "declared_unbound"
    assert oldest["expression"] == "amused"
    assert oldest["entry_state"] == "still_ready"
    assert oldest["descriptor"]["name"] == "amused"
    assert doc["kept_limit"] == ex.MAX_HISTORY_KEPT
    assert doc["at_kept_limit"] is False
    assert doc["paired"] is True


async def test_cleared_event_rides_and_selection_still_pairs(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.clear_selection(uid, chat_id, reason="scene over") is True
    doc = await speak_hist(factory, uid, chat_id)
    assert doc["selection_count"] == 1 and doc["cleared_count"] == 1
    cleared = doc["events"][0]
    assert cleared["entry_state"] == "cleared"
    assert cleared["descriptor"] is None
    # The kept selection still stands in the history, so the
    # pairing stands; the clearing is an event, not an erasure.
    assert doc["paired"] is True
    assert doc["voice"]["state"] == sh.VOICE_DEFAULT


# -- The voice half: S512 states --------------------------------


async def test_profile_voice_and_carried_affect(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1", language="en-gb",
            params={"affect": "whispering", "prompt_text": "Hush."})
    doc = await speak_hist(factory, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sh.VOICE_PROFILE
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
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        await voice_profiles.set_character_voice(
            session, uid, cid, voice_id="only-voice")
    doc = await speak_hist(factory, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sh.VOICE_PROFILE
    assert voice["stored_backend"] == ""
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == "only-voice"
    assert doc["paired"] is True


async def test_legacy_backend_is_profile_fallback(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        session.add(CharacterVoiceProfile(
            character_id=cid, user_id=uid,
            tts_backend="kokoro-onnx", voice_id="af_heart",
            language="en-us", params_json="{}"))
        await session.commit()
    doc = await speak_hist(factory, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sh.VOICE_PROFILE_FALLBACK
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "kokoro-onnx"
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert set(sh.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


async def test_default_voice_affect_is_neutral_unconsumed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    doc = await speak_hist(factory, uid, chat_id)
    affect = doc["voice"]["affect"]
    assert affect["affect"] == "neutral"
    assert affect["source"] == "default"
    assert affect["consumed"] is False
    assert doc["paired"] is True


# -- Voice honesty: today's resolution only ----------------------


async def test_voice_is_todays_resolution_only(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        # The selection happens while NO profile exists...
        await ex.select_for_chat(session, uid, chat_id, "amused")
        before = await sh.resolve_speaking_history(session, uid, chat_id)
        assert before["voice"]["state"] == sh.VOICE_DEFAULT
        # ...and the profile is set only afterwards.
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="late-voice")
    doc = await speak_hist(factory, uid, chat_id)
    # The document names the voice as it resolves TODAY...
    assert doc["voice"]["state"] == sh.VOICE_PROFILE
    assert doc["voice"]["voice_id"] == "late-voice"
    assert doc["voice_scope"] == sh.VOICE_SCOPE == "current_only"
    # ...and no event is dressed in it: events carry no voice
    # field of any kind, then or now.
    for event in doc["events"]:
        assert "voice" not in event
        assert "tts_backend" not in event
        assert "voice_id" not in event
    assert doc["events"] == before["events"]


async def test_document_keys_are_exactly_the_contract(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    doc = await speak_hist(factory, uid, chat_id)
    assert set(doc) == {
        "schema", "chat_id", "character_id",
        "presentation_state", "current", "events",
        "event_count", "selection_count", "cleared_count",
        "still_ready_count", "kept_limit", "at_kept_limit",
        "voice", "voice_scope", "paired", "notes"}
    assert set(doc["voice"]) == {
        "state", "profile_exists", "stored_backend",
        "tts_backend", "voice_id", "language", "params",
        "affect"}


# -- Pure read / notes -------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
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
    first = await speak_hist(factory, uid, chat_id)
    second = await speak_hist(factory, uid, chat_id)
    assert first == second
    assert store.read_bytes() == before
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        assert (row.tts_backend, row.voice_id, row.updated_at) == stamp_before


async def test_notes_are_the_five_standing_notes(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    doc = await speak_hist(factory, uid, chat_id)
    assert doc["notes"] == list(sh.NOTES)
    assert len(doc["notes"]) == 5
    assert "synthesizes no" in doc["notes"][0]
    assert "lip-sync" in doc["notes"][0]
    assert "current_only" in doc["notes"][1]
    assert "no voice history" in doc["notes"][1]
    assert "kept window" in doc["notes"][3]
    assert "consumed" in doc["notes"][4]


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


def test_http_speaking_history_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
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
    before = client.get("/api/v1/faces/speaking-history",
                        params={"chat_id": chat_id})
    assert before.status_code == 200, before.text
    assert before.json()["events"] == []
    assert before.json()["voice"]["state"] == "default_voice"
    assert before.json()["paired"] is False
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/speaking-history",
                       params={"chat_id": chat_id})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p161-speaking-history-v1"
    assert doc["voice_scope"] == "current_only"
    assert doc["event_count"] == 1
    assert doc["events"][0]["expression"] == "amused"
    assert doc["events"][0]["entry_state"] == "still_ready"
    assert doc["paired"] is True
    missing = client.get("/api/v1/faces/speaking-history",
                         params={"chat_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/speaking-history" in paths


def test_http_unbound_chat_is_data_at_200(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Solo"})
    assert chat.status_code in (200, 201), chat.text
    res = client.get("/api/v1/faces/speaking-history",
                     params={"chat_id": chat.json()["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["presentation_state"] == "no_character"
    assert res.json()["voice"] is None
    assert res.json()["voice_scope"] == "current_only"
    assert res.json()["events"] == []


# -- Neighbours ------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
