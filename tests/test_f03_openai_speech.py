"""F-03 acceptance: the generic OpenAI-compatible speech adapter.

Part I follow-on F-03 (homed by the P-014 gate from P-010's
first recommendation): synthesis and transcription behind the
existing TTS/STT seams, covering the census's 4 WANTED-GENERIC
voice rows (OpenAI TTS, OpenAI STT, Pollinations, and the
OpenAI-compatible provider slot itself) with ONE adapter pair.
Fixture transports only; no live endpoint is involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from runmal.backends.openai_compat import DEFAULT_BASE_URL as CHAT_DEFAULT_BASE_URL
from runmal.voice import SAMPLE_RATE
from runmal.voice.backends import (
    DEFAULT_TTS_BACKEND,
    KNOWN_TTS_BACKENDS,
    TTS_REGISTRY,
    build_tts_backend,
)
from runmal.voice.openai_compat import (
    DEFAULT_BASE_URL,
    SPEECH_PCM_RATE,
    OpenAICompatibleSTTBackend,
    OpenAICompatibleTTSBackend,
    SpeechError,
)
from runmal.voice.settings import VoiceSettings
from runmal.voice.stt_backends import (
    DEFAULT_STT_BACKEND,
    KNOWN_STT_BACKENDS,
    STT_REGISTRY,
    build_stt_backend,
)
from runmal.voice.tts import VoiceInfo

FIX = Path(__file__).parent / "fixtures" / "voice"
CANARY = "f03-canary-key"
# One centisecond of deterministic PCM16 at the pcm format's rate.
PCM = b"\x00\x10" * 240
VOICE = VoiceInfo(voice_id="nova", language="en", backend_key="openai")
# 0.5 s of silence-shaped PCM16 at the seam's rate, for STT inputs.
AUDIO = b"\x00\x00" * (SAMPLE_RATE // 2)


def tts_backend(captured: dict | None = None, status: int = 200, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.setdefault("calls", []).append(
                {
                    "path": request.url.path,
                    "auth": request.headers.get("Authorization"),
                    "json": json.loads(request.content),
                }
            )
        return httpx.Response(status, content=PCM)

    return OpenAICompatibleTTSBackend(
        api_key=CANARY, transport=httpx.MockTransport(handler), **kw
    )


def stt_backend(captured: dict | None = None, status: int = 200, body=None, **kw):
    payload = (
        body
        if body is not None
        else json.loads((FIX / "openai_transcription.json").read_text())
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.update(
                {
                    "path": request.url.path,
                    "auth": request.headers.get("Authorization"),
                    "content_type": request.headers.get("Content-Type", ""),
                    "content": request.content,
                }
            )
        return httpx.Response(status, content=json.dumps(payload).encode())

    return OpenAICompatibleSTTBackend(
        api_key=CANARY, transport=httpx.MockTransport(handler), **kw
    )


# ------------------------------------------------------------------ TTS


def test_tts_synthesize_yields_pcm_chunks_and_final_sentinel():
    chunks = list(tts_backend().synthesize("Hello world. Balance above all.", VOICE))
    assert [c.text for c in chunks[:-1]] == ["Hello world.", "Balance above all."]
    assert all(c.pcm == PCM for c in chunks[:-1])
    assert all(c.sample_rate == SPEECH_PCM_RATE == 24000 for c in chunks)
    assert [c.index for c in chunks] == [0, 1, 2]
    assert chunks[-1].is_final and chunks[-1].pcm == b""
    # The seam's cancellable view materializes the same stream.
    import threading

    streamed = list(
        tts_backend().synthesize_stream("Hello world.", VOICE, threading.Event())
    )
    assert streamed[-1].is_final


def test_tts_wire_payload_voice_speed_and_key_discipline():
    captured: dict = {}
    backend = tts_backend(captured)
    _ = list(backend.synthesize("Hello world.", VOICE, speaking_rate=10.0))
    (call,) = captured["calls"]
    assert call["path"].endswith("/audio/speech")
    payload = call["json"]
    assert payload["model"] == "tts-1"
    assert payload["input"] == "Hello world."
    assert payload["voice"] == "nova"  # the caller's voice wins
    assert payload["response_format"] == "pcm"
    assert payload["speed"] == 4.0  # speaking_rate clipped to the served range
    assert call["auth"] == f"Bearer {CANARY}"
    assert CANARY not in json.dumps(payload)  # key is a header, never a field
    info = backend.model_info()
    assert info.backend_key == "openai" and info.native_sample_rate == 24000
    assert backend.voices()[0].voice_id == "alloy"  # configured default voice


def test_tts_default_voice_used_when_caller_names_none():
    captured: dict = {}
    _ = list(
        tts_backend(captured).synthesize(
            "Hi.", VoiceInfo(voice_id="", backend_key="openai")
        )
    )
    assert captured["calls"][0]["json"]["voice"] == "alloy"


def test_tts_errors_map_without_echoing_bodies():
    with pytest.raises(SpeechError, match="authentication"):
        _ = list(tts_backend(status=401).synthesize("Hi.", VOICE))
    with pytest.raises(SpeechError, match="rate limited"):
        _ = list(tts_backend(status=429).synthesize("Hi.", VOICE))
    with pytest.raises(SpeechError, match="invalid request"):
        _ = list(tts_backend(status=422).synthesize("Hi.", VOICE))

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    backend = OpenAICompatibleTTSBackend(
        api_key=CANARY, transport=httpx.MockTransport(boom)
    )
    with pytest.raises(SpeechError, match="unreachable"):
        _ = list(backend.synthesize("Hi.", VOICE))


# ------------------------------------------------------------------ STT


def test_stt_transcribe_normalizes_verbose_json():
    transcript = stt_backend().transcribe(AUDIO)
    assert transcript.text == "Hello world. Balance above all."
    assert transcript.language == "english"
    assert transcript.model_id == "whisper-1"
    assert transcript.backend_key == "openai"
    assert len(transcript.segments) == 2
    words = transcript.words
    assert [w.text for w in words] == ["Hello", "world.", "Balance", "above", "all."]
    assert words[0].start_s == 0.0 and words[-1].end_s == 1.5
    info = stt_backend().model_info()
    assert info.supports_word_timestamps is True
    assert info.supports_streaming is False


def test_stt_wire_is_multipart_wav_with_key_only_in_header():
    captured: dict = {}
    _ = stt_backend(captured).transcribe(AUDIO)
    assert captured["path"].endswith("/audio/transcriptions")
    assert "multipart/form-data" in captured["content_type"]
    body = captured["content"]
    assert b'name="model"' in body and b"whisper-1" in body
    assert b"verbose_json" in body
    assert b'filename="audio.wav"' in body
    assert body.count(b"RIFF") == 1 and b"WAVE" in body  # stdlib WAV framing
    assert captured["auth"] == f"Bearer {CANARY}"
    assert CANARY.encode() not in body


def test_stt_reply_without_segments_becomes_one_spanning_segment():
    backend = stt_backend(body={"text": "one segment", "language": "en"})
    transcript = backend.transcribe(AUDIO)
    assert transcript.text == "one segment"
    (segment,) = transcript.segments
    assert segment.start_s == 0.0 and segment.end_s == 0.5  # the audio's span


def test_stt_errors_map():
    with pytest.raises(SpeechError, match="authentication"):
        stt_backend(status=403).transcribe(AUDIO)
    with pytest.raises(SpeechError, match="unavailable"):
        stt_backend(status=503).transcribe(AUDIO)


# ------------------------------------------------------- wiring / config


def test_factories_and_registries_carry_the_connect_adapter():
    assert isinstance(build_tts_backend("openai", api_key="k"), OpenAICompatibleTTSBackend)
    assert isinstance(build_stt_backend("openai", api_key="k"), OpenAICompatibleSTTBackend)
    # Both seams name the adapter "openai", in their own namespaces.
    assert "openai" in TTS_REGISTRY and "openai" in STT_REGISTRY
    assert KNOWN_TTS_BACKENDS == tuple(TTS_REGISTRY) + ("fake-tts",)
    assert KNOWN_STT_BACKENDS == tuple(STT_REGISTRY) + ("fake-stt",)
    # A connection, not an install: no recipe runs, nothing ships,
    # and the shipped defaults are untouched.
    for registry in (TTS_REGISTRY, STT_REGISTRY):
        spec = registry["openai"]
        assert spec.default_shipped is False and spec.verified is True
        assert spec.plan.enable is False and spec.tree_packages == ()
        assert "Connection, not an install" in spec.plan.note
    assert DEFAULT_TTS_BACKEND == "cosyvoice"
    assert DEFAULT_STT_BACKEND == "faster-whisper"
    shipped_tts = [k for k, s in TTS_REGISTRY.items() if s.default_shipped]
    shipped_stt = [k for k, s in STT_REGISTRY.items() if s.default_shipped]
    assert shipped_tts == ["cosyvoice"] and shipped_stt == ["faster-whisper"]
    # Selectable through the persisted voice settings, both seams.
    settings = VoiceSettings()
    settings.set_tts_backend("openai")
    settings.set_stt_backend("openai")
    assert settings.to_dict()["tts_backend"] == "openai"
    # The STT adapter is distinct from the registered local
    # ``openai-whisper`` reference implementation.
    assert "openai-whisper" in STT_REGISTRY and "openai" != "openai-whisper"


def test_env_configuration_and_default_base_url_parity(monkeypatch):
    # The default endpoint is F-01's chat default, pinned equal so
    # the two generic adapters cannot drift apart.
    assert DEFAULT_BASE_URL == CHAT_DEFAULT_BASE_URL == "https://api.openai.com/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-f03")
    monkeypatch.setenv("RUNMAL_SPEECH_BASE_URL", "http://127.0.0.1:9999/v1")
    captured: dict = {}
    backend = build_tts_backend("openai", transport=_capture_transport(captured))
    assert str(backend._client.base_url).rstrip("/") == "http://127.0.0.1:9999/v1"
    _ = list(backend.synthesize("Hi.", VOICE))
    assert captured["auth"] == "Bearer env-key-f03"


def _capture_transport(captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, content=PCM)

    return httpx.MockTransport(handler)


def test_census_carries_the_f03_follow_on():
    census = (
        Path(__file__).parent.parent / "docs" / "VOICE_PROVIDER_CENSUS_2026-10-30.md"
    ).read_text(encoding="utf-8")
    assert "F-03 follow-on" in census
    assert "WANTED-GENERIC" in census
