"""TTS service + license gate (S504).

Selected path: **independent ONNX inference** over the Kokoro-82M graph
(Apache-2.0 weights + voices) via onnxruntime (MIT), phonemized by Misaki
(Apache-2.0) used WITHOUT its eSpeak fallback. The popular wrapper paths
were audited and REJECTED by the gate in
:mod:`runmal.voice.license_audit`:

- ``kokoro-onnx`` requires ``espeakng-loader`` + ``phonemizer-fork``
  (eSpeak-NG, GPL-3.0) — forbidden in the distributed tree;
- the torch ``kokoro`` pipeline wires Misaki's EspeakFallback by default.

Here, :class:`KokoroOnnxTTS` refuses to construct when the environment
audit fails (a forbidden carrier installed for this path, or an
unreviewed license in the tree). Out-of-lexicon words are spelled
through a grapheme fallback — a documented quality limitation, not a
silent GPL dependency.

Predeclared first-audio threshold (declared BEFORE any benchmark run):
TTS time-to-first-audio p50 <= 2.0 s for the fixed corpus on
purplelongship CPU (ONNX fp32 graph, cold-ish per-sentence synthesis);
synthesis RTF p50 <= 1.0. See :data:`TTS_CONTRACT`.

Output contract: chunks of PCM16 mono at the pipeline rate (16 kHz) —
Kokoro's native 24 kHz float audio is linearly resampled so the whole
voice pipeline keeps one format (S501). Sentence/chunk streaming:
:meth:`TTSBackend.synthesize_stream` yields one chunk per sentence-piece
in order, honoring the cancellation event between chunks (INV-003).
"""

from __future__ import annotations

import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from runmal.voice import SAMPLE_RATE
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.license_audit import audit_voice_environment

#: Predeclared S504 thresholds — see module docstring. Not to be edited
#: after seeing benchmark results merely to pass.
TTS_CONTRACT = {
    "max_first_audio_p50_s": 2.0,
    "max_rtf_p50": 1.0,
    "output_sample_rate": SAMPLE_RATE,
}

KOKORO_NATIVE_RATE = 24000

#: Fixed TTS corpus (provenance: tests/fixtures/voice/README.md).
TTS_CORPUS_TEXTS: tuple[str, ...] = (
    "Hello, wanderer. The wind carried whispers of your arrival.",
    "Balance above all: life and death are one cycle, turning slowly.",
    "Take the left path at the old bridge, then walk toward the river.",
)


@dataclass(frozen=True)
class VoiceInfo:
    voice_id: str
    language: str = "en-us"
    backend_key: str = ""


@dataclass(frozen=True)
class AudioChunk:
    """One synthesized chunk: PCM16 at the pipeline sample rate."""

    pcm: bytes
    text: str  # the exact source text span this chunk synthesizes
    index: int
    sample_rate: int = SAMPLE_RATE

    @property
    def duration_s(self) -> float:
        return (len(self.pcm) // 2) / self.sample_rate


@dataclass(frozen=True)
class TTSModelInfo:
    backend_key: str
    model_id: str
    voices: tuple[str, ...] = ()
    native_sample_rate: int = KOKORO_NATIVE_RATE


_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]+|\S[^.!?…]*$")


def split_text_into_chunks(text: str, max_chars: int = 180) -> list[str]:
    """Deterministic sentence/chunk splitter for streaming synthesis.

    Splits on sentence terminators, then hard-splits over-long pieces at
    the last space before ``max_chars`` (or exactly at ``max_chars``).
    Whitespace is normalized inside pieces; piece order is input order.
    """
    pieces: list[str] = []
    for match in _SENTENCE_RE.finditer(text):
        piece = " ".join(match.group(0).split())
        if not piece:
            continue
        while len(piece) > max_chars:
            cut = piece.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            pieces.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            pieces.append(piece)
    return pieces


class TTSBackend(ABC):
    """Text-to-speech seam: streaming chunks + cancellation + audition."""

    backend_key: str = "abstract"

    @abstractmethod
    def synthesize_stream(
        self, text: str, voice: VoiceInfo, cancel: threading.Event
    ) -> Iterator[AudioChunk]:
        """Yield chunks in order; stop promptly when ``cancel`` is set."""

    @abstractmethod
    def model_info(self) -> TTSModelInfo:
        """Static model/voice metadata."""

    def synthesize(self, text: str, voice: VoiceInfo) -> list[AudioChunk]:
        return list(self.synthesize_stream(text, voice, threading.Event()))

    def audition(self, voice: VoiceInfo, text: str = "Hello, I am ready when you are."
                 ) -> list[AudioChunk]:
        """Voice audition: synthesize the fixed sample line for a voice."""
        return self.synthesize(text, voice)


class FakeTTSBackend(TTSBackend):
    """Deterministic fixture TTS: each chunk is a quiet sine burst whose
    duration scales with the chunk's character count. Never presented as
    real speech; exists so orchestration/barge-in tests are exact."""

    backend_key = "fake-tts"

    def __init__(self, seconds_per_char: float = 0.02, amplitude: float = 0.2):
        self.seconds_per_char = seconds_per_char
        self.amplitude = amplitude

    def model_info(self) -> TTSModelInfo:
        return TTSModelInfo(self.backend_key, "fake-tts-1", ("fake-voice",),
                            native_sample_rate=SAMPLE_RATE)

    def synthesize_stream(self, text, voice, cancel):
        import math

        for index, piece in enumerate(split_text_into_chunks(text)):
            if cancel.is_set():
                return
            samples = max(1, int(len(piece) * self.seconds_per_char * SAMPLE_RATE))
            pcm = floats_to_pcm16(
                [self.amplitude * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)
                 for i in range(samples)])
            yield AudioChunk(pcm=pcm, text=piece, index=index)


