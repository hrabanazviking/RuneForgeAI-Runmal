"""P-101 — Voice sessions (Part VII opener, DERIVED scope).

Pins: honest per-chat settings resolution (character equipment
over defaults, registry truth as data, named fallback — never a
resurrected engine), playback-truth turn records (no ledger
evidence = nothing claimed certain, INV-020), the durable JSON
session store (restart reload, tolerant load, chat housekeeping),
the one-active-session lifecycle, and the /api/v1/voice/sessions
HTTP surface with owner scoping. No network: fakes/fixtures only.
Migration head stays 0041 (the store is the voice JSON pattern).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, Chat, User
from runmal.voice.ledger import HeardReconstruction
from runmal.voice.orchestrator import TurnRecord
from runmal.voice.profiles import CharacterVoice, set_character_voice
from runmal.voice.session import (
    VoiceSessionError,
    VoiceSessionStore,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings
from runmal.voice.stt import FakeSTTBackend

NOW = "2026-11-07T12:00:00+00:00"
LATER = "2026-11-07T12:05:00+00:00"


def _settings(character=None, defaults=None):
    return resolve_session_settings(
        defaults=defaults or VoiceSettings(), character=character
    )


# ------------------------------------------------------- resolver


def test_resolve_defaults_truth():
    s = _settings()
    assert s.tts_backend == "cosyvoice" and s.stt_backend == "faster-whisper"
    assert s.voice_id == "cosyvoice-zero-shot" and s.language == "en-us"
    assert s.tts_truth.selected_via == "default"
    assert s.tts_truth.known and s.tts_truth.verified
    assert s.tts_truth.admission == "default-shipped"
    assert s.stt_truth.selected_via == "default" and s.stt_truth.verified


def test_resolve_character_voice_wins():
    char = CharacterVoice("chatterbox", "cb-voice", "en-gb", {})
    s = _settings(character=char)
    assert (s.tts_backend, s.voice_id, s.language) == ("chatterbox", "cb-voice", "en-gb")
    assert s.tts_truth.selected_via == "character"
    assert s.tts_truth.admission == "user-installed" and s.tts_truth.verified
    assert s.stt_backend == "faster-whisper"  # the ear stays the user's default


def test_resolve_character_user_installed_unverified_truth():
    s = _settings(character=CharacterVoice("kitten", "k1", "en-us", {}))
    assert s.tts_truth.known and not s.tts_truth.verified
    assert s.tts_truth.admission == "user-installed"


def test_resolve_unknown_character_backend_falls_back_named():
    s = _settings(character=CharacterVoice("kokoro-onnx", "k", "en-us", {}))
    assert s.tts_backend == "cosyvoice"  # the default, never the removed engine
    assert s.voice_id == "cosyvoice-zero-shot"
    assert s.tts_truth.selected_via == "fallback"
    assert "kokoro-onnx" in s.tts_truth.note


def test_resolve_character_empty_voice_falls_to_default_voice():
    s = _settings(character=CharacterVoice("piper", "", "", {}))
    assert s.tts_backend == "piper"
    assert s.voice_id == "cosyvoice-zero-shot" and s.language == "en-us"
    assert s.tts_truth.selected_via == "character"


def test_resolve_unknown_stt_default_falls_back():
    defaults = VoiceSettings()
    defaults.stt_backend = "no-such-ear"  # bypasses __post_init__ guard
    s = _settings(defaults=defaults)
    assert s.stt_backend == "faster-whisper"
    assert s.stt_truth.selected_via == "fallback"
    assert "no-such-ear" in s.stt_truth.note


def test_settings_dict_round_trip():
    s = _settings(character=CharacterVoice("piper", "p1", "de", {}))
    from runmal.voice.session import SessionSettings

    assert SessionSettings.from_dict(s.to_dict()) == s
    assert json.loads(json.dumps(s.to_dict())) == s.to_dict()


# ---------------------------------------------------- turn truth


def _orch_record(**kw):
    base = dict(turn_id=1, response_text="Hello there traveller.", chunks_total=2, chunks_played=2)
    base.update(kw)
    record = TurnRecord(**base)
    record.transcript = FakeSTTBackend(text="hello").transcribe(b"\x00\x00" * 100)
    return record


def test_turn_from_orchestrator_with_ledger_evidence():
    heard = HeardReconstruction("Hello there", "traveller.", "")
    turn = _settings()
    from runmal.voice.session import VoiceTurnRecord

    t = VoiceTurnRecord.from_orchestrator(
        _orch_record(), heard, turn_no=1, stt_backend="faster-whisper", recorded_at=NOW
    )
    assert t.heard_certain == "Hello there" and t.heard_uncertain == "traveller."
    assert t.transcript_text == "hello" and t.stt_backend == "faster-whisper"
    assert turn is not None


def test_turn_without_evidence_claims_nothing_certain():
    from runmal.voice.session import VoiceTurnRecord

    played = VoiceTurnRecord.from_orchestrator(
        _orch_record(), None, turn_no=1, stt_backend="faster-whisper", recorded_at=NOW
    )
    assert played.heard_certain == "" and played.heard_uncertain == "Hello there traveller."
    silent = VoiceTurnRecord.from_orchestrator(
        _orch_record(chunks_played=0), None, turn_no=2,
        stt_backend="faster-whisper", recorded_at=NOW,
    )
    assert silent.heard_certain == "" and silent.heard_unplayed == "Hello there traveller."


def test_turn_history_text_law():
    from runmal.voice.session import VoiceTurnRecord

    t = VoiceTurnRecord(
        turn_no=1, response_text="a b c", heard_certain="a",
        heard_uncertain="b", heard_unplayed="c", recorded_at=NOW,
    )
    assert t.history_text() == "a [uncertain: b…]"  # unplayed never included
    full = VoiceTurnRecord(turn_no=2, heard_certain="all of it", recorded_at=NOW)
    assert full.history_text() == "all of it"


def test_turn_dict_round_trip():
    from runmal.voice.session import VoiceTurnRecord

    t = VoiceTurnRecord(
        turn_no=3, transcript_text="hi", transcript_language="en",
        stt_backend="faster-whisper", response_text="yo", heard_certain="yo",
        interrupted=True, chunks_total=1, chunks_played=1, recorded_at=NOW,
    )
    assert VoiceTurnRecord.from_dict(t.to_dict()) == t


# ------------------------------------------------- store + life


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _start(store, chat_id="chat-1"):
    return start_session(
        store, chat_id=chat_id, user_id="u1", character_id=None,
        settings=_settings(), now=NOW,
    )


def test_store_round_trip_survives_reload(tmp_path):
    store = _store(tmp_path)
    s = _start(store)
    s.record_turn(transcript_text="hi", response_text="hello", heard_certain="hello",
                  chunks_total=1, chunks_played=1, recorded_at=NOW)
    store.save_session(s)
    fresh = _store(tmp_path)
    loaded = fresh.get(s.session_id)
    assert loaded is not None and loaded.active and loaded.chat_id == "chat-1"
    assert loaded.turns[0].heard_certain == "hello"
    assert fresh.active_for_chat("chat-1").session_id == s.session_id


def test_store_corrupt_and_missing_are_empty(tmp_path):
    assert _store(tmp_path).all_sessions() == []
    (tmp_path / "voice_sessions.json").write_text("{not json")
    assert _store(tmp_path).all_sessions() == []
    (tmp_path / "voice_sessions.json").write_text(json.dumps({"sessions": "nope"}))
    assert _store(tmp_path).all_sessions() == []


def test_store_skips_malformed_entries(tmp_path):
    store = _store(tmp_path)
    s = _start(store)
    doc = json.loads((tmp_path / "voice_sessions.json").read_text())
    doc["sessions"].append({"bogus": True})
    (tmp_path / "voice_sessions.json").write_text(json.dumps(doc))
    fresh = _store(tmp_path)
    assert [x.session_id for x in fresh.all_sessions()] == [s.session_id]


def test_start_supersedes_active_session(tmp_path):
    store = _store(tmp_path)
    first = _start(store)
    second = start_session(
        store, chat_id="chat-1", user_id="u1", character_id=None,
        settings=_settings(), now=LATER,
    )
    old = store.get(first.session_id)
    assert not old.active and old.stop_note == "superseded" and old.stopped_at == LATER
    assert store.active_for_chat("chat-1").session_id == second.session_id
    assert len(store.list_for_chat("chat-1")) == 2


def test_record_turn_on_stopped_session_refused(tmp_path):
    store = _store(tmp_path)
    s = _start(store)
    s.stop("done", at=LATER)
    with pytest.raises(VoiceSessionError):
        s.record_turn(response_text="late")
    with pytest.raises(VoiceSessionError):
        s.append_orchestrator_turn(_orch_record(), None)


def test_first_stop_wins(tmp_path):
    s = _start(_store(tmp_path))
    s.stop("first", at=NOW)
    s.stop("second", at=LATER)
    assert s.stop_note == "first" and s.stopped_at == NOW


def test_record_turn_validation(tmp_path):
    s = _start(_store(tmp_path))
    with pytest.raises(VoiceSessionError):
        s.record_turn(chunks_total=1, chunks_played=2)
    with pytest.raises(VoiceSessionError):
        s.record_turn(chunks_total=-1)
    turn = s.record_turn(transcript_text="a", recorded_at=NOW)
    assert turn.turn_no == 1 and turn.stt_backend == "faster-whisper"


def test_drop_chat_housekeeping(tmp_path):
    store = _store(tmp_path)
    _start(store, "chat-1")
    keep = _start(store, "chat-2")
    assert store.drop_chat("chat-1") == 1
    assert store.list_for_chat("chat-1") == []
    fresh = _store(tmp_path)
    assert [x.session_id for x in fresh.all_sessions()] == [keep.session_id]
    assert store.drop_chat("chat-1") == 0


def test_append_orchestrator_turn_via_session(tmp_path):
    s = _start(_store(tmp_path))
    heard = HeardReconstruction("Hello there traveller.", "", "")
    turn = s.append_orchestrator_turn(_orch_record(), heard, recorded_at=NOW)
    assert turn.turn_no == 1 and turn.heard_certain == "Hello there traveller."
    assert s.turns == [turn]


# --------------------------------------------------------- HTTP


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


def _chat(client, title="voice chat"):
    res = client.post("/api/v1/chats", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_http_start_session_defaults_truth(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["chat_id"] == chat_id and body["state"] == "active"
    assert body["settings"]["tts_backend"] == "cosyvoice"
    assert body["settings"]["tts_truth"]["selected_via"] == "default"
    assert body["turns"] == []


def test_http_start_missing_and_foreign_chat_404(tmp_path, monkeypatch):
    client, factory, _db = make_client(tmp_path, monkeypatch)
    assert client.post("/api/v1/voice/sessions", json={"chat_id": "nope"}).status_code == 404
    assert client.post("/api/v1/voice/sessions", json={}).status_code == 404

    async def seed_foreign():
        async with factory() as db:
            other = User(name="someone-else")
            db.add(other)
            await db.commit()
            chat = Chat(user_id=other.id, title="not yours")
            db.add(chat)
            await db.commit()
            return chat.id

    foreign = asyncio.run(seed_foreign())
    res = client.post("/api/v1/voice/sessions", json={"chat_id": foreign})
    assert res.status_code == 404  # owner scoping never leaks existence


def test_http_full_flow_and_persistence(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    sid = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id}).json()["session_id"]
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "hello", "response_text": "Hello there traveller.",
              "heard_certain": "Hello there traveller.", "chunks_total": 2, "chunks_played": 2},
    )
    assert turn.status_code == 201, turn.text
    assert turn.json()["turn_no"] == 1 and turn.json()["stt_backend"] == "faster-whisper"
    listing = client.get("/api/v1/voice/sessions", params={"chat_id": chat_id}).json()
    assert listing["active_session_id"] == sid
    assert listing["sessions"][0]["turn_count"] == 1
    # Persistence: a fresh client (fresh store load) still sees the turn.
    client2, _f2, _db2 = make_client(tmp_path, monkeypatch)
    got = client2.get(f"/api/v1/voice/sessions/{sid}").json()
    assert got["turns"][0]["heard_certain"] == "Hello there traveller."
    stopped = client2.post(f"/api/v1/voice/sessions/{sid}/stop", json={"note": "done"})
    assert stopped.json()["state"] == "stopped" and stopped.json()["stop_note"] == "done"
    late = client2.post(f"/api/v1/voice/sessions/{sid}/turns", json={"response_text": "x"})
    assert late.status_code == 409


def test_http_turn_validation_and_unknown_session(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/voice/sessions/nope").status_code == 404
    assert client.post("/api/v1/voice/sessions/nope/stop", json={}).status_code == 404
    assert client.post("/api/v1/voice/sessions/nope/turns", json={}).status_code == 404
    chat_id = _chat(client)
    sid = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id}).json()["session_id"]
    bad = client.post(
        f"/api/v1/voice/sessions/{sid}/turns", json={"chunks_total": 1, "chunks_played": 5}
    )
    assert bad.status_code == 422


def test_http_supersede_and_drop(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    first = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id}).json()
    second = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id}).json()
    old = client.get(f"/api/v1/voice/sessions/{first['session_id']}").json()
    assert old["state"] == "stopped" and old["stop_note"] == "superseded"
    listing = client.get("/api/v1/voice/sessions", params={"chat_id": chat_id}).json()
    assert listing["active_session_id"] == second["session_id"]
    dropped = client.delete(f"/api/v1/voice/chats/{chat_id}/sessions")
    assert dropped.json()["dropped"] == 2
    assert client.get(f"/api/v1/voice/sessions/{second['session_id']}").status_code == 404


def test_http_character_voice_session(tmp_path, monkeypatch):
    client, factory, _db = make_client(tmp_path, monkeypatch)
    _chat(client)  # creates the owner row

    async def seed():
        async with factory() as db:
            owner = (await db.execute(select(User).limit(1))).scalar_one()
            char = Character(user_id=owner.id, name="Skald")
            db.add(char)
            await db.commit()
            await set_character_voice(db, owner.id, char.id, tts_backend="kitten",
                                      voice_id="kitten-1", language="en-us", params={})
            chat = Chat(user_id=owner.id, character_id=char.id, title="skald chat")
            db.add(chat)
            await db.commit()
            return chat.id

    chat_id = asyncio.run(seed())
    res = client.post("/api/v1/voice/sessions", json={"chat_id": chat_id})
    assert res.status_code == 201, res.text
    settings = res.json()["settings"]
    assert settings["tts_backend"] == "kitten" and settings["voice_id"] == "kitten-1"
    assert settings["tts_truth"]["selected_via"] == "character"
    assert settings["tts_truth"]["admission"] == "user-installed"
    assert settings["tts_truth"]["verified"] is False


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"


def test_founding_status_surface_unchanged(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    data = client.get("/api/v1/voice/status").json()
    assert data["state"] == "LISTENING" and data["turns"] == 0
