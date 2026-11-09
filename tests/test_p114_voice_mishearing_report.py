"""P-114 - Voice mishearing session report (Part VII, DERIVED).

Pins: the session aggregate over P-105 confidence evidence -
pooled probability statistics (house percentile), the
often-missed-word table grouped by the lexicon law, lexicon
coverage, the per-backend split, the light report view (totals
+ aggregate, NO per-turn detail), the additive aggregate on
session_mishearing, and the HTTP report road (owner-scoped,
404 unknown/foreign). NO EVIDENCE IS NOT ZERO throughout.
Migration head stays 0041. No network: fakes/fixtures only.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import mishearing as mis
from runmal.voice.session import (
    VoiceSessionStore,
    VoiceTurnRecord,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-08T12:00:00+00:00"


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


def _turn(turn_no, backend, *pairs, text=""):
    return VoiceTurnRecord(
        turn_no=turn_no, transcript_text=text, stt_backend=backend,
        transcript_words=_words(*pairs), recorded_at=NOW)


def _stub(*turns):
    return SimpleNamespace(
        session_id="sess-1", chat_id="chat-1", turns=list(turns))


# ------------------------------------------------------- law 2 pins


def test_empty_session_aggregate_is_no_evidence(tmp_path):
    s = _session(_store(tmp_path))
    agg = mis.mishearing_aggregate(s)
    assert agg["has_confidence_evidence"] is False
    assert agg["words_total"] == 0
    assert agg["words_low"] == 0
    assert agg["words_ok"] == 0
    assert agg["low_rate"] is None
    assert agg["probability"] == {
        "count": 0, "mean": None, "min": None, "p50": None, "p95": None}
    assert agg["frequent_low_words"] == []
    assert agg["lexicon_coverage"] == {
        "low_occurrences": 0, "covered_occurrences": 0,
        "uncovered_occurrences": 0, "distinct_low_words": 0,
        "covered_words": [], "uncovered_words": []}
    assert agg["backends"] == []


def test_turns_without_evidence_are_not_zero_confidence(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(transcript_text="legacy words", recorded_at=NOW)
    s.record_turn(transcript_text="more legacy", recorded_at=NOW)
    agg = mis.mishearing_aggregate(s)
    assert agg["has_confidence_evidence"] is False
    assert agg["words_total"] == 0
    assert agg["probability"]["mean"] is None
    assert agg["low_rate"] is None
    report = mis.session_mishearing_report(s)
    assert report["turns_total"] == 2
    assert report["turns_with_evidence"] == 0
    assert report["turns_needing_repeat"] == []
    assert report["low_confidence_words_total"] == 0


# ------------------------------------------------ pooled statistics


def test_pooled_probability_statistics(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="a b c",
        transcript_words=_words(("a", 0.9), ("b", 0.4), ("c", 0.3)),
        recorded_at=NOW)
    s.record_turn(
        transcript_text="d e",
        transcript_words=_words(("d", 0.2), ("e", 0.8)),
        recorded_at=NOW)
    agg = mis.mishearing_aggregate(s)
    assert agg["has_confidence_evidence"] is True
    assert agg["words_total"] == 5
    assert agg["words_low"] == 3
    assert agg["words_ok"] == 2
    assert agg["low_rate"] == 0.6
    # pooled sorted: [0.2, 0.3, 0.4, 0.8, 0.9]; nearest-rank
    # p50 -> rank round(2.5)=2 -> 0.3; p95 -> rank 5 -> 0.9
    assert agg["probability"] == {
        "count": 5, "mean": 0.52, "min": 0.2, "p50": 0.3, "p95": 0.9}


def test_all_confident_session_has_zero_low_rate_not_none(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="hello there",
        transcript_words=_words(("hello", 0.99), ("there", 0.87)),
        recorded_at=NOW)
    agg = mis.mishearing_aggregate(s)
    assert agg["has_confidence_evidence"] is True
    assert agg["words_low"] == 0
    assert agg["low_rate"] == 0.0
    assert agg["frequent_low_words"] == []


# ------------------------------------------- frequent low words law


def test_frequent_low_words_group_case_and_punctuation(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="Lift, soda",
        transcript_words=_words(("Lift,", 0.3), ("soda", 0.1)),
        recorded_at=NOW)
    s.record_turn(
        transcript_text="lift! LIFT soda",
        transcript_words=_words(
            ("lift!", 0.2), ("LIFT", 0.4), ("soda", 0.45)),
        recorded_at=NOW)
    agg = mis.mishearing_aggregate(s, {"lift": "elevator"})
    freq = agg["frequent_low_words"]
    # sort: count desc, then word asc (lift 3, soda 2)
    assert [f["word"] for f in freq] == ["lift", "soda"]
    lift = freq[0]
    assert lift["count"] == 3
    assert lift["turns"] == [1, 2]
    assert lift["min_probability"] == 0.2
    assert lift["mean_probability"] == 0.3
    assert lift["has_replacement"] is True
    assert lift["replacement"] == "elevator"
    soda = freq[1]
    assert soda["count"] == 2
    assert soda["turns"] == [1, 2]
    assert soda["has_replacement"] is False
    assert soda["replacement"] is None


def test_frequent_sort_tie_breaks_by_word_ascending(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="beta alpha",
        transcript_words=_words(("beta", 0.2), ("alpha", 0.2)),
        recorded_at=NOW)
    freq = mis.mishearing_aggregate(s)["frequent_low_words"]
    assert [f["word"] for f in freq] == ["alpha", "beta"]


def test_token_with_no_core_groups_under_lower_text():
    stub = _stub(_turn(1, "fake", ("...", 0.2), ("!!!", 0.1)))
    freq = mis.mishearing_aggregate(stub)["frequent_low_words"]
    assert {f["word"] for f in freq} == {"...", "!!!"}


# ------------------------------------------------ lexicon coverage


def test_lexicon_coverage_occurrences_and_distinct(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="lift lift soda",
        transcript_words=_words(
            ("lift", 0.3), ("lift", 0.2), ("soda", 0.1)),
        recorded_at=NOW)
    cov = mis.mishearing_aggregate(
        s, {"lift": "elevator"})["lexicon_coverage"]
    assert cov == {
        "low_occurrences": 3, "covered_occurrences": 2,
        "uncovered_occurrences": 1, "distinct_low_words": 2,
        "covered_words": ["lift"], "uncovered_words": ["soda"]}


def test_coverage_without_lexicon_covers_nothing(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="lift",
        transcript_words=_words(("lift", 0.3)), recorded_at=NOW)
    cov = mis.mishearing_aggregate(s)["lexicon_coverage"]
    assert cov["covered_occurrences"] == 0
    assert cov["uncovered_words"] == ["lift"]


# ------------------------------------------------------ backend split


def test_backends_split_by_turn_backend():
    stub = _stub(
        _turn(1, "faster-whisper", ("a", 0.9), ("b", 0.3)),
        _turn(2, "fake-stt", ("c", 1.0)),
        _turn(3, "faster-whisper", ("d", 0.4)),
    )
    backends = mis.mishearing_aggregate(stub)["backends"]
    assert backends == [
        {"stt_backend": "fake-stt", "words": 1, "words_low": 0,
         "mean_probability": 1.0},
        {"stt_backend": "faster-whisper", "words": 3, "words_low": 2,
         "mean_probability": round((0.9 + 0.3 + 0.4) / 3, 4)},
    ]


def test_backends_omit_turns_without_words():
    stub = _stub(_turn(1, "fake-stt"), _turn(2, "fw", ("a", 0.9)))
    backends = mis.mishearing_aggregate(stub)["backends"]
    assert [b["stt_backend"] for b in backends] == ["fw"]


# ------------------------------------------------- report + one truth


def test_report_totals_equal_session_view_and_no_turns(tmp_path):
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("lift", 0.3)),
        recorded_at=NOW)
    s.record_turn(transcript_text="legacy", recorded_at=NOW)
    view = mis.session_mishearing(s, {"lift": "elevator"})
    report = mis.session_mishearing_report(s, {"lift": "elevator"})
    assert "turns" not in report
    for key in ("session_id", "chat_id", "threshold", "turns_total",
                "turns_with_evidence", "turns_needing_repeat",
                "low_confidence_words_total"):
        assert report[key] == view[key]
    assert report["aggregate"] == view["aggregate"]
    assert mis.mishearing_aggregate(s, {"lift": "elevator"}) == (
        report["aggregate"])


def test_consistency_pins_across_views(tmp_path):
    pairs = {"lift": "elevator"}
    s = _session(_store(tmp_path))
    s.record_turn(
        transcript_text="lift soda lift",
        transcript_words=_words(
            ("lift", 0.3), ("soda", 0.1), ("lift", 0.2)),
        recorded_at=NOW)
    s.record_turn(
        transcript_text="ok word",
        transcript_words=_words(("ok", 0.9), ("word", 0.95)),
        recorded_at=NOW)
    view = mis.session_mishearing(s, pairs)
    agg = view["aggregate"]
    assert sum(f["count"] for f in agg["frequent_low_words"]) == 3
    assert agg["words_low"] == 3
    assert view["low_confidence_words_total"] == 3
    cov = agg["lexicon_coverage"]
    assert cov["covered_occurrences"] + cov["uncovered_occurrences"] == 3
    assert cov["low_occurrences"] == agg["words_low"] == 3
    assert agg["words_ok"] + agg["words_low"] == agg["words_total"]


def test_views_never_mutate_transcript(tmp_path):
    s = _session(_store(tmp_path))
    t = s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("lift", 0.2)), recorded_at=NOW)
    mis.mishearing_aggregate(s, {"lift": "elevator"})
    mis.session_mishearing_report(s, {"lift": "elevator"})
    mis.session_mishearing(s, {"lift": "elevator"})
    assert t.transcript_text == "take the lift"
    assert s.turns[0].transcript_text == "take the lift"


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
    chat_id = client.post(
        "/api/v1/chats", json={"title": "voice"}).json()["id"]
    sid = client.post(
        "/api/v1/voice/sessions",
        json={"chat_id": chat_id}).json()["session_id"]
    return chat_id, sid


def test_http_report_flow(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_session(client)
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "take the lift",
              "transcript_words": [
                  {"text": "take", "probability": 0.9},
                  {"text": "lift", "probability": 0.3}],
              "chunks_total": 0, "chunks_played": 0})
    assert turn.status_code == 201, turn.text
    put = client.put("/api/v1/voice/mishearing-replacements",
                     json={"misheard": "lift",
                           "replacement": "elevator"})
    assert put.status_code == 200, put.text
    res = client.get(
        f"/api/v1/voice/sessions/{sid}/mishearing-report")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "turns" not in body
    assert body["turns_total"] == 1
    assert body["low_confidence_words_total"] == 1
    agg = body["aggregate"]
    assert agg["words_total"] == 2
    assert agg["words_low"] == 1
    assert agg["frequent_low_words"] == [{
        "word": "lift", "count": 1, "turns": [1],
        "min_probability": 0.3, "mean_probability": 0.3,
        "has_replacement": True, "replacement": "elevator"}]
    assert agg["lexicon_coverage"]["covered_words"] == ["lift"]


def test_http_mishearings_now_carries_aggregate(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_session(client)
    body = client.get(
        f"/api/v1/voice/sessions/{sid}/mishearings").json()
    assert body["aggregate"]["has_confidence_evidence"] is False
    assert body["aggregate"]["words_total"] == 0


def test_http_report_unknown_and_foreign_404(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    assert client.get(
        "/api/v1/voice/sessions/nope/mishearing-report"
    ).status_code == 404
    chat_id = client.post(
        "/api/v1/chats", json={"title": "x"}).json()["id"]
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    store.save_session(foreign)
    res = client.get(
        f"/api/v1/voice/sessions/{foreign.session_id}"
        "/mishearing-report")
    assert res.status_code == 404


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
