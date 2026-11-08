"""P-111 - Voice repeat-acknowledgement housekeeping (Part VII,
DERIVED scope, VX-11 follow-through).

Pins: the closing of P-108's recorded limitation - the
acknowledgement records of a deleted session are inert
(they name a session that no longer exists and drive
nothing) and, before this slice, no road could ever
remove them. The housekeeping truth is a pure read that
splits the store into live and inert and names the inert
session ids; pruning removes inert records ONLY (a live
session's records survive verbatim, acknowledgement
state included); a no-op prune leaves the store document
byte-identical; dropping a chat's sessions prunes the
records that act orphans in the same act and reports the
count. Detection truth (P-105) is never touched and no
chat message is created by any road here. Migration head
stays 0041.
"""

from __future__ import annotations

import json

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


def _ack_store(tmp_path):
    return rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)


def _seeded_store(tmp_path):
    """live-a: 2 records; ghost-b: 1; ghost-a: 2 (inert)."""
    store = _ack_store(tmp_path)
    store.acknowledge("live-a", 1, "ui host", at=NOW)
    store.acknowledge("live-a", 3, at=NOW)
    store.acknowledge("ghost-b", 2, at=NOW)
    store.acknowledge("ghost-a", 1, "old host", at=LATER)
    store.acknowledge("ghost-a", 4, at=LATER)
    return store


# ------------------------------------------------------- pure views


def test_housekeeping_view_empty_store(tmp_path):
    view = rr.housekeeping_view(_ack_store(tmp_path), {"live-a"})
    assert view == {
        "acknowledged_sessions": 0,
        "acknowledged_records": 0,
        "live_acknowledged_sessions": 0,
        "inert_sessions": 0,
        "inert_records": 0,
        "inert_session_ids": [],
    }


def test_housekeeping_view_splits_live_and_inert(tmp_path):
    store = _seeded_store(tmp_path)
    view = rr.housekeeping_view(store, {"live-a"})
    assert view["acknowledged_sessions"] == 3
    assert view["acknowledged_records"] == 5
    assert view["live_acknowledged_sessions"] == 1
    assert view["inert_sessions"] == 2
    assert view["inert_records"] == 3
    # Inert ids are named, sorted, so a host sees exactly
    # what a prune would remove before calling it.
    assert view["inert_session_ids"] == ["ghost-a", "ghost-b"]


def test_session_ids_and_record_count(tmp_path):
    store = _seeded_store(tmp_path)
    assert store.session_ids() == ["ghost-a", "ghost-b", "live-a"]
    assert store.record_count() == 5
    assert _ack_store(tmp_path).record_count() == 5  # round trip


def test_housekeeping_view_is_a_pure_read(tmp_path):
    store = _seeded_store(tmp_path)
    path = tmp_path / rr.ACK_FILENAME
    before = path.read_bytes()
    rr.housekeeping_view(store, {"live-a"})
    assert path.read_bytes() == before
    assert store.record_count() == 5


# ------------------------------------------------------------ prune


def test_prune_removes_only_inert_records(tmp_path):
    store = _seeded_store(tmp_path)
    removed = store.prune_orphans({"live-a"})
    assert removed == {
        "removed_sessions": ["ghost-a", "ghost-b"],
        "removed_records": 3,
    }
    # Live records survive verbatim - note and stamp alike.
    assert store.get("live-a", 1) == {
        "acknowledged_at": NOW, "note": "ui host"}
    assert store.get("live-a", 3) == {
        "acknowledged_at": NOW, "note": ""}
    assert store.acks_for("ghost-a") == {}
    # The prune persisted: a fresh store sees the same truth.
    reloaded = _ack_store(tmp_path)
    assert reloaded.session_ids() == ["live-a"]
    assert reloaded.record_count() == 2


