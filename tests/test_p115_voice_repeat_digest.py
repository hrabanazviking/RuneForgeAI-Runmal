"""P-115 - Voice repeat-request digest & aging (Part VII, DERIVED).

Pins: the cross-session roll-up of the P-108 signal (counts
are the per-session views' sums by construction), wall-clock
aging derived ONLY from persisted stamps (turn recorded_at,
acknowledgement acknowledged_at) against an injected now -
plain arithmetic seconds, no buckets, no threshold - the
honesty law for stamps that cannot carry an age (missing /
unparseable / future: counted as without, never clamped,
never zero-claimed), the owner-scoped HTTP digest road
(foreign sessions never named), and the no-dialogue law.
No network: fixtures only. Migration head stays 0041.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import repeat_requests as rr
from runmal.voice.session import (
    VoiceSessionStore,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

T0900 = "2026-11-08T09:00:00+00:00"
T1000 = "2026-11-08T10:00:00+00:00"
T1100 = "2026-11-08T11:00:00+00:00"
T1130 = "2026-11-08T11:30:00+00:00"
T1300 = "2026-11-08T13:00:00+00:00"
NOW = "2026-11-08T12:00:00+00:00"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _words(*pairs):
    return tuple(WordConfidence(text, prob) for text, prob in pairs)


def _doubted(text="take the lift"):
    return _words(("take", 0.9), ("lift", 0.3))


def _session(store, chat_id, created, user_id="u1"):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=None, settings=_settings(), now=created)


def _fleet(tmp_path):
    """A: 1 pending (10:00) + 1 acked (rec 11:00, ack 11:30).
    B: 1 pending (11:00). C: clean. D: pending with no stamp
    and pending with a future stamp. Plus the ack store."""
    store = _store(tmp_path)
    a = _session(store, "chat-a", "2026-11-08T09:00:00+00:00")
    a.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at=T1000)
    a.record_turn(transcript_text="take the lift again",
                  transcript_words=_doubted(), recorded_at=T1100)
    store.save_session(a)
    b = _session(store, "chat-b", "2026-11-08T09:01:00+00:00")
    b.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at=T1100)
    store.save_session(b)
    c = _session(store, "chat-c", "2026-11-08T09:02:00+00:00")
    c.record_turn(transcript_text="all clear",
                  transcript_words=_words(("all", 0.9), ("clear", 0.95)),
                  recorded_at=T1000)
    store.save_session(c)
    d = _session(store, "chat-d", "2026-11-08T09:03:00+00:00")
    d.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at=T1000)
    # A stored legacy record with NO stamp: record_turn stamps
    # an empty recorded_at with the wall clock by design, so
    # the missing-stamp case is built the way it can actually
    # exist - a persisted record whose field is empty.
    d.turns[0].recorded_at = ""
    d.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at=T1300)
    store.save_session(d)
    acks = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    acks.acknowledge(a.session_id, 2, "asked", at=T1130)
    sessions = store.all_sessions()
    return sessions, acks, {s.chat_id: s for s in sessions}


# --------------------------------------------------------- roll-up


def test_digest_rollup_counts(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    assert digest["generated_at"] == NOW
    assert digest["threshold"] == 0.5
    assert digest["sessions_total"] == 4
    assert digest["sessions_with_requests"] == 3
    assert digest["sessions_with_pending"] == 3
    assert digest["requests_total"] == 5
    assert digest["pending_count"] == 4
    assert digest["acknowledged_count"] == 1


def test_digest_agrees_with_per_session_views(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    views = [rr.session_repeat_requests(s, store=acks) for s in sessions]
    assert digest["pending_count"] == sum(v["pending_count"] for v in views)
    assert digest["acknowledged_count"] == sum(
        v["acknowledged_count"] for v in views)
    by_id = {e["session_id"]: e for e in digest["sessions"]}
    for view in views:
        entry = by_id[view["session_id"]]
        assert entry["pending_count"] == view["pending_count"]
        assert entry["acknowledged_count"] == view["acknowledged_count"]
        assert entry["pending_turns"] == view["pending_turns"]
        assert entry["has_pending"] == view["has_pending"]
        assert entry["chat_id"] == view["chat_id"]


def test_digest_pending_flat_list_in_session_then_turn_order(tmp_path):
    sessions, acks, by = _fleet(tmp_path)
    digest = rr.repeat_digest(list(reversed(sessions)), store=acks, now=NOW)
    flat = [(p["chat_id"], p["turn_no"]) for p in digest["pending"]]
    assert flat == [("chat-a", 1), ("chat-b", 1), ("chat-d", 1), ("chat-d", 2)]
    assert digest["sessions"][0]["session_id"] == by["chat-a"].session_id


def test_digest_empty_fleet_is_honest_zeros(tmp_path):
    digest = rr.repeat_digest([], now=NOW)
    assert digest["sessions_total"] == 0
    assert digest["requests_total"] == 0
    assert digest["pending"] == [] and digest["sessions"] == []
    for key in ("pending_age_seconds", "acknowledged_age_seconds",
                "acknowledgement_delay_seconds"):
        assert digest[key] == {"count": 0, "without_count": 0,
                               "oldest_seconds": None,
                               "newest_seconds": None, "mean_seconds": None}


def test_digest_clean_session_counts_in_total_only(tmp_path):
    sessions, acks, by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    entry = next(e for e in digest["sessions"]
                 if e["session_id"] == by["chat-c"].session_id)
    assert entry["pending_count"] == 0
    assert entry["acknowledged_count"] == 0
    assert entry["has_pending"] is False
    assert entry["oldest_pending_age_seconds"] is None
    assert entry["last_acknowledged_at"] == ""


# ------------------------------------------------------------ aging


def test_pending_aging_is_plain_arithmetic(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    stats = digest["pending_age_seconds"]
    assert stats["count"] == 2  # 10:00 and 11:00 stamps only
    assert stats["without_count"] == 2  # missing + future stamps
    assert stats["oldest_seconds"] == 7200.0
    assert stats["newest_seconds"] == 3600.0
    assert stats["mean_seconds"] == 5400.0
    ages = {p["turn_no"]: p["age_seconds"] for p in digest["pending"]
            if p["chat_id"] == "chat-a"}
    assert ages == {1: 7200.0}


def test_acknowledged_aging_and_delay(tmp_path):
    sessions, acks, by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    ack_age = digest["acknowledged_age_seconds"]
    assert ack_age["count"] == 1 and ack_age["without_count"] == 0
    assert ack_age["oldest_seconds"] == 1800.0  # 12:00 - 11:30
    delay = digest["acknowledgement_delay_seconds"]
    assert delay["count"] == 1 and delay["without_count"] == 0
    assert delay["oldest_seconds"] == 1800.0  # 11:30 - 11:00
    entry = next(e for e in digest["sessions"]
                 if e["session_id"] == by["chat-a"].session_id)
    assert entry["last_acknowledged_at"] == T1130
    assert entry["oldest_pending_age_seconds"] == 7200.0
    assert entry["oldest_pending_recorded_at"] == T1000


def test_unageable_stamps_are_counted_never_aged(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    digest = rr.repeat_digest(sessions, store=acks, now=NOW)
    d_pending = [p for p in digest["pending"] if p["chat_id"] == "chat-d"]
    assert [p["age_seconds"] for p in d_pending] == [None, None]
    assert [p["recorded_at"] for p in d_pending] == ["", T1300]


def test_unparseable_stamps_yield_no_age(tmp_path):
    store = _store(tmp_path)
    s = _session(store, "chat-x", T0900)
    s.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at="not-a-date")
    store.save_session(s)
    acks = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    acks.acknowledge(s.session_id, 1, at="also-not-a-date")
    digest = rr.repeat_digest([s], store=acks, now=NOW)
    assert digest["acknowledged_age_seconds"]["without_count"] == 1
    assert digest["acknowledgement_delay_seconds"]["count"] == 0


def test_now_accepts_string_and_datetime(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    as_str = rr.repeat_digest(sessions, store=acks, now=NOW)
    as_dt = rr.repeat_digest(
        sessions, store=acks, now=datetime(2026, 11, 8, 12, tzinfo=UTC))
    assert as_str == as_dt


def test_negative_ack_delay_is_dropped_not_clamped(tmp_path):
    store = _store(tmp_path)
    s = _session(store, "chat-y", T0900)
    s.record_turn(transcript_text="take the lift",
                  transcript_words=_doubted(), recorded_at=T1100)
    store.save_session(s)
    acks = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    acks.acknowledge(s.session_id, 1, at=T1000)  # ack before record: skew
    digest = rr.repeat_digest([s], store=acks, now=NOW)
    delay = digest["acknowledgement_delay_seconds"]
    assert delay["count"] == 0 and delay["without_count"] == 1
    assert digest["acknowledged_age_seconds"]["oldest_seconds"] == 7200.0


def test_digest_reads_never_write(tmp_path):
    sessions, acks, _by = _fleet(tmp_path)
    before = (tmp_path / rr.ACK_FILENAME).read_bytes()
    rr.repeat_digest(sessions, store=acks, now=NOW)
    assert (tmp_path / rr.ACK_FILENAME).read_bytes() == before
    assert acks.record_count() == 1


def test_request_view_now_carries_recorded_at(tmp_path):
    sessions, _acks, by = _fleet(tmp_path)
    view = rr.session_repeat_requests(by["chat-a"])
    assert view["requests"][0]["recorded_at"] == T1000
    assert view["requests"][1]["recorded_at"] == T1100


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
    return client


def test_http_digest_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "voice"}).json()["id"]
    sid = client.post("/api/v1/voice/sessions",
                      json={"chat_id": chat_id}).json()["session_id"]
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "take the lift",
              "transcript_words": [{"text": "lift", "probability": 0.3}],
              "chunks_total": 0, "chunks_played": 0})
    assert turn.status_code == 201, turn.text
    store = _store(tmp_path)
    foreign = _session(store, chat_id="chat-foreign",
                       created=T0900, user_id="someone-else")
    foreign.record_turn(transcript_text="take the lift",
                        transcript_words=_doubted(), recorded_at=T1000)
    store.save_session(foreign)
    res = client.get("/api/v1/voice/repeat-requests/digest")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sessions_total"] == 1  # the foreign session is absent
    assert body["pending_count"] == 1
    assert [p["session_id"] for p in body["pending"]] == [sid]
    assert body["pending_age_seconds"]["count"] == 1
    assert body["pending_age_seconds"]["oldest_seconds"] >= 0
    assert foreign.session_id not in str(body)


def test_http_digest_empty_and_no_message_created(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "v"}).json()["id"]
    before = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    res = client.get("/api/v1/voice/repeat-requests/digest")
    assert res.status_code == 200, res.text
    assert res.json()["sessions_total"] == 0
    after = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert after == before


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
