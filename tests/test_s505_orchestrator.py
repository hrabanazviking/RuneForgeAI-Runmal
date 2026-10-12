"""S505 — Voice orchestrator: deterministic simulated state transitions
for a full turn, an interrupted turn, an empty turn, and error recovery."""

from __future__ import annotations

import math

from runmal.voice.audio import FixturePlayback, floats_to_pcm16
from runmal.voice.orchestrator import SimulatedClock, VoiceOrchestrator, VoiceState
from runmal.voice.stt import FakeSTTBackend
from runmal.voice.tts import FakeTTSBackend, VoiceInfo
from runmal.voice.vad import EnergyVadModel, VadSegmenter

VOICE = VoiceInfo("fake-voice", backend_key="fake-tts")


def frame(amplitude: float) -> bytes:
    from runmal.voice import FRAME_SAMPLES

    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000)
         for i in range(FRAME_SAMPLES)])


SPEECH, SILENCE = frame(0.5), frame(0.0)
UTTERANCE = [SILENCE] * 3 + [SPEECH] * 8 + [SILENCE] * 15


def make_orchestrator(responder=None, **kwargs) -> VoiceOrchestrator:
    return VoiceOrchestrator(
        segmenter=VadSegmenter(EnergyVadModel()),
        stt=FakeSTTBackend("hello companion"),
        responder=responder or (lambda text: iter(["Hello there. ", "How are you?"])),
        tts=FakeTTSBackend(),
        voice=VOICE,
        playback=FixturePlayback(),
        clock=SimulatedClock(),
        **kwargs)


def test_full_turn_state_sequence_is_deterministic():
    orch = make_orchestrator()
    orch.feed_frames(UTTERANCE)
    assert orch.state_sequence() == [
        VoiceState.LISTENING, VoiceState.USER_SPEAKING, VoiceState.FINALIZING,
        VoiceState.THINKING, VoiceState.SYNTHESIZING, VoiceState.SPEAKING,
        VoiceState.LISTENING,
    ]
    (turn,) = orch.turns
    assert turn.transcript.text == "hello companion"
    assert turn.response_text == "Hello there. How are you?"
    assert turn.chunks_played == turn.chunks_total == 2
    assert not turn.interrupted
    stamps = [t.at for t in orch.transitions]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)


def test_same_scenario_repeats_identically():
    a, b = make_orchestrator(), make_orchestrator()
    a.feed_frames(UTTERANCE)
    b.feed_frames(UTTERANCE)
    assert a.state_sequence() == b.state_sequence()
    assert [(t.from_state, t.to_state) for t in a.transitions] == \
        [(t.from_state, t.to_state) for t in b.transitions]


def test_interrupt_during_playback_lands_in_listening():
    orch = make_orchestrator()
    fired = {"done": False}

    def hook(turn_id, frames_played):
        if not fired["done"]:
            fired["done"] = True
            assert orch.interrupt() is True

    orch._frame_hook = hook
    orch.feed_frames(UTTERANCE)
    (turn,) = orch.turns
    assert turn.interrupted
    assert VoiceState.INTERRUPTING in orch.state_sequence()
    assert orch.state is VoiceState.LISTENING


def test_interrupt_when_idle_is_noop():
    orch = make_orchestrator()
    assert orch.interrupt() is False
    assert orch.state is VoiceState.LISTENING
    assert orch.transitions == []


def test_empty_transcript_returns_to_listening_without_thinking():
    orch = make_orchestrator()
    orch.stt = FakeSTTBackend("   ")
    orch.feed_frames(UTTERANCE)
    assert VoiceState.THINKING not in orch.state_sequence()
    assert orch.state is VoiceState.LISTENING


def test_responder_error_goes_through_error_recovery():
    def boom(text):
        raise RuntimeError("backend exploded")
        yield  # pragma: no cover

    orch = make_orchestrator(responder=boom)
    orch.feed_frames(UTTERANCE)
    assert VoiceState.ERROR_RECOVERY in orch.state_sequence()
    assert orch.state is VoiceState.LISTENING
    assert "backend exploded" in orch.turns[-1].error


def test_two_turns_increment_turn_ids():
    orch = make_orchestrator()
    orch.feed_frames(UTTERANCE)
    orch.feed_frames(UTTERANCE)
    assert [t.turn_id for t in orch.turns] == [1, 2]
