"""Silero VAD (S502): frame/state/hysteresis/pre-roll/tunable parameters.

Acceptance (ROADMAP S502): fixture speech/noise/silence segmentation
meets a threshold defined in the slice BEFORE results are run. The
predeclared thresholds live in :data:`SEGMENTATION_CONTRACT` below and in
``docs/VOICE_ARCHITECTURE.md`` — written before the fixture corpus was
executed, and not revised after seeing results:

- segment recall >= 0.90 (at most 1 of 10 fixture utterances missed);
- segment precision >= 0.90 (noise bursts must not hallucinate speech);
- onset absolute error <= 3 frames (96 ms) per detected segment;
- offset absolute error <= 4 frames (128 ms) per detected segment.

Model seam: :class:`VadModel` returns a speech probability per 512-sample
frame. The real model is :class:`SileroVadModel` — the official Silero
VAD ONNX graph (MIT, snakers4/silero-vad) run through onnxruntime (MIT),
loaded from a local model file; it is a tagged-optional path (needs the
``voice`` extras + a downloaded model file, never committed). Tests use
:class:`EnergyVadModel`, a deterministic fixture model whose probability
is a fixed function of frame RMS — the segmentation *logic* (hysteresis,
hangover, pre-roll) under test is identical for both models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import pcm16_to_floats

#: Predeclared S502 segmentation contract — DO NOT edit after running the
#: fixture corpus merely to pass; revise only with a recorded reason.
SEGMENTATION_CONTRACT = {
    "min_recall": 0.90,
    "min_precision": 0.90,
    "max_onset_error_frames": 3,
    "max_offset_error_frames": 4,
}


@dataclass(frozen=True)
class VadConfig:
    """Tunable VAD parameters (all times in 32 ms frames unless noted)."""

    start_threshold: float = 0.5  # prob >= this opens a candidate segment
    end_threshold: float = 0.35  # hysteresis: prob < this counts as silence
    min_speech_frames: int = 3  # shorter bursts are rejected as transients
    hangover_frames: int = 10  # silence tolerated inside a segment (320 ms)
    pre_roll_frames: int = 8  # frames prepended before detected onset (256 ms)
    max_segment_frames: int = 3000  # hard cap ~96 s

    def validate(self) -> None:
        if not (0.0 <= self.end_threshold < self.start_threshold <= 1.0):
            raise ValueError("need 0 <= end_threshold < start_threshold <= 1")
        if self.min_speech_frames < 1 or self.hangover_frames < 0:
            raise ValueError("min_speech_frames >= 1 and hangover_frames >= 0 required")
        if self.pre_roll_frames < 0 or self.max_segment_frames < self.min_speech_frames:
            raise ValueError("invalid pre-roll / max segment frames")


class VadModel(ABC):
    """Per-frame speech-probability seam."""

    model_key: str = "abstract"

    @abstractmethod
    def probability(self, frame: bytes) -> float:
        """Speech probability in [0, 1] for one 512-sample PCM16 frame."""

    def reset(self) -> None:  # noqa: B027 - stateless models need nothing
        pass


class EnergyVadModel(VadModel):
    """Deterministic fixture model: probability from frame RMS energy.

    probability = clamp((rms - floor) / span) — a pure function of the
    frame bytes, so fixture segmentation is byte-for-byte reproducible.
    """

    model_key = "energy-fixture"

    def __init__(self, floor: float = 0.02, span: float = 0.10):
        self.floor = floor
        self.span = span

    def probability(self, frame: bytes) -> float:
        values = pcm16_to_floats(frame)
        if not values:
            return 0.0
        rms = (sum(v * v for v in values) / len(values)) ** 0.5
        return max(0.0, min(1.0, (rms - self.floor) / self.span))


class SileroVadModel(VadModel):
    """Real Silero VAD via its official ONNX graph + onnxruntime.

    The model file (``silero_vad.onnx``, MIT — snakers4/silero-vad) is
    downloaded to a cache directory, never committed. Stateful: carries
    the LSTM state + context exactly as the upstream reference requires.
    """

    model_key = "silero-vad-onnx"

    def __init__(self, model_path: str | Path):
        try:
            import numpy as np
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError(f"silero onnx path needs numpy+onnxruntime: {exc}") from exc
        self._np = np
        path = Path(model_path)
        if not path.exists():
            raise RuntimeError(f"silero model file missing: {path}")
        self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self) -> None:
        np = self._np
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def probability(self, frame: bytes) -> float:
        np = self._np
        values = pcm16_to_floats(frame)
        samples = np.array(values, dtype=np.float32).reshape(1, -1)
        if samples.shape[1] != FRAME_SAMPLES:
            raise ValueError(f"silero frame must be {FRAME_SAMPLES} samples")
        x = np.concatenate([self._context, samples], axis=1)
        out, state = self._session.run(
            None, {"input": x, "state": self._state, "sr": np.array(16000, dtype=np.int64)}
        )
        self._state = state
        self._context = x[:, -64:]
        return float(out[0][0])


@dataclass
class SpeechSegment:
    """One segmented utterance; indices are frame numbers in the stream."""

    start_frame: int  # onset frame MINUS pre-roll (the segment's audio start)
    onset_frame: int  # first frame the model called speech
    end_frame: int  # one past the last speech frame (incl. hangover tail cut)
    frames: list[bytes] = field(default_factory=list)

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    @property
    def audio(self) -> bytes:
        return b"".join(self.frames)


class VadSegmenter:
    """Streaming hysteresis segmenter over a VadModel.

    State machine per frame: SILENCE → (prob >= start) CANDIDATE →
    (>= min_speech frames) SPEECH → (prob < end for hangover frames)
    closed segment. Sub-minimum bursts are dropped as transients. The
    pre-roll frames are retained from a rolling history so a segment's
    audio starts BEFORE the detected onset (word onsets are not clipped).
    """

    def __init__(self, model: VadModel, config: VadConfig | None = None):
        self.model = model
        self.config = config or VadConfig()
        self.config.validate()
        self._history: list[bytes] = []
        self._frame_index = 0
        self._candidate: list[bytes] = []
        self._candidate_start = 0
        self._segment: list[bytes] | None = None
        self._segment_onset = 0
        self._segment_start = 0
        self._silence_run = 0
        self._last_speech_end = 0

    @property
    def in_speech(self) -> bool:
        """True while a candidate or confirmed segment is open."""
        return self._segment is not None or bool(self._candidate)

    @property
    def segment_open(self) -> bool:
        """True only once a segment is CONFIRMED (>= min_speech frames)."""
        return self._segment is not None

    @property
    def open_segment_frames(self) -> list[bytes]:
        """Frames of the currently open segment (incl. its onset frames)."""
        return list(self._segment) if self._segment is not None else []

    @property
    def open_segment_speech_frames(self) -> list[bytes]:
        """Open-segment frames trimmed to the last speech frame — the
        hangover tail the segmenter is still holding is excluded."""
        if self._segment is None:
            return []
        keep = self._last_speech_end - self._segment_start
        return list(self._segment[:keep])

    def reset(self) -> None:
        self.model.reset()
        self._history.clear()
        self._frame_index = 0
        self._candidate = []
        self._segment = None
        self._silence_run = 0

    def _close_segment(self) -> SpeechSegment | None:
        if self._segment is None:
            return None
        # Trim the trailing hangover silence beyond the last speech frame.
        keep = self._last_speech_end - self._segment_start
        frames = self._segment[:keep]
        segment = SpeechSegment(
            start_frame=self._segment_start,
            onset_frame=self._segment_onset,
            end_frame=self._segment_start + keep,
            frames=frames,
        )
        self._segment = None
        self._silence_run = 0
        return segment

    def feed(self, frame: bytes) -> list[SpeechSegment]:
        """Feed one frame; returns any segments completed by it."""
        cfg = self.config
        prob = self.model.probability(frame)
        done: list[SpeechSegment] = []
        idx = self._frame_index
        self._frame_index += 1

        if self._segment is not None:
            self._segment.append(frame)
            if prob >= cfg.end_threshold:
                self._silence_run = 0
                self._last_speech_end = idx + 1
            else:
                self._silence_run += 1
                if self._silence_run > cfg.hangover_frames:
                    closed = self._close_segment()
                    if closed is not None:
                        done.append(closed)
            if self._segment is not None and len(self._segment) >= cfg.max_segment_frames:
                closed = self._close_segment()
                if closed is not None:
                    done.append(closed)
            return done

        if self._candidate:
            if prob >= cfg.end_threshold:
                self._candidate.append(frame)
                if len(self._candidate) >= cfg.min_speech_frames:
                    pre = self._history[-cfg.pre_roll_frames :] if cfg.pre_roll_frames else []
                    self._segment = list(pre) + list(self._candidate)
                    self._segment_onset = self._candidate_start
                    self._segment_start = self._candidate_start - len(pre)
                    self._last_speech_end = idx + 1
                    self._candidate = []
                    self._silence_run = 0
            else:
                # Transient burst: reject, remember frame as history only.
                self._history.extend(self._candidate)
                self._candidate = []
                self._history.append(frame)
            self._trim_history()
            return done

        if prob >= cfg.start_threshold:
            self._candidate = [frame]
            self._candidate_start = idx
            if cfg.min_speech_frames <= 1:
                pre = self._history[-cfg.pre_roll_frames :] if cfg.pre_roll_frames else []
                self._segment = list(pre) + list(self._candidate)
                self._segment_onset = idx
                self._segment_start = idx - len(pre)
                self._last_speech_end = idx + 1
                self._candidate = []
        else:
            self._history.append(frame)
            self._trim_history()
        return done

    def _trim_history(self) -> None:
        keep = max(self.config.pre_roll_frames, 1)
        if len(self._history) > keep:
            del self._history[: len(self._history) - keep]

    def flush(self) -> list[SpeechSegment]:
        """End-of-stream: close any open segment (candidate bursts drop)."""
        closed = self._close_segment()
        return [closed] if closed is not None else []

    def segment_stream(self, frames: list[bytes]) -> list[SpeechSegment]:
        out: list[SpeechSegment] = []
        for frame in frames:
            out.extend(self.feed(frame))
        out.extend(self.flush())
        return out


def segmentation_metrics(expected: list[tuple[int, int]], detected: list[SpeechSegment]) -> dict:
    """Score detected segments against expected (onset, end) frame spans.

    A detection matches an expectation when their spans overlap; onset /
    offset errors are measured on the matched pairs.
    """
    matched_expected: set[int] = set()
    onset_errors: list[int] = []
    offset_errors: list[int] = []
    true_positive = 0
    for segment in detected:
        best: int | None = None
        for i, (start, end) in enumerate(expected):
            if i in matched_expected:
                continue
            if segment.onset_frame < end and segment.end_frame > start:
                best = i
                break
        if best is None:
            continue
        matched_expected.add(best)
        true_positive += 1
        onset_errors.append(abs(segment.onset_frame - expected[best][0]))
        offset_errors.append(abs(segment.end_frame - expected[best][1]))
    precision = true_positive / len(detected) if detected else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else 1.0
    return {
        "true_positive": true_positive,
        "false_positive": len(detected) - true_positive,
        "false_negative": len(expected) - true_positive,
        "precision": precision,
        "recall": recall,
        "max_onset_error_frames": max(onset_errors, default=0),
        "max_offset_error_frames": max(offset_errors, default=0),
    }
