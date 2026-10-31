"""P-010 acceptance: the voice provider census.

The census (docs/VOICE_PROVIDER_CENSUS_2026-10-30.md) judges the
mirrors' named STT/TTS providers against Rúnmál's licence gate.
These tests pin the tree-side facts the census rests on — the
exact TTS/STT registries, their defaults and classes — and the
census's own completeness (every judged provider named, the
verdict totals and the NO-HOME recommendations recorded), so a
future voice slice must update the census deliberately instead
of the census silently going stale.

Updated deliberately by F-03 (the gate's follow-on slice that
built the generic speech adapter): the registry pins below now
record the post-F-03 tree — the ``openai`` connect adapter
appended on both seams — and the census carries F-03's
follow-on note in its §7.
"""

from __future__ import annotations

from pathlib import Path

from runmal.voice.backends import (
    DEFAULT_TTS_BACKEND,
    KNOWN_TTS_BACKENDS,
    TTS_REGISTRY,
)
from runmal.voice.stt_backends import (
    DEFAULT_STT_BACKEND,
    KNOWN_STT_BACKENDS,
    STT_REGISTRY,
)

CENSUS = (
    Path(__file__).parent.parent
    / "docs"
    / "VOICE_PROVIDER_CENSUS_2026-10-30.md"
)

# The 18 distinct TTS providers judged in census §1.
TTS_PROVIDERS = (
    "AllTalk", "Azure TTS", "Coqui-TTS", "Edge", "Electron Hub",
    "ElevenLabs", "Google Translate", "Google Gemini TTS", "Kokoro",
    "MiniMax", "NovelAI", "OpenAI", "Pollinations",
    "OpenAI-compatible", "Silero", "System", "XTTS", "Voxta Cloud",
)

# The 5 distinct STT providers judged in census §2 (all Voxta's).
STT_PROVIDERS = (
    "OpenAI", "WhisperLive", "AssemblyAI", "Deepgram", "Voxta Cloud",
)


def test_tts_registry_is_exactly_the_census_tree_side() -> None:
    assert tuple(TTS_REGISTRY) == (
        "cosyvoice", "chatterbox", "kitten", "piper", "openai",
    )
    assert DEFAULT_TTS_BACKEND == "cosyvoice"
    assert KNOWN_TTS_BACKENDS == tuple(TTS_REGISTRY) + ("fake-tts",)
    # The census's class claims: exactly one default-shipped TTS
    # backend, and it is the admitted one.
    shipped = [k for k, s in TTS_REGISTRY.items() if s.default_shipped]
    assert shipped == ["cosyvoice"]
    assert TTS_REGISTRY["cosyvoice"].verified is True


def test_stt_registry_is_exactly_the_census_tree_side() -> None:
    assert tuple(STT_REGISTRY) == (
        "faster-whisper", "distil-whisper", "whisper-cpp",
        "openai-whisper", "moonshine", "parakeet", "canary", "vosk",
        "sherpa-onnx-stt", "silero-stt", "openai",
    )
    assert DEFAULT_STT_BACKEND == "faster-whisper"
    assert KNOWN_STT_BACKENDS == tuple(STT_REGISTRY) + ("fake-stt",)
    shipped = [k for k, s in STT_REGISTRY.items() if s.default_shipped]
    assert shipped == ["faster-whisper"]


def test_census_judges_every_mirror_provider() -> None:
    text = CENSUS.read_text(encoding="utf-8")
    for name in TTS_PROVIDERS + STT_PROVIDERS:
        assert name in text, f"census does not judge {name}"


def test_census_records_totals_and_verdict_classes() -> None:
    text = CENSUS.read_text(encoding="utf-8")
    # 23 distinct judged; the totals line is the census's count.
    assert "23 distinct mirror voice providers judged" in text
    assert "18 judged" in text and "5 judged" in text
    # Both FAIL-SHIP rows rest on the founding survey's two traps.
    assert "FAIL-SHIP" in text
    assert "Coqui Public Model License" in text  # XTTS weights
    assert "eSpeak" in text  # Kokoro's phonemization heart
    # The gate's scope line: it guards only what Rúnmál ships.
    assert "only what Rúnmál ships by default" in text


def test_census_records_flags_and_gate_recommendations() -> None:
    text = CENSUS.read_text(encoding="utf-8")
    # Surveyed-but-not-enumerated is recorded, never invented.
    assert "surveyed-but-not-enumerated" in text
    # The 2026 refresh entrant and its non-commercial verdict.
    assert "Voxtral TTS" in text and "CC-BY-NC-4.0" in text
    # REVERIFY rows: papers not read, no gate pass claimed.
    assert "REVERIFY" in text and "WhisperLive" in text
    # Generic speech adapter + cloud connectors: NO HOME, P-014.
    assert "NO HOME" in text and "P-014" in text
    # Vice versa: the shipped default is named by neither mirror.
    assert "CosyVoice 2" in text
