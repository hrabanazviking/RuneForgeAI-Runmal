"""Token counting utilities (shared).

:func:`estimate_tokens` is a deterministic heuristic -- cheap,
dependency-free, good enough for budget decisions. PROMPT_COMPOSER §8
requires count *quality* metadata so estimates are never mistaken for
precision; see :class:`TokenQuality`.
"""

from __future__ import annotations

from enum import Enum


class TokenQuality(str, Enum):
    EXACT = "exact"  # tokenizer/provider exact for the selected model
    PROVIDER = "provider"  # provider endpoint/service result
    ESTIMATED = "estimated"  # conservative approximation


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: ``max(1, len(text) // 4)``."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return max(1, len(text) // 4)
