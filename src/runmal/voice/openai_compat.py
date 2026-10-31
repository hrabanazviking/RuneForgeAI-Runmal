"""Generic OpenAI-compatible speech adapter (F-03, Part I follow-on).

One adapter for every endpoint that speaks the common OpenAI-shaped
speech surface (``POST /audio/speech``, ``POST /audio/transcriptions``):
OpenAI itself, Pollinations, and any compatible local or cloud speech
server (P-010 census: the 4 WANTED-GENERIC voice rows — OpenAI TTS,
OpenAI STT, Pollinations, and the OpenAI-compatible provider slot —
are one build, exactly as P-008/F-01 found for chat). Synthesis sits
behind the :class:`~runmal.voice.tts.TTSBackend` seam and
transcription behind the :class:`~runmal.voice.stt.STTBackend` seam;
no provider wire object crosses into ``AudioChunk`` / ``Transcript``
(INV-001/002 in spirit: provider shapes stay behind adapters).

Wire shape, stated exactly:

- **TTS** sends JSON ``{model, input, voice, response_format, speed}``
  and asks for ``response_format="pcm"`` — the speech surface's raw
  format: PCM16 little-endian mono at 24 kHz, no header. The seam's
  chunks therefore carry the returned bytes unmodified at
  ``sample_rate=24000``; no transcoding is claimed and none happens.
  Long text is split with the seam's own sentence splitter, one
  request per piece, so each piece stays far below the surface's
  per-request input limit and the first piece can play while the
  rest synthesize. The stream ends with the seam's explicit
  ``is_final`` sentinel, like every real Rúnmál TTS backend.
- **STT** uploads the caller's PCM16 mono audio as a WAV file
  (stdlib ``wave`` framing — the surface takes files, not raw PCM)
  in a multipart form ``{file, model, response_format, language?}``
  with ``response_format="verbose_json"``, and normalizes the
  reply's ``segments`` / ``words`` into ``Transcript`` segments and
  word timings. A reply without segments becomes one segment
  spanning the audio; a word without a served probability is
  recorded at the seam's neutral default, never invented precision.

Configuration is the CONNECT pattern (P-010's class: the user
connects a service with their own key or their own server; Rúnmál
ships only this adapter code, so no shipped-artifact licence
arises): ``base_url`` + models + optional bearer key come from the
constructor, falling back to ``RUNMAL_SPEECH_BASE_URL`` /
``OPENAI_API_KEY`` in the environment — the key is sent only as an
Authorization header and never serialized. Nothing is installed
for this backend and no live endpoint is called by its tests:
fixture transports only.

Errors are honest and generic-worded (statuses mapped, response
bodies never echoed — a body can carry anything, including a
reflected key): transport failures, auth refusals, rate limits
and server errors all raise :class:`SpeechError`; a failed
synthesis never yields partial audio as if it were complete.
"""

from __future__ import annotations

import io
import os
import wave

import httpx

