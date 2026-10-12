"""Token counting utilities (shared).

:func:`estimate_tokens` is a deterministic heuristic -- cheap,
dependency-free, good enough for budget decisions. PROMPT_COMPOSER §8
requires count *quality* metadata so estimates are never mistaken for
precision; see :class:`TokenQuality`.

S214 counting discipline:
- exact tokenizer counts (when a tokenizer is available) -> EXACT
- provider-reported usage counts -> PROVIDER
- everything else -> the heuristic, labeled ESTIMATED
A combined label is only as strong as its weakest part
(:func:`worst_quality`): a manifest with any estimated part is ESTIMATED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TokenQuality(str, Enum):
    EXACT = "exact"  # tokenizer/provider exact for the selected model
    PROVIDER = "provider"  # provider endpoint/service result
    ESTIMATED = "estimated"  # conservative approximation


_QUALITY_RANK = {TokenQuality.ESTIMATED: 0, TokenQuality.PROVIDER: 1,
                 TokenQuality.EXACT: 2}


def worst_quality(qualities: list[TokenQuality]) -> TokenQuality:
    """The weakest label in a set (conservative manifest labeling)."""
    if not qualities:
        return TokenQuality.ESTIMATED
    return min(qualities, key=lambda q: _QUALITY_RANK[q])


@dataclass(frozen=True)
class TokenCount:
    value: int
    quality: TokenQuality


#: An exact tokenizer maps text to its true token count for a model.
Tokenizer = Callable[[str], int]


def get_exact_tokenizer() -> Tokenizer | None:
    """The best available exact tokenizer, or None.

    Uses tiktoken (cl100k_base) when installed; Rúnmál does not hard-depend
    on it, so absence simply means counts fall back to ESTIMATED.
    """
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None
    return lambda text: len(encoding.encode(text))


def count_tokens(text: str, tokenizer: Tokenizer | None = None) -> TokenCount:
    """Count ``text`` at the best available quality, honestly labeled."""
    counter = tokenizer or get_exact_tokenizer()
    if counter is not None:
        return TokenCount(counter(text), TokenQuality.EXACT)
    return TokenCount(estimate_tokens(text), TokenQuality.ESTIMATED)


def count_from_provider_usage(usage: dict | None) -> TokenCount | None:
    """Provider-reported prompt-token count, or None when not reported."""
    if not usage:
        return None
    for key in ("prompt_tokens", "input_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return TokenCount(value, TokenQuality.PROVIDER)
    return None


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: ``max(1, len(text) // 4)``."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return max(1, len(text) // 4)
