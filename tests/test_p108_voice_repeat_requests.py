"""P-108 - Voice repeat-request signal (Part VII, DERIVED scope, VX-11).

Pins: the host half of VX-11's "ask the user to repeat" as
DATA only - pending repeat requests derived from P-105's
mishearing truth (the single source: a turn is a request
exactly when turn_mishearing says needs_repeat), the
durable acknowledgement lifecycle (first acknowledgement
wins; clearing returns the request to pending; detection
truth is never changed by handling), the owner-scoped
HTTP roads on the founding /api/v1/voice surface (404 for
unknown/foreign, 422 when acknowledging a turn with no
request), and the no-dialogue law (no chat message is
created, no responder is touched, the stored transcript
is never rewritten). No network: fixtures only. Migration
head stays 0041.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import mishearing as mis
from runmal.voice import repeat_requests as rr
from runmal.voice.session import (
    VoiceSessionStore,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-08T12:00:00+00:00"
LATER = "2026-11-08T12:05:00+00:00"


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


def _doubted_session(store):
    """Turn 1 doubted (lift), turn 2 clean, turn 3 no evidence."""
    s = _session(store)
    s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("the", 0.95), ("lift", 0.3)),
        recorded_at=NOW)
    s.record_turn(
        transcript_text="all clear here",
        transcript_words=_words(("all", 0.9), ("clear", 0.95), ("here", 0.99)),
        recorded_at=NOW)
    s.record_turn(transcript_text="no evidence", recorded_at=NOW)
    return store.save_session(s)


# ------------------------------------------------------- derivation


def test_request_derives_from_p105_truth(tmp_path):
    s = _doubted_session(_store(tmp_path))
    view = rr.session_repeat_requests(s)
    assert view["session_id"] == s.session_id
    assert view["chat_id"] == "chat-1"
    assert view["threshold"] == mis.LOW_CONFIDENCE_THRESHOLD == 0.5
    assert view["has_pending"] is True
    assert view["pending_count"] == 1
    assert view["acknowledged_count"] == 0
    assert view["pending_turns"] == [1]
    (request,) = view["requests"]
    assert request["turn_no"] == 1
    assert request["state"] == "pending"
    assert request["low_confidence_words"] == ["lift"]
    assert request["low_confidence_count"] == 1
    assert request["word_count"] == 3
    assert request["min_probability"] == 0.3
    assert request["acknowledged_at"] == ""
    assert request["transcript_text"] == "take the lift"


def test_signal_agrees_with_p105_view(tmp_path):
    s = _doubted_session(_store(tmp_path))
    truth = mis.session_mishearing(s)
    view = rr.session_repeat_requests(s)
    assert [r["turn_no"] for r in view["requests"]] == (
        truth["turns_needing_repeat"])
    for request in view["requests"]:
        source = truth["turns"][request["turn_no"] - 1]
        assert request["low_confidence_words"] == (
            source["low_confidence_words"])
        assert request["suggested_text"] == source["suggested_text"]


def test_no_evidence_turn_is_never_a_request(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.record_turn(transcript_text="plain", recorded_at=NOW)
    store.save_session(s)
    assert rr.turn_repeat_request(s.turns[0]) is None
    view = rr.session_repeat_requests(s)
    assert view["requests"] == [] and view["has_pending"] is False


def test_clean_turn_is_not_a_request(tmp_path):
    s = _doubted_session(_store(tmp_path))
    assert rr.turn_repeat_request(s.turns[1]) is None


def test_suggestion_is_a_view_transcript_untouched(tmp_path):
    s = _doubted_session(_store(tmp_path))
    pairs = {"lift": "elevator"}
    request = rr.turn_repeat_request(s.turns[0], pairs)
    assert request["suggested_text"] == "take the elevator"
    assert request["replacements_applied"] == [
        {"misheard": "lift", "replacement": "elevator", "count": 1}]
    assert s.turns[0].transcript_text == "take the lift"


# ------------------------------------------------- acknowledgement


def test_acknowledge_moves_request_to_acknowledged(tmp_path):
    s = _doubted_session(_store(tmp_path))
    store = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    store.acknowledge(s.session_id, 1, "asked in UI", at=NOW)
    view = rr.session_repeat_requests(s, store=store)
    assert view["has_pending"] is False
    assert view["pending_turns"] == []
    assert view["acknowledged_count"] == 1
    (request,) = view["requests"]
    assert request["state"] == "acknowledged"
    assert request["acknowledged_at"] == NOW
    assert request["acknowledged_note"] == "asked in UI"


def test_first_acknowledgement_wins(tmp_path):
    store = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    first = store.acknowledge("sess", 1, "first host", at=NOW)
    second = store.acknowledge("sess", 1, "second host", at=LATER)
    assert second == first
    assert second["acknowledged_at"] == NOW
    assert second["note"] == "first host"


def test_clear_returns_request_to_pending(tmp_path):
    s = _doubted_session(_store(tmp_path))
    store = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    store.acknowledge(s.session_id, 1, at=NOW)
    assert store.clear(s.session_id, 1) is True
    assert store.clear(s.session_id, 1) is False  # absence is not an error
    view = rr.session_repeat_requests(s, store=store)
    assert view["pending_turns"] == [1]


def test_acknowledgement_never_changes_detection(tmp_path):
    s = _doubted_session(_store(tmp_path))
    store = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    before = mis.session_mishearing(s)
    store.acknowledge(s.session_id, 1, at=NOW)
    store.clear(s.session_id, 1)
    after = mis.session_mishearing(s)
    assert before == after
    assert s.turns[0].transcript_text == "take the lift"


def test_ack_store_round_trip_and_tolerant_load(tmp_path):
    path = tmp_path / rr.ACK_FILENAME
    store = rr.AcknowledgementStore(path)
    store.acknowledge("sess-a", 2, "ui", at=NOW)
    store.acknowledge("sess-a", 5, at=LATER)
    reloaded = rr.AcknowledgementStore(path)
    assert reloaded.get("sess-a", 2) == {
        "acknowledged_at": NOW, "note": "ui"}
    assert reloaded.get("sess-a", 5)["acknowledged_at"] == LATER
    assert reloaded.get("sess-a", 9) is None
    doc = json.loads(path.read_text())
    assert doc["version"] == rr.ACK_VERSION
    path.write_text("{corrupt")
    assert rr.AcknowledgementStore(path).acks_for("sess-a") == {}
    path.write_text(json.dumps({"acknowledgements": {
        "sess-b": {"x": {"acknowledged_at": NOW},
                   "3": "not-a-dict",
                   "4": {"acknowledged_at": NOW, "note": 7}}}}))
    tolerant = rr.AcknowledgementStore(path)
    assert tolerant.get("sess-b", 4) == {
        "acknowledged_at": NOW, "note": "7"}
    assert tolerant.acks_for("sess-b").keys() == {4}


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


def _http_doubted_session(client):
    chat_id = client.post("/api/v1/chats", json={"title": "voice"}).json()["id"]
    sid = client.post(
        "/api/v1/voice/sessions", json={"chat_id": chat_id}).json()["session_id"]
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "take the lift",
              "transcript_words": [
                  {"text": "take", "probability": 0.9},
                  {"text": "the", "probability": 0.95},
                  {"text": "lift", "probability": 0.3}],
              "chunks_total": 0, "chunks_played": 0})
    assert turn.status_code == 201, turn.text
    return chat_id, sid


def test_http_signal_flow(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_doubted_session(client)
    view = client.get(f"/api/v1/voice/sessions/{sid}/repeat-requests")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["has_pending"] is True and body["pending_turns"] == [1]
    ack = client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge",
        json={"note": "prompt shown"})
    assert ack.status_code == 200, ack.text
    body = ack.json()
    assert body["has_pending"] is False and body["acknowledged_count"] == 1
    assert body["requests"][0]["acknowledged_note"] == "prompt shown"
    assert body["requests"][0]["acknowledged_at"] != ""
    # Idempotent: a second acknowledgement changes nothing.
    again = client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge",
        json={"note": "second host"})
    assert again.status_code == 200
    assert again.json()["requests"][0]["acknowledged_note"] == "prompt shown"
    assert again.json()["requests"][0]["acknowledged_at"] == (
        body["requests"][0]["acknowledged_at"])
    cleared = client.delete(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge")
    assert cleared.status_code == 200 and cleared.json()["removed"] is True
    assert cleared.json()["pending_turns"] == [1]
    absent = client.delete(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge")
    assert absent.status_code == 200 and absent.json()["removed"] is False


def test_http_acknowledge_without_request_422(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_doubted_session(client)
    clean = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "all clear",
              "transcript_words": [
                  {"text": "all", "probability": 0.9},
                  {"text": "clear", "probability": 0.95}],
              "chunks_total": 0, "chunks_played": 0})
    assert clean.status_code == 201, clean.text
    assert client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/2/acknowledge",
        json={}).status_code == 422  # clean turn: no request exists
    assert client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/99/acknowledge",
        json={}).status_code == 422  # no such turn


def test_http_signal_creates_no_chat_message(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id, sid = _http_doubted_session(client)
    before = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    client.get(f"/api/v1/voice/sessions/{sid}/repeat-requests")
    client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge",
        json={"note": "host acted"})
    after = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert after == before  # the signal is data, never dialogue
    record = client.get(f"/api/v1/voice/sessions/{sid}").json()
    assert record["turns"][0]["transcript_text"] == "take the lift"
    assert record["turns"][0]["response_text"] == ""


def test_http_repeat_requests_unknown_and_foreign_404(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    base = "/api/v1/voice/sessions/nope/repeat-requests"
    assert client.get(base).status_code == 404
    assert client.post(base + "/1/acknowledge", json={}).status_code == 404
    assert client.delete(base + "/1/acknowledge").status_code == 404
    chat_id = client.post("/api/v1/chats", json={"title": "x"}).json()["id"]
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    foreign.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("lift", 0.3)), recorded_at=NOW)
    store.save_session(foreign)
    res = client.get(
        f"/api/v1/voice/sessions/{foreign.session_id}/repeat-requests")
    assert res.status_code == 404  # owner scoping never leaks existence


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
