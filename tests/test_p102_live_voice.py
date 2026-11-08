"""P-102 — Live voice orchestrator (Part VII, DERIVED scope, L1).

Pins: the additive orchestrator speak road, the live builder
(registry honesty — BackendUnavailable wrapped, never a silent
fake; ledger subscribed; wiring labels follow the BUILT
backend), the controller (start/speak/feed/interrupt/stop with
turns persisted through the session citizen's own append road,
never double-recorded), and the HTTP surface on the founding
road with the founding /voice/status slot finally filled.

The session citizen is P-101's; on a tree without it the HTTP
and controller roads run against a labelled test-double session
+ store implementing the P-101 protocol in shape, and the
guarded real-citizen test skips (importorskip). No network:
fakes/fixtures only. Migration head stays 0041.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice.audio import FixturePlayback, floats_to_pcm16
from runmal.voice.ledger import PlaybackLedger
from runmal.voice.live import (
    LiveVoiceController,
    LiveVoiceError,
    build_live_orchestrator,
    unavailable_responder,
)
from runmal.voice.orchestrator import SimulatedClock, VoiceOrchestrator, VoiceState
from runmal.voice.stt import FakeSTTBackend
from runmal.voice.tts import FakeTTSBackend, VoiceInfo
from runmal.voice.vad import EnergyVadModel, VadSegmenter

# ------------------------------------------------------ test doubles
# A labelled double implementing the P-101 session protocol in
# shape (session_id / chat_id / active / settings / turns /
# stop / append_orchestrator_turn) and the store's shape.


@dataclass
class DoubleSettings:
    tts_backend: str = "fake-tts"
    stt_backend: str = "fake-stt"
    voice_id: str = "fake-voice"
    language: str = "en"


@dataclass
class DoubleTurn:
    turn_no: int
    transcript_text: str = ""
    response_text: str = ""
    heard_certain: str = ""
    heard_uncertain: str = ""
    heard_unplayed: str = ""
    interrupted: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "turn_no": self.turn_no,
            "transcript_text": self.transcript_text,
            "response_text": self.response_text,
            "heard_certain": self.heard_certain,
            "heard_uncertain": self.heard_uncertain,
            "heard_unplayed": self.heard_unplayed,
            "interrupted": self.interrupted,
            "error": self.error,
        }


class DoubleSessionError(ValueError):
    pass


@dataclass
class DoubleSession:
    session_id: str = "sess-1"
    chat_id: str = "chat-1"
    user_id: str = "owner"
    settings: DoubleSettings = field(default_factory=DoubleSettings)
    active: bool = True
    stop_note: str = ""
    turns: list = field(default_factory=list)

    def stop(self, note: str = "", *, at: str = "") -> None:
        if not self.active:
            return
        self.active = False
        self.stop_note = note

    def append_orchestrator_turn(self, record, heard, *, recorded_at: str = ""):
        if not self.active:
            raise DoubleSessionError("session is stopped; its turns are history")
        turn = DoubleTurn(
            turn_no=len(self.turns) + 1,
            transcript_text=record.transcript.text if record.transcript else "",
            response_text=record.response_text,
            heard_certain=heard.certain_text,
            heard_uncertain=heard.uncertain_text,
            heard_unplayed=heard.unplayed_text,
            interrupted=record.interrupted,
            error=record.error,
        )
        self.turns.append(turn)
        return turn


class DoubleStore:
    def __init__(self, *sessions):
        self._sessions = {s.session_id: s for s in sessions}
        self.saved: list[str] = []

    def get(self, session_id):
        return self._sessions.get(session_id)

    def save_session(self, session):
        self._sessions[session.session_id] = session
        self.saved.append(session.session_id)
        return session


def _frame(amplitude: float) -> bytes:
    from runmal.voice import FRAME_SAMPLES

    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000) for i in range(FRAME_SAMPLES)]
    )


SPEECH, SILENCE = _frame(0.5), _frame(0.0)
UTTERANCE = [SILENCE] * 3 + [SPEECH] * 8 + [SILENCE] * 15
RESPONDER = lambda text: iter(["Hello there. ", "How are you?"])  # noqa: E731


def _controller(**kw) -> LiveVoiceController:
    kw.setdefault("responder", RESPONDER)
    kw.setdefault("playback_factory", lambda session: FixturePlayback())
    return LiveVoiceController(**kw)


def _start_double(controller=None, session=None, store=None):
    controller = controller or _controller()
    session = session or DoubleSession()
    store = store if store is not None else DoubleStore(session)
    status = controller.start(session, store=store)
    return controller, session, store, status


# ------------------------------------------------------------ builder


def test_build_requires_explicit_playback():
    with pytest.raises(LiveVoiceError, match="explicit playback"):
        build_live_orchestrator(DoubleSettings())


def test_build_registry_fake_keys_and_wiring_labels():
    orch, ledger, wiring = build_live_orchestrator(
        DoubleSettings(), responder=RESPONDER, playback=FixturePlayback()
    )
    assert wiring.road_tts == "fake" and wiring.road_stt == "fake"
    assert wiring.tts_backend == "fake-tts" and wiring.stt_backend == "fake-stt"
    assert wiring.responder == "injected" and wiring.vad_model == "energy-fixture"
    assert orch.voice.voice_id == "fake-voice" and orch.voice.language == "en"


def test_build_unknown_backend_wrapped_never_faked():
    settings = DoubleSettings(tts_backend="no-such-voice")
    with pytest.raises(LiveVoiceError, match="no-such-voice"):
        build_live_orchestrator(settings, playback=FixturePlayback())


def test_build_default_responder_is_unavailable_label():
    _orch, _ledger, wiring = build_live_orchestrator(
        DoubleSettings(), tts=FakeTTSBackend(), stt=FakeSTTBackend(),
        playback=FixturePlayback(),
    )
    assert wiring.responder == "unavailable"
    with pytest.raises(LiveVoiceError, match="no voice responder"):
        list(unavailable_responder("hi"))


def test_build_ledger_is_subscribed():
    orch, ledger, _w = build_live_orchestrator(
        DoubleSettings(), responder=RESPONDER, playback=FixturePlayback()
    )
    record = orch.speak_text("Hello there traveller.")
    assert ledger.records(record.turn_id)
    heard = ledger.heard_text(record.turn_id, record.response_text)
    assert heard.certain_text == "Hello there traveller."
    assert heard.uncertain_text == "" and heard.unplayed_text == ""


# ------------------------------------------------------ speak_text road


def _direct_orchestrator(**kw) -> VoiceOrchestrator:
    return VoiceOrchestrator(
        segmenter=VadSegmenter(EnergyVadModel()),
        stt=FakeSTTBackend("hello companion"),
        responder=RESPONDER,
        tts=FakeTTSBackend(),
        voice=VoiceInfo("fake-voice", backend_key="fake-tts"),
        playback=FixturePlayback(),
        clock=SimulatedClock(),
        **kw,
    )


def test_speak_text_state_sequence_and_counts():
    orch = _direct_orchestrator()
    record = orch.speak_text("Hello there. How are you?")
    assert orch.state_sequence() == [
        VoiceState.LISTENING, VoiceState.SYNTHESIZING,
        VoiceState.SPEAKING, VoiceState.LISTENING,
    ]
    assert record.response_text == "Hello there. How are you?"
    assert record.chunks_total == record.chunks_played == 2
    assert not record.interrupted and not record.error


def test_speak_text_empty_is_a_quiet_record():
    orch = _direct_orchestrator()
    record = orch.speak_text("   ")
    assert record.chunks_total == 0 and orch.state is VoiceState.LISTENING
    assert orch.turns == [record]


def test_speak_text_interruption_lands_in_listening():
    orch = _direct_orchestrator()
    fired = {"done": False}

    def hook(turn_id, frames_played):
        if not fired["done"]:
            fired["done"] = True
            assert orch.interrupt() is True

    orch._frame_hook = hook
    record = orch.speak_text("Hello there. How are you today, traveller?")
    assert record.interrupted
    assert VoiceState.INTERRUPTING in orch.state_sequence()
    assert orch.state is VoiceState.LISTENING


def test_speak_text_tts_failure_recovers_with_error():
    class BoomTTS(FakeTTSBackend):
        def synthesize(self, text, voice, *, speaking_rate=1.0):
            raise RuntimeError("synth exploded")
            yield  # pragma: no cover

    orch = _direct_orchestrator()
    orch.tts = BoomTTS()
    record = orch.speak_text("Hello there.")
    assert "synth exploded" in record.error
    assert VoiceState.ERROR_RECOVERY in orch.state_sequence()
    assert orch.state is VoiceState.LISTENING


# ---------------------------------------------------------- controller


def test_controller_start_status_and_wiring():
    _c, _s, _store, status = _start_double()
    assert status["live"] is True and status["state"] == "LISTENING"
    assert status["wiring"]["road_tts"] == "fake"
    assert status["turns_live"] == 0 and status["turns_recorded"] == 0


def test_controller_double_start_and_stopped_refused():
    controller, session, _store, _st = _start_double()
    with pytest.raises(LiveVoiceError, match="already live"):
        controller.start(session)
    stopped = DoubleSession(session_id="sess-2")
    stopped.stop("done")
    with pytest.raises(LiveVoiceError, match="stopped"):
        controller.start(stopped)


def test_controller_start_without_playback_refuses_plainly():
    controller = LiveVoiceController(responder=RESPONDER)
    with pytest.raises(LiveVoiceError, match="explicit playback"):
        controller.start(DoubleSession())


def test_controller_speak_persists_with_heard_truth():
    controller, session, store, _st = _start_double()
    turn = controller.speak(session.session_id, "Hello there traveller.")
    assert turn["turn_no"] == 1
    assert turn["heard_certain"] == "Hello there traveller."
    assert turn["heard_uncertain"] == "" and turn["heard_unplayed"] == ""
    assert len(session.turns) == 1 and store.saved
    again = controller.speak(session.session_id, "Second line.")
    assert again["turn_no"] == 2 and len(session.turns) == 2


def test_controller_speak_validation_and_unknown():
    controller, session, _store, _st = _start_double()
    with pytest.raises(LiveVoiceError, match="must not be empty"):
        controller.speak(session.session_id, "  ")
    assert session.turns == []
    with pytest.raises(LiveVoiceError, match="not live"):
        controller.speak("nope", "hello")


def test_controller_feed_frames_mic_turn_persists():
    controller, session, _store, _st = _start_double()
    recorded = controller.feed_frames(session.session_id, UTTERANCE)
    assert len(recorded) == 1
    turn = recorded[0]
    assert turn["transcript_text"] == "hello world"  # registry FakeSTT default script
    assert turn["response_text"] == "Hello there. How are you?"
    assert turn["heard_certain"] == "Hello there. How are you?"
    # Silence alone completes no turn and records nothing new.
    assert controller.feed_frames(session.session_id, [SILENCE] * 5) == []
    assert len(session.turns) == 1


def test_controller_unavailable_responder_records_honest_error_turn():
    controller = _controller(responder=None)
    # responder=None at controller level means the builder default.
    session = DoubleSession()
    controller.start(session, store=DoubleStore(session))
    recorded = controller.feed_frames(session.session_id, UTTERANCE)
    assert len(recorded) == 1
    assert "no voice responder" in recorded[0]["error"]
    assert recorded[0]["response_text"] == ""


def test_controller_interrupt_idle_is_false():
    controller, session, _store, _st = _start_double()
    assert controller.interrupt(session.session_id) is False


def test_controller_stop_stops_citizen_saves_and_clears_slot():
    import types

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    controller = _controller()
    controller.attach_app(app)
    session = DoubleSession()
    store = DoubleStore(session)
    controller.start(session, store=store)
    assert app.state.voice_session is not None
    final = controller.stop(session.session_id, note="done")
    assert final["live"] is False and final["turns_recorded"] == 0
    assert session.active is False and session.stop_note == "done"
    assert store.saved
    assert app.state.voice_session is None
    assert controller.is_live(session.session_id) is False
    with pytest.raises(LiveVoiceError, match="not live"):
        controller.stop(session.session_id)


def test_controller_status_listing_shape():
    controller, session, _store, _st = _start_double()
    listing = controller.status()
    assert [s["session_id"] for s in listing["sessions"]] == [session.session_id]
    missing = controller.status("nope")
    assert missing["live"] is False and missing["wiring"] is None


# ---------------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, app


def _http_world(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    session = DoubleSession()
    store = DoubleStore(session)
    controller = _controller()
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    return client, app, session, store, controller


def test_http_full_live_flow_and_founding_status(tmp_path, monkeypatch):
    client, _app, session, _store, _c = _http_world(tmp_path, monkeypatch)
    sid = session.session_id
    started = client.post(f"/api/v1/voice/sessions/{sid}/live/start")
    assert started.status_code == 201, started.text
    assert started.json()["live"] is True
    assert started.json()["wiring"]["road_tts"] == "fake"
    live = client.get(f"/api/v1/voice/sessions/{sid}/live")
    assert live.json()["live"] is True and live.json()["chat_id"] == "chat-1"
    status0 = client.get("/api/v1/voice/status").json()
    assert status0["state"] == "LISTENING" and status0["turns"] == 0
    spoken = client.post(
        f"/api/v1/voice/sessions/{sid}/live/speak", json={"text": "Hello there traveller."}
    )
    assert spoken.status_code == 201, spoken.text
    assert spoken.json()["heard_certain"] == "Hello there traveller."
    status1 = client.get("/api/v1/voice/status").json()
    assert status1["turns"] == 1  # the founding slot, finally filled
    intr = client.post(f"/api/v1/voice/sessions/{sid}/live/interrupt")
    assert intr.json()["interrupted"] is False
    stopped = client.post(f"/api/v1/voice/sessions/{sid}/live/stop", json={"note": "done"})
    assert stopped.json()["live"] is False
    assert session.active is False
    status2 = client.get("/api/v1/voice/status").json()
    assert status2["turns"] == 0 and status2["state"] == "LISTENING"


def test_http_error_roads(tmp_path, monkeypatch):
    client, _app, session, _store, _c = _http_world(tmp_path, monkeypatch)
    sid = session.session_id
    assert client.post("/api/v1/voice/sessions/nope/live/start").status_code == 404
    assert client.get("/api/v1/voice/sessions/nope/live").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/speak", json={"text": "x"}).status_code == 409
    not_live = client.get(f"/api/v1/voice/sessions/{sid}/live")
    assert not_live.status_code == 200 and not_live.json()["live"] is False
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/start").status_code == 201
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/start").status_code == 409
    empty = client.post(f"/api/v1/voice/sessions/{sid}/live/speak", json={"text": "  "})
    assert empty.status_code == 422
    client.post(f"/api/v1/voice/sessions/{sid}/live/stop", json={})
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/start").status_code == 409


def test_http_default_controller_refuses_without_playback_role(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    session = DoubleSession()
    app.state.live_session_store = DoubleStore(session)
    res = client.post(f"/api/v1/voice/sessions/{session.session_id}/live/start")
    assert res.status_code == 503, res.text
    assert "playback" in res.json()["detail"]


def test_boot_constructs_controller_and_migration_pin(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    controller = app.state.live_voice_controller
    assert isinstance(controller, LiveVoiceController)
    assert controller.status() == {"sessions": []}
    db_path = tmp_path / "test.db"
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"


# ------------------------------------------- real P-101 citizen (guarded)


def test_real_p101_citizen_live_round_trip(tmp_path):
    session_mod = pytest.importorskip("runmal.voice.session")
    from runmal.voice.settings import VoiceSettings

    store = session_mod.VoiceSessionStore(tmp_path / "voice_sessions.json")
    settings = session_mod.resolve_session_settings(
        defaults=VoiceSettings(), character=None
    )
    citizen = session_mod.start_session(
        store, chat_id="chat-real", user_id="owner",
        character_id=None, settings=settings,
    )
    controller = LiveVoiceController(responder=RESPONDER)
    status = controller.start(
        citizen, store=store, tts=FakeTTSBackend(), stt=FakeSTTBackend("hi"),
        playback=FixturePlayback(),
    )
    assert status["live"] is True and status["wiring"]["road_tts"] == "fake"
    turn = controller.speak(citizen.session_id, "Hello there traveller.")
    assert turn["heard_certain"] == "Hello there traveller."
    controller.stop(citizen.session_id, note="done")
    fresh = session_mod.VoiceSessionStore(tmp_path / "voice_sessions.json")
    reloaded = fresh.get(citizen.session_id)
    assert reloaded is not None and reloaded.state == "stopped"
    assert reloaded.turns[0].heard_certain == "Hello there traveller."