def test_prune_noop_leaves_document_byte_identical(tmp_path):
    store = _seeded_store(tmp_path)
    path = tmp_path / rr.ACK_FILENAME
    before = path.read_bytes()
    removed = store.prune_orphans({"live-a", "ghost-a", "ghost-b"})
    assert removed == {"removed_sessions": [], "removed_records": 0}
    assert path.read_bytes() == before
    # And on a store whose file does not exist yet, a prune
    # creates nothing.
    empty_path = tmp_path / "sub" / rr.ACK_FILENAME
    empty = rr.AcknowledgementStore(empty_path)
    assert empty.prune_orphans(set())["removed_records"] == 0
    assert not empty_path.exists()


def test_prune_report_carries_before_and_after(tmp_path):
    store = _seeded_store(tmp_path)
    report = rr.prune_inert_acknowledgements(store, {"live-a"})
    assert report["inert_sessions_before"] == 2
    assert report["inert_records_before"] == 3
    assert report["removed_sessions"] == ["ghost-a", "ghost-b"]
    assert report["removed_records"] == 3
    assert report["inert_sessions"] == 0
    assert report["inert_records"] == 0
    assert report["inert_session_ids"] == []
    assert report["acknowledged_sessions"] == 1
    assert report["acknowledged_records"] == 2
    assert report["live_acknowledged_sessions"] == 1


def test_prune_is_idempotent_and_accepts_any_id_iterable(tmp_path):
    store = _seeded_store(tmp_path)
    first = store.prune_orphans(["live-a"])  # a list, not a set
    assert first["removed_records"] == 3
    second = store.prune_orphans(["live-a"])
    assert second == {"removed_sessions": [], "removed_records": 0}
    assert store.record_count() == 2


def test_live_acknowledgement_state_survives_prune(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("the", 0.95), ("lift", 0.3)),
        recorded_at=NOW)
    store.save_session(s)
    acks = _ack_store(tmp_path)
    acks.acknowledge(s.session_id, 1, "asked in UI", at=NOW)
    acks.acknowledge("ghost-session", 1, at=NOW)
    acks.prune_orphans({s.session_id})
    view = rr.session_repeat_requests(s, store=_ack_store(tmp_path))
    assert view["has_pending"] is False
    assert view["acknowledged_count"] == 1
    assert view["requests"][0]["acknowledged_note"] == "asked in UI"


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


def _http_doubted_session(client, title="voice"):
    chat_id = client.post("/api/v1/chats", json={"title": title}).json()["id"]
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
    ack = client.post(
        f"/api/v1/voice/sessions/{sid}/repeat-requests/1/acknowledge",
        json={"note": "prompt shown"})
    assert ack.status_code == 200, ack.text
    return chat_id, sid


def _plant_ghost(tmp_path, session_id="ghost-session", turns=(1, 2)):
    store = _ack_store(tmp_path)
    for turn_no in turns:
        store.acknowledge(session_id, turn_no, "stale host", at=NOW)
    return store


