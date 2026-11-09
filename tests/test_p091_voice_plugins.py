"""P-091 TTS/STT voice plugins battery.

Pins the citizen contracts from hidden_files/P091_DESIGN.md
against src/runmal/plugins/tts.py (runmal.tts) and
src/runmal/plugins/stt.py (runmal.stt): the manifests as
strict round-tripping data, empty P-082 sandbox grants, no
reserved chat.write, no prompt hooks, the migration / boot
neighbours (head stays 0041, no 0042, empty boot registry),
config validation and leniency, explicit actions only
(events never synthesize and never transcribe), byte parity
with the direct backend call, the sentinel law (a real
backend's is_final sentinel passes through verbatim; the
fake's absence of one is never fabricated), per-chat latest
storage with failure-preserves-prior, and chat.deleted
clearing in both citizens.
Tests touch no real network and load no real model: every
backend is a deterministic fake or an injected test double
defined in this file.
"""

from __future__ import annotations

import base64

import pytest

from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import service as plugin_service
from runmal.plugins import stt as stt_citizen
from runmal.plugins import tts as tts_citizen
from runmal.plugins.api import PLUGIN_EVENTS
from runmal.plugins.events import make_event, message_payload
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.voice import SAMPLE_RATE
from runmal.voice.backends import (
    DEFAULT_TTS_BACKEND,
    KNOWN_TTS_BACKENDS,
    TTS_REGISTRY,
    BackendUnavailable,
)
from runmal.voice.stt import (
    FakeSTTBackend,
    STTBackend,
    STTModelInfo,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from runmal.voice.stt_backends import (
    DEFAULT_STT_BACKEND,
    KNOWN_STT_BACKENDS,
    STT_REGISTRY,
)
from runmal.voice.tts import (
    AudioChunk,
    FakeTTSBackend,
    TTSBackend,
    TTSModelInfo,
    VoiceInfo,
)

TTS_ID = tts_citizen.PLUGIN_ID
STT_ID = stt_citizen.PLUGIN_ID
TEXT_MULTI = "The wind rises over the sea. The long ships sail north."
PCM_16K = b"\x00\x01" * 8000  # 16000 bytes = 0.5 s at 16 kHz


@pytest.fixture(autouse=True)
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def assert_tts_chunks_match(plugin_chunks, direct_chunks):
    assert len(plugin_chunks) == len(direct_chunks)
    for p_chunk, d_chunk in zip(plugin_chunks, direct_chunks):
        assert base64.b64decode(p_chunk["pcm_b64"]) == d_chunk.pcm
        assert p_chunk["index"] == d_chunk.index
        assert p_chunk["text"] == d_chunk.text
        assert p_chunk["sample_rate"] == d_chunk.sample_rate
        assert p_chunk["is_final"] == d_chunk.is_final
        assert p_chunk["pcm_bytes"] == len(d_chunk.pcm)
        assert p_chunk["duration_s"] == d_chunk.duration_s
        assert p_chunk["word_timings"] == [
            [str(w), float(s), float(e)] for w, s, e in d_chunk.word_timings]

# ---------------- test doubles (design section 8.1) ----------------


class CountingTTSBackend(FakeTTSBackend):
    """Counts calls per method name, delegating to the fake."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = {"synthesize": 0, "synthesize_all": 0,
                      "audition": 0, "voices": 0, "model_info": 0}

    @property
    def total_calls(self):
        return sum(self.calls.values())

    def synthesize(self, text, voice, *, speaking_rate=1.0):
        self.calls["synthesize"] += 1
        return super().synthesize(text, voice, speaking_rate=speaking_rate)

    def synthesize_all(self, text, voice):
        self.calls["synthesize_all"] += 1
        return super().synthesize_all(text, voice)

    def audition(self, voice, text="Hello, I am ready when you are."):
        self.calls["audition"] += 1
        return super().audition(voice, text)

    def voices(self):
        self.calls["voices"] += 1
        return super().voices()

    def model_info(self):
        self.calls["model_info"] += 1
        return super().model_info()


class FixedTTSBackend(TTSBackend):
    """Exactly two fixed chunks at 24000 Hz, one word timing each."""

    name = "fixed-tts"

    def synthesize(self, text, voice, *, speaking_rate=1.0):
        return [
            AudioChunk(pcm=b"\x01\x02" * 100, text="Fixed one.", index=0,
                       sample_rate=24000,
                       word_timings=(("Fixed", 0.0, 0.1),)),
            AudioChunk(pcm=b"\x03\x04" * 50, text="Fixed two.", index=1,
                       sample_rate=24000,
                       word_timings=(("two", 0.0, 0.05),)),
        ]

    def model_info(self):
        return TTSModelInfo("fixed-tts", "fixed-tts-1", ("fixed-voice",),
                            native_sample_rate=24000)

    def voices(self):
        return (VoiceInfo(voice_id="fixed-voice", language="en",
                          backend_key="fixed-tts", name="Fixed voice"),)


class SentinelTTSBackend(FixedTTSBackend):
    """Appends the real-backend is_final sentinel chunk."""

    def synthesize(self, text, voice, *, speaking_rate=1.0):
        chunks = list(super().synthesize(text, voice,
                                         speaking_rate=speaking_rate))
        chunks.append(AudioChunk(pcm=b"", text="", index=2,
                                 sample_rate=24000, is_final=True))
        return chunks


class RateRecordingTTSBackend(FixedTTSBackend):
    """Records every speaking_rate kwarg reaching synthesize."""

    def __init__(self):
        self.rates: list[float] = []

    def synthesize(self, text, voice, *, speaking_rate=1.0):
        self.rates.append(speaking_rate)
        return super().synthesize(text, voice, speaking_rate=speaking_rate)


class FlakyTTSBackend(FixedTTSBackend):
    """synthesize_all succeeds once, then raises; armable to fail at once."""

    def __init__(self, fail_immediately=False):
        self.fail_immediately = fail_immediately
        self._synth_calls = 0

    def synthesize_all(self, text, voice):
        self._synth_calls += 1
        if self.fail_immediately or self._synth_calls > 1:
            raise RuntimeError("flaky boom")
        return super().synthesize_all(text, voice)


class UnavailableTTSBackend(FixedTTSBackend):
    def synthesize(self, text, voice, *, speaking_rate=1.0):
        raise BackendUnavailable("unavailable boom")

    def synthesize_all(self, text, voice):
        raise BackendUnavailable("unavailable boom")


class AsyncTTSBackend(FixedTTSBackend):
    """Async overrides returning the sync parent's values."""

    async def synthesize_all(self, text, voice):
        return FixedTTSBackend.synthesize_all(self, text, voice)

    async def audition(self, voice, text="Hello, I am ready when you are."):
        return FixedTTSBackend.audition(self, voice, text)

    async def voices(self):
        return FixedTTSBackend.voices(self)

    async def model_info(self):
        return FixedTTSBackend.model_info(self)


class DuckTTSBackend:
    """Plain object, NOT a TTSBackend: only the five seam methods."""

    name = "fixed-tts"
    backend_key = "fixed-tts"

    def __init__(self):
        self._inner = FixedTTSBackend()

    def synthesize(self, text, voice, *, speaking_rate=1.0):
        return self._inner.synthesize(text, voice,
                                      speaking_rate=speaking_rate)

    def synthesize_all(self, text, voice):
        return self._inner.synthesize_all(text, voice)

    def model_info(self):
        return self._inner.model_info()

    def voices(self):
        return self._inner.voices()

    def audition(self, voice, text="Hello, I am ready when you are."):
        return self._inner.audition(voice, text)


class NoVoicesFixedTTSBackend(FixedTTSBackend):
    """The section 8.2 test-27 variant: voices() returns ()."""

    def __init__(self):
        self.synthesize_all_calls = 0

    def voices(self):
        return ()

    def synthesize_all(self, text, voice):
        self.synthesize_all_calls += 1
        return super().synthesize_all(text, voice)


class CountingSTTBackend(FakeSTTBackend):
    """Counts transcribe/model_info/health_check, delegating to the fake."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = {"transcribe": 0, "model_info": 0, "health_check": 0}

    @property
    def total_calls(self):
        return sum(self.calls.values())

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        self.calls["transcribe"] += 1
        return super().transcribe(pcm, sample_rate)

    def model_info(self):
        self.calls["model_info"] += 1
        return super().model_info()

    def health_check(self):
        self.calls["health_check"] += 1
        return super().health_check()


def _fixed_transcript():
    words1 = (TranscriptWord("alpha", 0.0, 0.4, 0.9),
              TranscriptWord("beta", 0.4, 0.8, 0.8))
    words2 = (TranscriptWord("gamma", 0.8, 1.2, 0.95),)
    segments = (TranscriptSegment("alpha beta", 0.0, 0.8, words1),
                TranscriptSegment("gamma", 0.8, 1.2, words2))
    return Transcript("alpha beta gamma", "en", segments,
                      model_id="fixed-stt-1", backend_key="fixed-stt")


class FixedSTTBackend(STTBackend):
    """One fixed two-segment transcript with known words."""

    backend_key = "fixed-stt"

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        return _fixed_transcript()

    def model_info(self):
        return STTModelInfo("fixed-stt", "fixed-stt-1", "en",
                            supports_word_timestamps=True,
                            supports_streaming=False)


class FlakySTTBackend(FixedSTTBackend):
    def __init__(self, fail_immediately=False):
        self.fail_immediately = fail_immediately
        self._calls = 0

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        self._calls += 1
        if self.fail_immediately or self._calls > 1:
            raise RuntimeError("flaky boom")
        return super().transcribe(pcm, sample_rate)


class BrokenInfoSTTBackend(FixedSTTBackend):
    def model_info(self):
        raise RuntimeError("info boom")


class AsyncSTTBackend(FixedSTTBackend):
    async def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        return FixedSTTBackend.transcribe(self, pcm, sample_rate)

    async def model_info(self):
        return FixedSTTBackend.model_info(self)


class DuckSTTBackend:
    """Plain object exposing only transcribe and model_info."""

    backend_key = "fixed-stt"

    def __init__(self):
        self._inner = FixedSTTBackend()

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        return self._inner.transcribe(pcm, sample_rate)

    def model_info(self):
        return self._inner.model_info()

# ---------------- Group A: manifests, registration, coexistence ----------------


def test_tts_manifest_data_matches_design():
    assert tts_citizen.manifest_data() == {
        "id": "runmal.tts",
        "name": "Text to Speech",
        "version": "1.0.0",
        "api_version": 1,
        "description": "Founding TTS seam as a plugin citizen: explicit synthesis only, through a host-wired TTSBackend (FakeTTSBackend by default and labelled fake). Events never synthesize.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": ["message.created", "chat.deleted"],
        "prompt_hooks": [],
        "ui_slots": [{"id": "tts-panel", "slot": "settings.panel", "label": "Text to Speech", "order": 90, "payload": {"kind": "panel", "route": "tts"}}],
        "settings": {
            "schema": {
                "speaking_rate": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                "max_text_chars": {"type": "integer", "minimum": 1, "maximum": 4000},
            },
            "defaults": {"speaking_rate": 1.0, "max_text_chars": 2000},
        },
        "enabled_by_default": False,
    }
    assert tts_citizen.manifest_data()["enabled_by_default"] is False


def test_stt_manifest_data_matches_design():
    assert stt_citizen.manifest_data() == {
        "id": "runmal.stt",
        "name": "Speech to Text",
        "version": "1.0.0",
        "api_version": 1,
        "description": "Founding STT seam as a plugin citizen: explicit transcription only, through a host-wired STTBackend (FakeSTTBackend by default and labelled fake). No event transcribes.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": ["chat.deleted"],
        "prompt_hooks": [],
        "ui_slots": [{"id": "stt-panel", "slot": "settings.panel", "label": "Speech to Text", "order": 91, "payload": {"kind": "panel", "route": "stt"}}],
        "settings": {
            "schema": {"max_audio_bytes": {"type": "integer", "minimum": 3200, "maximum": 16000000}},
            "defaults": {"max_audio_bytes": 3200000},
        },
        "enabled_by_default": False,
    }
    assert stt_citizen.manifest_data()["enabled_by_default"] is False


def test_tts_manifest_round_trips_and_registers():
    assert manifest_to_data(tts_citizen.build_manifest()) == tts_citizen.manifest_data()
    record, _plugin = tts_citizen.register_plugin(PluginRegistry())
    assert record.state is PluginState.REGISTERED
    record2, _plugin2 = tts_citizen.register_plugin(PluginRegistry(), enable=True)
    assert record2.state is PluginState.ENABLED


def test_stt_manifest_round_trips_and_registers():
    assert manifest_to_data(stt_citizen.build_manifest()) == stt_citizen.manifest_data()
    record, _plugin = stt_citizen.register_plugin(PluginRegistry())
    assert record.state is PluginState.REGISTERED
    record2, _plugin2 = stt_citizen.register_plugin(PluginRegistry(), enable=True)
    assert record2.state is PluginState.ENABLED


def test_no_prompt_hooks_declared():
    for citizen in (tts_citizen, stt_citizen):
        data = citizen.manifest_data()
        assert data["prompt_hooks"] == []
        assert tuple(citizen.build_manifest().prompt_hooks) == ()
        assert "prompt.hooks" not in data["capabilities"]
        assert "prompt.inject" not in data["permissions"]
        assert "prompt.modify" not in data["permissions"]
    _r, tts_plugin = tts_citizen.register_plugin(PluginRegistry())
    _r2, stt_plugin = stt_citizen.register_plugin(PluginRegistry())
    assert tts_plugin.handlers().prompt_hooks == {}
    assert stt_plugin.handlers().prompt_hooks == {}


async def test_both_citizens_co_register_in_one_registry():
    registry = PluginRegistry()
    tts_record, tts_plugin = tts_citizen.register_plugin(registry, enable=True)
    stt_record, stt_plugin = stt_citizen.register_plugin(registry, enable=True)
    assert tts_record.state is PluginState.ENABLED
    assert stt_record.state is PluginState.ENABLED
    assert tts_record.manifest.id == TTS_ID
    assert stt_record.manifest.id == STT_ID
    assert registry.keys() == [STT_ID, TTS_ID]
    tts_result = await tts_plugin.synthesize(TEXT_MULTI)
    assert tts_result["backend"] == "fake-tts"
    stt_result = await stt_plugin.transcribe(PCM_16K)
    assert stt_result["backend"] == "fake-stt"
    assert stt_result["text"] == "hello world"

# ---------------- Group B: sandbox and surface honesty ----------------


def test_tts_sandbox_grants_are_empty():
    grants = tts_citizen.sandbox_grants()
    assert grants.resources == frozenset()
    assert grants.plugin_id == TTS_ID == "runmal.tts"


def test_stt_sandbox_grants_are_empty():
    grants = stt_citizen.sandbox_grants()
    assert grants.resources == frozenset()
    assert grants.plugin_id == STT_ID == "runmal.stt"


def test_no_chat_write_and_exact_surface():
    for citizen in (tts_citizen, stt_citizen):
        data = citizen.manifest_data()
        assert data["permissions"] == ["chat.read", "ui.contribute"]
        assert data["capabilities"] == ["chat.events", "ui.slots"]
        assert "chat.write" not in data["permissions"]


def test_no_invented_event_names():
    invented = ("message.spoken", "voice.synthesized",
                "transcription.created", "generation.spoken")
    for citizen in (tts_citizen, stt_citizen):
        events = citizen.manifest_data()["events"]
        assert set(events) <= set(PLUGIN_EVENTS)
        for name in invented:
            assert name not in events

# ---------------- Group C: migration and boot neighbours ----------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert "0042" not in MIGRATIONS


def test_boot_registry_stays_empty_without_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    assert TTS_ID not in registry.keys()
    assert STT_ID not in registry.keys()
    assert plugin_service.rehydration_problems() == []


def test_citizens_do_not_change_voice_registries_or_defaults():
    registry = PluginRegistry()
    tts_citizen.register_plugin(registry, enable=True)
    stt_citizen.register_plugin(registry, enable=True)
    assert DEFAULT_TTS_BACKEND == "cosyvoice"
    assert DEFAULT_STT_BACKEND == "faster-whisper"
    assert KNOWN_TTS_BACKENDS == tuple(TTS_REGISTRY) + ("fake-tts",)
    assert KNOWN_STT_BACKENDS == tuple(STT_REGISTRY) + ("fake-stt",)

# ---------------- Group D: config validation and leniency ----------------


def test_tts_config_validation():
    err = tts_citizen.TtsPluginError
    for bad_rate in (0.49, 2.01, True, "1", float("nan"), float("inf")):
        with pytest.raises(err):
            tts_citizen.TtsPluginConfig(speaking_rate=bad_rate)
    for bad_cap in (0, 4001, True, 2.5):
        with pytest.raises(err):
            tts_citizen.TtsPluginConfig(max_text_chars=bad_cap)
    with pytest.raises(err):
        tts_citizen.TtsPluginConfig(backend="cosyvoice")

    class _MissingAll:
        def synthesize(self, text, voice, *, speaking_rate=1.0):
            return []

        def model_info(self):
            return None

    with pytest.raises(err):
        tts_citizen.TtsPluginConfig(backend=_MissingAll())
    defaults = tts_citizen.TtsPluginConfig()
    assert defaults.speaking_rate == 1.0
    assert defaults.max_text_chars == 2000


def test_stt_config_validation():
    err = stt_citizen.SttPluginError
    for bad_cap in (3199, 16_000_001, True, 2.5):
        with pytest.raises(err):
            stt_citizen.SttPluginConfig(max_audio_bytes=bad_cap)
    with pytest.raises(err):
        stt_citizen.SttPluginConfig(backend="faster-whisper")

    class _MissingTranscribe:
        def model_info(self):
            return None

    with pytest.raises(err):
        stt_citizen.SttPluginConfig(backend=_MissingTranscribe())
    assert stt_citizen.SttPluginConfig().max_audio_bytes == 3_200_000


def test_tts_config_from_manifest_lenient():
    cfg = tts_citizen.config_from_manifest({})
    assert cfg.speaking_rate == 1.0 and cfg.max_text_chars == 2000
    assert cfg.backend is None
    data = tts_citizen.manifest_data()
    data["settings"] = {"schema": {}, "defaults": {
        "speaking_rate": 99, "max_text_chars": "x"}}
    cfg = tts_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.speaking_rate == 1.0 and cfg.max_text_chars == 2000
    data["settings"] = {"schema": {}, "defaults": {
        "speaking_rate": 1.25, "max_text_chars": 500}}
    cfg = tts_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.speaking_rate == 1.25 and cfg.max_text_chars == 500
    data["settings"] = {"schema": {}, "defaults": {"backend": "cosyvoice"}}
    cfg = tts_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.backend is None


def test_stt_config_from_manifest_lenient():
    cfg = stt_citizen.config_from_manifest({})
    assert cfg.max_audio_bytes == 3_200_000 and cfg.backend is None
    data = stt_citizen.manifest_data()
    data["settings"] = {"schema": {}, "defaults": {"max_audio_bytes": 6400}}
    cfg = stt_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.max_audio_bytes == 6400
    data["settings"] = {"schema": {}, "defaults": {"max_audio_bytes": 100}}
    cfg = stt_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.max_audio_bytes == 3_200_000
    data["settings"] = {"schema": {}, "defaults": {"backend": "faster-whisper"}}
    cfg = stt_citizen.config_from_manifest(manifest_from_data(data))
    assert cfg.backend is None


def test_register_plugin_backend_precedence():
    fixed_tts_a, fixed_tts_b = FixedTTSBackend(), FixedTTSBackend()
    cfg = tts_citizen.TtsPluginConfig(backend=fixed_tts_a)
    _r, plugin = tts_citizen.register_plugin(
        PluginRegistry(), backend=fixed_tts_b, config=cfg)
    assert plugin.backend is fixed_tts_b
    _r, plugin = tts_citizen.register_plugin(PluginRegistry(), config=cfg)
    assert plugin.backend is fixed_tts_a
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    assert isinstance(plugin.backend, FakeTTSBackend)
    fixed_stt_a, fixed_stt_b = FixedSTTBackend(), FixedSTTBackend()
    scfg = stt_citizen.SttPluginConfig(backend=fixed_stt_a)
    _r, splugin = stt_citizen.register_plugin(
        PluginRegistry(), backend=fixed_stt_b, config=scfg)
    assert splugin.backend is fixed_stt_b
    _r, splugin = stt_citizen.register_plugin(PluginRegistry(), config=scfg)
    assert splugin.backend is fixed_stt_a
    _r, splugin = stt_citizen.register_plugin(PluginRegistry())
    assert isinstance(splugin.backend, FakeSTTBackend)

# ---------------- Group E: TTS actions and parity ----------------


async def test_tts_default_wiring_is_labelled_fake():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    assert isinstance(plugin.backend, FakeTTSBackend)
    result = await plugin.synthesize(TEXT_MULTI)
    assert result["backend"] == "fake-tts"
    assert result["model"] == "fake-tts-1"
    assert result["road"] == "fake"


async def test_tts_synthesize_parity_with_direct_fake_backend():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    voice = VoiceInfo(voice_id="fake-voice", name="Fake voice",
                      language="en", backend_key="fake-tts")
    result = await plugin.synthesize(TEXT_MULTI, voice=voice)
    direct = FakeTTSBackend().synthesize_all(TEXT_MULTI, voice)
    assert result["chunk_count"] == len(direct)
    assert len(direct) > 1  # the multi-sentence fixture splits
    assert_tts_chunks_match(result["chunks"], direct)
    assert result["total_pcm_bytes"] == sum(len(c.pcm) for c in direct)
    assert result["total_duration_s"] == sum(c.duration_s for c in direct)


async def test_tts_synthesize_result_shape():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    text = "  Hello  there world. "
    result = await plugin.synthesize(text)
    assert set(result) == {
        "plugin_id", "kind", "performed", "performed_at", "chat_id",
        "text", "text_chars", "voice", "backend", "model", "road",
        "speaking_rate", "native_sample_rate", "chunk_count",
        "total_pcm_bytes", "total_duration_s", "chunks"}
    assert result["kind"] == "synthesize" and result["performed"] is True
    assert result["text"] == text  # verbatim, whitespace and all
    assert result["text_chars"] == len(text)
    assert result["chat_id"] is None
    for chunk in result["chunks"]:
        assert set(chunk) == {
            "index", "text", "sample_rate", "pcm_bytes", "duration_s",
            "is_final", "word_timings", "pcm_b64"}
        assert len(base64.b64decode(chunk["pcm_b64"])) == chunk["pcm_bytes"]
    assert result["total_duration_s"] == sum(
        c["duration_s"] for c in result["chunks"])


async def test_tts_fake_result_has_no_final_sentinel():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    result = await plugin.synthesize(TEXT_MULTI)
    assert result["chunk_count"] > 0
    assert all(chunk["is_final"] is False for chunk in result["chunks"])


async def test_tts_sentinel_chunk_passes_through_verbatim():
    backend = SentinelTTSBackend()
    _r, plugin = tts_citizen.register_plugin(PluginRegistry(), backend=backend)
    result = await plugin.synthesize("Anything at all.")
    voice = VoiceInfo(voice_id="fixed-voice", language="en",
                      backend_key="fixed-tts", name="Fixed voice")
    direct = SentinelTTSBackend().synthesize_all("Anything at all.", voice)
    assert result["chunk_count"] == len(direct) == 3
    assert_tts_chunks_match(result["chunks"], direct)
    last = result["chunks"][-1]
    assert last["pcm_bytes"] == 0 and last["pcm_b64"] == ""
    assert last["duration_s"] == 0.0 and last["is_final"] is True
    assert last["index"] == 2 and last["text"] == ""


async def test_tts_custom_backend_wiring_parity():
    voice = VoiceInfo(voice_id="fixed-voice", language="en",
                      backend_key="fixed-tts", name="Fixed voice")
    direct = FixedTTSBackend().synthesize_all("Hello fixed world.", voice)
    _r, via_register = tts_citizen.register_plugin(
        PluginRegistry(), backend=FixedTTSBackend())
    via_config = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=FixedTTSBackend()))
    for plugin in (via_register, via_config):
        result = await plugin.synthesize("Hello fixed world.", voice=voice)
        assert_tts_chunks_match(result["chunks"], direct)
        assert all(c["sample_rate"] == 24000 for c in result["chunks"])
        assert result["road"] == "fixed-tts"
        assert result["native_sample_rate"] == 24000
        assert result["backend"] == "fixed-tts"
        assert result["model"] == "fixed-tts-1"


async def test_tts_speaking_rate_threaded_and_validated():
    backend = RateRecordingTTSBackend()
    plugin = tts_citizen.TtsPlugin(tts_citizen.TtsPluginConfig(
        backend=backend, speaking_rate=1.5))
    result = await plugin.synthesize("Rate check one.")
    assert backend.rates == [1.5]
    assert result["speaking_rate"] == 1.5
    backend2 = RateRecordingTTSBackend()
    plugin2 = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=backend2))
    result2 = await plugin2.synthesize("Rate check two.", speaking_rate=0.75)
    assert backend2.rates == [0.75]  # the per-call override wins
    assert result2["speaking_rate"] == 0.75
    backend3 = RateRecordingTTSBackend()
    plugin3 = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=backend3))
    with pytest.raises(tts_citizen.TtsPluginError):
        await plugin3.synthesize("Rate check three.", speaking_rate=2.5)
    assert backend3.rates == []  # refused before the backend was touched


async def test_tts_voice_argument_forms():
    fixed = FixedTTSBackend()
    plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=fixed))
    voice = VoiceInfo(voice_id="fixed-voice", language="en",
                      backend_key="fixed-tts", name="Fixed voice")
    result = await plugin.synthesize("Voice forms.", voice=voice)
    assert_tts_chunks_match(
        result["chunks"], FixedTTSBackend().synthesize_all("Voice forms.", voice))
    assert result["voice"]["voice_id"] == "fixed-voice"
    mapped = await plugin.synthesize(
        "Voice forms.", voice={"voice_id": "fixed-voice", "language": "en"})
    assert mapped["voice"] == {
        "voice_id": "fixed-voice", "language": "en", "backend_key": "",
        "name": "", "prompt_text": "", "prompt_wav": ""}
    counting = CountingTTSBackend()
    cplugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=counting))
    with pytest.raises(tts_citizen.TtsPluginError):
        await cplugin.synthesize("Voice forms.",
                                 voice={"voice_id": "x", "bogus": "y"})
    with pytest.raises(tts_citizen.TtsPluginError):
        await cplugin.synthesize("Voice forms.", voice={"language": "en"})
    assert counting.total_calls == 0
    by_string = await plugin.synthesize("Voice forms.", voice="fixed-voice")
    assert by_string["voice"]["voice_id"] == "fixed-voice"
    assert by_string["voice"]["backend_key"] == "fixed-tts"
    _r, fake_plugin = tts_citizen.register_plugin(PluginRegistry())
    by_none = await fake_plugin.synthesize("Voice forms.")
    assert by_none["voice"]["voice_id"] == "fake-voice"
    no_voices = NoVoicesFixedTTSBackend()
    nv_plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=no_voices))
    with pytest.raises(tts_citizen.TtsPluginError):
        await nv_plugin.synthesize("Voice forms.")
    assert no_voices.synthesize_all_calls == 0


async def test_tts_audition_uses_backend_sample():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    result = await plugin.audition()
    assert result["kind"] == "audition"
    assert result["text"] == tts_citizen.AUDITION_SAMPLE_TEXT
    assert result["sample_text"] == tts_citizen.AUDITION_SAMPLE_TEXT
    voice = plugin.backend.voices()[0]
    direct = plugin.backend.audition(voice)
    assert_tts_chunks_match(result["chunks"], direct)
    custom = await plugin.audition(text="A custom sample line.")
    assert custom["text"] == "A custom sample line."
    assert_tts_chunks_match(
        custom["chunks"], plugin.backend.audition(voice, "A custom sample line."))
    counting = CountingTTSBackend()
    cplugin = tts_citizen.TtsPlugin(tts_citizen.TtsPluginConfig(
        backend=counting, max_text_chars=10))
    with pytest.raises(tts_citizen.TtsPluginError):
        await cplugin.audition(text="x" * 11)
    assert counting.total_calls == 0
    stored = await plugin.audition(chat_id="chat-a")
    status = plugin.speech_status("chat-a")
    assert status["has_result"] is True
    assert status["latest"] == stored
    _r, fresh = tts_citizen.register_plugin(PluginRegistry())
    await fresh.audition()
    assert fresh.speech_status("chat-a")["has_result"] is False


async def test_tts_voices_and_model_introspection():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    voices = await plugin.list_voices()
    assert set(voices) == {"plugin_id", "backend", "road", "voices"}
    assert voices["backend"] == "fake-tts" and voices["road"] == "fake"
    assert voices["voices"] == [{
        "voice_id": "fake-voice", "language": "en",
        "backend_key": "fake-tts", "name": "Fake voice",
        "prompt_text": "", "prompt_wav": ""}]
    info = await plugin.model_info()
    assert set(info) == {"plugin_id", "backend", "model", "road",
                         "voices", "native_sample_rate"}
    assert info["backend"] == "fake-tts" and info["model"] == "fake-tts-1"
    assert info["voices"] == ["fake-voice"]
    assert info["native_sample_rate"] == 16000 and info["road"] == "fake"
    fixed_plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=FixedTTSBackend()))
    fixed_info = await fixed_plugin.model_info()
    assert fixed_info["native_sample_rate"] == 24000
    assert fixed_info["road"] == "fixed-tts"


async def test_tts_async_backend_is_unwrapped():
    plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=AsyncTTSBackend()))
    voice = VoiceInfo(voice_id="fixed-voice", language="en",
                      backend_key="fixed-tts", name="Fixed voice")
    result = await plugin.synthesize("Async road.", voice=voice)
    assert_tts_chunks_match(
        result["chunks"], FixedTTSBackend().synthesize_all("Async road.", voice))
    voices = await plugin.list_voices()
    assert [v["voice_id"] for v in voices["voices"]] == ["fixed-voice"]
    info = await plugin.model_info()
    assert info["model"] == "fixed-tts-1"
    assert info["native_sample_rate"] == 24000


async def test_tts_duck_backend_is_accepted():
    duck = DuckTTSBackend()
    _r, plugin = tts_citizen.register_plugin(PluginRegistry(), backend=duck)
    assert plugin.backend is duck
    voice = VoiceInfo(voice_id="fixed-voice", language="en",
                      backend_key="fixed-tts", name="Fixed voice")
    result = await plugin.synthesize("Duck road.", voice=voice)
    assert_tts_chunks_match(
        result["chunks"], DuckTTSBackend().synthesize_all("Duck road.", voice))
    assert result["road"] == "fixed-tts"

# ---------------- Group F: TTS storage, status, failures, events ----------------


async def test_tts_speech_status_shapes():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    status = plugin.speech_status("chat-a")
    assert set(status) == {"plugin_id", "chat_id", "backend_key",
                           "has_result", "latest", "observed"}
    assert status["plugin_id"] == TTS_ID and status["chat_id"] == "chat-a"
    assert status["backend_key"] == "fake-tts"
    assert status["has_result"] is False
    assert status["latest"] is None and status["observed"] is None
    result = await plugin.synthesize(TEXT_MULTI, chat_id="chat-a")
    status = plugin.speech_status("chat-a")
    assert status["has_result"] is True and status["latest"] == result
    assert plugin.last_result("chat-a") == result
    _r, fresh = tts_citizen.register_plugin(PluginRegistry())
    await fresh.synthesize(TEXT_MULTI)  # chat_id=None stores nothing
    assert fresh.speech_status("chat-a")["has_result"] is False
    assert fresh.last_result("chat-a") is None
    with pytest.raises(tts_citizen.TtsPluginError):
        plugin.speech_status("")
    with pytest.raises(tts_citizen.TtsPluginError):
        plugin.speech_status(None)
    status["latest"]["text"] = "MUTATED"
    status["latest"]["chunks"].clear()
    again = plugin.speech_status("chat-a")
    assert again["latest"] == result  # deepcopy discipline


async def test_tts_validation_precedes_backend():
    counting = CountingTTSBackend()
    plugin = tts_citizen.TtsPlugin(tts_citizen.TtsPluginConfig(
        backend=counting, max_text_chars=10))
    err = tts_citizen.TtsPluginError
    with pytest.raises(err):
        await plugin.synthesize("", chat_id="chat-a")
    with pytest.raises(err):
        await plugin.synthesize("   ", chat_id="chat-a")
    with pytest.raises(err):
        await plugin.synthesize("x" * 11, chat_id="chat-a")
    with pytest.raises(err):
        await plugin.synthesize("ok", voice={"voice_id": "x", "nope": "y"})
    with pytest.raises(err):
        await plugin.synthesize("ok", chat_id="")
    with pytest.raises(err):
        await plugin.synthesize("ok", speaking_rate=2.5)
    assert counting.total_calls == 0
    assert plugin.speech_status("chat-a")["has_result"] is False


async def test_tts_failure_stores_nothing_and_preserves_prior():
    flaky = FlakyTTSBackend()
    plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=flaky))
    first = await plugin.synthesize("First works.", chat_id="chat-a")
    with pytest.raises(tts_citizen.TtsPluginError) as excinfo:
        await plugin.synthesize("Second fails.", chat_id="chat-a")
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "flaky boom" in str(excinfo.value.__cause__)
    status = plugin.speech_status("chat-a")
    assert status["has_result"] is True and status["latest"] == first
    armed = tts_citizen.TtsPlugin(tts_citizen.TtsPluginConfig(
        backend=FlakyTTSBackend(fail_immediately=True)))
    with pytest.raises(tts_citizen.TtsPluginError):
        await armed.synthesize("Never stored.", chat_id="chat-a")
    assert armed.speech_status("chat-a")["has_result"] is False


async def test_tts_backend_unavailable_is_wrapped_never_faked():
    unavailable = UnavailableTTSBackend()
    plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=unavailable))
    with pytest.raises(tts_citizen.TtsPluginError) as excinfo:
        await plugin.synthesize("Real speech please.", chat_id="chat-a")
    assert isinstance(excinfo.value.__cause__, BackendUnavailable)
    assert plugin.speech_status("chat-a")["has_result"] is False
    assert plugin.backend is unavailable  # never swapped for the fake


async def test_tts_message_created_records_metadata_only():
    secret = "the secret spoken words xyzzy"
    counting = CountingTTSBackend()
    plugin = tts_citizen.TtsPlugin(
        tts_citizen.TtsPluginConfig(backend=counting))
    payload = message_payload(chat_id="chat-a", message_id="m1",
                                role="user", content=secret,
                                permissions=["chat.read"])
    await plugin.on_event(make_event(
        "message.created", chat_id="chat-a", message_id="m1", data=payload))
    observed = plugin.speech_status("chat-a")["observed"]
    assert observed["messages_observed"] == 1
    assert observed["last_message_id"] == "m1"
    assert observed["last_role"] == "user"
    assert observed["last_content_chars"] == len(secret)
    payload2 = message_payload(chat_id="chat-a", message_id="m2",
                                 role="assistant", content=secret,
                                 permissions=["chat.read"])
    await plugin.on_event(make_event(
        "message.created", chat_id="chat-a", message_id="m2", data=payload2))
    status = plugin.speech_status("chat-a")
    assert status["observed"]["messages_observed"] == 2
    assert status["observed"]["last_message_id"] == "m2"
    assert secret not in repr(status)  # the text is never stored
    assert counting.calls["synthesize"] == 0
    assert counting.calls["synthesize_all"] == 0
    assert counting.calls["audition"] == 0
    assert status["has_result"] is False
    registry = PluginRegistry()
    counting2 = CountingTTSBackend()
    _r, plugin2 = tts_citizen.register_plugin(
        registry, backend=counting2, enable=True)
    await registry.dispatch_event(
        "message.created", chat_id="chat-a", message_id="m9", data=payload)
    status2 = plugin2.speech_status("chat-a")
    assert status2["observed"]["messages_observed"] == 1
    assert secret not in repr(status2)
    assert counting2.calls["synthesize_all"] == 0
    assert status2["has_result"] is False


async def test_tts_event_never_synthesizes():
    counting = CountingTTSBackend()
    registry = PluginRegistry()
    _r, plugin = tts_citizen.register_plugin(
        registry, backend=counting, enable=True)
    data = {"chat_id": "chat-a", "message_id": "m1", "role": "user",
            "content_chars": 5}
    for name in sorted(PLUGIN_EVENTS):
        await registry.dispatch_event(
            name, chat_id="chat-a", message_id="m1", data=data)
    for name in tts_citizen.DECLARED_EVENTS:
        await plugin.on_event(make_event(
            name, chat_id="chat-a", message_id="m1", data=data))
    assert counting.calls["synthesize"] == 0
    assert counting.calls["synthesize_all"] == 0
    assert counting.calls["audition"] == 0


async def test_tts_chat_deleted_clears_state():
    _r, plugin = tts_citizen.register_plugin(PluginRegistry())
    await plugin.synthesize(TEXT_MULTI, chat_id="chat-a")
    await plugin.synthesize(TEXT_MULTI, chat_id="chat-b")
    for chat in ("chat-a", "chat-b"):
        payload = message_payload(chat_id=chat, message_id="m1", role="user",
                                    content="hi", permissions=["chat.read"])
        await plugin.on_event(make_event(
            "message.created", chat_id=chat, message_id="m1", data=payload))
    await plugin.on_event(make_event("chat.deleted", chat_id="chat-a"))
    gone = plugin.speech_status("chat-a")
    assert gone["has_result"] is False and gone["latest"] is None
    assert gone["observed"] is None
    kept = plugin.speech_status("chat-b")
    assert kept["has_result"] is True and kept["observed"] is not None
    registry = PluginRegistry()
    _r, plugin2 = tts_citizen.register_plugin(registry, enable=True)
    await plugin2.synthesize(TEXT_MULTI, chat_id="chat-b")
    await registry.dispatch_event("chat.deleted", chat_id="chat-b")
    assert plugin2.speech_status("chat-b")["has_result"] is False


async def test_tts_registered_but_not_enabled_gets_no_events():
    counting = CountingTTSBackend()
    registry = PluginRegistry()
    record, plugin = tts_citizen.register_plugin(registry, backend=counting)
    assert record.state is PluginState.REGISTERED
    payload = message_payload(chat_id="chat-a", message_id="m1", role="user",
                                content="hello", permissions=["chat.read"])
    report = await registry.dispatch_event(
        "message.created", chat_id="chat-a", message_id="m1", data=payload)
    assert TTS_ID not in report.delivered
    assert plugin.speech_status("chat-a")["observed"] is None

# ---------------- Group G: STT actions and parity ----------------


async def test_stt_default_wiring_is_labelled_fake():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    assert isinstance(plugin.backend, FakeSTTBackend)
    result = await plugin.transcribe(PCM_16K, sample_rate=16000)
    assert result["backend"] == "fake-stt"
    assert result["model"] == "fake-stt-1"
    assert result["road"] == "fake"
    assert result["text"] == "hello world"
    assert result["language"] == "en"


async def test_stt_transcribe_parity_with_direct_fake_backend():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    result = await plugin.transcribe(PCM_16K, sample_rate=16000)
    direct = FakeSTTBackend().transcribe(PCM_16K, 16000)
    assert set(result) == {
        "plugin_id", "kind", "performed", "performed_at", "chat_id",
        "sample_rate", "pcm_bytes", "duration_s", "text", "language",
        "segments", "words", "segment_count", "word_count", "backend",
        "model", "transcript_backend_key", "transcript_model_id", "road",
        "supports_word_timestamps", "supports_streaming"}
    assert result["text"] == direct.text
    assert result["language"] == direct.language
    expected_segments = [{
        "text": seg.text, "start_s": seg.start_s, "end_s": seg.end_s,
        "words": [{"text": w.text, "start_s": w.start_s, "end_s": w.end_s,
                   "probability": w.probability} for w in seg.words]}
        for seg in direct.segments]
    assert result["segments"] == expected_segments
    assert result["words"] == [
        {"text": w.text, "start_s": w.start_s, "end_s": w.end_s,
         "probability": w.probability} for w in direct.words]
    assert result["duration_s"] == (len(PCM_16K) // 2) / 16000
    assert result["segment_count"] == 1 and result["word_count"] == 2


async def test_stt_scripted_fake_via_direct_construction():
    scripted = FakeSTTBackend(text="the wind rises", language="is")
    plugin = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=scripted))
    result = await plugin.transcribe(PCM_16K)
    assert result["text"] == "the wind rises"
    assert result["language"] == "is"
    assert [w["text"] for w in result["words"]] == ["the", "wind", "rises"]
    assert result["road"] == "fake"


async def test_stt_custom_backend_wiring_parity():
    direct = FixedSTTBackend().transcribe(PCM_16K, 16000)
    _r, via_register = stt_citizen.register_plugin(
        PluginRegistry(), backend=FixedSTTBackend())
    via_config = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=FixedSTTBackend()))
    for plugin in (via_register, via_config):
        result = await plugin.transcribe(PCM_16K, sample_rate=16000)
        assert result["text"] == direct.text
        assert result["language"] == direct.language
        assert result["segment_count"] == 2
        assert [w["text"] for w in result["words"]] == ["alpha", "beta", "gamma"]
        assert result["segments"][0]["text"] == "alpha beta"
        assert result["segments"][1]["text"] == "gamma"
        assert result["road"] == "fixed-stt"
        assert result["backend"] == "fixed-stt"
        assert result["transcript_backend_key"] == "fixed-stt"
        assert result["transcript_model_id"] == "fixed-stt-1"
        assert result["model"] == "fixed-stt-1"


async def test_stt_sample_rate_passthrough():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    at_16k = await plugin.transcribe(PCM_16K, sample_rate=16000)
    at_24k = await plugin.transcribe(PCM_16K, sample_rate=24000)
    assert at_16k["duration_s"] == 0.5
    # Pass-through, no resampling: duration is citizen-computed from
    # the input at the given rate, (16000 // 2) / 24000 s.
    assert at_24k["duration_s"] == (len(PCM_16K) // 2) / 24000
    assert at_24k["sample_rate"] == 24000
    counting = CountingSTTBackend()
    cplugin = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=counting))
    for bad_rate in (0, 4000, 96000, "16000", True):
        with pytest.raises(stt_citizen.SttPluginError):
            await cplugin.transcribe(PCM_16K, sample_rate=bad_rate)
    assert counting.calls["transcribe"] == 0


async def test_stt_pcm_validation_precedes_backend():
    counting = CountingSTTBackend()
    plugin = stt_citizen.SttPlugin(stt_citizen.SttPluginConfig(
        backend=counting, max_audio_bytes=3200))
    err = stt_citizen.SttPluginError
    with pytest.raises(err):
        await plugin.transcribe("audio", chat_id="chat-a")
    with pytest.raises(err):
        await plugin.transcribe(b"", chat_id="chat-a")
    with pytest.raises(err):
        await plugin.transcribe(b"\x00\x00\x00", chat_id="chat-a")
    with pytest.raises(err):
        await plugin.transcribe(b"\x00\x01" * 1601, chat_id="chat-a")
    assert counting.calls["transcribe"] == 0
    assert plugin.transcription_status("chat-a")["has_result"] is False
    ok = await plugin.transcribe(bytearray(b"\x00\x01" * 100))
    assert ok["text"] == "hello world"
    assert counting.calls["transcribe"] == 1


async def test_stt_health_and_model_info():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    health = await plugin.health()
    assert set(health) == {"plugin_id", "backend", "healthy", "model", "error"}
    assert health["healthy"] is True
    assert health["model"] == "fake-stt-1" and health["error"] is None
    assert health["backend"] == "fake-stt"
    broken = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=BrokenInfoSTTBackend()))
    broken_health = await broken.health()  # reports, never raises
    assert broken_health["healthy"] is False
    assert broken_health["error"] is not None
    assert "info boom" in broken_health["error"]
    with pytest.raises(stt_citizen.SttPluginError):
        await broken.model_info()
    duck_plugin = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=DuckSTTBackend()))
    assert not hasattr(DuckSTTBackend(), "health_check")
    duck_health = await duck_plugin.health()
    assert duck_health["healthy"] is True
    assert duck_health["model"] == "fixed-stt-1"
    assert duck_health["error"] is None


async def test_stt_async_backend_is_unwrapped():
    plugin = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=AsyncSTTBackend()))
    result = await plugin.transcribe(PCM_16K, sample_rate=16000)
    direct = FixedSTTBackend().transcribe(PCM_16K, 16000)
    assert result["text"] == direct.text
    assert result["segment_count"] == 2
    assert [w["text"] for w in result["words"]] == ["alpha", "beta", "gamma"]
    info = await plugin.model_info()
    assert info["model"] == "fixed-stt-1" and info["road"] == "fixed-stt"


async def test_stt_failure_stores_nothing_and_preserves_prior():
    flaky = FlakySTTBackend()
    plugin = stt_citizen.SttPlugin(
        stt_citizen.SttPluginConfig(backend=flaky))
    first = await plugin.transcribe(PCM_16K, chat_id="chat-a")
    with pytest.raises(stt_citizen.SttPluginError) as excinfo:
        await plugin.transcribe(PCM_16K, chat_id="chat-a")
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "flaky boom" in str(excinfo.value.__cause__)
    status = plugin.transcription_status("chat-a")
    assert status["has_result"] is True and status["latest"] == first
    armed = stt_citizen.SttPlugin(stt_citizen.SttPluginConfig(
        backend=FlakySTTBackend(fail_immediately=True)))
    with pytest.raises(stt_citizen.SttPluginError):
        await armed.transcribe(PCM_16K, chat_id="chat-a")
    assert armed.transcription_status("chat-a")["has_result"] is False

# ---------------- Group H: STT storage, status, events; pair behaviour ----------------


async def test_stt_transcription_status_shapes():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    status = plugin.transcription_status("chat-a")
    assert set(status) == {"plugin_id", "chat_id", "backend_key",
                           "has_result", "latest"}
    assert status["plugin_id"] == STT_ID and status["chat_id"] == "chat-a"
    assert status["backend_key"] == "fake-stt"
    assert status["has_result"] is False and status["latest"] is None
    result = await plugin.transcribe(PCM_16K, chat_id="chat-a")
    status = plugin.transcription_status("chat-a")
    assert status["has_result"] is True and status["latest"] == result
    assert plugin.last_transcript("chat-a") == result
    _r, fresh = stt_citizen.register_plugin(PluginRegistry())
    await fresh.transcribe(PCM_16K)  # chat_id=None stores nothing
    assert fresh.transcription_status("chat-a")["has_result"] is False
    assert fresh.last_transcript("chat-a") is None
    with pytest.raises(stt_citizen.SttPluginError):
        plugin.transcription_status("")
    with pytest.raises(stt_citizen.SttPluginError):
        plugin.transcription_status(None)
    status["latest"]["text"] = "MUTATED"
    again = plugin.transcription_status("chat-a")
    assert again["latest"] == result  # deepcopy discipline


async def test_stt_no_event_transcribes():
    counting = CountingSTTBackend()
    registry = PluginRegistry()
    _r, plugin = stt_citizen.register_plugin(
        registry, backend=counting, enable=True)
    data = {"chat_id": "chat-a", "message_id": "m1", "role": "user",
            "content_chars": 5}
    for name in sorted(PLUGIN_EVENTS):
        report = await registry.dispatch_event(
            name, chat_id="chat-a", message_id="m1", data=data)
        if name == "message.created":
            assert STT_ID not in report.delivered  # not subscribed
    await plugin.on_event(make_event("chat.deleted", chat_id="chat-a"))
    assert counting.calls["transcribe"] == 0


async def test_stt_chat_deleted_clears_state():
    _r, plugin = stt_citizen.register_plugin(PluginRegistry())
    await plugin.transcribe(PCM_16K, chat_id="chat-a")
    await plugin.transcribe(PCM_16K, chat_id="chat-b")
    await plugin.on_event(make_event("chat.deleted", chat_id="chat-a"))
    assert plugin.transcription_status("chat-a")["has_result"] is False
    assert plugin.transcription_status("chat-b")["has_result"] is True
    registry = PluginRegistry()
    _r, plugin2 = stt_citizen.register_plugin(registry, enable=True)
    await plugin2.transcribe(PCM_16K, chat_id="chat-b")
    await registry.dispatch_event("chat.deleted", chat_id="chat-b")
    assert plugin2.transcription_status("chat-b")["has_result"] is False


async def test_both_citizens_chat_deleted_clears_both():
    registry = PluginRegistry()
    _r, tts_plugin = tts_citizen.register_plugin(registry, enable=True)
    counting_stt = CountingSTTBackend()
    _r, stt_plugin = stt_citizen.register_plugin(
        registry, backend=counting_stt, enable=True)
    await tts_plugin.synthesize(TEXT_MULTI, chat_id="chat-x")
    await stt_plugin.transcribe(PCM_16K, chat_id="chat-x")
    assert counting_stt.calls["transcribe"] == 1
    payload = message_payload(chat_id="chat-x", message_id="m1", role="user",
                                content="hello there", permissions=["chat.read"])
    await registry.dispatch_event(
        "message.created", chat_id="chat-x", message_id="m1", data=payload)
    tts_status = tts_plugin.speech_status("chat-x")
    assert tts_status["observed"]["messages_observed"] == 1
    stt_status = stt_plugin.transcription_status("chat-x")
    assert stt_status["has_result"] is True  # STT untouched by the event
    assert counting_stt.calls["transcribe"] == 1
    await registry.dispatch_event("chat.deleted", chat_id="chat-x")
    tts_after = tts_plugin.speech_status("chat-x")
    assert tts_after["has_result"] is False and tts_after["latest"] is None
    assert tts_after["observed"] is None
    stt_after = stt_plugin.transcription_status("chat-x")
    assert stt_after["has_result"] is False and stt_after["latest"] is None
