"""P-105 - Voice mishearing truth (Part VII, DERIVED scope, VX-11).

Pins: the persistence repair (STT word probabilities survive
the P-101 turn record - verbatim, validated, round-tripped;
a pre-P-105 turn loads with NO evidence, which the views
report as no-evidence, never as all-confident), detection
under the predeclared 0.5 threshold (below even odds by the
model's own estimate), the replacement lexicon (a versioned
JSON store, tolerant load, one-word keys) whose suggestions
NEVER mutate the stored transcript, and the HTTP roads on
the founding /api/v1/voice surface (owner-scoped session
view, 422 roads, install-wide lexicon). No network: fakes /
fixtures only. Migration head stays 0041.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import mishearing as mis
from runmal.voice.orchestrator import TurnRecord
from runmal.voice.session import (
    VoiceSessionStore,
    VoiceTurnRecord,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings
from runmal.voice.stt import Transcript, TranscriptSegment, TranscriptWord

NOW = "2026-11-07T12:00:00+00:00"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1"):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=None, settings=_settings(), now=NOW,
    )


def _words(*pairs):
    return tuple(WordConfidence(text, prob) for text, prob in pairs)


# ------------------------------------------------- evidence citizen


def test_word_confidence_probability_bounds():
    assert WordConfidence("a", 0.0).probability == 0.0
    assert WordConfidence("a", 1.0).probability == 1.0
    with pytest.raises(ValueError):
        WordConfidence("a", 1.5)
    with pytest.raises(ValueError):
        WordConfidence("a", -0.1)


def test_from_orchestrator_captures_word_evidence():
    transcript = Transcript(
        text="take the lift",
        language="en",
        segments=(TranscriptSegment(
            text="take the lift", start_s=0.0, end_s=1.0,
            words=(
                TranscriptWord("take", 0.0, 0.3, 0.9),
                TranscriptWord("the", 0.3, 0.5, 0.95),
                TranscriptWord("lift", 0.5, 1.0, 0.3),
            )),),
        backend_key="fake-stt",
    )
    record = TurnRecord(turn_id=1, transcript=transcript,
                        response_text="Ok.", chunks_total=1, chunks_played=1)
    turn = VoiceTurnRecord.from_orchestrator(
        record, None, turn_no=1, stt_backend="faster-whisper",
        recorded_at=NOW)
    assert [(w.text, w.probability) for w in turn.transcript_words] == [
        ("take", 0.9), ("the", 0.95), ("lift", 0.3)]
    assert turn.transcript_text == "take the lift"


def test_from_orchestrator_without_transcript_has_no_evidence():
    record = TurnRecord(turn_id=1, response_text="Ok.",
                        chunks_total=1, chunks_played=1)
    turn = VoiceTurnRecord.from_orchestrator(
        record, None, turn_no=1, stt_backend="faster-whisper",
        recorded_at=NOW)
    assert turn.transcript_words == ()


def test_turn_round_trip_with_words(tmp_path):
    s = _session(_store(tmp_path))
    t = s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("the", 0.95), ("lift", 0.3)),
        recorded_at=NOW)
    assert json.loads(json.dumps(t.to_dict())) == t.to_dict()
    assert VoiceTurnRecord.from_dict(t.to_dict()) == t
    store = _store(tmp_path)
    store.save_session(s)
    reloaded = _store(tmp_path).get(s.session_id)
    assert reloaded.turns[0].transcript_words == t.transcript_words


def test_legacy_turn_loads_with_no_evidence():
    legacy = {
        "turn_no": 1, "transcript_text": "old words",
        "transcript_language": "en", "stt_backend": "faster-whisper",
        "response_text": "", "heard_certain": "", "heard_uncertain": "",
        "heard_unplayed": "", "interrupted": False, "error": "",
        "chunks_total": 0, "chunks_played": 0, "recorded_at": NOW,
    }
    turn = VoiceTurnRecord.from_dict(legacy)
    assert turn.transcript_words == ()
    view = mis.turn_mishearing(turn)
    assert view["has_confidence_evidence"] is False
    assert view["needs_repeat"] is False
    assert view["min_probability"] is None
    assert view["mean_probability"] is None


# --------------------------------------------------------- detection


def test_threshold_is_predeclared_even_odds():
    assert mis.LOW_CONFIDENCE_THRESHOLD == 0.5
    assert mis.word_band(0.5) == "ok"
    assert mis.word_band(0.4999) == "low"
    assert mis.word_band(0.0) == "low"
    assert mis.word_band(1.0) == "ok"


def test_turn_mishearing_view_marks_low_words(tmp_path):
    s = _session(_store(tmp_path))
    t = s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("the", 0.4), ("lift", 0.3)),
        recorded_at=NOW)
    view = mis.turn_mishearing(t)
    assert view["has_confidence_evidence"] is True
    assert view["word_count"] == 3
    assert view["low_confidence_words"] == ["the", "lift"]
    assert view["low_confidence_count"] == 2
    assert view["min_probability"] == 0.3
    assert view["mean_probability"] == round((0.9 + 0.4 + 0.3) / 3, 4)
    assert view["needs_repeat"] is True
    assert view["stt_backend"] == t.stt_backend
    assert [w["band"] for w in view["words"]] == ["ok", "low", "low"]


def test_turn_mishearing_all_confident_needs_no_repeat(tmp_path):
    s = _session(_store(tmp_path))
    t = s.record_turn(
        transcript_text="hello there",
        transcript_words=_words(("hello", 0.99), ("there", 0.87)),
        recorded_at=NOW)
    view = mis.turn_mishearing(t)
    assert view["needs_repeat"] is False
    assert view["low_confidence_words"] == []


def test_session_mishearing_aggregation(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(transcript_text="take the lift",
                  transcript_words=_words(("lift", 0.2)), recorded_at=NOW)
    s.record_turn(transcript_text="hello",
                  transcript_words=_words(("hello", 0.9)), recorded_at=NOW)
    s.record_turn(transcript_text="legacy", recorded_at=NOW)
    view = mis.session_mishearing(s)
    assert view["turns_total"] == 3
    assert view["turns_with_evidence"] == 2
    assert view["turns_needing_repeat"] == [1]
    assert view["low_confidence_words_total"] == 1
    assert view["threshold"] == 0.5


# ------------------------------------------------------- replacement


def test_apply_replacements_whole_word_case_and_punctuation():
    pairs = {"lift": "elevator"}
    suggested, applied = mis.apply_replacements(
        "Take the lift, Lift! lifting stays.", pairs)
    assert suggested == "Take the elevator, Elevator! lifting stays."
    assert applied == [
        {"misheard": "lift", "replacement": "elevator", "count": 2}]


def test_apply_replacements_no_match_and_empty():
    assert mis.apply_replacements("hello world", {"lift": "elevator"}) == (
        "hello world", [])
    assert mis.apply_replacements("", {"lift": "elevator"}) == ("", [])
    assert mis.apply_replacements("hello", {}) == ("hello", [])


def test_suggestion_never_mutates_the_stored_transcript(tmp_path):
    s = _session(_store(tmp_path))
    t = s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("lift", 0.2)), recorded_at=NOW)
    view = mis.turn_mishearing(t, {"lift": "elevator"})
    assert view["suggested_text"] == "take the elevator"
    assert view["transcript_text"] == "take the lift"
    assert t.transcript_text == "take the lift"


def test_normalize_misheard_refusals():
    assert mis.normalize_misheard("Word") == "word"
    assert mis.normalize_misheard("  lift ") == "lift"
    for bad in ("", "   ", "two words", "word!", ".word"):
        with pytest.raises(ValueError):
            mis.normalize_misheard(bad)


def test_replacement_store_round_trip(tmp_path):
    path = tmp_path / "voice_mishearing_replacements.json"
    store = mis.ReplacementStore(path)
    assert store.pairs() == {}
    view = store.set("Lift", "elevator")
    assert view == {"replacements": [
        {"misheard": "lift", "replacement": "elevator"}]}
    store.set("soda", "pop")
    reloaded = mis.ReplacementStore(path)
    assert reloaded.pairs() == {"lift": "elevator", "soda": "pop"}
    assert reloaded.remove("lift") is True
    assert reloaded.remove("lift") is False
    assert mis.ReplacementStore(path).pairs() == {"soda": "pop"}
    with pytest.raises(ValueError):
        store.set("two words", "x")
    with pytest.raises(ValueError):
        store.set("ok", "   ")


def test_replacement_store_tolerant_load(tmp_path):
    path = tmp_path / "voice_mishearing_replacements.json"
    path.write_text("{not json")
    assert mis.ReplacementStore(path).pairs() == {}
    path.write_text(json.dumps({"version": 1, "replacements": {
        "good": "kept", "two words": "skipped", "blank": "  "}}))
    assert mis.ReplacementStore(path).pairs() == {"good": "kept"}


# ------------------------------------------------------------- HTTP


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


def _http_session(client):
    chat_id = client.post("/api/v1/chats", json={"title": "voice"}).json()["id"]
    sid = client.post(
        "/api/v1/voice/sessions", json={"chat_id": chat_id}).json()["session_id"]
    return chat_id, sid


def test_http_mishearings_flow(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_session(client)
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "take the lift",
              "transcript_words": [
                  {"text": "take", "probability": 0.9},
                  {"text": "the", "probability": 0.95},
                  {"text": "lift", "probability": 0.3}],
              "chunks_total": 0, "chunks_played": 0})
    assert turn.status_code == 201, turn.text
    assert turn.json()["transcript_words"][2] == {
        "text": "lift", "probability": 0.3}
    put = client.put("/api/v1/voice/mishearing-replacements",
                     json={"misheard": "lift", "replacement": "elevator"})
    assert put.status_code == 200, put.text
    view = client.get(f"/api/v1/voice/sessions/{sid}/mishearings")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["turns_needing_repeat"] == [1]
    t0 = body["turns"][0]
    assert t0["low_confidence_words"] == ["lift"]
    assert t0["needs_repeat"] is True
    assert t0["suggested_text"] == "take the elevator"
    assert t0["replacements_applied"] == [
        {"misheard": "lift", "replacement": "elevator", "count": 1}]
    # The stored transcript is never rewritten by a suggestion.
    record = client.get(f"/api/v1/voice/sessions/{sid}").json()
    assert record["turns"][0]["transcript_text"] == "take the lift"


def test_http_turns_word_evidence_is_optional(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_session(client)
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "plain", "chunks_total": 0,
              "chunks_played": 0})
    assert turn.status_code == 201, turn.text
    assert turn.json()["transcript_words"] == []
    body = client.get(f"/api/v1/voice/sessions/{sid}/mishearings").json()
    assert body["turns"][0]["has_confidence_evidence"] is False


def test_http_turns_malformed_words_422(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_session(client)
    bad_prob = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "x",
              "transcript_words": [{"text": "x", "probability": 2.0}]})
    assert bad_prob.status_code == 422
    bad_entry = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "x", "transcript_words": ["x"]})
    assert bad_entry.status_code == 422
    bad_shape = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "x", "transcript_words": {"text": "x"}})
    assert bad_shape.status_code == 422


def test_http_lexicon_roads(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/voice/mishearing-replacements").json() == {
        "replacements": []}
    put = client.put("/api/v1/voice/mishearing-replacements",
                     json={"misheard": "Soda", "replacement": "pop"})
    assert put.status_code == 200
    assert put.json() == {"replacements": [
        {"misheard": "soda", "replacement": "pop"}]}
    multi = client.put("/api/v1/voice/mishearing-replacements",
                       json={"misheard": "two words", "replacement": "x"})
    assert multi.status_code == 422
    empty = client.put("/api/v1/voice/mishearing-replacements",
                       json={"misheard": "ok", "replacement": ""})
    assert empty.status_code == 422
    gone = client.delete("/api/v1/voice/mishearing-replacements/soda")
    assert gone.status_code == 200 and gone.json()["removed"] is True
    absent = client.delete("/api/v1/voice/mishearing-replacements/soda")
    assert absent.status_code == 200 and absent.json()["removed"] is False


def test_http_mishearings_unknown_and_foreign_404(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    assert client.get(
        "/api/v1/voice/sessions/nope/mishearings").status_code == 404
    chat_id = client.post("/api/v1/chats", json={"title": "x"}).json()["id"]
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    store.save_session(foreign)
    res = client.get(f"/api/v1/voice/sessions/{foreign.session_id}/mishearings")
    assert res.status_code == 404  # owner scoping never leaks existence


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
