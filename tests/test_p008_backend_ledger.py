"""P-008 acceptance: the backend parity ledger.

The ledger (docs/BACKEND_PARITY_LEDGER_2026-10-30.md) judges every
backend the mirrors name against this tree. These tests pin the
tree-side facts the ledger rests on, so a future slice that changes
one (above all the generic OpenAI-compatible adapter the ledger
recommends to the P-014 gate) must update the ledger deliberately
instead of the ledger silently going stale.

Updated deliberately by F-01 (the gate's follow-on slice that built
the generic adapter): the pins below now record the post-F-01 tree —
five chat backends including ``openai``, embeddings including
``openai`` — and the ledger carries F-01's follow-on note.
"""

from __future__ import annotations

from pathlib import Path

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.fake import FakeChatBackend
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
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


def test_chat_backends_are_exactly_the_five_adapters() -> None:
    # Five since F-01 added the generic OpenAI-compatible adapter.
    assert CHAT_BACKENDS == ("fake", "ollama", "openrouter", "aesir", "openai")
    assert FakeChatBackend.backend_key == "fake"
    assert OllamaChatBackend.backend_key == "ollama"
    assert OpenRouterChatBackend.backend_key == "openrouter"
    assert AesirChatBackend.backend_key == "aesir"
    assert OpenAICompatibleChatBackend.backend_key == "openai"


def test_embedding_backends_are_independent_and_named() -> None:
    assert EMBEDDING_BACKENDS == ("", "fake", "ollama", "aesir", "openai")


def test_generic_openai_gap_is_closed_by_f01() -> None:
    # The connection layer (S211) names a generic "openai" kind, and
    # the sampler layer (S208) has an "openai" wire profile; F-01
    # made the kind real behind both. This test replaces the
    # gap-pinning test F-01 was instructed to update on purpose.
    assert CONNECTION_BACKENDS == ("fake", "ollama", "openai")
    assert "openai" in CHAT_BACKENDS
    assert set(SAMPLER_PROFILES) == {"openai", "ollama"}
    text = LEDGER.read_text(encoding="utf-8")
    assert "F-01 follow-on" in text


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
