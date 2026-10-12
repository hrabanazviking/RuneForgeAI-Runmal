"""Turn-taking (S506): endpoint hangover, preemptive trigger, resume
cancellation.

VAD answers "is speech occurring?"; this module answers "did the user
finish the turn?" (VOICE_ARCHITECTURE §5). It sits on top of the S502
segmenter and adds the conversational timing policy:

- **Endpoint hangover**: after speech stops, wait ``hangover_frames`` of
  silence before treating the turn as finished — mid-sentence pauses do
  not amputate the turn.
- **Preemptive trigger**: when the hangover expires, emit
  ``PREEMPTIVE_FINALIZE`` — downstream STT/LLM work may START (to hide
  latency) but is not yet committed.
- **Resume cancellation**: if the user resumes speaking within
  ``resume_window_frames`` after the preemptive trigger, emit
  ``RESUME_CANCEL`` — the preemptive work must be discarded and the turn
  continues (the resumed audio joins the same utterance). After the
  window (or an explicit commit), the turn is ``COMMITTED`` and later
  speech is a NEW turn.

All timing is in frames with an injected frame counter — deterministic
fixture scenarios, no wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from runmal.voice.vad import VadConfig, VadModel, VadSegmenter


@dataclass(frozen=True)
class TurnTakingConfig:
    hangover_frames: int = 10  # 320 ms of silence ends the speaking phase
    resume_window_frames: int = 25  # ~0.8 s where a resume cancels preempt
    min_speech_frames: int = 3

    def validate(self) -> None:
        if self.hangover_frames < 0 or self.resume_window_frames < 0:
            raise ValueError("hangover/resume window must be >= 0")
        if self.min_speech_frames < 1:
            raise ValueError("min_speech_frames must be >= 1")


class TurnEventKind(StrEnum):
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"  # raw VAD segment end (pre-hangover view)
    PREEMPTIVE_FINALIZE = "preemptive_finalize"
    RESUME_CANCEL = "resume_cancel"
    COMMITTED = "committed"


@dataclass(frozen=True)
class TurnEvent:
    kind: TurnEventKind
    frame_index: int
    utterance_id: int
    audio: bytes = b""  # utterance audio for finalize/commit events


@dataclass
class _Utterance:
    utterance_id: int
    frames: list[bytes] = field(default_factory=list)
    preemptive_at: int | None = None
    committed: bool = False
    speech_end_pos: int = 0  # frames[:speech_end_pos] = audio through last speech

    @property
    def audio(self) -> bytes:
        return b"".join(self.frames[: self.speech_end_pos])


class TurnCoordinator:
    """Frame-driven turn-taking policy over a VadSegmenter.

    Feed frames; collect events. ``utterance_id`` is stable across a
    preemptive-finalize → resume → re-finalize cycle: the resumed speech
    CONTINUES the same utterance (its audio accumulates).
    """

    def __init__(self, model: VadModel, config: TurnTakingConfig | None = None):
        self.config = config or TurnTakingConfig()
        self.config.validate()
        self._segmenter = VadSegmenter(model, VadConfig(
            min_speech_frames=self.config.min_speech_frames,
            hangover_frames=0,  # hangover policy lives HERE, not in the VAD
            pre_roll_frames=0,
        ))
        self._frame_index = 0
        self._next_id = 1
        self._current: _Utterance | None = None
        self._silence_run = 0
        self._in_speech = False
        self._segment_consumed = 0

    # ------------------------------------------------------------ feeding

    def feed(self, frame: bytes) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        idx = self._frame_index
        self._frame_index += 1
        segments = self._segmenter.feed(frame)
        # Only CONFIRMED segments start/continue a turn: a sub-minimum
        # transient candidate must never open an utterance (S502 contract).
        in_speech = self._segmenter.segment_open

        if in_speech and not self._in_speech:
            events.extend(self._on_speech_start(idx))
            self._segment_consumed = 0
        if in_speech:
            self._silence_run = 0
            if self._current is not None:
                # Append exactly the segment frames not yet consumed, so
                # a (re)confirmed segment's onset frames are never lost
                # and never double-counted.
                open_frames = self._segmenter.open_segment_speech_frames
                fresh = open_frames[self._segment_consumed:]
                self._current.frames.extend(fresh)
                self._segment_consumed = len(open_frames)
                if fresh:
                    self._current.speech_end_pos = len(self._current.frames)
        elif self._current is not None and not self._current.committed:
            # Frames belonging to a pending VAD candidate are NOT
            # appended here: if the candidate confirms, its frames
            # arrive via the segment view; if it dies, they were a
            # transient and never belonged to the utterance.
            if not self._segmenter.in_speech:
                self._current.frames.append(frame)
            self._silence_run += 1
            current = self._current
            if (current.preemptive_at is None
                    and self._silence_run > self.config.hangover_frames):
                current.preemptive_at = idx
                events.append(TurnEvent(
                    TurnEventKind.PREEMPTIVE_FINALIZE, idx, current.utterance_id,
                    audio=current.audio))
            elif (current.preemptive_at is not None
                  and idx - current.preemptive_at > self.config.resume_window_frames):
                current.committed = True
                events.append(TurnEvent(
                    TurnEventKind.COMMITTED, idx, current.utterance_id,
                    audio=current.audio))
                self._current = None
        for _segment in segments:
            if self._current is not None and not self._current.committed:
                events.append(TurnEvent(
                    TurnEventKind.SPEECH_ENDED, idx, self._current.utterance_id))
        self._in_speech = in_speech
        return events

    def _on_speech_start(self, idx: int) -> list[TurnEvent]:
        if self._current is not None and not self._current.committed:
            current = self._current
            if current.preemptive_at is not None:
                # Resume inside the window: cancel the preemptive work and
                # continue the SAME utterance.
                current.preemptive_at = None
                self._silence_run = 0
                return [TurnEvent(TurnEventKind.RESUME_CANCEL, idx,
                                  current.utterance_id)]
            return []  # still the same speaking phase (shouldn't happen)
        utterance = _Utterance(utterance_id=self._next_id)
        self._next_id += 1
        self._current = utterance
        self._silence_run = 0
        return [TurnEvent(TurnEventKind.SPEECH_STARTED, idx, utterance.utterance_id)]

    def flush(self) -> list[TurnEvent]:
        """End of stream: a pending utterance commits with its audio."""
        events: list[TurnEvent] = []
        for segment in self._segmenter.flush():
            _ = segment
        if self._current is not None and not self._current.committed:
            current = self._current
            current.committed = True
            if current.preemptive_at is None:
                events.append(TurnEvent(
                    TurnEventKind.PREEMPTIVE_FINALIZE, self._frame_index,
                    current.utterance_id, audio=current.audio))
            events.append(TurnEvent(
                TurnEventKind.COMMITTED, self._frame_index, current.utterance_id,
                audio=current.audio))
            self._current = None
        return events

    def feed_all(self, frames) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        for frame in frames:
            events.extend(self.feed(frame))
        events.extend(self.flush())
        return events
