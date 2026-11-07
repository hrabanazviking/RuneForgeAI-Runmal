"""Entry states for lorebook entries (P-035).

Pure-domain module: no DB, no I/O, no network, no randomness, no
wall-clock. It owns the activation-kind vocabulary -- the three
kinds an entry can be in -- and the single derivation function the
activation pipeline consults. Entry states are the three activation
kinds, one engine.

Semantics (normative):
- Every entry has exactly ONE activation kind, derived from its
  flags (the kind itself is derived, never stored):
  - ``constant=True`` -> ``"constant"``: always fires.
  - else ``vectorised=True`` -> ``"vectorised"``: fires only on a
    vector/embedding hit supplied to the engine; the embedding
    matcher itself is P-041.
  - else -> ``"selective"``: fires on keyword scan hits, gated by
    selective logic.
- Precedence ``constant > vectorised > selective`` is Rúnmál's own:
  constant means always-inserted, so it dominates. A both-flags
  entry (the P-005 corpus Harbour Law entry carries ``constant=True``
  and ``vectorized=True``) behaves as constant, and its vectorised
  flag is still carried/stored/reported, never silently dropped.
"""
from __future__ import annotations

KIND_CONSTANT = "constant"
KIND_SELECTIVE = "selective"
KIND_VECTORISED = "vectorised"

ACTIVATION_KINDS = frozenset({KIND_CONSTANT, KIND_SELECTIVE, KIND_VECTORISED})

DEFAULT_ACTIVATION_KIND = KIND_SELECTIVE

__all__ = [
    "KIND_CONSTANT",
    "KIND_SELECTIVE",
    "KIND_VECTORISED",
    "ACTIVATION_KINDS",
    "DEFAULT_ACTIVATION_KIND",
    "check_activation_kind",
    "normalise_activation_kind",
    "activation_kind_for",
    "normalise_vectorised",
]


def check_activation_kind(value) -> str:
    """Strict validation: return ``value`` if it is a canonical kind.

    Raises ValueError for anything else (wrong case, separators,
    None, non-strings).
    """
    if isinstance(value, str) and value in ACTIVATION_KINDS:
        return value
    raise ValueError(
        f"invalid activation_kind: {value!r} (valid: {sorted(ACTIVATION_KINDS)})"
    )


def normalise_activation_kind(value) -> str:
    """Tolerant kind normaliser: canonical name -> itself, else default."""
    if isinstance(value, str) and value in ACTIVATION_KINDS:
        return value
    return DEFAULT_ACTIVATION_KIND


def normalise_vectorised(value) -> bool:
    """Tolerant vectorised-flag coercion: None -> False, else bool(value)."""
    if value is None:
        return False
    return bool(value)


def activation_kind_for(constant=False, vectorised=False) -> str:
    """Derive an entry's single activation kind from its flags.

    Precedence is constant > vectorised > selective (see the module
    docstring): a constant entry is always inserted, so it dominates
    even when the entry also carries the vectorised flag.
    """
    if bool(constant):
        return KIND_CONSTANT
    if normalise_vectorised(vectorised):
        return KIND_VECTORISED
    return KIND_SELECTIVE