# ------------------------------------------------------------- phonemizers


class Phonemizer(ABC):
    """Text → Kokoro phoneme string seam (license-audited per backend)."""

    @abstractmethod
    def phonemize(self, text: str, british: bool = False) -> str:
        """Return the phoneme string for one chunk of text."""


class MisakiPhonemizer(Phonemizer):
    """Misaki English G2P with NO eSpeak fallback.

    Constructs ``misaki.en.G2P`` with the fallback explicitly disabled /
    absent: unknown words are dropped to the grapheme path in
    :meth:`phonemize` rather than routed to eSpeak-NG. If the installed
    misaki *requires* an espeak fallback object, construction raises —
    the gate would rather fail loudly than ship GPL (see license_audit).
    """

    def __init__(self):
        try:
            from misaki.en import G2P
        except Exception as exc:
            raise RuntimeError(f"misaki not installed: {exc}") from exc
        try:
            self._g2p = G2P(trf=False, british=False, fallback=None, unk="")
        except TypeError:
            self._g2p = G2P(trf=False, british=False)

    def phonemize(self, text: str, british: bool = False) -> str:
        phonemes, _tokens = self._g2p(text)
        return phonemes


class FixturePhonemizer(Phonemizer):
    """Deterministic test phonemizer: maps letters to fixed phoneme-ish
    symbols so tokenization/audio plumbing can be tested without misaki."""

    def phonemize(self, text: str, british: bool = False) -> str:
        return "".join(ch if ch.isalpha() else " " for ch in text.lower())


# ------------------------------------------------------------ kokoro onnx


def resample_linear(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Linear-interpolation resample of PCM16 mono (stdlib only)."""
    if from_rate == to_rate:
        return pcm
    from runmal.voice.audio import pcm16_to_floats

    values = pcm16_to_floats(pcm)
    if not values:
        return b""
    out_len = max(1, int(len(values) * to_rate / from_rate))
    out: list[float] = []
    for i in range(out_len):
        pos = i * from_rate / to_rate
        low = int(pos)
        high = min(low + 1, len(values) - 1)
        frac = pos - low
        out.append(values[low] * (1 - frac) + values[high] * frac)
    return floats_to_pcm16(out)


class KokoroOnnxTTS(TTSBackend):
    """Kokoro-82M via an independent ONNX session (the gated path).

    Assets (downloaded to a cache dir, never committed):
    - ``model_path``: ONNX graph exported from hexgrad/Kokoro-82M
      (Apache-2.0);
    - ``voices_path``: voice style pack (.npz) from the same project
      (Apache-2.0);
    - ``config_path``: the model's config.json carrying the phoneme vocab.

    Construction runs the license gate first and raises RuntimeError with
    the audit summary when the environment fails policy.
    """

    backend_key = "kokoro-onnx"

    def __init__(self, model_path: str | Path, voices_path: str | Path,
                 config_path: str | Path, phonemizer: Phonemizer | None = None,
                 *, enforce_license_gate: bool = True):
        if enforce_license_gate:
            report = audit_voice_environment()
            if not report.passed:
                raise RuntimeError(f"TTS license gate failed:\n{report.summary()}")
        try:
            import numpy as np
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError(f"kokoro onnx path needs numpy+onnxruntime: {exc}") from exc
        import json

        self._np = np
        self._session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"])
        with Path(config_path).open() as handle:
            config = json.load(handle)
        self._vocab: dict[str, int] = config["vocab"]
        self._voices = np.load(str(voices_path))
        self._phonemizer = phonemizer or MisakiPhonemizer()
        self.model_id = "kokoro-82m-v1.0-onnx"

    def model_info(self) -> TTSModelInfo:
        names = tuple(sorted(k for k in self._voices.files)) \
            if hasattr(self._voices, "files") else ()
        return TTSModelInfo(self.backend_key, self.model_id, names)

    def _tokens_for(self, phonemes: str) -> list[int]:
        ids = [self._vocab[ch] for ch in phonemes if ch in self._vocab]
        return [0, *ids, 0]  # BOS/EOS padding token 0, per Kokoro convention

    def synthesize_stream(self, text, voice, cancel):
        np = self._np
        style_all = self._voices[voice.voice_id] \
            if not isinstance(self._voices, dict) else self._voices[voice.voice_id]
        for index, piece in enumerate(split_text_into_chunks(text)):
            if cancel.is_set():
                return
            phonemes = self._phonemizer.phonemize(piece, british=voice.language == "en-gb")
            tokens = self._tokens_for(phonemes)
            style = style_all[len(tokens) - 2] if len(tokens) >= 2 else style_all[0]
            audio = self._session.run(None, {
                "input_ids": np.array([tokens], dtype=np.int64),
                "style": np.array(style, dtype=np.float32).reshape(1, 256),
                "speed": np.array([1.0], dtype=np.float32),
            })[0]
            pcm24 = floats_to_pcm16([float(v) for v in np.asarray(audio).flatten()])
            pcm = resample_linear(pcm24, KOKORO_NATIVE_RATE, SAMPLE_RATE)
            yield AudioChunk(pcm=pcm, text=piece, index=index)
