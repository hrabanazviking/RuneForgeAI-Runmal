"""P-104 - Voice auto-projection (Part VII, DERIVED scope).

Pins: the per-session opt-in citizen flag (durable, default
OFF, tolerant load of the pre-P-104 shape), the async host
service (never raises; disabled / no-pending / failure are all
reported in-band; the landing is P-103's one service with its
heard-text law unchanged), the toggle/status HTTP roads
(owner-scoped 404), and the host wiring: the P-101 manual
turns road and the P-102 live speak/stop roads auto-project
ONLY for opted-in sessions, and response shapes change only
by the additive auto_projection report. No network: fakes and
fixtures only. Migration head stays 0041.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.owners import get_or_create_owner
from runmal.voice import autoproject as auto
from runmal.voice.audio import FixturePlayback
from runmal.voice.live import LiveVoiceController
from runmal.voice.session import (
    ProviderTruth,
    SessionSettings,
    VoiceSession,
    VoiceSessionStore,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-07T12:00:00+00:00"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1", character_id=None, **kw):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=character_id, settings=_settings(), now=NOW, **kw,
    )


def _turn(session, **kw):
    base = dict(recorded_at=NOW)
    base.update(kw)
    return session.record_turn(**base)


def _db(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def _seed_chat(factory, title="voice chat"):
    async def run():
        async with factory() as db:
            owner = await get_or_create_owner(db)
            chat = await chats_svc.create_chat(db, owner.id, title, None)
            return owner.id, chat.id
    return asyncio.run(run())


def _history(factory, user_id, chat_id):
    async def run():
        async with factory() as db:
            msgs = await chats_svc.get_history(db, user_id, chat_id) or []
            return [chats_svc.message_to_dict(m) for m in msgs]
    return asyncio.run(run())


def _autoproject(factory, session, store):
    async def run():
        async with factory() as db:
            return await auto.autoproject_session(db, session=session, store=store)
    return asyncio.run(run())


# --------------------------------------------------------- citizen


def test_flag_defaults_off_and_round_trips(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    assert s.auto_project is False
    assert s.summary_dict()["auto_project"] is False
    assert s.to_dict()["auto_project"] is False
    on = _session(store, chat_id="chat-2", auto_project=True)
    assert on.auto_project is True
    fresh = _store(tmp_path).get(on.session_id)
    assert fresh.auto_project is True  # durable across a reload
    assert VoiceSession.from_dict(on.to_dict()).auto_project is True


def test_legacy_stored_session_loads_off(tmp_path):
    store = _store(tmp_path)
    s = _session(store, auto_project=True)
    legacy = s.to_dict()
    del legacy["auto_project"]  # the pre-P-104 stored shape
    old = VoiceSession.from_dict(legacy)
    assert old.auto_project is False


# ------------------------------------------------------ pure views


def test_pending_and_status_views(tmp_path):
    store = _store(tmp_path)
    s = _session(store, auto_project=True)
    _turn(s, transcript_text="hi", response_text="yo", heard_certain="yo",
          chunks_total=1, chunks_played=1)
    _turn(s)
    store.save_session(s)
    assert auto.pending_turns(s) == 2
    view = auto.autoproject_status(s)
    assert view == {
        "session_id": s.session_id, "chat_id": "chat-1",
        "auto_project": True, "pending_turns": 2, "turns_total": 2,
        "turns_projected": 0, "messages_projected": 0,
    }


# ---------------------------------------------------------- service


def test_service_disabled_attempts_nothing(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)  # flag OFF
    _turn(s, transcript_text="hi", response_text="yo", heard_certain="yo",
          chunks_total=1, chunks_played=1)
    store.save_session(s)
    report = _autoproject(factory, s, store)
    assert report["enabled"] is False and report["attempted"] is False
    assert report["ok"] is True and "reason" in report
    assert _history(factory, user_id, chat_id) == []
    assert s.turns[0].projected is False


def test_service_enabled_no_pending_attempts_nothing(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id, auto_project=True)
    report = _autoproject(factory, s, store)
    assert report["enabled"] is True and report["attempted"] is False
    assert report["reason"] == "no unprojected turns"


def test_service_enabled_projects_with_p103_law(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id, auto_project=True)
    _turn(s, transcript_text="hello", response_text="a b c",
          heard_certain="a", heard_uncertain="b", heard_unplayed="c",
          chunks_total=3, chunks_played=2)
    store.save_session(s)
    report = _autoproject(factory, s, store)
    assert report["attempted"] is True and report["ok"] is True
    assert report["projected_turns"] == 1 and report["messages_created"] == 2
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hello"), ("assistant", "a [uncertain: b\u2026]")]
    assert history[1]["provenance"]["origin"]["via"] == "voice_session"
    again = _autoproject(factory, s, store)
    assert again["attempted"] is False  # idempotent: nothing pending
    assert len(_history(factory, user_id, chat_id)) == 2


def test_service_failure_is_reported_never_raised(tmp_path):
    factory = _db(tmp_path)
    user_id, _chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    ghost = _session(store, chat_id="no-such-chat", user_id=user_id,
                     auto_project=True)
    _turn(ghost, transcript_text="hi")
    store.save_session(ghost)
    report = _autoproject(factory, ghost, store)
    assert report["attempted"] is True and report["ok"] is False
    assert "error" in report and report["error"]
    assert ghost.turns[0].projected is False  # retryable by the manual road


def test_service_no_content_turn_accounted(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id, auto_project=True)
    _turn(s, response_text="never heard", heard_unplayed="never heard",
          chunks_total=1, chunks_played=0)
    store.save_session(s)
    report = _autoproject(factory, s, store)
    assert report["ok"] is True and report["no_content_turns"] == 1
    assert report["messages_created"] == 0
    assert _history(factory, user_id, chat_id) == []


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


def _http_session(client, **extra):
    chat_id = client.post("/api/v1/chats", json={"title": "voice"}).json()["id"]
    body = {"chat_id": chat_id}
    body.update(extra)
    created = client.post("/api/v1/voice/sessions", json=body)
    assert created.status_code == 201, created.text
    return chat_id, created.json()["session_id"], created.json()


def test_http_start_flag_and_toggle_roads(tmp_path, monkeypatch):
    client, _f, _dbp = make_client(tmp_path, monkeypatch)
    _chat, sid, created = _http_session(client)
    assert created["auto_project"] is False  # default off, in the record
    view = client.get(f"/api/v1/voice/sessions/{sid}/auto-projection")
    assert view.status_code == 200 and view.json()["auto_project"] is False
    missing = client.post(f"/api/v1/voice/sessions/{sid}/auto-project", json={})
    assert missing.status_code == 422
    on = client.post(
        f"/api/v1/voice/sessions/{sid}/auto-project", json={"enabled": True})
    assert on.status_code == 200 and on.json()["auto_project"] is True
    got = client.get(f"/api/v1/voice/sessions/{sid}").json()
    assert got["auto_project"] is True  # durable on the citizen itself
    off = client.post(
        f"/api/v1/voice/sessions/{sid}/auto-project", json={"enabled": False})
    assert off.json()["auto_project"] is False
    _c2, sid2, created2 = _http_session(client, auto_project=True)
    assert created2["auto_project"] is True  # opt in at start
    assert client.get(
        f"/api/v1/voice/sessions/{sid2}/auto-projection").json()["auto_project"] is True


def test_http_toggle_unknown_and_foreign_404(tmp_path, monkeypatch):
    client, _f, _dbp = make_client(tmp_path, monkeypatch)
    assert client.post("/api/v1/voice/sessions/nope/auto-project",
                       json={"enabled": True}).status_code == 404
    assert client.get("/api/v1/voice/sessions/nope/auto-projection").status_code == 404
    chat_id, _sid, _c = _http_session(client)
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    store.save_session(foreign)
    assert client.post(f"/api/v1/voice/sessions/{foreign.session_id}/auto-project",
                       json={"enabled": True}).status_code == 404
    assert client.get(
        f"/api/v1/voice/sessions/{foreign.session_id}/auto-projection").status_code == 404


def test_http_manual_turn_auto_projects_when_opted_in(tmp_path, monkeypatch):
    client, _f, _dbp = make_client(tmp_path, monkeypatch)
    chat_id, sid, _c = _http_session(client, auto_project=True)
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "hello", "response_text": "Hi there",
              "heard_certain": "Hi there", "chunks_total": 1, "chunks_played": 1})
    assert turn.status_code == 201, turn.text
    report = turn.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    assert report["messages_created"] == 2
    chat = client.get(f"/api/v1/chats/{chat_id}").json()
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [
        ("user", "hello"), ("assistant", "Hi there")]


def test_http_manual_turn_default_off_is_unchanged(tmp_path, monkeypatch):
    client, _f, _dbp = make_client(tmp_path, monkeypatch)
    chat_id, sid, _c = _http_session(client)
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "hello", "response_text": "Hi there",
              "heard_certain": "Hi there", "chunks_total": 1, "chunks_played": 1})
    assert turn.status_code == 201, turn.text
    assert "auto_projection" not in turn.json()  # P-101 shape, unchanged
    assert client.get(f"/api/v1/chats/{chat_id}").json()["messages"] == []
    status = client.get(f"/api/v1/voice/sessions/{sid}/auto-projection").json()
    assert status["pending_turns"] == 1  # waiting for the explicit road


# ------------------------------------------------- HTTP live wiring


def _fake_settings():
    truth = ProviderTruth(
        kind="tts", backend="fake-tts", known=False, verified=False,
        admission="unknown", selected_via="default")
    return SessionSettings(
        tts_backend="fake-tts", stt_backend="fake-stt",
        voice_id="fake-voice", language="en",
        tts_truth=truth,
        stt_truth=ProviderTruth(
            kind="stt", backend="fake-stt", known=False, verified=False,
            admission="unknown", selected_via="default"))


def test_http_live_speak_and_stop_auto_project(tmp_path, monkeypatch):
    client, factory, _dbp = make_client(tmp_path, monkeypatch)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    session = start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW, auto_project=True)
    controller = LiveVoiceController(
        responder=lambda text: iter(["Hello there."]),
        playback_factory=lambda s: FixturePlayback())
    app = client.app
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    sid = session.session_id
    started = client.post(f"/api/v1/voice/sessions/{sid}/live/start")
    assert started.status_code == 201, started.text
    spoken = client.post(
        f"/api/v1/voice/sessions/{sid}/live/speak",
        json={"text": "Hello there traveller."})
    assert spoken.status_code == 201, spoken.text
    report = spoken.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("assistant", "Hello there traveller.")]
    stopped = client.post(
        f"/api/v1/voice/sessions/{sid}/live/stop", json={"note": "done"})
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["live"] is False


def test_http_live_speak_default_off_has_no_report(tmp_path, monkeypatch):
    client, factory, _dbp = make_client(tmp_path, monkeypatch)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    session = start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW)  # flag OFF
    controller = LiveVoiceController(
        responder=lambda text: iter(["Hello there."]),
        playback_factory=lambda s: FixturePlayback())
    app = client.app
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    sid = session.session_id
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/start").status_code == 201
    spoken = client.post(
        f"/api/v1/voice/sessions/{sid}/live/speak", json={"text": "Quiet."})
    assert spoken.status_code == 201, spoken.text
    assert "auto_projection" not in spoken.json()  # P-102 shape, unchanged
    assert _history(factory, user_id, chat_id) == []
    client.post(f"/api/v1/voice/sessions/{sid}/live/stop", json={})


def test_controller_accessors(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    controller = LiveVoiceController(
        playback_factory=lambda sess: FixturePlayback())
    assert controller.session_for(s.session_id) is None
    assert controller.store_for(s.session_id) is None
    controller.start(s, store=store, tts=_fake_backend(), stt=_fake_stt())
    assert controller.session_for(s.session_id) is s
    assert controller.store_for(s.session_id) is store
    controller.stop(s.session_id)
    assert controller.session_for(s.session_id) is None


def _fake_backend():
    from runmal.voice.tts import FakeTTSBackend
    return FakeTTSBackend()


def _fake_stt():
    from runmal.voice.stt import FakeSTTBackend
    return FakeSTTBackend()


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"


def test_http_stop_catches_up_feed_frames_after_live_toggle(tmp_path, monkeypatch):
    import math

    from runmal.voice import FRAME_SAMPLES
    from runmal.voice.audio import floats_to_pcm16

    def frame(amp):
        return floats_to_pcm16(
            [amp * math.sin(2 * math.pi * 200 * i / 16000)
             for i in range(FRAME_SAMPLES)])

    utterance = [frame(0.0)] * 3 + [frame(0.5)] * 8 + [frame(0.0)] * 15
    client, factory, _dbp = make_client(tmp_path, monkeypatch)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    session = start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW)  # flag OFF at start
    controller = LiveVoiceController(
        responder=lambda text: iter(["Hello there. ", "How are you?"]),
        playback_factory=lambda s: FixturePlayback())
    app = client.app
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    sid = session.session_id
    assert client.post(f"/api/v1/voice/sessions/{sid}/live/start").status_code == 201
    recorded = controller.feed_frames(sid, utterance)
    assert len(recorded) == 1  # the mic road persisted its turn
    assert _history(factory, user_id, chat_id) == []  # nothing landed yet
    on = client.post(
        f"/api/v1/voice/sessions/{sid}/auto-project", json={"enabled": True})
    assert on.status_code == 200 and on.json()["pending_turns"] == 1
    assert session.auto_project is True  # the live host object was synced
    stopped = client.post(
        f"/api/v1/voice/sessions/{sid}/live/stop", json={"note": "done"})
    assert stopped.status_code == 200, stopped.text
    report = stopped.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    assert report["messages_created"] == 2
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hello world"), ("assistant", "Hello there. How are you?")]
