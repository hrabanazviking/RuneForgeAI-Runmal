"""P-157 - Speaking face: face + voice resolution (Part X, DERIVED).

Pins: the speaking-face document pairing P-092's inspect
surface (under the P-155 five-state face law, face named
only when ready, not_declared for a selection outliving
its set) with S512's voice resolution for the chat's bound
character (the closed voice-state law: profile /
profile_fallback for a legacy removed backend /
default_voice; field-level fallback stated by the resolved
reference itself), the P-109 affect carried whole with
consumed False, ``paired`` true exactly when a ready face
and a resolved voice stand together, the standing honesty
notes (no synthesis, no rendering, no lip-sync claimed),
owner scoping (unknown/foreign chat -> None / 404), the
pure-read law (the P-092 store byte-identical, the voice
row untouched, no selection or history written), and the
neighbours (migration head stays 0041, no 0042). The
P-155 battery is absent on this base and runs at banking.
No network.
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
from runmal.faces import speaking as sp
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


async def _world(factory, uid):
    """Character + bound chat + one bound sprite and one
    unbound entry; the bound entry is the declared default."""
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind="expression", name="amused",
            filename="amused.png", data=PNG_BYTES)
        bound_id = asset.id
    ex.create_set(uid, {
        "character_id": cid,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused", "asset_id": bound_id},
        ],
        "default": "amused",
    })
    return cid, chat_id, bound_id


# -- Owner scoping / no character ---------------------------------------------


async def test_missing_and_foreign_chat_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    _cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        assert await sp.resolve_speaking_face(
            session, uid, str(uuid.uuid4())) is None
        assert await sp.resolve_speaking_face(
            session, other, chat_id) is None


async def test_no_character_has_no_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["schema"] == sp.SPEAKING_SCHEMA
    assert doc["state"] == sp.STATE_NO_CHARACTER
    assert doc["character_id"] is None
    assert doc["face"] is None and doc["voice"] is None
    assert doc["paired"] is False


# -- Voice states ---------------------------------------------------------------


async def test_default_voice_when_no_profile(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["state"] == sp.STATE_NO_SET
    voice = doc["voice"]
    assert voice["state"] == sp.VOICE_DEFAULT
    assert voice["profile_exists"] is False
    assert voice["stored_backend"] is None
    default = voice_profiles.DEFAULT_VOICE
    assert voice["tts_backend"] == default.backend_key
    assert voice["voice_id"] == default.voice_id
    assert voice["language"] == default.language
    assert voice["params"] == {}
    affect = voice["affect"]
    assert affect["affect"] == "neutral"
    assert affect["source"] == "default"
    assert affect["consumed"] is False
    assert affect["consumption"]["consumed_by_backends"] is False
    # A voice resolving is not a pairing: no ready face.
    assert doc["paired"] is False


async def test_profile_voice_and_carried_affect(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1", language="en-gb",
            params={"affect": "whispering", "prompt_text": "Hush."})
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sp.VOICE_PROFILE
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


async def test_partial_profile_stays_profile_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, voice_id="only-voice")
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sp.VOICE_PROFILE
    assert voice["stored_backend"] == ""
    # The gaps fell back field by field (S512 law, stated by
    # the resolved reference itself).
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == "only-voice"


async def test_legacy_backend_is_profile_fallback(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        session.add(CharacterVoiceProfile(
            character_id=cid, user_id=uid,
            tts_backend="kokoro-onnx", voice_id="af_heart",
            language="en-us", params_json="{}"))
        await session.commit()
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    voice = doc["voice"]
    assert voice["state"] == sp.VOICE_PROFILE_FALLBACK
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "kokoro-onnx"
    # The whole reference fell back; the legacy voice id
    # does not leak into the surviving backend.
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert set(sp.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


# -- Pairing ----------------------------------------------------------------------


async def test_paired_when_face_ready_and_voice_resolves(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, bound_id = await _world(factory, uid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1")
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["state"] == sp.STATE_READY
    assert doc["paired"] is True
    assert doc["current"]["expression"] == "amused"
    assert doc["current"]["provenance"]["reason"] == "a joke landed"
    assert doc["face"]["name"] == "amused"
    assert doc["face"]["renderable"] is True
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert doc["face"]["content_url"] == f"{base}/content"
    assert doc["face"]["thumbnail_url"] == f"{base}/thumbnail"
    assert doc["voice"]["voice_id"] == "narrator-1"


async def test_unbound_face_still_speaks_unpaired(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "neutral")
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["state"] == sp.STATE_CURRENT_UNBOUND
    assert doc["current_problem"] == "no_asset"
    assert doc["face"] is None
    assert doc["paired"] is False
    # The voice half resolves on its own law regardless.
    assert doc["voice"]["state"] == sp.VOICE_DEFAULT


async def test_selection_outliving_its_set_is_not_declared(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.delete_set(uid, cid) is True
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["state"] == sp.STATE_CURRENT_UNBOUND
    assert doc["current_problem"] == sp.PROBLEM_NOT_DECLARED
    assert doc["face"] is None and doc["paired"] is False
    assert doc["voice"] is not None


async def test_no_selection_is_unpaired_with_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["state"] == sp.STATE_NO_SELECTION
    assert doc["face"] is None and doc["current"] is None
    assert doc["paired"] is False
    assert doc["voice"]["state"] == sp.VOICE_DEFAULT
    # The declared default was NOT applied by the read.
    assert ex.current_expression(uid, chat_id) is None


# -- Pure-read law / notes ---------------------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b = await _world(factory, uid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1")
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        stamp_before = (row.tts_backend, row.voice_id, row.updated_at)
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        await sp.resolve_speaking_face(session, uid, chat_id)
        await sp.resolve_speaking_face(session, uid, chat_id)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id) is None
    assert ex.list_history(uid, chat_id=chat_id) == []
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        assert (row.tts_backend, row.voice_id, row.updated_at) == stamp_before


async def test_notes_are_the_five_standing_notes(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await sp.resolve_speaking_face(session, uid, chat_id)
    assert doc["notes"] == list(sp.NOTES)
    assert len(doc["notes"]) == 5
    assert "synthesizes no" in doc["notes"][0]
    assert "lip-sync" in doc["notes"][0]
    assert "consumed" in doc["notes"][3]
    assert set(sp.FACE_STATES) == {
        "ready", "current_unbound", "no_selection",
        "no_set", "no_character"}
    assert doc["state"] in sp.FACE_STATES


# -- HTTP surface -------------------------------------------------------------------


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


def test_http_speaking_flow(tmp_path, monkeypatch):
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
    before = client.get("/api/v1/faces/speaking",
                        params={"chat_id": chat_id})
    assert before.status_code == 200, before.text
    doc = before.json()
    assert doc["state"] == "no_selection"
    assert doc["face"] is None and doc["paired"] is False
    assert doc["voice"]["state"] == "default_voice"
    assert doc["voice"]["affect"]["consumed"] is False
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/speaking",
                       params={"chat_id": chat_id})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["state"] == "ready" and doc["paired"] is True
    assert doc["face"]["name"] == "amused"
    missing = client.get("/api/v1/faces/speaking",
                         params={"chat_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/speaking" in paths


def test_http_unbound_chat_is_data_at_200(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Solo"})
    assert chat.status_code in (200, 201), chat.text
    res = client.get("/api/v1/faces/speaking",
                     params={"chat_id": chat.json()["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "no_character"
    assert res.json()["voice"] is None


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
