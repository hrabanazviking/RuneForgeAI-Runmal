"""P-159 - Speaking roster: roster + voice resolution (Part X, DERIVED).

Pins: the per-character (chat-less) speaking roster as a
pure read composing P-156's roster document whole (every
declared entry a presentation descriptor in P-155's
shape, the roster classified under the same closed
ROSTER_STATES law, the declared default and the avatar
named as fallback DATA) with S512's voice resolution for
the character (the closed voice-state law: profile /
profile_fallback for a legacy removed backend /
default_voice; field-level fallback stated by the
resolved reference itself), the P-109 affect carried
whole with consumed False, ``paired`` true exactly when
a ready roster and a resolved voice stand together, NO
current face anywhere in the document (selection is per
chat, P-092's explicit act), the standing honesty notes
(no synthesis, no rendering, no lip-sync claimed), owner
scoping (unknown/foreign character -> None / 404), the
pure-read law (the P-092 store byte-identical, the voice
row untouched, no selection or history written), the
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
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import CharacterVoiceProfile, User
from runmal.faces import roster as fr
from runmal.faces import speaking_roster as sr
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


async def seed_asset(factory, uid, cid, kind="expression",
                     name="amused", filename="amused.png"):
    async with factory() as session:
        row = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=filename, data=PNG_BYTES)
        await session.commit()
        return row.id


def declare(uid, cid, base, entries, default=None):
    return ex.create_set(uid, {
        "character_id": cid, "entries": entries,
        "default": default}, base_dir=base)


async def roster(factory, uid, cid, base):
    async with factory() as session:
        return await sr.resolve_character_speaking_roster(
            session, uid, cid, base_dir=base)


# -- Existence / owner scoping ---------------------------------


async def test_missing_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await roster(factory, uid, str(uuid.uuid4()),
                       tmp_path / "store")
    assert doc is None


async def test_foreign_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "other")
    cid = await seed_character(factory, uid)
    assert await roster(factory, other, cid,
                        tmp_path / "store") is None
    assert await roster(factory, uid, cid,
                        tmp_path / "store") is not None


# -- Roster states on the pairing axis ---------------------------


async def test_no_set_state_default_voice_unpaired(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    doc = await roster(factory, uid, cid, tmp_path / "store")
    assert doc["schema"] == sr.SPEAKING_ROSTER_SCHEMA == (
        "runmal-p159-speaking-roster-v1")
    assert doc["state"] == fr.STATE_NO_SET == "no_set"
    assert doc["state"] in fr.ROSTER_STATES
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["set"] is None
    assert doc["entries"] == []
    assert doc["entry_count"] == doc["bound_count"] == 0
    assert doc["renderable_count"] == doc["unbound_count"] == 0
    assert doc["default_entry"] is None
    assert doc["avatar"] == {"has_avatar": False,
                             "avatar_asset": None,
                             "avatar_url": None}
    assert doc["selection_scope"] == "per_chat"
    voice = doc["voice"]
    assert voice["state"] == sr.VOICE_DEFAULT
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
    # A voice resolving is not a pairing: no renderable face.
    assert doc["paired"] is False


async def test_empty_set_state_unpaired(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base, [], default=None)
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_EMPTY_SET == "empty_set"
    assert doc["set"] is not None
    assert doc["entries"] == []
    assert doc["voice"]["state"] == sr.VOICE_DEFAULT
    assert doc["paired"] is False


async def test_no_renderable_state_still_names_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base,
            [{"name": "neutral", "label": "Neutral"},
             {"name": "ghost", "asset_id": str(uuid.uuid4())}],
            default="neutral")
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_NO_RENDERABLE
    assert doc["renderable_count"] == 0
    assert doc["unbound_count"] == 2
    problems = {e["name"]: e["problem"] for e in doc["entries"]}
    assert problems == {"neutral": "no_asset",
                        "ghost": "asset_missing"}
    for entry in doc["entries"]:
        assert entry["renderable"] is False
        assert entry["content_url"] is None
        assert entry["thumbnail_url"] is None
    assert doc["default_entry"]["name"] == "neutral"
    # The voice half resolves on its own law regardless.
    assert doc["voice"]["state"] == sr.VOICE_DEFAULT
    assert doc["paired"] is False


async def test_ready_roster_paired_with_default_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    asset_id = await seed_asset(factory, uid, cid)
    bg_id = await seed_asset(factory, uid, cid, kind="background",
                             name="hall", filename="hall.png")
    declare(uid, cid, base,
            [{"name": "neutral", "label": "Neutral"},
             {"name": "amused", "label": "Amused",
              "asset_id": asset_id, "notes": " grin "},
             {"name": "hall", "asset_id": bg_id}],
            default="amused")
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_READY == "ready"
    assert doc["entry_count"] == 3
    assert doc["bound_count"] == 1
    assert doc["renderable_count"] == 1
    assert doc["unbound_count"] == 2
    by_name = {e["name"]: e for e in doc["entries"]}
    amused = by_name["amused"]
    assert amused["bound"] is True
    assert amused["problem"] is None
    assert amused["renderable"] is True
    assert amused["asset"]["id"] == asset_id
    assert amused["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    assert amused["thumbnail_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/thumbnail")
    assert by_name["hall"]["problem"] == "wrong_kind"
    assert by_name["neutral"]["problem"] == "no_asset"
    assert doc["default_entry"] == amused
    assert doc["set"]["default"] == "amused"
    # Even the default voice pairs with a ready roster.
    assert doc["voice"]["state"] == sr.VOICE_DEFAULT
    assert doc["paired"] is True


# -- Voice states ---------------------------------------------------


async def test_profile_voice_and_carried_affect(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    asset_id = await seed_asset(factory, uid, cid)
    declare(uid, cid, base,
            [{"name": "amused", "asset_id": asset_id}],
            default="amused")
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1", language="en-gb",
            params={"affect": "whispering", "prompt_text": "Hush."})
    doc = await roster(factory, uid, cid, base)
    voice = doc["voice"]
    assert voice["state"] == sr.VOICE_PROFILE
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
    cid = await seed_character(factory, uid)
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, voice_id="only-voice")
    doc = await roster(factory, uid, cid, tmp_path / "store")
    voice = doc["voice"]
    assert voice["state"] == sr.VOICE_PROFILE
    assert voice["stored_backend"] == ""
    # The gaps fell back field by field (S512 law, stated by
    # the resolved reference itself).
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == "only-voice"
    assert doc["paired"] is False


async def test_legacy_backend_is_profile_fallback(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        session.add(CharacterVoiceProfile(
            character_id=cid, user_id=uid,
            tts_backend="kokoro-onnx", voice_id="af_heart",
            language="en-us", params_json="{}"))
        await session.commit()
    doc = await roster(factory, uid, cid, tmp_path / "store")
    voice = doc["voice"]
    assert voice["state"] == sr.VOICE_PROFILE_FALLBACK
    assert voice["profile_exists"] is True
    assert voice["stored_backend"] == "kokoro-onnx"
    # The whole reference fell back; the legacy voice id
    # does not leak into the surviving backend.
    assert voice["tts_backend"] == voice_profiles.DEFAULT_VOICE.backend_key
    assert voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert set(sr.VOICE_STATES) == {
        "profile", "profile_fallback", "default_voice"}


# -- No current face / pure read -------------------------------------


async def test_roster_names_no_current_face(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    asset_id = await seed_asset(factory, uid, cid)
    declare(uid, cid, base,
            [{"name": "amused", "asset_id": asset_id}],
            default="amused")
    doc = await roster(factory, uid, cid, base)
    assert "current" not in doc
    assert "face" not in doc
    assert "current_binding" not in doc
    assert "chat_id" not in doc
    assert doc["selection_scope"] == sr.SELECTION_SCOPE


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base, [{"name": "neutral"}], default="neutral")
    async with factory() as session:
        await voice_profiles.set_character_voice(
            session, uid, cid, tts_backend="fake-tts",
            voice_id="narrator-1")
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        stamp_before = (row.tts_backend, row.voice_id, row.updated_at)
    store = ex.store_path(uid, base_dir=base)
    before = store.read_bytes()
    first = await roster(factory, uid, cid, base)
    second = await roster(factory, uid, cid, base)
    assert first == second
    assert store.read_bytes() == before
    assert ex.get_set(uid, cid, base_dir=base) is not None
    assert ex.list_history(uid, base_dir=base) == []
    async with factory() as session:
        row = await voice_profiles.get_character_voice(session, uid, cid)
        assert (row.tts_backend, row.voice_id, row.updated_at) == stamp_before


# -- Avatar fallback ---------------------------------------------------


async def test_avatar_fallback_named_as_data(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        stored = await characters_svc.set_avatar(
            session, uid, cid, "asta.png", PNG_BYTES)
    assert stored == "asta.png"
    doc = await roster(factory, uid, cid, tmp_path / "store")
    assert doc["avatar"] == {
        "has_avatar": True, "avatar_asset": "asta.png",
        "avatar_url": f"/api/v1/characters/{cid}/avatar"}
    assert doc["character"]["has_avatar"] is True


# -- Notes ----------------------------------------------------------------


async def test_notes_are_the_five_standing_notes(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    doc = await roster(factory, uid, cid, tmp_path / "store")
    assert doc["notes"] == list(sr.NOTES)
    assert len(doc["notes"]) == 5
    assert "synthesizes no" in doc["notes"][0]
    assert "lip-sync" in doc["notes"][0]
    assert "consumed" in doc["notes"][3]


# -- HTTP surface ------------------------------------------------------------


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
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def test_http_speaking_roster_flow(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters",
                          json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    res = client.get("/api/v1/faces/speaking-roster",
                     params={"character_id": cid})
    assert res.status_code == 200, res.text
    doc = res.json()
    assert doc["schema"] == sr.SPEAKING_ROSTER_SCHEMA
    assert doc["state"] == "no_set"
    assert doc["voice"]["state"] == "default_voice"
    assert doc["voice"]["affect"]["consumed"] is False
    assert doc["paired"] is False
    assert "current" not in doc and "face" not in doc
    missing = client.get("/api/v1/faces/speaking-roster",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/speaking-roster" in paths


def test_http_speaking_roster_ready(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters",
                          json={"card": card_dict()})
    cid = created.json()["id"]
    up = client.post(
        f"/api/v1/characters/{cid}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", make_png_bytes(), "image/png")})
    assert up.status_code == 201, up.text
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "amused",
                     "asset_id": up.json()["id"]}],
        "default": "amused"})
    assert made.status_code == 201, made.text
    res = client.get("/api/v1/faces/speaking-roster",
                     params={"character_id": cid})
    assert res.status_code == 200, res.text
    doc = res.json()
    assert doc["state"] == "ready"
    assert doc["renderable_count"] == 1
    assert doc["default_entry"]["name"] == "amused"
    assert doc["entries"][0]["content_url"].endswith("/content")
    assert doc["paired"] is True


# -- Neighbours -------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
