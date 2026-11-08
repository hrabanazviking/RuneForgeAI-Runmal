"""P-107 - Voice rendered confidence markings (Part VII, DERIVED scope, VX-11).

Pins: the marking view for one landed message (the P-103
provenance origin link resolved into the P-101 session
store, the truth read from P-105's own turn_mishearing -
threshold, bands and suggestion are P-105's, never a second
source), the honesty law (a non-voice message gets NO
marking; an unresolvable voice transcript gets the GAP
marking - evidence_available False, never a silent clean
bill; a turn with no recorded words reports no-evidence
exactly as P-105 does), the additive voice_marking key on
the two thread surfaces (GET chat payload + GET messages,
bare and paged shapes) with stored content verbatim, and
the web renderer under node (low word wrapped with its
punctuation outside the span, XSS escaped first, no low
words renders plain). No network. Migration head stays 0041.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import markings as mark
from runmal.voice import mishearing as mis
from runmal.voice.session import (
    VoiceSessionStore,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-07T12:00:00+00:00"
REPO = Path(__file__).parent.parent
RENDERER = REPO / "src" / "runmal" / "web" / "static" / "renderer.js"


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1"):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=None, settings=_settings(), now=NOW)


def _words(*pairs):
    return tuple(WordConfidence(text, prob) for text, prob in pairs)


def _view(session_id, turn_no, side="transcript", recorded=True):
    return {
        "recorded": recorded,
        "origin": {
            "kind": "manual",
            "via": "voice_session",
            "voice_session_id": session_id,
            "voice_turn_no": turn_no,
            "voice_side": side,
            "stt_backend": "fake-ear",
        },
    }


def _worded_session(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.record_turn(
        transcript_text="take the lift",
        transcript_words=_words(("take", 0.9), ("the", 0.95), ("lift", 0.3)),
        recorded_at=NOW)
    store.save_session(s)
    return store, s


# ------------------------------------------------------- pure views


def test_non_voice_messages_get_no_marking(tmp_path):
    store, s = _worded_session(tmp_path)
    assert mark.message_marking(None, store) is None
    assert mark.message_marking({}, store) is None
    assert mark.message_marking({"recorded": False}, store) is None
    assert mark.message_marking(_view(s.session_id, 1, recorded=False), store) is None
    plain = {"recorded": True, "origin": {"kind": "manual"}}
    assert mark.message_marking(plain, store) is None


def test_response_side_gets_no_marking(tmp_path):
    store, s = _worded_session(tmp_path)
    assert mark.message_marking(_view(s.session_id, 1, side="response"), store) is None


def test_resolved_marking_matches_p105_truth(tmp_path):
    store, s = _worded_session(tmp_path)
    m = mark.message_marking(_view(s.session_id, 1), store)
    assert m["evidence_available"] is True
    assert m["has_confidence_evidence"] is True
    assert m["needs_repeat"] is True
    assert m["threshold"] == mis.LOW_CONFIDENCE_THRESHOLD
    assert m["word_count"] == 3
    assert m["low_confidence_words"] == ["lift"]
    assert m["low_confidence_count"] == 1
    assert m["min_probability"] == 0.3
    assert m["words"][2] == {"text": "lift", "probability": 0.3, "band": "low"}
    truth = mis.turn_mishearing(s.turns[0])
    assert m["mean_probability"] == truth["mean_probability"]
    assert m["suggested_text"] == "take the lift"  # no lexicon yet


def test_marking_suggestion_comes_from_p105_lexicon(tmp_path):
    store, s = _worded_session(tmp_path)
    m = mark.message_marking(_view(s.session_id, 1), store, {"lift": "elevator"})
    assert m["suggested_text"] == "take the elevator"
    assert m["replacements_applied"] == [
        {"misheard": "lift", "replacement": "elevator", "count": 1}]


def test_gap_marking_when_session_or_turn_unresolvable(tmp_path):
    store, s = _worded_session(tmp_path)
    gone = mark.message_marking(_view("no-such-session", 1), store)
    assert gone["evidence_available"] is False
    assert gone["has_confidence_evidence"] is False
    assert gone["needs_repeat"] is False
    assert gone["low_confidence_words"] == []
    assert gone["min_probability"] is None
    missing_turn = mark.message_marking(_view(s.session_id, 99), store)
    assert missing_turn["evidence_available"] is False


def test_no_evidence_turn_reports_no_evidence(tmp_path):
    store = _store(tmp_path)
    s = _session(store)
    s.record_turn(transcript_text="hello", recorded_at=NOW)
    store.save_session(s)
    m = mark.message_marking(_view(s.session_id, 1), store)
    assert m["evidence_available"] is True
    assert m["has_confidence_evidence"] is False
    assert m["needs_repeat"] is False
    assert m["word_count"] == 0


def test_attach_helper_only_touches_qualifying_dicts(tmp_path):
    store, s = _worded_session(tmp_path)
    dicts = [
        {"id": "m1", "provenance": _view(s.session_id, 1)},
        {"id": "m2", "provenance": _view(s.session_id, 1, side="response")},
        {"id": "m3", "provenance": {"recorded": False}},
        {"id": "m4"},
    ]
    assert mark.markings_for_messages(dicts, store) == 1
    assert "voice_marking" in dicts[0]
    assert all("voice_marking" not in d for d in dicts[1:])


# --------------------------------------------------------- HTTP flow


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


def _project_worded_turn(client):
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
              "response_text": "Right away",
              "heard_certain": "Right away",
              "chunks_total": 1, "chunks_played": 1})
    assert turn.status_code == 201, turn.text
    res = client.post(f"/api/v1/voice/sessions/{sid}/project")
    assert res.status_code == 201, res.text
    return chat_id, sid


def test_http_thread_surfaces_carry_the_marking(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    put = client.put("/api/v1/voice/mishearing-replacements",
                     json={"misheard": "lift", "replacement": "elevator"})
    assert put.status_code == 200, put.text
    chat_id, _sid = _project_worded_turn(client)
    plain = client.post(f"/api/v1/chats/{chat_id}/messages",
                        json={"role": "user", "content": "typed line"})
    assert plain.status_code == 201, plain.text
    chat = client.get(f"/api/v1/chats/{chat_id}").json()
    by_role = {m["role"]: m for m in chat["messages"] if m["content"] != "typed line"}
    user_msg = by_role["user"]
    assert user_msg["content"] == "take the lift"  # verbatim, never suggested
    m = user_msg["voice_marking"]
    assert m["has_confidence_evidence"] is True
    assert m["needs_repeat"] is True
    assert m["low_confidence_words"] == ["lift"]
    assert m["suggested_text"] == "take the elevator"
    assert "voice_marking" not in by_role["assistant"]  # response side: none
    typed = [x for x in chat["messages"] if x["content"] == "typed line"][0]
    assert "voice_marking" not in typed
    listing = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    marked = [x for x in listing if "voice_marking" in x]
    assert len(marked) == 1 and marked[0]["id"] == user_msg["id"]
    page = client.get(
        f"/api/v1/chats/{chat_id}/messages?limit=10&offset=0").json()
    marked_page = [x for x in page["messages"] if "voice_marking" in x]
    assert len(marked_page) == 1


def test_http_chat_without_voice_has_no_markings(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "plain"}).json()["id"]
    client.post(f"/api/v1/chats/{chat_id}/messages",
                json={"role": "user", "content": "hello"})
    chat = client.get(f"/api/v1/chats/{chat_id}").json()
    assert all("voice_marking" not in m for m in chat["messages"])


# ------------------------------------------------------------- node


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_renderer_marks_low_words_under_node():
    script = (
        "const r = require(" + repr(str(RENDERER)) + ");"
        "const a = r.renderMarkedTranscript('the lift, please', ['lift']);"
        "const b = r.renderMarkedTranscript('a <script> lift', ['lift']);"
        "const c = r.renderMarkedTranscript('plain words', []);"
        "console.log(a); console.log(b); console.log(c);"
    )
    proc = subprocess.run(["node", "-e", script],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    wrapped, xss, plain = proc.stdout.strip().splitlines()
    assert '<span class="stt-low"' in wrapped
    assert '>lift</span>,' in wrapped  # punctuation outside the span
    assert "<script>" not in xss and "&lt;script&gt;" in xss  # escaped first
    assert '<span class="stt-low"' in xss  # the clean token still marked
    assert "stt-low" not in plain and plain == "plain words"


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"


def test_css_marking_colour_flows_from_a_token():
    # S301 law, pinned for this slice's own rule: the .stt-low
    # tint is a design token, never a raw colour in the rule.
    css = (REPO / "src" / "runmal" / "web" / "static" / "style.css").read_text()
    rule = css.split(".stt-low {", 1)[1].split("}", 1)[0]
    assert "var(--stt-low-tint)" in rule
    assert "rgba(" not in rule and "#" not in rule
    assert "--stt-low-tint:" in css  # defined in the token blocks
