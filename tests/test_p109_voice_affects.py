"""P-109 - Voice affects as carried data (Part VII, DERIVED scope).

Pins: the closed VX-12 vocabulary (neutral + the census-named
anger / whispering / laughing), strict write doors (profile
params validation, with_affect), tolerant reads with the
fallback NAMED (S512 law), resolution into the P-101 session
settings snapshot, the founding-road surfaces, and the honesty
law on every surface: consumed is False - no backend accepts
an affect and synthesis is unchanged by one. Fakes only.
Migration head stays 0041.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, Chat, User
from runmal.voice import affects as aff
from runmal.voice.profiles import CharacterVoice, set_character_voice
from runmal.voice.session import SessionSettings, resolve_session_settings
from runmal.voice.settings import VoiceSettings


# ---------------------------------------------------- vocabulary


def test_vocabulary_is_closed_and_census_shaped():
    assert aff.AFFECTS == ("neutral", "anger", "whispering", "laughing")
    assert aff.DEFAULT_AFFECT == "neutral"
    assert aff.PARAM_KEY == "affect"


def test_consumption_truth_says_no_consumer():
    view = aff.consumption_view()
    assert view["consumed_by_backends"] is False
    assert view["voice_info_field"] is False
    assert "no TTS backend" in view["note"]
    vocab = aff.vocabulary_view()
    assert vocab["affects"] == list(aff.AFFECTS)
    assert vocab["consumed"] is False


def test_normalize_strict():
    assert aff.normalize_affect("Anger") == "anger"
    assert aff.normalize_affect(" whispering ") == "whispering"
    assert aff.normalize_affect("neutral") == "neutral"
    for bad in ("", "joy", "angry", None, 3):
        with pytest.raises(ValueError):
            aff.normalize_affect(bad)


def test_affect_from_params_tolerant_reads():
    assert aff.affect_from_params(None) == ("neutral", "default")
    assert aff.affect_from_params({}) == ("neutral", "default")
    assert aff.affect_from_params({"affect": ""}) == ("neutral", "default")
    assert aff.affect_from_params({"affect": "Laughing"}) == ("laughing", "profile")
    # Out-of-vocabulary stored value: neutral, fallback NAMED.
    assert aff.affect_from_params({"affect": "ecstatic"}) == ("neutral", "fallback")
    assert aff.affect_from_params("junk") == ("neutral", "default")


def test_with_affect_write_helper():
    base = {"prompt_text": "hi"}
    out = aff.with_affect(base, "anger")
    assert out == {"prompt_text": "hi", "affect": "anger"}
    assert base == {"prompt_text": "hi"}  # input untouched
    # Neutral removes the key: absence is its one representation.
    assert aff.with_affect(out, "neutral") == {"prompt_text": "hi"}
    with pytest.raises(ValueError):
        aff.with_affect(base, "gleeful")


def test_affect_view_is_honestly_labelled():
    view = aff.affect_view("whispering", "profile")
    assert view["affect"] == "whispering" and view["source"] == "profile"
    assert view["consumed"] is False
    assert view["consumption"]["consumed_by_backends"] is False


# ------------------------------------------------------- resolver


def test_resolve_session_settings_carries_profile_affect():
    char = CharacterVoice("cosyvoice", "v1", "en-us", {"affect": "anger"})
    s = resolve_session_settings(defaults=VoiceSettings(), character=char)
    assert s.affect == "anger" and s.affect_source == "profile"
    data = s.to_dict()
    assert data["affect"] == "anger" and data["affect_consumed"] is False


def test_resolve_session_settings_defaults_and_fallback():
    s = resolve_session_settings(defaults=VoiceSettings(), character=None)
    assert (s.affect, s.affect_source) == ("neutral", "default")
    bad = CharacterVoice("cosyvoice", "v1", "en-us", {"affect": "bogus"})
    s2 = resolve_session_settings(defaults=VoiceSettings(), character=bad)
    assert (s2.affect, s2.affect_source) == ("neutral", "fallback")


def test_session_settings_roundtrip_and_legacy_snapshot():
    char = CharacterVoice("cosyvoice", "v1", "en-us", {"affect": "laughing"})
    s = resolve_session_settings(defaults=VoiceSettings(), character=char)
    back = SessionSettings.from_dict(s.to_dict())
    assert (back.affect, back.affect_source) == ("laughing", "profile")
    # A pre-P-109 snapshot (no affect keys) constructs unchanged.
    legacy = SessionSettings.from_dict(
        {"tts_backend": "cosyvoice", "stt_backend": "faster-whisper",
         "voice_id": "v", "language": "en-us"})
    assert (legacy.affect, legacy.affect_source) == ("neutral", "default")
    # Round trip is faithful for neutral too: the stored source
    # is provenance (default / fallback), not recomputed away.
    plain = resolve_session_settings(defaults=VoiceSettings(), character=None)
    back2 = SessionSettings.from_dict(plain.to_dict())
    assert (back2.affect, back2.affect_source) == ("neutral", "default")
    fb = SessionSettings.from_dict({"affect": "neutral", "affect_source": "fallback"})
    assert (fb.affect, fb.affect_source) == ("neutral", "fallback")
    # An unknown stored source string is recomputed, not trusted.
    weird = SessionSettings.from_dict({"affect": "anger", "affect_source": "mars"})
    assert (weird.affect, weird.affect_source) == ("anger", "profile")
    # A corrupt stored affect never bricks the snapshot.
    corrupt = SessionSettings.from_dict({"affect": "manic"})
    assert (corrupt.affect, corrupt.affect_source) == ("neutral", "fallback")


# ------------------------------------------------------------ HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory, db_path


def test_http_affects_vocabulary(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/voice/affects")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["affects"] == ["neutral", "anger", "whispering", "laughing"]
    assert body["default"] == "neutral" and body["consumed"] is False


def test_http_session_affect_flow(tmp_path, monkeypatch):
    client, factory, _db = make_client(tmp_path, monkeypatch)
    res = client.post("/api/v1/chats", json={"title": "voice chat"})
    assert res.status_code == 201, res.text

    async def seed():
        async with factory() as db:
            owner = (await db.execute(select(User).limit(1))).scalar_one()
            char = Character(user_id=owner.id, name="Skald")
            db.add(char)
            await db.commit()
            await set_character_voice(
                db, owner.id, char.id, tts_backend="kitten",
                voice_id="kitten-1", language="en-us",
                params={"affect": "whispering"})
            chat = Chat(user_id=owner.id, character_id=char.id, title="skald chat")
            db.add(chat)
            await db.commit()
            return chat.id

    chat_id = asyncio.run(seed())
    started = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id})
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["settings"]["affect"] == "whispering"
    assert body["settings"]["affect_source"] == "profile"
    assert body["settings"]["affect_consumed"] is False
    view = client.get(f"/api/v1/voice/sessions/{body['session_id']}/affect")
    assert view.status_code == 200, view.text
    data = view.json()
    assert data["affect"] == "whispering" and data["consumed"] is False
    assert data["session_id"] == body["session_id"]
    missing = client.get("/api/v1/voice/sessions/nope/affect")
    assert missing.status_code == 404


def test_profile_write_door_refuses_unknown_affect(tmp_path, monkeypatch):
    _client, factory, _db = make_client(tmp_path, monkeypatch)

    async def seed():
        async with factory() as db:
            owner = User(name="owner")
            db.add(owner)
            await db.commit()
            char = Character(user_id=owner.id, name="Skald")
            db.add(char)
            await db.commit()
            return owner.id, char.id

    owner_id, char_id = asyncio.run(seed())

    async def attempt():
        async with factory() as db:
            await set_character_voice(
                db, owner_id, char_id, tts_backend="kitten",
                voice_id="k1", params={"affect": "ecstatic"})

    with pytest.raises(ValueError):
        asyncio.run(attempt())


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
