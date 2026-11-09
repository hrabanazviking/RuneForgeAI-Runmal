"""P-103 - Voice turn projection (Part VII, DERIVED scope, L2).

Pins: the landing law (transcript verbatim as a user message;
the HEARD response - history_text, certain + uncertainty
marker, unplayed NEVER - as an assistant message; error and
empty turns land nothing they do not have), P-075 provenance
under the P-089 closed-vocabulary doctrine (kind stays
"manual"; scalar origin facts name the voice road; the
response's model is a recorded unknown, never invented),
the projection service (owner-scoped, turn order, idempotent,
per-side resumable, store saved per turn, stopped sessions
project as history), and the HTTP roads on the founding
/api/v1/voice surface. No network: fakes/fixtures only.
Migration head stays 0041.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import provenance as prov_mod
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character
from runmal.db.owners import get_or_create_owner
from runmal.voice import projection as proj
from runmal.voice.session import (
    VoiceSessionStore,
    VoiceTurnRecord,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-07T12:00:00+00:00"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1", character_id=None):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=character_id, settings=_settings(), now=NOW,
    )


def _turn(session, **kw):
    base = dict(recorded_at=NOW)
    base.update(kw)
    return session.record_turn(**base)


# --------------------------------------------------------- planning


def test_plan_full_turn_both_sides(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, transcript_text="hello there", response_text="Hi!",
              heard_certain="Hi!", chunks_total=1, chunks_played=1)
    plan = proj.plan_turn(s, t)
    assert [(p["side"], p["role"], p["content"]) for p in plan] == [
        ("transcript", "user", "hello there"),
        ("response", "assistant", "Hi!"),
    ]


def test_plan_uncertain_marker_unplayed_never_lands(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, response_text="a b c", heard_certain="a",
              heard_uncertain="b", heard_unplayed="c",
              chunks_total=3, chunks_played=2)
    plan = proj.plan_turn(s, t)
    assert len(plan) == 1 and plan[0]["role"] == "assistant"
    assert plan[0]["content"] == "a [uncertain: b\u2026]"
    assert "c" not in plan[0]["content"].replace("[uncertain: b\u2026]", "")


def test_plan_unplayed_only_response_lands_nothing(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, response_text="never heard", heard_unplayed="never heard",
              chunks_total=1, chunks_played=0)
    assert proj.plan_turn(s, t) == []


def test_plan_error_turn_and_empty_turn(tmp_path):
    s = _session(_store(tmp_path))
    err = _turn(s, transcript_text="are you there", error="tts failed",
                chunks_total=1, chunks_played=0)
    plan = proj.plan_turn(s, err)
    assert [(p["side"], p["content"]) for p in plan] == [
        ("transcript", "are you there")]
    empty = _turn(s)
    assert proj.plan_turn(s, empty) == []


def test_plan_resume_omits_landed_side(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, transcript_text="hi", response_text="yo",
              heard_certain="yo", chunks_total=1, chunks_played=1)
    t.projected_user_message_id = "msg-already"
    plan = proj.plan_turn(s, t)
    assert [p["side"] for p in plan] == ["response"]
    t.projected_assistant_message_id = "msg-done"
    assert proj.plan_turn(s, t) == []


# ------------------------------------------------------- provenance


def test_provenance_transcript_facts(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, transcript_text="hello", transcript_language="en")
    rec = proj.transcript_provenance(s, t)
    assert rec["origin"]["kind"] == "manual"  # closed vocabulary (P-089)
    assert rec["origin"]["via"] == "voice_session"
    assert rec["origin"]["voice_session_id"] == s.session_id
    assert rec["origin"]["voice_turn_no"] == 1
    assert rec["origin"]["voice_side"] == "transcript"
    assert rec["origin"]["stt_backend"] == "faster-whisper"
    assert rec["model"]["status"] == "not_applicable"
    assert rec["lore"]["status"] == "not_applicable"
    assert rec["speaker"]["speaker_id"] == "u1"


def test_provenance_response_honest_gaps(tmp_path):
    s = _session(_store(tmp_path), character_id="char-9")
    t = _turn(s, response_text="a b c", heard_certain="a",
              heard_uncertain="b", heard_unplayed="c", interrupted=True,
              chunks_total=3, chunks_played=2)
    rec = proj.response_provenance(s, t)
    assert rec["origin"]["kind"] == "manual"
    assert rec["origin"]["voice_side"] == "response"
    assert rec["origin"]["tts_backend"] == "cosyvoice"
    assert rec["origin"]["heard_certain_chars"] == 1
    assert rec["origin"]["heard_unplayed_chars"] == 1
    assert rec["origin"]["interrupted"] is True
    assert rec["model"]["status"] == "unknown"  # recorded gap, not a claim
    assert rec["preset"]["status"] == "unknown"
    assert rec["speaker"]["speaker_id"] == "char-9"


def test_provenance_survives_tolerant_reader(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, transcript_text="hi", response_text="yo", heard_certain="yo")
    for record in (proj.transcript_provenance(s, t),
                   proj.response_provenance(s, t)):
        doc = prov_mod.parse_document(prov_mod.build_document(record))
        assert doc["recorded"] is True
        active = doc["swipes"]["0"]
        assert active["origin"]["kind"] == "manual"
        assert active["origin"]["via"] == "voice_session"


def test_turn_projection_fields_round_trip():
    t = VoiceTurnRecord(
        turn_no=2, transcript_text="hi", response_text="yo",
        heard_certain="yo", recorded_at=NOW, projected=True,
        projected_user_message_id="m1", projected_assistant_message_id="m2",
        projected_at=NOW)
    assert VoiceTurnRecord.from_dict(t.to_dict()) == t
    legacy = t.to_dict()
    for key in ("projected", "projected_user_message_id",
                "projected_assistant_message_id", "projected_at"):
        del legacy[key]
    old = VoiceTurnRecord.from_dict(legacy)  # pre-P-103 stored shape
    assert old.projected is False and old.projected_user_message_id == ""


# ---------------------------------------------------------- service


def _db(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def _project(factory, session, store, user_id):
    async def run():
        async with factory() as db:
            return await proj.project_session_turns(
                db, user_id=user_id, session=session, store=store)
    return asyncio.run(run())


def _history(factory, user_id, chat_id):
    async def run():
        async with factory() as db:
            msgs = await chats_svc.get_history(db, user_id, chat_id) or []
            return [chats_svc.message_to_dict(m) for m in msgs]
    return asyncio.run(run())


def _seed_chat(factory, title="voice chat", character_name=None):
    async def run():
        async with factory() as db:
            owner = await get_or_create_owner(db)
            char_id = None
            if character_name:
                import json as _json
                char = Character(
                    user_id=owner.id, name=character_name,
                    card_json=_json.dumps({"name": character_name,
                                           "first_mes": "",
                                           "alternate_greetings": []}))
                db.add(char)
                await db.commit()
                char_id = char.id
            chat = await chats_svc.create_chat(db, owner.id, title, char_id)
            return owner.id, chat.id, char_id
    return asyncio.run(run())


def test_service_projects_in_order_with_provenance(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    _turn(s, transcript_text="hello", response_text="Hi there",
          heard_certain="Hi there", chunks_total=1, chunks_played=1)
    _turn(s, transcript_text="and again", response_text="Second",
          heard_certain="Second", chunks_total=1, chunks_played=1)
    store.save_session(s)
    report = _project(factory, s, store, user_id)
    assert report["projected_turns"] == 2 and report["messages_created"] == 4
    assert report["already_projected"] == 0 and report["no_content_turns"] == 0
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hello"), ("assistant", "Hi there"),
        ("user", "and again"), ("assistant", "Second")]
    first = history[0]["provenance"]
    assert first["recorded"] is True
    assert first["origin"]["via"] == "voice_session"
    assert first["origin"]["voice_side"] == "transcript"
    assert first["origin"]["voice_turn_no"] == 1
    assert history[1]["provenance"]["origin"]["voice_side"] == "response"
    assert history[1]["provenance"]["model"]["status"] == "unknown"
    assert s.turns[0].projected and s.turns[0].projected_user_message_id == history[0]["id"]
    assert s.turns[0].projected_assistant_message_id == history[1]["id"]


def test_service_idempotent_second_run(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    _turn(s, transcript_text="hi", response_text="yo", heard_certain="yo",
          chunks_total=1, chunks_played=1)
    store.save_session(s)
    _project(factory, s, store, user_id)
    again = _project(factory, s, store, user_id)
    assert again["messages_created"] == 0 and again["already_projected"] == 1
    assert len(_history(factory, user_id, chat_id)) == 2
    fresh = _store(tmp_path).get(s.session_id)  # state survived via the store
    assert fresh.turns[0].projected is True
    third = _project(factory, fresh, _store(tmp_path), user_id)
    assert third["messages_created"] == 0


def test_service_resume_half_projected(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    t = _turn(s, transcript_text="hi", response_text="yo", heard_certain="yo",
              chunks_total=1, chunks_played=1)
    async def seed_msg():
        async with factory() as db:
            m = await chats_svc.append_message(db, user_id, chat_id, "user", "hi")
            return m.id
    t.projected_user_message_id = asyncio.run(seed_msg())
    store.save_session(s)
    report = _project(factory, s, store, user_id)
    assert report["messages_created"] == 1  # only the missing side landed
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hi"), ("assistant", "yo")]


def test_service_error_empty_and_unplayed_turns(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    _turn(s, transcript_text="you there?", error="no responder wired",
          chunks_total=0, chunks_played=0)
    _turn(s, response_text="unplayed words", heard_unplayed="unplayed words",
          chunks_total=1, chunks_played=0)
    _turn(s)
    store.save_session(s)
    report = _project(factory, s, store, user_id)
    assert report["messages_created"] == 1  # only the spoken question lands
    assert report["projected_turns"] == 1 and report["no_content_turns"] == 2
    history = _history(factory, user_id, chat_id)
    assert [(m["role"], m["content"]) for m in history] == [("user", "you there?")]
    assert all(t.projected for t in s.turns)  # considered, never re-landed


def test_service_stopped_session_projects_history(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    _turn(s, transcript_text="bye", response_text="Farewell",
          heard_certain="Farewell", chunks_total=1, chunks_played=1)
    s.stop("done", at=NOW)
    store.save_session(s)
    report = _project(factory, s, store, user_id)
    assert report["messages_created"] == 2
    assert len(_history(factory, user_id, chat_id)) == 2


def test_service_ownership_refusals(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, _c = _seed_chat(factory)
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    with pytest.raises(proj.ProjectionError):
        _project(factory, foreign, store, user_id)
    ghost = _session(store, chat_id="no-such-chat", user_id=user_id)
    with pytest.raises(KeyError):
        _project(factory, ghost, store, user_id)


def test_service_character_speaker_resolved(tmp_path):
    factory = _db(tmp_path)
    user_id, chat_id, char_id = _seed_chat(factory, character_name="Skald")
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id, character_id=char_id)
    _turn(s, transcript_text="sing", response_text="La!", heard_certain="La!",
          chunks_total=1, chunks_played=1)
    store.save_session(s)
    _project(factory, s, store, user_id)
    history = _history(factory, user_id, chat_id)
    assert history[0]["speaker_id"] == user_id
    assert history[1]["speaker_id"] == char_id
    assert history[1]["speaker_name"] == "Skald"
    assert history[1]["provenance"]["speaker"]["speaker_name"] == "Skald"


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


def _http_session_with_turns(client):
    chat_id = client.post("/api/v1/chats", json={"title": "voice"}).json()["id"]
    sid = client.post(
        "/api/v1/voice/sessions", json={"chat_id": chat_id}).json()["session_id"]
    turn = client.post(
        f"/api/v1/voice/sessions/{sid}/turns",
        json={"transcript_text": "hello", "response_text": "Hi there",
              "heard_certain": "Hi there", "chunks_total": 1, "chunks_played": 1})
    assert turn.status_code == 201, turn.text
    return chat_id, sid


def test_http_project_flow(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id, sid = _http_session_with_turns(client)
    before = client.get(f"/api/v1/voice/sessions/{sid}/projection")
    assert before.status_code == 200 and before.json()["turns_projected"] == 0
    res = client.post(f"/api/v1/voice/sessions/{sid}/project")
    assert res.status_code == 201, res.text
    report = res.json()
    assert report["messages_created"] == 2 and report["projected_turns"] == 1
    chat = client.get(f"/api/v1/chats/{chat_id}").json()
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [
        ("user", "hello"), ("assistant", "Hi there")]
    assert chat["messages"][0]["provenance"]["origin"]["via"] == "voice_session"
    after = client.get(f"/api/v1/voice/sessions/{sid}/projection").json()
    assert after["turns_projected"] == 1 and after["messages_projected"] == 2
    assert after["turns"][0]["user_message_id"] == chat["messages"][0]["id"]
    again = client.post(f"/api/v1/voice/sessions/{sid}/project")
    assert again.json()["messages_created"] == 0  # idempotent over HTTP too
    assert len(client.get(f"/api/v1/chats/{chat_id}").json()["messages"]) == 2


def test_http_unknown_and_foreign_session_404(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    assert client.post("/api/v1/voice/sessions/nope/project").status_code == 404
    assert client.get("/api/v1/voice/sessions/nope/projection").status_code == 404
    chat_id = client.post("/api/v1/chats", json={"title": "x"}).json()["id"]
    store = _store(tmp_path)
    foreign = _session(store, chat_id=chat_id, user_id="someone-else")
    _turn(foreign, transcript_text="hi")
    store.save_session(foreign)
    res = client.post(f"/api/v1/voice/sessions/{foreign.session_id}/project")
    assert res.status_code == 404  # owner scoping never leaks existence
    got = client.get(f"/api/v1/voice/sessions/{foreign.session_id}/projection")
    assert got.status_code == 404
    assert client.get(f"/api/v1/chats/{chat_id}").json()["messages"] == []


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
