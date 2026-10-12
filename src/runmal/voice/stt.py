"""STT service (S503): faster-whisper ``small`` int8 baseline with word
timestamps, behind the STTBackend seam, plus a benchmark harness hook.

Acceptance (ROADMAP S503): a fixed fixture corpus meets PREDECLARED
transcript-quality / RTF thresholds on the reference hardware
(purplelongship), or a deliberate contract revision is recorded. The
thresholds in :data:`STT_CONTRACT` were declared before any benchmark
run on the reference hardware:

- word error rate (WER) <= 0.25 over the fixture corpus;
- real-time factor (RTF = transcribe_seconds / audio_seconds) p50 <= 1.0
  (at least real-time on CPU, int8).

Fixture corpus: short known-text utterances synthesized with the CMU
Flite voice via ffmpeg's ``flite`` source filter (libflite, permissive
CMU license) — real speech waveforms with exact reference transcripts,
generated on the test host; WAVs are never committed. Provenance and
generation are documented in ``tests/fixtures/voice/README.md`` and
implemented in :mod:`runmal.voice.corpus`.

The real backend is tagged-optional: :class:`FasterWhisperSTT` imports
``faster_whisper`` lazily and downloads the ``small`` model (OpenAI
Whisper weights, MIT) into a cache dir outside the repo. Tests of the
seam use :class:`FakeSTTBackend`, which is deterministic.
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from runmal.voice import SAMPLE_RATE
from runmal.voice.audio import pcm16_to_floats

#: Predeclared S503 contract — see module docstring. Do not edit after
#: seeing benchmark results merely to pass; revise deliberately instead.
STT_CONTRACT = {
    "model": "small",
    "compute_type": "int8",
    "max_wer": 0.25,
    "max_rtf_p50": 1.0,
}


@dataclass(frozen=True)
class TranscriptWord:
    text: str
    start_s: float
    end_s: float
    probability: float = 1.0


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_s: float
    end_s: float
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str = ""
    segments: tuple[TranscriptSegment, ...] = ()
    model_id: str = ""
    backend_key: str = ""

    @property
    def words(self) -> tuple[TranscriptWord, ...]:
        return tuple(w for seg in self.segments for w in seg.words)


@dataclass(frozen=True)
class STTModelInfo:
    backend_key: str
    model_id: str
    language: str = "en"
    supports_word_timestamps: bool = False
    supports_streaming: bool = False


class STTBackend(ABC):
    """Speech-to-text seam (BACKEND_CONTRACT: STT is its own modality)."""

    backend_key: str = "abstract"

    @abstractmethod
    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcript:
        """Transcribe PCM16 mono audio into a normalized Transcript."""

    @abstractmethod
    def model_info(self) -> STTModelInfo:
        """Static model/backend metadata."""

    def health_check(self) -> bool:
        try:
            self.model_info()
            return True
        except Exception:
            return False


class FakeSTTBackend(STTBackend):
    """Deterministic fake: returns a scripted transcript whose word
    timestamps tile the audio duration evenly. Used by seam/orchestrator
    tests; never presented as a real transcription."""

    backend_key = "fake-stt"

    def __init__(self, text: str = "hello world", language: str = "en"):
        self._text = text
        self._language = language

    def model_info(self) -> STTModelInfo:
        return STTModelInfo(self.backend_key, "fake-stt-1", self._language,
                            supports_word_timestamps=True)

    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcript:
        duration = (len(pcm) // 2) / sample_rate if sample_rate else 0.0
        words = self._text.split()
        step = duration / len(words) if words else 0.0
        timed = tuple(
            TranscriptWord(w, round(i * step, 3), round((i + 1) * step, 3))
            for i, w in enumerate(words))
        segment = TranscriptSegment(self._text, 0.0, round(duration, 3), timed)
        return Transcript(self._text, self._language, (segment,),
                          model_id="fake-stt-1", backend_key=self.backend_key)


class FasterWhisperSTT(STTBackend):
    """Real baseline: faster-whisper (MIT) + Whisper ``small`` (MIT),
    int8 CPU, word timestamps on. Model files land in ``cache_dir``."""

    backend_key = "faster-whisper"

    def __init__(self, model_size: str = "small", cache_dir: str | Path | None = None,
                 language: str = "en"):
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(f"faster-whisper not installed: {exc}") from exc
        self.model_id = model_size
        self._language = language
        self._model = WhisperModel(
            model_size, device="cpu", compute_type=STT_CONTRACT["compute_type"],
            download_root=str(cache_dir) if cache_dir else None)

    def model_info(self) -> STTModelInfo:
        return STTModelInfo(self.backend_key, self.model_id, self._language,
                            supports_word_timestamps=True)

    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcript:
        import numpy as np

        floats = pcm16_to_floats(pcm)
        audio = np.array(floats, dtype=np.float32)
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"faster-whisper path expects {SAMPLE_RATE} Hz, got {sample_rate}")
        segments_iter, info = self._model.transcribe(
            audio, language=self._language or None, word_timestamps=True,
            vad_filter=False)
        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        for seg in segments_iter:
            words = tuple(
                TranscriptWord(w.word.strip(), float(w.start), float(w.end),
                               float(w.probability))
                for w in (seg.words or []) if w.word.strip())
            text = seg.text.strip()
            texts.append(text)
            segments.append(TranscriptSegment(text, float(seg.start), float(seg.end), words))
        return Transcript(" ".join(t for t in texts if t), info.language or self._language,
                          tuple(segments), model_id=self.model_id,
                          backend_key=self.backend_key)


# ------------------------------------------------------------- WER + bench


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein WER over normalized (lowercased, punctuation-stripped)
    word sequences. 0.0 = identical; can exceed 1.0 with insertions."""
    def words(text: str) -> list[str]:
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower())
        return cleaned.split()

    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[len(hyp)] / len(ref)


