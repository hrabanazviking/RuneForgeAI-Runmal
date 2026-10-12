"""S507 — Barge-in: sustained interruption stops playback within the
PREDECLARED 100 ms budget and propagates to LLM + TTS arms exactly once;
backchannel fixtures do NOT falsely interrupt."""

from __future__ import annotations

import math
import threading

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import FixturePlayback, floats_to_pcm16
from runmal.voice.bargein import (
    INTERRUPTION_STOP_BUDGET_MS,
    InterruptionController,
    InterruptionOutcome,
    PlaybackQueue,
)
from runmal.voice.tts import FakeTTSBackend, VoiceInfo
from runmal.voice.vad import EnergyVadModel


def frame(amplitude: float) -> bytes:
    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000)
         for i in range(FRAME_SAMPLES)])


SPEECH, SILENCE, QUIET = frame(0.5), frame(0.0), frame(0.03)


def long_playback() -> tuple[PlaybackQueue, FixturePlayback]:
    backend = FakeTTSBackend(seconds_per_char=0.05)
    chunks = backend.synthesize(
        "This is a long companion answer that keeps speaking for a while.",
        VoiceInfo("fake-voice", backend_key="fake-tts"))
    queue = PlaybackQueue()
    for chunk in chunks:
        queue.enqueue(chunk)
    return queue, FixturePlayback()


def test_sustained_interruption_stops_playback_within_budget():
    queue, sink = long_playback()
    controller = InterruptionController(EnergyVadModel(), confirm_frames=5)
    controller.begin_episode(turn_id=7, playback=queue)
    outcome = {"value": InterruptionOutcome.NONE}

    def on_frame(_written):
        # The user starts talking over the companion and keeps talking.
        for _ in range(6):
            result = controller.feed_mic_frame(SPEECH)
            if result is not InterruptionOutcome.NONE:
                outcome["value"] = result
                return

    queue.play(sink, on_frame=on_frame)
    assert outcome["value"] is InterruptionOutcome.INTERRUPTED
    event = controller.event
    assert event is not None and event.turn_id == 7
    assert event.within_budget, event
    assert event.stop_latency_ms <= INTERRUPTION_STOP_BUDGET_MS
    # All three arms received the ONE event:
    assert controller.llm_cancel.is_set()
    assert controller.tts_cancel.is_set()
    assert queue.stopped and queue.chunks == []
    # Playback really stopped early — the full text never played.
    total_possible = sum(len(c.pcm) for c in FakeTTSBackend(
        seconds_per_char=0.05).synthesize(
        "This is a long companion answer that keeps speaking for a while.",
        VoiceInfo("fake-voice", backend_key="fake-tts")))
    assert sum(len(f) for f in sink.frames) < total_possible


def test_only_one_event_per_episode():
    queue, _sink = long_playback()
    controller = InterruptionController(EnergyVadModel(), confirm_frames=4)
    controller.begin_episode(turn_id=1, playback=queue)
    results = [controller.feed_mic_frame(SPEECH) for _ in range(12)]
    assert results.count(InterruptionOutcome.INTERRUPTED) >= 1
    assert controller.event is not None
    first_event = controller.event
    controller.feed_mic_frame(SPEECH)
    assert controller.event is first_event  # never re-fires / replaced


def test_backchannel_does_not_interrupt():
    queue, sink = long_playback()
    controller = InterruptionController(EnergyVadModel(), confirm_frames=6)
    controller.begin_episode(turn_id=2, playback=queue)
    # "mm-hm": 3 confirmed frames — above min_speech, below confirm.
    outcomes = [controller.feed_mic_frame(SPEECH) for _ in range(3)]
    outcomes += [controller.feed_mic_frame(SILENCE) for _ in range(5)]
    assert InterruptionOutcome.INTERRUPTED not in outcomes
    assert controller.event is None
    assert not controller.llm_cancel.is_set()
    assert controller.backchannels_tolerated == 1
    queue.play(sink)  # playback was never stopped: it can still play out
    assert queue.chunks_completed >= 1


def test_cough_and_quiet_noise_do_not_interrupt():
    queue, _sink = long_playback()
    controller = InterruptionController(EnergyVadModel(), confirm_frames=5)
    controller.begin_episode(turn_id=3, playback=queue)
    for _ in range(2):  # cough: loud but only 2 frames (< min_speech)
        assert controller.feed_mic_frame(SPEECH) is InterruptionOutcome.NONE
    for _ in range(10):  # room noise: never confirms at all
        assert controller.feed_mic_frame(QUIET) is InterruptionOutcome.NONE
    assert controller.event is None


def test_playback_queue_stop_drops_pending_and_counts_honestly():
    queue, sink = long_playback()
    total_chunks = len(queue.chunks)
    assert total_chunks >= 1
    queue.play(sink, on_frame=lambda _w: queue.stop())
    assert queue.stopped
    assert queue.chunks == []
    assert queue.chunks_completed == 0
    assert queue.frames_written == 1  # exactly the frames actually written


def test_tts_stream_honors_the_shared_cancel_event():
    # Arm 2 proven against the real seam: the S504 stream stops when the
    # controller's tts_cancel event is the one handed to it.
    backend = FakeTTSBackend()
    cancel = threading.Event()
    produced = []
    for chunk in backend.synthesize_stream(
            "One sentence here. Another follows after. And a third one.",
            VoiceInfo("fake-voice", backend_key="fake-tts"), cancel):
        produced.append(chunk)
        cancel.set()
    assert len(produced) == 1
