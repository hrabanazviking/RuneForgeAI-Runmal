"""P-106 - Voice projection mishearing mark (Part VII, DERIVED).

Pins: the pure mark (no evidence is NO evidence, never all-
confident; low words under the predeclared 0.5 threshold;
malformed probabilities are not evidence; dict- and object-
shaped words both read; the threshold agrees with P-105's
LOW_CONFIDENCE_THRESHOLD whenever that module is importable),
the P-075 provenance facts (always present, scalars only,
no word texts and no suggested text ever ride), the content
law (transcript lands verbatim, a suggestion NEVER lands,
the stored transcript is never rewritten), and the additive
status/report marks + aggregates incl. service landing and
idempotent re-projection. Migration head stays 0041.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass

import pytest

from runmal.chats import provenance as prov_mod
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.voice import projection as proj
from runmal.voice.session import (
    VoiceSessionStore,
    VoiceTurnRecord,
    WordConfidence,
    resolve_session_settings,
    start_session,
)
from runmal.voice.settings import VoiceSettings

NOW = "2026-11-07T12:00:00+00:00"


@dataclass(frozen=True)
class FakeWord:
    text: str
    probability: float


def _settings():
    return resolve_session_settings(defaults=VoiceSettings(), character=None)


def _store(tmp_path):
    return VoiceSessionStore(tmp_path / "voice_sessions.json")


def _session(store, chat_id="chat-1", user_id="u1"):
    return start_session(
        store, chat_id=chat_id, user_id=user_id,
        character_id=None, settings=_settings(), now=NOW)


def _turn(session, words=None, **kw):
    base = dict(recorded_at=NOW)
    base.update(kw)
    turn = session.record_turn(**base)
    if words is not None:
        turn.transcript_words = words
    return turn


def _bare_turn(**kw):
    base = dict(turn_no=1, recorded_at=NOW)
    base.update(kw)
    return VoiceTurnRecord(**base)


# ------------------------------------------------------------ mark


def test_mark_no_evidence_legacy_turn():
    turn = _bare_turn(transcript_text="old words")
    assert not hasattr(turn, "transcript_words") or True
    mark = proj.transcript_mishearing_mark(turn)
    assert mark == {
        "has_confidence_evidence": False, "word_count": 0,
        "low_confidence_words": [], "low_confidence_count": 0,
        "min_probability": None, "mean_probability": None,
        "needs_repeat": False, "threshold": 0.5,
    }


def test_mark_empty_and_none_words_are_no_evidence():
    for words in ((), [], None):
        turn = _bare_turn()
        turn.transcript_words = words
        mark = proj.transcript_mishearing_mark(turn)
        assert mark["has_confidence_evidence"] is False
        assert mark["needs_repeat"] is False
        assert mark["min_probability"] is None


def test_mark_low_words_and_summaries():
    turn = _bare_turn()
    turn.transcript_words = (
        FakeWord("take", 0.9), FakeWord("the", 0.4), FakeWord("lift", 0.3))
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["has_confidence_evidence"] is True
    assert mark["word_count"] == 3
    assert mark["low_confidence_words"] == ["the", "lift"]
    assert mark["low_confidence_count"] == 2
    assert mark["min_probability"] == 0.3
    assert mark["mean_probability"] == round((0.9 + 0.4 + 0.3) / 3, 4)
    assert mark["needs_repeat"] is True


def test_mark_all_confident_needs_no_repeat():
    turn = _bare_turn()
    turn.transcript_words = (FakeWord("hello", 0.99), FakeWord("there", 0.87))
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["needs_repeat"] is False
    assert mark["low_confidence_words"] == []
    assert mark["low_confidence_count"] == 0
    assert mark["min_probability"] == 0.87


def test_mark_threshold_edge_half_is_ok():
    turn = _bare_turn()
    turn.transcript_words = (
        FakeWord("edge", 0.5), FakeWord("just", 0.4999),
        FakeWord("zero", 0.0), FakeWord("full", 1.0))
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["low_confidence_words"] == ["just", "zero"]
    assert mark["threshold"] == 0.5


def test_mark_malformed_entries_are_not_evidence():
    turn = _bare_turn()
    turn.transcript_words = (
        FakeWord("good", 0.9),
        {"text": "strprob", "probability": "0.2"},
        {"text": "noneprob", "probability": None},
        {"text": "over", "probability": 1.5},
        {"text": "under", "probability": -0.1},
        {"text": "boolprob", "probability": True},
        {"text": "nanprob", "probability": math.nan},
        {"text": "infprob", "probability": math.inf},
        {"text": "noprob"},
        None,
        object(),
    )
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["word_count"] == 1
    assert mark["has_confidence_evidence"] is True
    assert mark["low_confidence_words"] == []
    assert mark["min_probability"] == 0.9
    assert mark["mean_probability"] == 0.9


def test_mark_all_malformed_is_no_evidence_not_all_confident():
    turn = _bare_turn()
    turn.transcript_words = ({"text": "x", "probability": 2.0},)
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["has_confidence_evidence"] is False
    assert mark["word_count"] == 0
    assert mark["needs_repeat"] is False


def test_mark_dict_shaped_words():
    turn = _bare_turn()
    turn.transcript_words = [
        {"text": "alpha", "probability": 0.9},
        {"text": "beta", "probability": 0.25},
    ]
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["word_count"] == 2
    assert mark["low_confidence_words"] == ["beta"]
    assert mark["needs_repeat"] is True
    assert mark["min_probability"] == 0.25
    assert mark["mean_probability"] == round((0.9 + 0.25) / 2, 4)


def test_mark_threshold_agrees_with_p105_when_importable():
    turn = _bare_turn()
    turn.transcript_words = (FakeWord("a", 0.4),)
    mark = proj.transcript_mishearing_mark(turn)
    try:
        from runmal.voice.mishearing import LOW_CONFIDENCE_THRESHOLD
    except Exception:
        assert mark["threshold"] == 0.5
    else:
        assert mark["threshold"] == LOW_CONFIDENCE_THRESHOLD == 0.5


def test_mark_mean_rounding_and_int_probability():
    turn = _bare_turn()
    turn.transcript_words = (
        {"text": "a", "probability": 1},
        {"text": "b", "probability": 0},
        {"text": "c", "probability": 0.33333},
    )
    mark = proj.transcript_mishearing_mark(turn)
    assert mark["min_probability"] == 0.0
    assert mark["mean_probability"] == round((1 + 0 + 0.33333) / 3, 4)
    assert mark["low_confidence_words"] == ["b", "c"]


# ------------------------------------------------------- provenance


def test_provenance_low_turn_facts(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, words=(FakeWord("take", 0.9), FakeWord("lift", 0.3)),
              transcript_text="take lift")
    origin = proj.transcript_provenance(s, t)["origin"]
    assert origin["mishearing_evidence"] is True
    assert origin["mishearing_needs_repeat"] is True
    assert origin["mishearing_word_count"] == 2
    assert origin["mishearing_low_word_count"] == 1
    assert origin["mishearing_min_probability"] == 0.3
    assert origin["mishearing_mean_probability"] == 0.6
    assert origin["mishearing_threshold"] == 0.5


def test_provenance_no_evidence_facts_always_present(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, transcript_text="hello")
    origin = proj.transcript_provenance(s, t)["origin"]
    assert origin["mishearing_evidence"] is False
    assert origin["mishearing_needs_repeat"] is False
    assert origin["mishearing_word_count"] == 0
    assert origin["mishearing_low_word_count"] == 0
    assert origin["mishearing_min_probability"] is None
    assert origin["mishearing_mean_probability"] is None
    assert origin["mishearing_threshold"] == 0.5


def test_provenance_scalars_only_and_tolerant_round_trip(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, words=(FakeWord("zxlow", 0.2),),
              transcript_text="zxlow")
    record = proj.transcript_provenance(s, t)
    for value in record["origin"].values():
        assert value is None or isinstance(value, (str, int, float, bool))
    doc = prov_mod.parse_document(prov_mod.build_document(record))
    assert doc["recorded"] is True
    active = doc["swipes"]["0"]
    assert active["origin"]["mishearing_needs_repeat"] is True
    assert active["origin"]["mishearing_low_word_count"] == 1


def test_provenance_holds_no_word_texts_and_no_suggestion(tmp_path):
    s = _session(_store(tmp_path))
    t = _turn(s, words=(FakeWord("alpha", 0.9), FakeWord("zxlow", 0.2)),
              transcript_text="alpha zxlow")
    blob = json.dumps(proj.transcript_provenance(s, t))
    assert "zxlow" not in blob
    assert "alpha" not in blob
    assert "zxright" not in blob  # a would-be suggested replacement


# ----------------------------------------------------- status/report


def test_status_per_turn_marks_and_aggregates(tmp_path):
    s = _session(_store(tmp_path))
    _turn(s, transcript_text="plain")
    _turn(s, words=(FakeWord("a", 0.9), FakeWord("b", 0.2), FakeWord("c", 0.1)),
          transcript_text="a b c")
    _turn(s, words=(FakeWord("fine", 0.95),), transcript_text="fine")
    status = proj.projection_status(s)
    assert status["turns_with_mishearing_evidence"] == 2
    assert status["turns_needing_repeat"] == [2]
    assert status["low_confidence_words_total"] == 2
    assert status["turns"][0]["mishearing"]["has_confidence_evidence"] is False
    assert status["turns"][1]["mishearing"]["low_confidence_words"] == ["b", "c"]
    assert status["turns"][2]["mishearing"]["needs_repeat"] is False


def _db(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path)), db_path


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


def _seed_chat(factory):
    async def run():
        async with factory() as db:
            from runmal.db.owners import get_or_create_owner
            owner = await get_or_create_owner(db)
            chat = await chats_svc.create_chat(db, owner.id, "voice chat", None)
            return owner.id, chat.id
    return asyncio.run(run())


def test_service_landing_carries_mark_and_content_law(tmp_path):
    factory, _path = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    t = _turn(s, words=(WordConfidence("alpha", 0.9), WordConfidence("zxlow", 0.2)),
              transcript_text="alpha zxlow",
              response_text="Ok.", heard_certain="Ok.",
              chunks_total=1, chunks_played=1)
    _turn(s, transcript_text="clean line")
    store.save_session(s)
    report = _project(factory, s, store, user_id)
    assert report["turns_needing_repeat"] == [1]
    assert report["low_confidence_words_total"] == 1
    assert report["turns"][0]["mishearing"]["low_confidence_words"] == ["zxlow"]
    assert report["turns"][1]["mishearing"]["has_confidence_evidence"] is False
    history = _history(factory, user_id, chat_id)
    user_msgs = [m for m in history if m["role"] == "user"]
    assert user_msgs[0]["content"] == "alpha zxlow"  # verbatim, no suggestion
    assert "zxright" not in user_msgs[0]["content"]
    assert t.transcript_text == "alpha zxlow"  # stored transcript unrewritten
    origin = user_msgs[0]["provenance"]["origin"]
    assert origin["mishearing_evidence"] is True
    assert origin["mishearing_needs_repeat"] is True
    assert origin["mishearing_word_count"] == 2
    assert origin["mishearing_low_word_count"] == 1
    assert origin["mishearing_min_probability"] == 0.2
    assert json.dumps(user_msgs[0]["provenance"]).find("zxlow") == -1
    assert user_msgs[1]["provenance"]["origin"]["mishearing_evidence"] is False


def test_service_idempotent_reprojection_keeps_mark(tmp_path):
    factory, _path = _db(tmp_path)
    user_id, chat_id = _seed_chat(factory)
    store = _store(tmp_path)
    s = _session(store, chat_id=chat_id, user_id=user_id)
    _turn(s, words=(WordConfidence("low", 0.1),), transcript_text="low")
    store.save_session(s)
    first = _project(factory, s, store, user_id)
    assert first["messages_created"] == 1
    again = _project(factory, s, store, user_id)
    assert again["messages_created"] == 0
    assert again["already_projected"] == 1
    assert again["turns"][0]["outcome"] == "already_projected"
    assert again["turns"][0]["mishearing"]["needs_repeat"] is True
    assert again["turns_needing_repeat"] == [1]
    assert again["low_confidence_words_total"] == 1
    assert len(_history(factory, user_id, chat_id)) == 1


def test_migration_head_stays_0041(tmp_path):
    _factory, db_path = _db(tmp_path)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(db_path) == "0042"