def test_http_housekeeping_view(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    empty = client.get("/api/v1/voice/repeat-requests/housekeeping")
    assert empty.status_code == 200, empty.text
    assert empty.json()["acknowledged_records"] == 0
    assert empty.json()["inert_session_ids"] == []
    _chat_id, _sid = _http_doubted_session(client)
    live = client.get("/api/v1/voice/repeat-requests/housekeeping").json()
    assert live["acknowledged_sessions"] == 1
    assert live["acknowledged_records"] == 1
    assert live["live_acknowledged_sessions"] == 1
    assert live["inert_sessions"] == 0
    _plant_ghost(tmp_path)
    mixed = client.get("/api/v1/voice/repeat-requests/housekeeping").json()
    assert mixed["acknowledged_sessions"] == 2
    assert mixed["acknowledged_records"] == 3
    assert mixed["inert_sessions"] == 1
    assert mixed["inert_records"] == 2
    assert mixed["inert_session_ids"] == ["ghost-session"]


def test_http_prune_removes_inert_only(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _chat_id, sid = _http_doubted_session(client)
    _plant_ghost(tmp_path)
    report = client.post("/api/v1/voice/repeat-requests/housekeeping/prune")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["inert_records_before"] == 2
    assert body["removed_sessions"] == ["ghost-session"]
    assert body["removed_records"] == 2
    assert body["inert_sessions"] == 0
    assert body["acknowledged_records"] == 1
    # The live session's acknowledgement is untouched.
    view = client.get(f"/api/v1/voice/sessions/{sid}/repeat-requests").json()
    assert view["has_pending"] is False
    assert view["requests"][0]["acknowledged_note"] == "prompt shown"
    # A second prune removes nothing and says so.
    again = client.post(
        "/api/v1/voice/repeat-requests/housekeeping/prune").json()
    assert again["removed_records"] == 0
    assert again["removed_sessions"] == []


def test_http_housekeeping_reads_are_pure(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _http_doubted_session(client)
    path = tmp_path / rr.ACK_FILENAME
    before = path.read_bytes()
    client.get("/api/v1/voice/repeat-requests/housekeeping")
    assert path.read_bytes() == before
    client.post("/api/v1/voice/repeat-requests/housekeeping/prune")
    assert path.read_bytes() == before  # nothing inert: no rewrite


def test_http_housekeeping_requires_auth(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    bare = TestClient(client.app)
    assert bare.get(
        "/api/v1/voice/repeat-requests/housekeeping").status_code == 401
    assert bare.post(
        "/api/v1/voice/repeat-requests/housekeeping/prune").status_code == 401


def test_http_drop_chat_prunes_its_acknowledgements(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_a, _sid_a = _http_doubted_session(client, title="a")
    chat_b, sid_b = _http_doubted_session(client, title="b")
    dropped = client.delete(f"/api/v1/voice/chats/{chat_a}/sessions")
    assert dropped.status_code == 200, dropped.text
    body = dropped.json()
    assert body["chat_id"] == chat_a
    assert body["dropped"] == 1
    assert body["repeat_acknowledgements_pruned"] == 1
    # The surviving chat's record is untouched and still live.
    view = client.get("/api/v1/voice/repeat-requests/housekeeping").json()
    assert view["acknowledged_records"] == 1
    assert view["inert_sessions"] == 0
    signal = client.get(
        f"/api/v1/voice/sessions/{sid_b}/repeat-requests").json()
    assert signal["has_pending"] is False
    # Dropping the second chat prunes its record too.
    dropped_b = client.delete(f"/api/v1/voice/chats/{chat_b}/sessions").json()
    assert dropped_b["dropped"] == 1
    assert dropped_b["repeat_acknowledgements_pruned"] == 1
    assert client.get(
        "/api/v1/voice/repeat-requests/housekeeping"
    ).json()["acknowledged_records"] == 0


def test_http_drop_chat_without_acknowledgements_reports_zero(
        tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "plain"}).json()["id"]
    client.post("/api/v1/voice/sessions", json={"chat_id": chat_id})
    dropped = client.delete(f"/api/v1/voice/chats/{chat_id}/sessions")
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["dropped"] == 1
    assert dropped.json()["repeat_acknowledgements_pruned"] == 0


def test_http_drop_prunes_preexisting_orphans_too(tmp_path, monkeypatch):
    # The drop road's prune is one housekeeping act over the
    # whole store (see the slice doc): an orphan left by an
    # earlier deletion is cleared by any later drop, and the
    # reported count is the act's total.
    client, _f, _db = make_client(tmp_path, monkeypatch)
    _plant_ghost(tmp_path, turns=(1,))
    chat_id = client.post("/api/v1/chats", json={"title": "empty"}).json()["id"]
    dropped = client.delete(f"/api/v1/voice/chats/{chat_id}/sessions")
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["dropped"] == 0
    assert dropped.json()["repeat_acknowledgements_pruned"] == 1
    assert client.get(
        "/api/v1/voice/repeat-requests/housekeeping"
    ).json()["acknowledged_records"] == 0


def test_http_housekeeping_creates_no_chat_message(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id, _sid = _http_doubted_session(client)
    _plant_ghost(tmp_path)
    before = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    client.get("/api/v1/voice/repeat-requests/housekeeping")
    client.post("/api/v1/voice/repeat-requests/housekeeping/prune")
    after = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert after == before  # housekeeping is data care, never dialogue
    doc = json.loads((tmp_path / rr.ACK_FILENAME).read_text())
    assert doc["version"] == rr.ACK_VERSION


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
