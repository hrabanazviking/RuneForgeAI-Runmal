"""P-008 acceptance: the backend parity ledger.

The ledger (docs/BACKEND_PARITY_LEDGER_2026-10-30.md) judges every
backend the mirrors name against this tree. These tests pin the
tree-side facts the ledger rests on, so a future slice that changes
one (above all the generic OpenAI-compatible adapter the ledger
recommends to the P-014 gate) must update the ledger deliberately
instead of the ledger silently going stale.
"""

from __future__ import annotations

from pathlib import Path

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.fake import FakeChatBackend
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.profiles import CHAT_BACKENDS, EMBEDDING_BACKENDS
from runmal.connections.service import VALID_BACKENDS as CONNECTION_BACKENDS
from runmal.generation.compat import PROFILES as SAMPLER_PROFILES

LEDGER = (
    Path(__file__).parent.parent
    / "docs"
    / "BACKEND_PARITY_LEDGER_2026-10-30.md"
)

# Every distinct backend/source named in ledger Tables A-C (22).
MIRROR_NAMES = (
    "OpenAI", "Claude", "Google AI Studio", "Google Vertex AI",
    "Mistral AI", "DeepSeek", "AI21", "Cohere", "Perplexity",
    "Fireworks AI", "Electron Hub", "OpenRouter",
    "Custom (OpenAI-compatible)", "llama.cpp",
    "Text Generation WebUI", "TabbyAPI", "KoboldCpp", "NovelAI",
    "Ollama", "AI Horde", "ExLlamaV3", "Voxta Cloud",
)


def test_chat_backends_are_exactly_the_four_adapters() -> None:
    assert CHAT_BACKENDS == ("fake", "ollama", "openrouter", "aesir")
    assert FakeChatBackend.backend_key == "fake"
    assert OllamaChatBackend.backend_key == "ollama"
    assert OpenRouterChatBackend.backend_key == "openrouter"
    assert AesirChatBackend.backend_key == "aesir"


def test_embedding_backends_are_independent_and_named() -> None:
    assert EMBEDDING_BACKENDS == ("", "fake", "ollama", "aesir")


def test_generic_openai_gap_is_pinned() -> None:
    # The connection layer (S211) names a generic "openai" kind, and
    # the sampler layer (S208) has an "openai" wire profile, but no
    # generic OpenAI-compatible CHAT backend exists yet. This is the
    # ledger's key gap; when a slice closes it, this test and the
    # ledger must both change on purpose.
    assert CONNECTION_BACKENDS == ("fake", "ollama", "openai")
    assert "openai" not in CHAT_BACKENDS
    assert set(SAMPLER_PROFILES) == {"openai", "ollama"}


def test_ledger_judges_every_mirror_name() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for name in MIRROR_NAMES:
        assert name in text, f"ledger does not judge {name}"


def test_ledger_records_the_reserved_verdicts() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    # ST-44's judgement was reserved to this slice by P-004.
    assert "AI Horde" in text and "UNWANTED" in text
    # The generic adapter recommendation and its NO-HOME flag.
    assert "WANTED-GENERIC" in text
    assert "NO HOME" in text and "P-014" in text
    # Vice versa: Rúnmál's own sovereign backend is in the ledger.
    assert "Aesir" in text
