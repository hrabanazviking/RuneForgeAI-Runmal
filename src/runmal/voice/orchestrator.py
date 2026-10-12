"""Voice orchestrator state machine (S505).

Explicit states (VOICE_ARCHITECTURE §2 / ROADMAP S505):
LISTENING → USER_SPEAKING → FINALIZING_STT → THINKING → SYNTHESIZING →
SPEAKING → (INTERRUPTING) → LISTENING, with ERROR_RECOVERY reachable
from any working state.

Acceptance: deterministic simulated state transitions — the whole loop
is driven synchronously frame-by-frame with an injectable monotonic
clock, a fixture VAD/STT/TTS and a scripted chat responder, so tests
assert the EXACT transition sequence a live session would take.

Wiring: VAD segment (S502) → STT (S503) → responder (any sync callable
``str -> Iterator[str]`` standing in for Prompt Composer + ChatBackend)
→ sentence chunks → TTS stream (S504) → playback sink (S501). One
cancellation event is shared by the responder loop, the TTS stream and
playback, so :meth:`VoiceOrchestrator.interrupt` is the single barge-in
funnel (fully exercised in S507).

Playback-truth hooks: ``on_chunk_started`` / ``on_chunk_finished``
callbacks receive (turn_id, AudioChunk, frames_played) — S508's ledger
subscribes here; history is never written from generated text alone
(INV-020).
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from runmal.voice.audio import CaptureSource, PlaybackSink
from runmal.voice.stt import STTBackend, Transcript
from runmal.voice.tts import TTSBackend, VoiceInfo
from runmal.voice.vad import SpeechSegment, VadSegmenter

Responder = Callable[[str], Iterator[str]]


class VoiceState(StrEnum):
    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    FINALIZING = "FINALIZING_STT"
    THINKING = "THINKING"
    SYNTHESIZING = "SYNTHESIZING"
    SPEAKING = "SPEAKING"
    INTERRUPTING = "INTERRUPTING"
    ERROR_RECOVERY = "ERROR_RECOVERY"


@dataclass(frozen=True)
class Transition:
    from_state: VoiceState
    to_state: VoiceState
    at: float  # monotonic seconds from the injected clock
    turn_id: int | None = None
    note: str = ""


@dataclass
class TurnRecord:
    turn_id: int
    transcript: Transcript | None = None
    response_text: str = ""
    chunks_total: int = 0
    chunks_played: int = 0
    interrupted: bool = False
    error: str = ""


class VoiceOrchestrator:
    """Synchronous, deterministic voice-loop state machine."""

    def __init__(
        self,
        *,
        segmenter: VadSegmenter,
        stt: STTBackend,
        responder: Responder,
        tts: TTSBackend,
        voice: VoiceInfo,
        playback: PlaybackSink,
        clock: Callable[[], float] = time.monotonic,
        on_chunk_started: Callable[[int, object], None] | None = None,
        on_chunk_finished: Callable[[int, object, int], None] | None = None,
        frame_hook: Callable[[int, int], None] | None = None,
    ):
        self.segmenter = segmenter
        self.stt = stt
        self.responder = responder
        self.tts = tts
        self.voice = voice
        self.playback = playback
        self._clock = clock
        self._on_chunk_started = on_chunk_started
        self._on_chunk_finished = on_chunk_finished
        self._frame_hook = frame_hook  # (turn_id, frames_played_in_chunk)
        self.state = VoiceState.LISTENING
        self.transitions: list[Transition] = []
        self.turns: list[TurnRecord] = []
        self._turn_counter = itertools.count(1)
        self._cancel = threading.Event()
        self._speaking = False

    # ------------------------------------------------------------ state

    def _set_state(self, to_state: VoiceState, turn_id: int | None = None,
                   note: str = "") -> None:
        if to_state is self.state:
            return
        self.transitions.append(Transition(
            self.state, to_state, self._clock(), turn_id, note))
        self.state = to_state

    def state_sequence(self) -> list[VoiceState]:
        seq = [VoiceState.LISTENING]
        seq.extend(t.to_state for t in self.transitions)
        return seq

    # -------------------------------------------------------------- mic

    def feed_frame(self, frame: bytes) -> None:
        """One capture frame while listening (or while speaking, for
        barge-in detection by the S507 controller's own VAD path)."""
        if self._speaking:
            return  # barge-in frames are the interruption controller's job
        segments = self.segmenter.feed(frame)
        if self.segmenter.in_speech:
            self._set_state(VoiceState.USER_SPEAKING)
        for segment in segments:
            self._run_turn(segment)

    def feed_frames(self, frames) -> None:
        for frame in frames:
            self.feed_frame(frame)
        for segment in self.segmenter.flush():
            self._run_turn(segment)

    def run_capture(self, source: CaptureSource) -> None:
        while True:
            frame = source.read_frame()
            if frame is None:
                break
            self.feed_frame(frame)
        for segment in self.segmenter.flush():
            self._run_turn(segment)

    # ------------------------------------------------------------- turn

    def _run_turn(self, segment: SpeechSegment) -> None:
        turn_id = next(self._turn_counter)
        record = TurnRecord(turn_id=turn_id)
        self.turns.append(record)
        self._cancel = threading.Event()
        try:
            self._set_state(VoiceState.FINALIZING, turn_id)
            transcript = self.stt.transcribe(segment.audio)
            record.transcript = transcript
            if not transcript.text.strip():
                self._set_state(VoiceState.LISTENING, turn_id, "empty transcript")
                return
            self._set_state(VoiceState.THINKING, turn_id)
            pieces: list[str] = []
            for delta in self.responder(transcript.text):
                if self._cancel.is_set():
                    record.interrupted = True
                    break
                pieces.append(delta)
            record.response_text = "".join(pieces)
            if record.interrupted:
                self._finish_interruption(turn_id)
                return
            if not record.response_text.strip():
                self._set_state(VoiceState.LISTENING, turn_id, "empty response")
                return
            self._speak(turn_id, record)
            if record.interrupted:
                self._finish_interruption(turn_id)
            else:
                self._set_state(VoiceState.LISTENING, turn_id)
        except Exception as exc:  # recovery is a state, not a crash
            record.error = f"{type(exc).__name__}: {exc}"
            self._set_state(VoiceState.ERROR_RECOVERY, turn_id, record.error)
            self._set_state(VoiceState.LISTENING, turn_id, "recovered")

    def _speak(self, turn_id: int, record: TurnRecord) -> None:
        self._set_state(VoiceState.SYNTHESIZING, turn_id)
        stream = self.tts.synthesize_stream(
            record.response_text, self.voice, self._cancel)
        first = True
        self._speaking = True
        try:
            for chunk in stream:
                if self._cancel.is_set():
                    record.interrupted = True
                    break
                if first:
                    self._set_state(VoiceState.SPEAKING, turn_id)
                    first = False
                record.chunks_total += 1
                if self._on_chunk_started:
                    self._on_chunk_started(turn_id, chunk)
                frames_played = self._play_chunk(turn_id, chunk)
                if self._on_chunk_finished:
                    self._on_chunk_finished(turn_id, chunk, frames_played)
                record.chunks_played += 1
                if self._cancel.is_set():
                    record.interrupted = True
                    break
        finally:
            self._speaking = False

    def _play_chunk(self, turn_id: int, chunk) -> int:
        """Write a chunk's frames to the sink, frame by frame, so an
        interruption lands mid-chunk (the ledger needs the true count)."""
        from runmal.voice import FRAME_SAMPLES
        from runmal.voice.audio import frame_bytes

        step = frame_bytes(FRAME_SAMPLES)
        played = 0
        total_frames = max(1, len(chunk.pcm) // step)
        for i in range(total_frames):
            if self._cancel.is_set():
                break
            piece = chunk.pcm[i * step:(i + 1) * step]
            if piece:
                self.playback.write_frame(piece)
            played += 1
            if self._frame_hook:
                self._frame_hook(turn_id, played)
        return played

    # ------------------------------------------------------- interruption

    def interrupt(self, note: str = "barge-in") -> bool:
        """The ONE interruption funnel (S507): cancels the responder loop,
        the TTS stream and playback via the shared event. Returns False
        when nothing was playing (a no-op, not an error)."""
        if not self._speaking and self.state not in (
                VoiceState.SPEAKING, VoiceState.SYNTHESIZING, VoiceState.THINKING):
            return False
        self._set_state(VoiceState.INTERRUPTING, note=note)
        self._cancel.set()
        return True

    def _finish_interruption(self, turn_id: int) -> None:
        if self.turns:
            self.turns[-1].interrupted = True
        self._set_state(VoiceState.LISTENING, turn_id, "interrupted")


@dataclass
class SimulatedClock:
    """Deterministic monotonic clock for tests: +1 ms per call."""

    step: float = 0.001
    now: float = field(default=0.0)

    def __call__(self) -> float:
        self.now += self.step
        return self.now
