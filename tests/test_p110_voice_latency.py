"""P-110 - Voice turn latency evidence (Part VII, DERIVED scope).

Pins: durations derived ONLY from the orchestrator's own
clock-stamped transitions (both endpoints stamped or the
duration is absent - never estimated, never zero-filled),
the persisted durations field on the P-101 turn record
(round-trip, legacy shape, malformed entries dropped - a
stored session never bricks), the live host passing its
transition log through the citizen's append road so live
turns persist their evidence, the per-session latency view
(per-turn evidence flags + the section-10 p50/p95 aggregate
from S510's own percentile), and the founding-road surface
(session payloads carry durations additively; GET
/voice/sessions/{id}/latency; unknown session 404). A
manually recorded turn carries NO evidence and says so.
No network: fakes/fixtures only. Migration head stays 0041.
"""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import latency as lat
from runmal.voice.audio import FixturePlayback, floats_to_pcm16
from runmal.voice.latency import (
    clean_durations,
    session_latency_view,
    turn_durations,
    turn_latency_view,
)
from runmal.voice.live import LiveVoiceController
from runmal.voice.orchestrator import (
    SimulatedClock,
    Transition,
    VoiceOrchestrator,
    VoiceState,
)
from runmal.voice.session import (
    VoiceSessionStore,
    VoiceTurnRecord,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings
from runmal.voice.stt import FakeSTTBackend
from runmal.voice.tts import FakeTTSBackend, VoiceInfo
from runmal.voice.vad import EnergyVadModel, VadSegmenter

NOW = "2026-11-08T12:00:00+00:00"
RESPONDER = lambda text: iter(["Hello there. ", "How are you?"])  # noqa: E731


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1"):
    return start_session(
        store, chat_id=chat_id, user_id="u1", character_id=None,
        settings=_settings(), now=NOW)


def _tr(to_state, at, turn_id=1, from_state=VoiceState.LISTENING):
    return Transition(from_state, to_state, at, turn_id)


FULL_CHAIN = [
    _tr(VoiceState.FINALIZING, 10.0),
    _tr(VoiceState.THINKING, 10.25),
    _tr(VoiceState.SYNTHESIZING, 11.25),
    _tr(VoiceState.SPEAKING, 11.5),
    _tr(VoiceState.LISTENING, 13.5),
]


# ---------------------------------------------------------- derivation


def test_full_mic_chain_exact_spans():
    d = turn_durations(FULL_CHAIN, 1)
    assert d == {
        "stt_seconds": 0.25,
        "response_seconds": 1.0,
        "synth_to_first_audio_seconds": 0.25,
        "playback_seconds": 2.0,
        "turn_seconds": 3.5,
    }
    assert list(d) == list(lat.DURATION_KEYS)  # canonical order


def test_speak_turn_partial_stages_only():
    d = turn_durations([
        _tr(VoiceState.SYNTHESIZING, 5.0, turn_id=7),
        _tr(VoiceState.SPEAKING, 5.5, turn_id=7),
        _tr(VoiceState.LISTENING, 6.5, turn_id=7),
    ], 7)
    assert d == {
        "synth_to_first_audio_seconds": 0.5,
        "playback_seconds": 1.0,
        "turn_seconds": 1.5,
    }


def test_missing_endpoint_means_absent_never_zero():
    d = turn_durations([
        _tr(VoiceState.FINALIZING, 1.0),
        _tr(VoiceState.LISTENING, 2.0),
    ], 1)
    assert "stt_seconds" not in d and "response_seconds" not in d
    assert d == {"turn_seconds": 1.0}


def test_no_transitions_and_other_turns_ignored():
    assert turn_durations([], 1) == {}
    assert turn_durations(FULL_CHAIN, 99) == {}
    mixed = FULL_CHAIN + [_tr(VoiceState.THINKING, 99.0, turn_id=2)]
    assert turn_durations(mixed, 1)["turn_seconds"] == 3.5


def test_negative_span_is_dropped_not_clamped():
    d = turn_durations([
        _tr(VoiceState.SYNTHESIZING, 5.0),
        _tr(VoiceState.SPEAKING, 4.0),  # impossible under monotonic clock
        _tr(VoiceState.LISTENING, 6.0),
    ], 1)
    assert "synth_to_first_audio_seconds" not in d
    assert d["playback_seconds"] == 2.0


def test_direct_orchestrator_turn_derives_evidence():
    orch = VoiceOrchestrator(
        segmenter=VadSegmenter(EnergyVadModel()),
        stt=FakeSTTBackend("hello companion"),
        responder=RESPONDER,
        tts=FakeTTSBackend(),
        voice=VoiceInfo("fake-voice", backend_key="fake-tts"),
        playback=FixturePlayback(),
        clock=SimulatedClock(),
    )
    record = orch.speak_text("Hello there. How are you?")
    d = turn_durations(orch.transitions, record.turn_id)
    assert set(d) == {
        "synth_to_first_audio_seconds", "playback_seconds", "turn_seconds"}
    assert all(v > 0 for v in d.values())


# ---------------------------------------------------------- cleaning


def test_clean_durations_drops_malformed():
    assert clean_durations(None) == {}
    assert clean_durations("nope") == {}
    assert clean_durations({
        "stt_seconds": 0.5,
        "response_seconds": -1.0,          # negative: dropped
        "playback_seconds": "fast",        # not a number: dropped
        "turn_seconds": True,              # bool is not a measurement
        "synth_to_first_audio_seconds": float("inf"),
        "unknown_key": 1.0,                # not a claimed duration
    }) == {"stt_seconds": 0.5}


# ---------------------------------------------------------- persistence


def _orch_record(**kw):
    from runmal.voice.orchestrator import TurnRecord
    from runmal.voice.stt import Transcript
    return TurnRecord(
        turn_id=kw.get("turn_id", 1),
        transcript=Transcript(text="hello companion"),
        response_text="Hello there traveller.",
        chunks_total=1, chunks_played=1)


def test_from_orchestrator_with_and_without_transitions():
    with_evidence = VoiceTurnRecord.from_orchestrator(
        _orch_record(), None, turn_no=1, stt_backend="fake-ear",
        recorded_at=NOW, transitions=FULL_CHAIN)
    assert with_evidence.durations["stt_seconds"] == 0.25
    without = VoiceTurnRecord.from_orchestrator(
        _orch_record(), None, turn_no=1, stt_backend="fake-ear",
        recorded_at=NOW)
    assert without.durations == {}


def test_durations_round_trip_and_legacy_shape(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    turn = s.append_orchestrator_turn(
        _orch_record(), None, recorded_at=NOW, transitions=FULL_CHAIN)
    store.save_session(s)
    reloaded = _store(tmp_path).get(s.session_id)
    assert reloaded.turns[0].durations == turn.durations
    legacy = turn.to_dict()
    del legacy["durations"]  # a pre-P-110 stored turn
    assert VoiceTurnRecord.from_dict(legacy).durations == {}


def test_malformed_stored_durations_never_brick(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.record_turn(transcript_text="hi", response_text="hello")
    data = s.to_dict()
    data["turns"][0]["durations"] = {"stt_seconds": "fast", "bogus": 3}
    loaded = type(s).from_dict(data)
    assert loaded.turns[0].durations == {}


# ---------------------------------------------------------- live flow


def _frame(amplitude: float) -> bytes:
    from runmal.voice import FRAME_SAMPLES
    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000)
         for i in range(FRAME_SAMPLES)])


