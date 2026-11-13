"""P-112 - Voice live-start back-projection (Part VII, DERIVED).

Pins: the live/start HTTP road - the one projection-aware
road P-104 left unwired (its slice doc section 4 limitation,
verbatim) - now walks the same P-104 autoproject service the
speak/stop/manual roads walk, after a successful start only.
An opted-in session's pre-existing unprojected turns land in
their chat at live start, under P-103's heard-text law,
through the one landing service; a default-off session and
a nothing-pending session keep the exact P-102 start shape;
a failed start projects nothing; a projection failure is
reported in-band and the start stays live; the in-process
controller stays synchronous/DB-free and does NOT
back-project. No network: fakes/fixtures only. Migration
head stays 0041.
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
from runmal.voice import autoproject as auto
from runmal.voice.audio import FixturePlayback
from runmal.voice.live import LiveVoiceController
from runmal.voice.session import (
    ProviderTruth,
    SessionSettings,
    VoiceSessionStore,
    start_session,
)

NOW = "2026-11-08T12:00:00+00:00"


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


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


def _db(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path)), db_path


def _seed_chat(factory, title="voice chat"):
    async def run():
        async with factory() as db:
            from runmal.db.owners import get_or_create_owner
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


def _rig(tmp_path, monkeypatch, *, auto_project=False, turns=()):
    """A client + a store-built fake session with an injected
    live controller (the P-104 live-test shape). ``turns`` are
    recorded through the citizen directly - the honest
    pre-existing state: recorded before the session went
    live, never projected."""
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory, db_path = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    session = start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW, auto_project=auto_project)
    for kw in turns:
        base = dict(recorded_at=NOW)
        base.update(kw)
        session.record_turn(**base)
    store.save_session(session)
    controller = LiveVoiceController(
        responder=lambda text: iter(["Hello there."]),
        playback_factory=lambda s: FixturePlayback())
    app = create_app(factory)
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory, store, session, user_id, chat_id, controller


_HEARD = dict(
    transcript_text="hello", response_text="a b c",
    heard_certain="a", heard_uncertain="b", heard_unplayed="c",
    chunks_total=3, chunks_played=2)


# ------------------------------------------------------ the gap closed


def test_start_back_projects_pre_existing_turns(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[_HEARD])
    assert auto.pending_turns(s) == 1
    started = client.post(f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["live"] is True
    report = body["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    assert report["projected_turns"] == 1 and report["messages_created"] == 2
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hello"), ("assistant", "a [uncertain: b\u2026]")]
    assert history[1]["provenance"]["origin"]["via"] == "voice_session"
    fresh = _store(tmp_path).get(s.session_id)
    assert fresh.turns[0].projected is True
    assert auto.pending_turns(fresh) == 0


def test_start_back_projection_is_idempotent(tmp_path, monkeypatch):
    client, factory, _store_obj, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[_HEARD])
    sid = s.session_id
    assert client.post(
        f"/api/v1/voice/sessions/{sid}/live/start").status_code == 201
    assert len(_history(factory, user_id, chat_id)) == 2
    stopped = client.post(
        f"/api/v1/voice/sessions/{sid}/live/stop", json={"note": "done"})
    assert stopped.status_code == 200, stopped.text
    assert "auto_projection" not in stopped.json()  # nothing pending
    assert len(_history(factory, user_id, chat_id)) == 2  # no duplicates


def test_start_no_content_turn_is_accounted_never_landed(tmp_path, monkeypatch):
    turn = dict(response_text="never heard", heard_unplayed="never heard",
                chunks_total=1, chunks_played=0)
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[turn])
    started = client.post(f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 201, started.text
    report = started.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    assert report["no_content_turns"] == 1 and report["messages_created"] == 0
    assert _history(factory, user_id, chat_id) == []
    assert _store(tmp_path).get(s.session_id).turns[0].projected is True


# ------------------------------------------------------- shape law


def test_start_default_off_shape_unchanged(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=False, turns=[_HEARD])
    started = client.post(f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 201, started.text
    assert "auto_projection" not in started.json()  # P-102 shape
    assert _history(factory, user_id, chat_id) == []
    fresh = _store(tmp_path).get(s.session_id)
    assert auto.pending_turns(fresh) == 1  # still waiting, honestly


def test_start_opted_in_nothing_pending_shape_unchanged(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[])
    started = client.post(f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 201, started.text
    assert started.json()["live"] is True
    assert "auto_projection" not in started.json()


def test_start_unknown_session_404(tmp_path, monkeypatch):
    client, _f, _s, _sess, _u, _chat, _c = _rig(tmp_path, monkeypatch)
    missing = client.post("/api/v1/voice/sessions/nope/live/start")
    assert missing.status_code == 404


# ------------------------------------------------- failure honesty


def test_failed_start_projects_nothing(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[_HEARD])
    s.stop("done", at=NOW)
    store.save_session(s)
    started = client.post(f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 409, started.text
    assert _history(factory, user_id, chat_id) == []
    assert auto.pending_turns(_store(tmp_path).get(s.session_id)) == 1


def test_second_start_conflicts_and_projects_nothing_new(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id, _c = _rig(
        tmp_path, monkeypatch, auto_project=True, turns=[_HEARD])
    sid = s.session_id
    assert client.post(
        f"/api/v1/voice/sessions/{sid}/live/start").status_code == 201
    again = client.post(f"/api/v1/voice/sessions/{sid}/live/start")
    assert again.status_code == 409, again.text
    assert len(_history(factory, user_id, chat_id)) == 2


def test_projection_failure_reports_in_band_and_start_stays_live(
        tmp_path, monkeypatch):
    # The session's chat does not exist in the DB: projection
    # fails, the report says so, the live start stands.
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory, _dbp = _db(tmp_path)
    user_id, _real_chat = _seed_chat(factory)
    store = _store(tmp_path)
    ghost = start_session(
        store, chat_id="no-such-chat", user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW, auto_project=True)
    ghost.record_turn(**_HEARD, recorded_at=NOW)
    store.save_session(ghost)
    controller = LiveVoiceController(
        responder=lambda text: iter(["Hello there."]),
        playback_factory=lambda s: FixturePlayback())
    app = create_app(factory)
    controller.attach_app(app)
    app.state.live_voice_controller = controller
    app.state.live_session_store = store
    client = TestClient(app)
    client.headers.update(
        {"Authorization": f"Bearer {get_or_create_credential()}"})
    started = client.post(f"/api/v1/voice/sessions/{ghost.session_id}/live/start")
    assert started.status_code == 201, started.text
    report = started.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is False
    assert report["error"]
    live = client.get(f"/api/v1/voice/sessions/{ghost.session_id}/live")
    assert live.json()["live"] is True  # the start itself stands
    assert _store(tmp_path).get(ghost.session_id).turns[0].projected is False


# ------------------------------------------- controller law (DB-free)


def test_in_process_controller_start_does_not_back_project(
        tmp_path, monkeypatch):
    factory, _dbp = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_fake_settings(), now=NOW, auto_project=True)
    s.record_turn(**_HEARD, recorded_at=NOW)
    store.save_session(s)
    controller = LiveVoiceController(
        playback_factory=lambda sess: FixturePlayback())
    from runmal.voice.stt import FakeSTTBackend
    from runmal.voice.tts import FakeTTSBackend
    controller.start(s, store=store, tts=FakeTTSBackend(), stt=FakeSTTBackend())
    # The synchronous DB-free controller changed nothing in
    # the chat: back-projection is the async host's act.
    assert _history(factory, user_id, chat_id) == []
    assert auto.pending_turns(s) == 1
    controller.stop(s.session_id)


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, _s, _sess, _u, _chat, _c = _rig(tmp_path, monkeypatch)
    db_path = tmp_path / "test.db"
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