@dataclass
class CorpusItem:
    name: str
    pcm: bytes
    reference_text: str

    @property
    def duration_s(self) -> float:
        return (len(self.pcm) // 2) / SAMPLE_RATE


@dataclass
class STTBenchmarkResult:
    items: list[dict] = field(default_factory=list)
    wer: float = 0.0
    rtf_p50: float = 0.0
    rtf_max: float = 0.0

    def meets_contract(self) -> dict:
        return {
            "wer": self.wer <= STT_CONTRACT["max_wer"],
            "rtf_p50": self.rtf_p50 <= STT_CONTRACT["max_rtf_p50"],
        }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def benchmark_stt(backend: STTBackend, corpus: list[CorpusItem]) -> STTBenchmarkResult:
    """Benchmark harness hook (exercised fully by S514): per-item WER +
    RTF against wall time, aggregated honestly (no cherry-picking)."""
    result = STTBenchmarkResult()
    rtfs: list[float] = []
    total_errors_weighted = 0.0
    total_ref_words = 0
    for item in corpus:
        started = time.perf_counter()
        transcript = backend.transcribe(item.pcm)
        elapsed = time.perf_counter() - started
        wer = word_error_rate(item.reference_text, transcript.text)
        rtf = elapsed / item.duration_s if item.duration_s else 0.0
        rtfs.append(rtf)
        ref_words = len(item.reference_text.split())
        total_errors_weighted += wer * ref_words
        total_ref_words += ref_words
        result.items.append({
            "name": item.name, "reference": item.reference_text,
            "hypothesis": transcript.text, "wer": round(wer, 4),
            "rtf": round(rtf, 4), "duration_s": round(item.duration_s, 3),
            "words": len(transcript.words),
        })
    result.wer = total_errors_weighted / total_ref_words if total_ref_words else 0.0
    result.rtf_p50 = _median(rtfs) if rtfs else 0.0
    result.rtf_max = max(rtfs, default=0.0)
    return result


# ------------------------------------------------------- flite corpus synth


def synthesize_flite_wav(text: str, out_path: Path, voice: str = "slt") -> Path:
    """Synthesize one utterance with ffmpeg's flite filter (CMU Flite).

    Raises RuntimeError when ffmpeg/flite is unavailable — callers treat
    the real-corpus path as tagged-optional, never as a silent pass.
    """
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", f"flite=text='{text}':voice={voice}",
        "-ar", str(SAMPLE_RATE), "-ac", "1", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"flite synthesis failed: {proc.stderr.strip()[:200]}")
    return out_path


def wav_to_pcm(path: Path) -> bytes:
    """Read a 16 kHz mono PCM16 WAV's data chunk (stdlib wave module)."""
    import wave

    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SAMPLE_RATE or handle.getnchannels() != 1:
            raise ValueError("corpus wav must be 16 kHz mono")
        return handle.readframes(handle.getnframes())
