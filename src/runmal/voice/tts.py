"""TTS service seam (S504, reworked by ADR-0005).

Rúnmál's speech is MULTI-BACKEND: engines sit behind this seam and
register in :mod:`runmal.voice.backends` — CosyVoice and Chatterbox
ship by default, Kitten and Piper are user-installed, and a future
first-party engine registers the same way. **Kokoro was REMOVED from
the product**: its English path phonemized through Misaki, whose
``misaki[en]`` tree directly requires the forbidden eSpeak-NG carriers
``espeakng-loader`` / ``phonemizer-fork`` (GPL-3.0) — the S504 license
gate (:mod:`runmal.voice.license_audit`, policy:
docs/VOICE_LICENSE_MATRIX.md) can never pass that tree, and better
engines exist (docs/TTS_ENGINE_SURVEY.md).

The seam contract:

- :meth:`TTSBackend.synthesize` — the core: an iterator of
  :class:`AudioChunk` (PCM16 mono; the rate is per-chunk — backends
  synthesize at their native rate), in text order. Real backends end
  the stream with an explicit ``is_final`` sentinel chunk.
- :meth:`TTSBackend.synthesize_stream` — the orchestrator's view:
  the same chunks, but production stops promptly when the caller's
  cancellation event is set (INV-003, barge-in).
- :meth:`TTSBackend.synthesize_all` — the materialized list, for
  audition and benchmark callers.

Per-backend latency thresholds are PREDECLARED per backend in
docs/BENCHMARKS.md and mirrored on the registry specs in
:mod:`runmal.voice.backends` — never rewritten after measurement
merely to pass.
"""

from __future__ import annotations

import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from runmal.voice import SAMPLE_RATE
from runmal.voice.audio import floats_to_pcm16

#: Fixed TTS corpus (provenance: tests/fixtures/voice/README.md).
TTS_CORPUS_TEXTS: tuple[str, ...] = (
    "Hello, wanderer. The wind carried whispers of your arrival.",
    "Balance above all: life and death are one cycle, turning slowly.",
    "Take the left path at the old bridge, then walk toward the river.",
)

#: The native rate most registered backends synthesize at.
DEFAULT_NATIVE_RATE = 24000


@dataclass(frozen=True)
class VoiceInfo:
    voice_id: str
    language: str = "en-us"
    backend_key: str = ""
    name: str = ""
    #: Zero-shot / cloning backends (CosyVoice): the prompt transcript
    #: and reference wav that define this voice. Empty for fixed-voice
    #: backends. Persona params may carry both (see profiles.py).
    prompt_text: str = ""
    prompt_wav: str = ""


@dataclass(frozen=True)
class AudioChunk:
    """One synthesized chunk: PCM16 mono at ``sample_rate``."""

    pcm: bytes
    text: str = ""  # the exact source text span this chunk synthesizes
    index: int = 0
    sample_rate: int = SAMPLE_RATE
    #: True on the explicit end-of-stream sentinel chunk (real backends
    #: emit one; its pcm is empty and it is never played as audio).
    is_final: bool = False
    #: Optional (word, start_s, end_s) alignment inside this chunk, when
    #: the backend can provide it. The S508 ledger uses it — and when it
    #: is absent, the ledger MUST stay conservative (no certain words
    #: from a partially played chunk).
    word_timings: tuple[tuple[str, float, float], ...] = ()

    @property
    def duration_s(self) -> float:
        return (len(self.pcm) // 2) / self.sample_rate


@dataclass(frozen=True)
class TTSModelInfo:
    backend_key: str
    model_id: str
    voices: tuple[str, ...] = ()
    native_sample_rate: int = DEFAULT_NATIVE_RATE


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
    """Text-to-speech seam: streaming chunks + cancellation + audition.

    Concrete backends register in :mod:`runmal.voice.backends` and set
    :attr:`name` to their registry key. Construction of a real backend
    whose runtime is not installed raises
    :class:`~runmal.voice.backends.BackendUnavailable` — installation
    is a user action, never a silent side effect.
    """

    name: str = "abstract"

    @property
    def backend_key(self) -> str:
        return self.name

    @abstractmethod
    def synthesize(
        self, text: str, voice: VoiceInfo, *, speaking_rate: float = 1.0
    ) -> Iterator[AudioChunk]:
        """Yield chunks in text order; real backends end with an
        ``is_final`` sentinel chunk (empty pcm)."""

    def synthesize_stream(
        self, text: str, voice: VoiceInfo, cancel: threading.Event
    ) -> Iterator[AudioChunk]:
        """The orchestrator's cancellable view of :meth:`synthesize`.

        Stops before the next chunk whenever ``cancel`` is set; the
        underlying generator is closed so backends release promptly.
        """
        if cancel.is_set():
            return
        stream = self.synthesize(text, voice)
        for chunk in stream:
            if cancel.is_set():
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
                return
            yield chunk

    def synthesize_all(self, text: str, voice: VoiceInfo) -> list[AudioChunk]:
        """Materialize the full chunk list (audition/benchmark path)."""
        return list(self.synthesize(text, voice))

    def model_info(self) -> TTSModelInfo:
        """Static model/voice metadata (backends may refine)."""
        return TTSModelInfo(self.backend_key, self.name)

    def voices(self) -> tuple[VoiceInfo, ...]:
        """Voices this backend instance offers (empty when unknown)."""
        return ()

    def audition(
        self, voice: VoiceInfo, text: str = "Hello, I am ready when you are."
    ) -> list[AudioChunk]:
        """Voice audition: synthesize the fixed sample line for a voice."""
        return self.synthesize_all(text, voice)


class FakeTTSBackend(TTSBackend):
    """Deterministic fixture TTS: each chunk is a quiet sine burst whose
    duration scales with the chunk's character count. Never presented as
    real speech; exists so orchestration/barge-in tests are exact."""

    name = "fake-tts"

    def __init__(self, seconds_per_char: float = 0.02, amplitude: float = 0.2):
        self.seconds_per_char = seconds_per_char
        self.amplitude = amplitude

    def model_info(self) -> TTSModelInfo:
        return TTSModelInfo(
            self.backend_key, "fake-tts-1", ("fake-voice",), native_sample_rate=SAMPLE_RATE
        )

    def voices(self) -> tuple[VoiceInfo, ...]:
        return (
            VoiceInfo(
                voice_id="fake-voice", name="Fake voice", language="en", backend_key=self.name
            ),
        )

    def synthesize(self, text, voice, *, speaking_rate: float = 1.0):
        import math

        for index, piece in enumerate(split_text_into_chunks(text)):
            samples = max(1, int(len(piece) * self.seconds_per_char * SAMPLE_RATE))
            pcm = floats_to_pcm16(
                [
                    self.amplitude * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)
                    for i in range(samples)
                ]
            )
            duration = samples / SAMPLE_RATE
            words = piece.split()
            step = duration / len(words) if words else 0.0
            timings = tuple(
                (w, round(i * step, 4), round((i + 1) * step, 4)) for i, w in enumerate(words)
            )
            yield AudioChunk(
                pcm=pcm, text=piece, index=index, sample_rate=SAMPLE_RATE, word_timings=timings
            )