def test_live_speak_and_mic_turns_persist_durations(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    controller = LiveVoiceController(
        responder=RESPONDER,
        playback_factory=lambda session: FixturePlayback(),
        clock=SimulatedClock())
    controller.start(s, store=store, tts=FakeTTSBackend(), stt=FakeSTTBackend("hello companion"))
    controller.speak(s.session_id, "Hello there. How are you?")
    speech, silence = _frame(0.5), _frame(0.0)
    controller.feed_frames(s.session_id, [silence] * 3 + [speech] * 8 + [silence] * 15)
    controller.stop(s.session_id)
    reloaded = _store(tmp_path).get(s.session_id)
    assert len(reloaded.turns) == 2
    speak_turn, mic_turn = reloaded.turns
    assert "synth_to_first_audio_seconds" in speak_turn.durations
    assert "stt_seconds" not in speak_turn.durations  # speak took no STT stage
    assert set(mic_turn.durations) == set(lat.DURATION_KEYS)
    assert all(v > 0 for v in mic_turn.durations.values())


# ---------------------------------------------------------- views


def test_views_evidence_flags_and_aggregate(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.append_orchestrator_turn(_orch_record(turn_id=1), None,
                                recorded_at=NOW, transitions=FULL_CHAIN)
    s.record_turn(transcript_text="manual", response_text="typed")
    view = session_latency_view(s)
    assert view["turn_count"] == 2 and view["turns_with_evidence"] == 1
    assert view["turns"][0]["has_latency_evidence"] is True
    assert view["turns"][0]["source"] == "orchestrator_transitions"
    assert view["turns"][1]["has_latency_evidence"] is False
    assert view["turns"][1]["source"] is None
    agg = view["aggregate"]
    assert agg["stt_seconds"] == {"count": 1, "p50": 0.25, "p95": 0.25}
    assert agg["playback_seconds"]["p95"] == 2.0
    assert turn_latency_view(s.turns[1])["durations"] == {}


def test_aggregate_percentiles_over_series(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    for i, stt in enumerate((0.1, 0.2, 0.3, 0.4), start=1):
        chain = [_tr(VoiceState.FINALIZING, 0.0, turn_id=i),
                 _tr(VoiceState.THINKING, stt, turn_id=i)]
        s.append_orchestrator_turn(_orch_record(turn_id=i), None,
                                    recorded_at=NOW, transitions=chain)
    agg = session_latency_view(s)["aggregate"]["stt_seconds"]
    assert agg["count"] == 4 and agg["p50"] == 0.2 and agg["p95"] == 0.4


# ---------------------------------------------------------- HTTP


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


def test_http_latency_road_and_payload(tmp_path, monkeypatch):
    # Seed a session WITH evidence straight into the store the
    # router reads (RUNMAL_DATA_DIR), before the client boots.
    store = _store(tmp_path)
    s = _session(store, chat_id="chat-seeded")
    s.append_orchestrator_turn(_orch_record(), None,
                                recorded_at=NOW, transitions=FULL_CHAIN)
    store.save_session(s)
    client = make_client(tmp_path, monkeypatch)
    res = client.get(f"/api/v1/voice/sessions/{s.session_id}")
    assert res.status_code == 200, res.text
    assert res.json()["turns"][0]["durations"]["stt_seconds"] == 0.25
    res = client.get(f"/api/v1/voice/sessions/{s.session_id}/latency")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["turns_with_evidence"] == 1
    assert body["aggregate"]["turn_seconds"]["p50"] == 3.5
    assert client.get("/api/v1/voice/sessions/nope/latency").status_code == 404


def test_http_manual_turn_has_no_evidence(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "voice chat"})
    assert chat.status_code == 201, chat.text
    res = client.post("/api/v1/voice/sessions", json={"chat_id": chat.json()["id"]})
    assert res.status_code == 201, res.text
    sid = res.json()["session_id"]
    res = client.post(f"/api/v1/voice/sessions/{sid}/turns", json={
        "transcript_text": "hi", "response_text": "hello"})
    assert res.status_code == 201, res.text
    body = client.get(f"/api/v1/voice/sessions/{sid}/latency").json()
    assert body["turns_with_evidence"] == 0 and body["aggregate"] == {}


# ---------------------------------------------------------- migration pin


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "pin.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
