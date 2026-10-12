"""S506 — Turn-taking: endpoint hangover, preemptive trigger, resume
cancellation; fixture scenarios cover pauses and resumed speech."""

from __future__ import annotations

import math

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.turntaking import TurnCoordinator, TurnEventKind, TurnTakingConfig
from runmal.voice.vad import EnergyVadModel


def frame(amplitude: float) -> bytes:
    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000)
         for i in range(FRAME_SAMPLES)])


SPEECH, SILENCE = frame(0.5), frame(0.0)
CFG = TurnTakingConfig(hangover_frames=10, resume_window_frames=25)


def kinds(events):
    return [e.kind for e in events]


def test_simple_turn_preemptive_then_commit():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    events = coord.feed_all([SPEECH] * 8 + [SILENCE] * 60)
    assert kinds(events) == [
        TurnEventKind.SPEECH_STARTED, TurnEventKind.SPEECH_ENDED,
        TurnEventKind.PREEMPTIVE_FINALIZE, TurnEventKind.COMMITTED]
    commit = events[-1]
    assert commit.utterance_id == 1
    assert len(commit.audio) == 8 * len(SPEECH)  # speech only, no tail silence


def test_short_pause_does_not_end_turn():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    frames = [SPEECH] * 6 + [SILENCE] * 5 + [SPEECH] * 6 + [SILENCE] * 60
    events = coord.feed_all(frames)
    assert TurnEventKind.PREEMPTIVE_FINALIZE in kinds(events)
    assert kinds(events).count(TurnEventKind.SPEECH_STARTED) == 1
    assert TurnEventKind.RESUME_CANCEL not in kinds(events)
    commit = events[-1]
    assert commit.kind is TurnEventKind.COMMITTED
    assert commit.utterance_id == 1
    # Both speech halves AND the real mid-turn pause between them: an
    # utterance's audio is its true timeline, trailing silence excluded.
    assert len(commit.audio) == (6 + 5 + 6) * len(SPEECH)


def test_resume_inside_window_cancels_preemptive_and_continues_turn():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    # Pause long enough to pass the hangover (preemptive fires), short
    # enough to stay inside the resume window.
    frames = [SPEECH] * 6 + [SILENCE] * 16 + [SPEECH] * 6 + [SILENCE] * 60
    events = coord.feed_all(frames)
    sequence = kinds(events)
    assert TurnEventKind.PREEMPTIVE_FINALIZE in sequence
    assert TurnEventKind.RESUME_CANCEL in sequence
    assert sequence.index(TurnEventKind.PREEMPTIVE_FINALIZE) < \
        sequence.index(TurnEventKind.RESUME_CANCEL)
    commits = [e for e in events if e.kind is TurnEventKind.COMMITTED]
    assert len(commits) == 1 and commits[0].utterance_id == 1
    assert len(commits[0].audio) == (6 + 16 + 6) * len(SPEECH)


def test_resume_after_window_is_a_new_turn():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    frames = [SPEECH] * 6 + [SILENCE] * 60 + [SPEECH] * 6 + [SILENCE] * 60
    events = coord.feed_all(frames)
    commits = [e for e in events if e.kind is TurnEventKind.COMMITTED]
    assert [c.utterance_id for c in commits] == [1, 2]
    assert TurnEventKind.RESUME_CANCEL not in kinds(events)


def test_flush_commits_pending_utterance():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    events = coord.feed_all([SPEECH] * 5)
    assert events[-1].kind is TurnEventKind.COMMITTED
    assert len(events[-1].audio) == 5 * len(SPEECH)


def test_transient_burst_never_starts_a_turn():
    coord = TurnCoordinator(EnergyVadModel(), CFG)
    events = coord.feed_all([SPEECH] * 2 + [SILENCE] * 50)
    assert events == []
