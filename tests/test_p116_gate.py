"""P-116 Part VII gate battery: Voice, the Voxta Way, whole.

Gate discipline (P-030 / P-100 pattern): the gate builds no
new behaviour; it judges the banked Part VII slices
(P-101..P-114, plus P-115 by auto-discovery) end to end
through their own public contracts, from measured evidence
only. Part VII's slice definitions are DERIVED (the filed
roadmap gives Part VII only its part line); the census this
gate judges is the one the banked slice docs declare.

- Area A (census): every P-101..P-114 voice surface is
  present - modules, service functions, HTTP roads, the
  voice __init__ module map, and the P-091 voice citizens
  inside the P-113 custody coverage.
- Area B (one world, together): one voice world walks
  sessions -> turns -> mishearing truth -> projection ->
  rendered markings -> repeat signal -> acknowledgement ->
  mishearing report -> latency view -> affects snapshot,
  and every surface AGREES with the one truth source
  (P-105); auto-projection and live-start back-projection
  land the same turns through the same landing service.
- Area C (P-115 auto-discovery): the repeat-request digest
  banks after this gate's base. Where repeat_digest is
  present it is exercised in full (counts are the P-108
  views' sums; aging is arithmetic from an injected now);
  where absent the pending state is pinned at equal
  strength. Either way the P-108 surface must hold.
- Area D (honest accounting): the carried limitations are
  pinned as measured facts, never loosened: the VX-12
  engine half (affects consumed by no backend), the
  character-asks half on the P-102 responder seam, L3
  host-explicit registration (empty boot registry), the
  single P-105 threshold source, the DB-free in-process
  live controller, and no-evidence-is-not-zero.
- Hygiene: migration head stays 0041; the gate world
  (ZqxGate116) lives only in this battery.

Clean-room note: the gate world is fresh-authored for this
gate (P-005 discipline); no SillyTavern or Voxta source was
inspected, and no real user files are read. The gate's test
turns carry word-confidence fixtures only - no fabricated
dialogue beyond the precedents' test-data allowance
(P-075 law). Plain pytest functions, no test classes.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import custody as cu
from runmal.plugins import service as plugin_service
from runmal.voice import affects as aff
from runmal.voice import autoproject as auto
from runmal.voice import latency as lat
from runmal.voice import markings as mark
from runmal.voice import mishearing as mis
from runmal.voice import projection as proj
from runmal.voice import repeat_requests as rr
from runmal.voice.audio import FixturePlayback
from runmal.voice.live import (
    LiveVoiceController,
    LiveVoiceError,
    unavailable_responder,
)
from runmal.voice.session import (
    ProviderTruth,
    SessionSettings,
    VoiceSessionStore,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

REPO = Path(__file__).parent.parent
Z = "ZqxGate116"
NOW = "2026-11-08T12:00:00+00:00"
LATER = "2026-11-08T12:10:00+00:00"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _fake_settings():
    truth = ProviderTruth(
        kind="tts", backend="fake-tts", known=False, verified=False,
        admission="unknown", selected_via="default")
    return SessionSettings(
        tts_backend="fake-tts", stt_backend="fake-stt",
        voice_id="fake-voice", language="en", tts_truth=truth,
        stt_truth=ProviderTruth(
            kind="stt", backend="fake-stt", known=False,
            verified=False, admission="unknown",
            selected_via="default"))


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1", **kw):
    return start_session(
        store, chat_id=chat_id, user_id=user_id, character_id=None,
        settings=_settings(), now=NOW, **kw)


def _words(*pairs):
    return tuple(WordConfidence(t, p) for t, p in pairs)


def _doubted_session(store, chat_id="chat-1"):
    """Two turns: turn 1 doubted (one low word), turn 2 clean."""
    s = _session(store, chat_id=chat_id)
    s.record_turn(
        transcript_text="weather gate words", recorded_at=NOW,
        transcript_words=_words(("weather", 0.91), ("gate", 0.21),
                                ("words", 0.88)))
    s.record_turn(
        transcript_text="clear sky", recorded_at=NOW,
        transcript_words=_words(("clear", 0.97), ("sky", 0.93)))
    store.save_session(s)
    return s


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


# -- Area A: the Part VII census is present ---------------------


def test_a_voice_modules_and_services_present():
    expected = {
        "session": ["start_session", "VoiceSessionStore",
                    "resolve_session_settings"],
        "live": ["LiveVoiceController", "build_live_orchestrator"],
        "projection": ["project_session_turns", "projection_status",
                       "transcript_mishearing_mark"],
        "autoproject": ["pending_turns", "autoproject_status"],
        "mishearing": ["turn_mishearing", "session_mishearing",
                       "mishearing_aggregate",
                       "session_mishearing_report", "ReplacementStore"],
        "markings": ["message_marking", "markings_for_messages"],
        "repeat_requests": ["turn_repeat_request",
                            "session_repeat_requests",
                            "AcknowledgementStore",
                            "housekeeping_view",
                            "prune_inert_acknowledgements"],
        "affects": ["vocabulary_view", "consumption_view",
                    "normalize_affect", "affect_view"],
        "latency": ["turn_latency_view", "session_latency_view"],
    }
    for module_name, funcs in expected.items():
        module = importlib.import_module(f"runmal.voice.{module_name}")
        for name in funcs:
            assert hasattr(module, name), f"{module_name}.{name} missing"
    for router_name in ("router", "live_router", "projection_router",
                        "autoproject_router", "mishearing_router",
                        "repeat_router"):
        module = importlib.import_module(f"runmal.voice.{router_name}")
        assert hasattr(module, "router"), router_name


def test_a_http_roads_present(tmp_path, monkeypatch):
    # The census reads the voice routers' own route tables
    # (the app includes them under /api/v1; the app-level
    # route tree wraps included routers opaquely).
    paths = set()
    for name in ("router", "live_router", "projection_router",
                 "autoproject_router", "mishearing_router",
                 "repeat_router"):
        module = importlib.import_module(f"runmal.voice.{name}")
        for route in module.router.routes:
            paths.add("/api/v1" + getattr(route, "path", ""))
    for road in (
            "/api/v1/voice/sessions",
            "/api/v1/voice/sessions/{session_id}",
            "/api/v1/voice/sessions/{session_id}/stop",
            "/api/v1/voice/sessions/{session_id}/turns",
            "/api/v1/voice/sessions/{session_id}/live/start",
            "/api/v1/voice/sessions/{session_id}/live/speak",
            "/api/v1/voice/sessions/{session_id}/live/stop",
            "/api/v1/voice/sessions/{session_id}/projection",
            "/api/v1/voice/sessions/{session_id}/auto-project",
            "/api/v1/voice/sessions/{session_id}/mishearings",
            "/api/v1/voice/sessions/{session_id}/mishearing-report",
            "/api/v1/voice/sessions/{session_id}/repeat-requests",
            "/api/v1/voice/repeat-requests/housekeeping",
            "/api/v1/voice/sessions/{session_id}/latency",
            "/api/v1/voice/sessions/{session_id}/affect",
            "/api/v1/voice/affects"):
        assert road in paths, road
    # The P-115 digest road is covered by auto-discovery
    # (Area C): present exactly when P-115 has banked.
    digest_road = "/api/v1/voice/repeat-requests/digest" in paths
    assert digest_road is hasattr(rr, "repeat_digest")


def test_a_module_map_and_slice_docs_present():
    init_text = (REPO / "src" / "runmal" / "voice" / "__init__.py"
                 ).read_text(encoding="utf-8")
    for token in ("session", "live", "projection", "autoproject",
                  "mishearing", "repeat_requests", "affects",
                  "latency", "P-101", "P-102", "P-103", "P-104",
                  "P-105", "P-108", "P-109", "P-110", "P-114"):
        assert token in init_text, token
    for doc in ("VOICE_SESSIONS_2026-11-07.md",
                "LIVE_VOICE_ORCHESTRATOR_2026-11-07.md",
                "VOICE_TURN_PROJECTION_2026-11-07.md",
                "VOICE_AUTO_PROJECTION_2026-11-07.md",
                "VOICE_MISHEARING_2026-11-07.md",
                "VOICE_PROJECTION_MISHEARING_MARK_2026-11-07.md",
                "VOICE_RENDERED_MARKINGS_2026-11-08.md",
                "VOICE_REPEAT_REQUESTS_2026-11-08.md",
                "VOICE_AFFECTS_2026-11-08.md",
                "VOICE_LATENCY_EVIDENCE_2026-11-08.md",
                "VOICE_REPEAT_HOUSEKEEPING_2026-11-08.md",
                "VOICE_LIVE_START_PROJECTION_2026-11-08.md",
                "PLUGIN_CUSTODY_COVERAGE_2026-11-08.md",
                "VOICE_MISHEARING_REPORT_2026-11-08.md"):
        assert (REPO / "docs" / doc).exists(), doc


def test_a_voice_citizens_inside_custody_coverage():
    coverage = cu.custody_coverage()
    assert coverage["citizens"] == list(cu.CITIZEN_PLUGIN_IDS)
    assert len(cu.CITIZEN_PLUGIN_IDS) == 14
    for plugin_id in ("runmal.tts", "runmal.stt",
                      "runmal.game-bridge",
                      "runmal.plugin-settings-ui"):
        assert plugin_id in cu.CITIZEN_PLUGIN_IDS, plugin_id


# -- Area B: one world, every surface together ------------------


def test_b_session_lifecycle_and_settings_truth(tmp_path):
    store = _store(tmp_path)
    s = _session(store, chat_id="chat-1")
    assert s.active is True
    assert s.settings.tts_truth.selected_via in (
        "character", "default", "fallback")
    assert s.settings.stt_truth.kind == "stt"
    second = _session(store, chat_id="chat-1")
    fresh = _store(tmp_path)
    assert fresh.get(s.session_id).active is False
    assert fresh.get(s.session_id).stop_note == "superseded"
    assert fresh.active_for_chat("chat-1").session_id == second.session_id
    second.stop("done", at=LATER)
    store.save_session(second)
    assert _store(tmp_path).get(second.session_id).active is False


def test_b_mishearing_truth_repeat_and_report_agree(tmp_path):
    store = _store(tmp_path)
    s = _doubted_session(store)
    truth = mis.session_mishearing(s)
    assert truth["turns_needing_repeat"] == [1]
    assert truth["low_confidence_words_total"] == 1
    assert truth["threshold"] == mis.LOW_CONFIDENCE_THRESHOLD
    signal = rr.session_repeat_requests(s)
    assert signal["has_pending"] is True
    assert signal["pending_turns"] == [1]
    assert signal["threshold"] == truth["threshold"]
    report = mis.session_mishearing_report(s)
    assert report["turns_needing_repeat"] == [1]
    agg = report["aggregate"]
    assert agg["words_total"] == 5
    assert agg["words_low"] == 1
    status = proj.projection_status(s)
    assert status["turns_needing_repeat"] == [1]
    assert status["low_confidence_words_total"] == 1
    turn_mark = proj.transcript_mishearing_mark(s.turns[0])
    assert turn_mark["needs_repeat"] is True
    assert turn_mark["low_confidence_words"] == ["gate"]


def test_b_acknowledgement_and_housekeeping_close_the_loop(tmp_path):
    store = _store(tmp_path)
    s = _doubted_session(store)
    acks = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    acks.acknowledge(s.session_id, 1, "gate host", at=LATER)
    signal = rr.session_repeat_requests(s, store=acks)
    assert signal["has_pending"] is False
    assert signal["acknowledged_count"] == 1
    view = rr.housekeeping_view(acks, {s.session_id})
    assert view["live_acknowledged_sessions"] == 1
    assert view["inert_records"] == 0
    acks.acknowledge("ghost-session", 2, at=NOW)
    view = rr.housekeeping_view(acks, {s.session_id})
    assert view["inert_session_ids"] == ["ghost-session"]
    result = rr.prune_inert_acknowledgements(acks, {s.session_id})
    assert result["removed_records"] == 1
    assert acks.get(s.session_id, 1) is not None
    assert acks.get("ghost-session", 2) is None


def test_b_projection_lands_and_markings_render(tmp_path):
    factory, _ = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _doubted_session(store, chat_id=chat_id)
    s.user_id = user_id
    store.save_session(s)

    async def run():
        async with factory() as db:
            return await proj.project_session_turns(
                db, user_id=user_id, session=s, store=store)
    outcome = asyncio.run(run())
    assert outcome["projected_turns"] == 2
    history = _history(factory, user_id, chat_id)
    assert len(history) == 2
    assert history[0]["content"] == "weather gate words"
    assert mark.markings_for_messages(history, store) == 2
    marked = [m for m in history if "voice_marking" in m]
    assert len(marked) == 2
    assert sum(1 for m in marked if m["voice_marking"]["needs_repeat"]) == 1
    marking = marked[0]["voice_marking"]
    assert marking["needs_repeat"] is True
    assert marking["low_confidence_words"] == ["gate"]
    assert marking["threshold"] == mis.LOW_CONFIDENCE_THRESHOLD
    fresh = _store(tmp_path).get(s.session_id)
    assert proj.projection_status(fresh)["turns_projected"] == 2


def test_b_latency_and_affects_views_are_honest(tmp_path):
    store = _store(tmp_path)
    s = _doubted_session(store)
    view = lat.session_latency_view(s)
    assert view["turn_count"] == 2
    assert view["turns_with_evidence"] == 0
    assert view["aggregate"] == {}
    assert all(t["has_latency_evidence"] is False for t in view["turns"])
    resolved, source = aff.affect_from_params({"affect": "whispering"})
    assert (resolved, source) == ("whispering", "profile")
    view_affect = aff.affect_view(resolved, source)
    assert view_affect["consumed"] is False
    vocab = aff.vocabulary_view()
    assert vocab["default"] in vocab["affects"]
    assert aff.consumption_view()["consumed_by_backends"] is False
    snap = s.to_dict()
    assert "settings" in snap


def _live_rig(tmp_path, monkeypatch, *, auto_project, turns):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory, _ = _db(tmp_path)
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
    client.headers.update(
        {"Authorization": f"Bearer {get_or_create_credential()}"})
    return client, factory, store, session, user_id, chat_id


_HEARD = dict(
    transcript_text="hello", response_text="a b c",
    heard_certain="a", heard_uncertain="b", heard_unplayed="c",
    chunks_total=3, chunks_played=2)


def test_b_live_start_back_projects_opted_in_turns(tmp_path, monkeypatch):
    client, factory, store, s, user_id, chat_id = _live_rig(
        tmp_path, monkeypatch, auto_project=True, turns=[_HEARD])
    assert auto.pending_turns(s) == 1
    started = client.post(
        f"/api/v1/voice/sessions/{s.session_id}/live/start")
    assert started.status_code == 201, started.text
    report = started.json()["auto_projection"]
    assert report["attempted"] is True and report["ok"] is True
    assert report["projected_turns"] == 1
    history = _history(factory, user_id, chat_id)
    assert [m["content"] for m in history] == [
        "hello", "a [uncertain: b\u2026]"]
    assert _store(tmp_path).get(s.session_id).turns[0].projected is True


def test_b_http_session_turn_and_report_roads(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    factory, _ = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    client = TestClient(create_app(factory))
    client.headers.update(
        {"Authorization": f"Bearer {get_or_create_credential()}"})
    created = client.post("/api/v1/chats", json={"title": f"{Z} Hall"})
    assert created.status_code == 201, created.text
    http_chat = created.json()["id"]
    started = client.post("/api/v1/voice/sessions",
                          json={"chat_id": http_chat})
    assert started.status_code == 201, started.text
    session_id = started.json()["session_id"]
    report = client.get(
        f"/api/v1/voice/sessions/{session_id}/mishearing-report")
    assert report.status_code == 200, report.text
    assert report.json()["aggregate"]["words_total"] == 0
    repeats = client.get(
        f"/api/v1/voice/sessions/{session_id}/repeat-requests")
    assert repeats.status_code == 200, repeats.text
    assert repeats.json()["has_pending"] is False
    latency = client.get(f"/api/v1/voice/sessions/{session_id}/latency")
    assert latency.status_code == 200, latency.text
    assert latency.json()["turns_with_evidence"] == 0


# -- Area C: P-115 digest, by auto-discovery --------------------


def test_c_digest_discovery_state_is_coherent(tmp_path):
    store = _store(tmp_path)
    s = _doubted_session(store)
    signal = rr.session_repeat_requests(s)
    assert signal["pending_count"] == 1  # P-108 holds either way
    if hasattr(rr, "repeat_digest"):
        digest = rr.repeat_digest([s], now=LATER)
        assert digest["pending_count"] == signal["pending_count"]
        assert digest["sessions_total"] == 1
    else:
        # Pending state, pinned at equal strength: the digest
        # surface does not exist on this base and nothing in
        # the tree pretends otherwise.
        assert not hasattr(rr, "repeat_digest")
        init_text = (REPO / "src" / "runmal" / "voice" / "__init__.py"
                     ).read_text(encoding="utf-8")
        assert "digest" not in init_text.lower()


def test_c_digest_aging_when_present(tmp_path):
    if not hasattr(rr, "repeat_digest"):
        pytest.skip("P-115 digest not on this base (pending banking)")
    store = _store(tmp_path)
    s = _doubted_session(store)
    acks = rr.AcknowledgementStore(tmp_path / rr.ACK_FILENAME)
    digest = rr.repeat_digest([s], store=acks, now=LATER)
    assert digest["pending_count"] == 1
    assert digest["acknowledged_count"] == 0
    assert digest["pending_age_seconds"]["oldest_seconds"] == 600.0
    acks.acknowledge(s.session_id, 1, "gate host", at=LATER)
    digest = rr.repeat_digest([s], store=acks, now=LATER)
    assert digest["pending_count"] == 0
    assert digest["acknowledged_count"] == 1
    empty = rr.repeat_digest([], now=LATER)
    assert empty["sessions_total"] == 0
    assert empty["pending_count"] == 0


# -- Area D: honest accounting, pinned --------------------------


def test_d_vx12_engine_half_stays_open_as_data():
    view = aff.consumption_view()
    assert view["consumed_by_backends"] is False
    assert view["voice_info_field"] is False
    assert "no TTS backend accepts or renders an affect yet" in view["note"]
    assert aff.affect_view("neutral", "default")["consumed"] is False


def test_d_character_asks_half_rides_the_responder_seam():
    with pytest.raises(LiveVoiceError):
        list(unavailable_responder("anything"))
    params = inspect.signature(LiveVoiceController.__init__).parameters
    assert "responder" in params  # the seam is the constructor's


def test_d_l3_boot_registry_empty_by_design(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    info = plugin_service.plugin_api_info(registry)
    assert info["registered"] == 0 and info["enabled"] == 0


def test_d_single_threshold_source():
    assert proj._threshold() == mis.LOW_CONFIDENCE_THRESHOLD == 0.5
    assert mis.word_band(0.49) == "low"
    assert mis.word_band(0.5) == "ok"


def test_d_live_controller_is_db_free_in_process():
    for method in ("start", "speak", "stop"):
        params = inspect.signature(
            getattr(LiveVoiceController, method)).parameters
        assert "db" not in params, method
        assert "session_factory" not in params, method


def test_d_no_evidence_is_not_zero(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    truth = mis.session_mishearing(s)
    assert truth["turns_with_evidence"] == 0
    report = mis.session_mishearing_report(s)
    assert report["aggregate"]["has_confidence_evidence"] is False
    assert report["aggregate"]["probability"]["mean"] is None
    assert rr.session_repeat_requests(s)["has_pending"] is False


# -- Hygiene ------------------------------------------------------


def test_hygiene_migration_head_and_part_span(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    roadmap = (REPO / "docs"
               / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
               ).read_text(encoding="utf-8")
    assert "P-101" in roadmap and "P-116" in roadmap
    assert "Voice, the Voxta Way" in roadmap


def test_hygiene_gate_world_lives_only_in_this_battery():
    src = REPO / "src" / "runmal"
    for path in src.rglob("*.py"):
        assert Z not in path.read_text(encoding="utf-8"), path
