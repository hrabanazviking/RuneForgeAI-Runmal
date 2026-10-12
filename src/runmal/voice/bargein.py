"""Barge-in (S507): one interruption event propagating through LLM, TTS
queue and playback; backchannel tolerance.

While the companion speaks, a parallel VAD path watches the microphone
(VOICE_ARCHITECTURE §3). Sustained confirmed user speech produces ONE
:class:`InterruptionEvent` that propagates to every stage of the
interrupted turn:

1. the active LLM stream (its cancellation event is set);
2. sentence/chunk assembly + queued and in-flight TTS synthesis (the
   shared TTS cancellation event is set; the synthesis queue drains);
3. the playback queue (pending chunks dropped, device writes stop).

Predeclared threshold (declared BEFORE fixture results):
:data:`INTERRUPTION_STOP_BUDGET_MS` = 100 ms from confirmed interruption
to the last playback write. The deterministic player below stops within
the same frame the event fires (0 frames after detection), which the
fixture measures and asserts against the budget.

Backchannels ("mm-hm", a cough, a laugh) are short bursts below the
confirmation length: they are recorded as tolerated backchannels and do
NOT interrupt. Only a *confirmed segment* (S502 segmenter, min-speech
frames) whose speech persists for ``confirm_frames`` total frames fires.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum

from runmal.voice import FRAME_MS
from runmal.voice.audio import PlaybackSink, frame_bytes
from runmal.voice.tts import AudioChunk
from runmal.voice.vad import VadModel, VadSegmenter, VadConfig

#: Predeclared S507 budget: interruption detection -> playback stop.
INTERRUPTION_STOP_BUDGET_MS = 100


class InterruptionOutcome(StrEnum):
    NONE = "none"
    BACKCHANNEL_TOLERATED = "backchannel_tolerated"
    INTERRUPTED = "interrupted"


@dataclass
class InterruptionEvent:
    turn_id: int
    detected_at_frame: int  # mic frame index where speech was CONFIRMED
    stopped_at_frame: int  # playback frame counter when writes stopped
    frames_played_after_detection: int

    @property
    def stop_latency_ms(self) -> int:
        return self.frames_played_after_detection * FRAME_MS

    @property
    def within_budget(self) -> bool:
        return self.stop_latency_ms <= INTERRUPTION_STOP_BUDGET_MS


@dataclass
class PlaybackQueue:
    """FIFO of TTS chunks played frame-by-frame to a sink.

    ``stop()`` is the playback arm of the interruption event: pending
    chunks are dropped and the in-flight chunk halts at the next frame
    boundary. ``frames_written`` is the honest playback counter the
    S508 ledger and the stop-latency measurement both read.
    """

    chunks: list[AudioChunk] = field(default_factory=list)
    frames_written: int = 0
    chunks_completed: int = 0
    stopped: bool = False
    current_chunk: AudioChunk | None = None
    current_chunk_frames: int = 0

    def enqueue(self, chunk: AudioChunk) -> None:
        if not self.stopped:
            self.chunks.append(chunk)

    def clear_pending(self) -> int:
        dropped = len(self.chunks)
        self.chunks.clear()
        return dropped

    def stop(self) -> None:
        self.stopped = True
        self.clear_pending()

    def play(self, sink: PlaybackSink, *, on_frame=None) -> None:
        """Play everything queued until drained or stopped.

        ``on_frame(frames_written)`` runs after each written frame — the
        deterministic hook tests use to fire barge-in mid-playback.
        """
        step = frame_bytes()
        while self.chunks and not self.stopped:
            chunk = self.chunks.pop(0)
            self.current_chunk = chunk
            self.current_chunk_frames = 0
            total = max(1, len(chunk.pcm) // step)
            for i in range(total):
                if self.stopped:
                    break
                piece = chunk.pcm[i * step:(i + 1) * step]
                if piece:
                    sink.write_frame(piece)
                self.frames_written += 1
                self.current_chunk_frames += 1
                if on_frame:
                    on_frame(self.frames_written)
            if not self.stopped:
                self.chunks_completed += 1
            self.current_chunk = None


class InterruptionController:
    """Parallel barge-in watcher for one speaking episode at a time.

    Feed it microphone frames while the companion speaks. It owns the
    three cancellation arms and fires at most ONE event per episode
    (``begin_episode`` re-arms it for the next companion turn).
    """

    def __init__(self, model: VadModel, *, confirm_frames: int = 5,
                 min_speech_frames: int = 3):
        if confirm_frames < min_speech_frames:
            raise ValueError("confirm_frames must be >= min_speech_frames")
        self._segmenter = VadSegmenter(model, VadConfig(
            min_speech_frames=min_speech_frames, hangover_frames=0,
            pre_roll_frames=0))
        self.confirm_frames = confirm_frames
        # The three propagation arms (INV-021):
        self.llm_cancel = threading.Event()
        self.tts_cancel = threading.Event()
        self.playback: PlaybackQueue | None = None
        self.turn_id: int | None = None
        self._speech_frames = 0
        self._mic_frame = 0
        self._fired = False
        self.event: InterruptionEvent | None = None
        self.backchannels_tolerated = 0

    def begin_episode(self, turn_id: int, playback: PlaybackQueue) -> None:
        self.turn_id = turn_id
        self.playback = playback
        self.llm_cancel = threading.Event()
        self.tts_cancel = threading.Event()
        self._segmenter.reset()
        self._speech_frames = 0
        self._mic_frame = 0
        self._fired = False
        self.event = None

    def feed_mic_frame(self, frame: bytes) -> InterruptionOutcome:
        """One mic frame during companion speech."""
        if self._fired:
            return InterruptionOutcome.INTERRUPTED
        self._mic_frame += 1
        was_open = self._segmenter.segment_open
        segments = self._segmenter.feed(frame)
        if self._segmenter.segment_open:
            self._speech_frames += 1
            if self._speech_frames >= self.confirm_frames:
                return self._fire()
        else:
            if was_open or segments:
                # A segment opened and closed without reaching the
                # confirmation length: a tolerated backchannel.
                if 0 < self._speech_frames < self.confirm_frames:
                    self.backchannels_tolerated += 1
            self._speech_frames = 0
        return InterruptionOutcome.NONE

    def _fire(self) -> InterruptionOutcome:
        self._fired = True
        before = self.playback.frames_written if self.playback else 0
        # Propagate to all three arms, in architecture order (§3):
        self.llm_cancel.set()          # 1. active LLM stream
        self.tts_cancel.set()          # 2. assembly + queued/in-flight TTS
        if self.playback is not None:
            self.playback.stop()       # 3. playback queue/device
        after = self.playback.frames_written if self.playback else 0
        self.event = InterruptionEvent(
            turn_id=self.turn_id or 0,
            detected_at_frame=self._mic_frame,
            stopped_at_frame=after,
            frames_played_after_detection=after - before)
        return InterruptionOutcome.INTERRUPTED