from runmal.voice import SAMPLE_RATE
from runmal.voice.stt import (
    STTBackend,
    STTModelInfo,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from runmal.voice.tts import (
    AudioChunk,
    TTSBackend,
    TTSModelInfo,
    VoiceInfo,
    split_text_into_chunks,
)

#: Default endpoint: OpenAI's own API — the same default F-01's
#: chat adapter declares (pinned equal by test). Any compatible
#: endpoint is a ``base_url`` away.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
#: Widely served compatible model names (local compatible servers
#: expose these spellings even when the engine behind them differs).
DEFAULT_TTS_MODEL = "tts-1"
DEFAULT_STT_MODEL = "whisper-1"
#: Default voice when neither the caller's VoiceInfo nor the
#: constructor names one.
DEFAULT_VOICE = "alloy"
#: The ``pcm`` speech format's rate: 24 kHz PCM16 mono, headerless.
SPEECH_PCM_RATE = 24000
#: Environment fallbacks for the factory-built (settings-selected)
#: instances: the standard key name, plus Rúnmál's base-URL override.
ENV_API_KEY = "OPENAI_API_KEY"
ENV_BASE_URL = "RUNMAL_SPEECH_BASE_URL"


class SpeechError(RuntimeError):
    """A speech endpoint failure, worded generically (no body echo)."""


def map_speech_error(code: int) -> SpeechError:
    if code in (401, 403):
        return SpeechError("openai-compatible speech authentication failed")
    if code == 404:
        return SpeechError("openai-compatible speech model not found")
    if code == 429:
        return SpeechError("openai-compatible speech rate limited")
    if code in (400, 422):
        return SpeechError("openai-compatible speech invalid request")
    if code >= 500:
        return SpeechError(f"openai-compatible speech unavailable (HTTP {code})")
    return SpeechError(f"openai-compatible speech provider error (HTTP {code})")


def _resolve(value: str | None, env_name: str, default: str) -> str:
    return value if value is not None else (os.environ.get(env_name) or default)


class _SpeechClient:
    """Shared sync-client + error discipline for both modalities."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 60.0,
    ):
        # Header only; never emitted in payloads or errors (INV-023).
        self._api_key = (
            api_key if api_key is not None else (os.environ.get(ENV_API_KEY) or None)
        )
        resolved_url = _resolve(base_url, ENV_BASE_URL, DEFAULT_BASE_URL)
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        self._client = client or httpx.Client(
            base_url=resolved_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            headers=headers,
        )

    def _post(self, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.post(path, **kwargs)
        except httpx.TimeoutException as exc:
            raise SpeechError("openai-compatible speech request timed out") from exc
        except httpx.ConnectError as exc:
            raise SpeechError("openai-compatible speech unreachable") from exc
        if resp.status_code >= 400:
            raise map_speech_error(resp.status_code)
        return resp

    def _models_ok(self) -> bool:
        try:
            resp = self._client.get("/models")
        except Exception:
            return False
        return resp.status_code < 400


class OpenAICompatibleTTSBackend(_SpeechClient, TTSBackend):
    """Synthesis via any OpenAI-compatible ``POST /audio/speech``."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = DEFAULT_VOICE,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._model = model
        self._voice = voice

    def model_info(self) -> TTSModelInfo:
        return TTSModelInfo(
            self.backend_key,
            self._model,
            (self._voice,),
            native_sample_rate=SPEECH_PCM_RATE,
        )

    def voices(self) -> tuple[VoiceInfo, ...]:
        return (
            VoiceInfo(
                voice_id=self._voice,
                name="OpenAI-compatible default voice",
                language="en",
                backend_key=self.name,
            ),
        )

    def synthesize(self, text, voice, *, speaking_rate: float = 1.0):
        voice_id = (voice.voice_id if voice is not None else "") or self._voice
        speed = min(max(float(speaking_rate), 0.25), 4.0)
        pieces = split_text_into_chunks(text)
        for index, piece in enumerate(pieces):
            resp = self._post(
                "/audio/speech",
                json={
                    "model": self._model,
                    "input": piece,
                    "voice": voice_id,
                    "response_format": "pcm",
                    "speed": speed,
                },
            )
            yield AudioChunk(
                pcm=resp.content, text=piece, index=index, sample_rate=SPEECH_PCM_RATE
            )
        yield AudioChunk(
            pcm=b"", index=len(pieces), sample_rate=SPEECH_PCM_RATE, is_final=True
        )


class OpenAICompatibleSTTBackend(_SpeechClient, STTBackend):
    """Transcription via any OpenAI-compatible
    ``POST /audio/transcriptions`` (the field's generic STT shape)."""

    backend_key = "openai"

    def __init__(
        self,
        *,
        model: str = DEFAULT_STT_MODEL,
        language: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._model = model
        self._language = language

    def model_info(self) -> STTModelInfo:
        return STTModelInfo(
            self.backend_key,
            self._model,
            self._language or "en",
            supports_word_timestamps=True,
            supports_streaming=False,
        )

    def health_check(self) -> bool:
        return self._models_ok()

    @staticmethod
    def _wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return buffer.getvalue()

    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcript:
        form: dict[str, str] = {
            "model": self._model,
            "response_format": "verbose_json",
        }
        if self._language:
            form["language"] = self._language
        resp = self._post(
            "/audio/transcriptions",
            data=form,
            files={"file": ("audio.wav", self._wav_bytes(pcm, sample_rate), "audio/wav")},
        )
        body = resp.json()
        duration = (len(pcm) // 2) / sample_rate if sample_rate else 0.0
        segments: list[TranscriptSegment] = []
        for raw in body.get("segments") or []:
            words = tuple(
                TranscriptWord(
                    str(w.get("word", "")).strip(),
                    float(w.get("start") or 0.0),
                    float(w.get("end") or 0.0),
                    float(w.get("probability", 1.0)),
                )
                for w in (raw.get("words") or [])
                if str(w.get("word", "")).strip()
            )
            segments.append(
                TranscriptSegment(
                    str(raw.get("text", "")).strip(),
                    float(raw.get("start") or 0.0),
                    float(raw.get("end") or 0.0),
                    words,
                )
            )
        if not segments:
            words = tuple(
                TranscriptWord(
                    str(w.get("word", "")).strip(),
                    float(w.get("start") or 0.0),
                    float(w.get("end") or 0.0),
                    float(w.get("probability", 1.0)),
                )
                for w in (body.get("words") or [])
                if str(w.get("word", "")).strip()
            )
            segments.append(
                TranscriptSegment(
                    str(body.get("text", "")).strip(), 0.0, round(duration, 3), words
                )
            )
        return Transcript(
            str(body.get("text", "")).strip(),
            str(body.get("language") or self._language),
            tuple(segments),
            model_id=self._model,
            backend_key=self.backend_key,
        )
