"""Message swipe decks: pure data contract (P-065, PROVISIONAL 0036).

A *swipe deck* is the ordered list of alternate contents for one
message. The deck contract:

- Alternates are ordered: index 0 is the original generation and
  each regeneration appends a new alternate at the end.
- INVARIANT: the message's ``content`` column always mirrors the
  active alternate -- ``content == swipes[swipe_id]``. Writers
  must uphold it; readers may rely on it (and :func:`deck_for`
  defends against rows that break it).
- Legacy rows carry ``swipes_json == '[]'`` (the migration
  default): that reads as the one-card deck ``[content]`` -- a
  message that was never swiped has exactly one alternate, its
  own content.
- Relative navigation (``next`` / ``prev`` / ``first`` / ``last``
  / ``goto``) CLAMPS into range, mirroring
  ``GenerationSession.swipe`` in ``runmal.generation.modes``:
  stepping past either end stays at that end, never wraps and
  never raises for being out of range.
- Explicit indexes NEVER clamp: :func:`select_index` is strict
  -- an out-of-range or negative index is a caller bug and raises
  ``ValueError`` instead of silently landing somewhere else.

This module is pure data only: no database imports, no I/O. The
one outside dependency is ``validate_params`` from
``runmal.presets.service`` (the canonical sampling-parameter
validator), lazy-imported inside the functions that need it so
this module stays importable without pulling the preset stack.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

__all__ = [
    "SwipeRegenSettings",
    "deck_for",
    "navigate",
    "resolve_params",
    "select_index",
    "settings_from_data",
    "settings_to_data",
    "stored_swipes",
    "swipes_from_session",
    "validate_new_alternate",
]


def _validate_params(params: dict) -> dict:
    """Lazy bridge to the canonical preset parameter validator."""
    from runmal.presets.service import validate_params

    return validate_params(params)


def stored_swipes(raw: str | None) -> list | None:
    """Decode the stored ``swipes_json`` column.

    Returns the validated stored list, or ``None`` when there is
    no usable deck stored: ``raw`` is ``None``, empty, the legacy
    ``'[]'`` default, corrupt JSON, not a list, an empty list, or
    a list containing non-string or empty entries. Never raises.
    """
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    for entry in parsed:
        if not isinstance(entry, str) or not entry:
            return None
    return list(parsed)


def deck_for(content: str, raw: str | None, swipe_id: int) -> tuple[list[str], int]:
    """Resolve a message row into its effective ``(deck, swipe_id)``.

    DEFENSIVE: any inconsistency -- missing/corrupt stored data,
    a non-integer or out-of-range ``swipe_id``, or a row breaking
    the invariant ``content == swipes[swipe_id]`` -- falls back to
    the legacy one-card deck ``([content], 0)``. A consistent row
    returns ``(list(swipes), swipe_id)`` (a copy). Never raises.
    """
    swipes = stored_swipes(raw)
    if swipes is None:
        return ([content], 0)
    if isinstance(swipe_id, bool) or not isinstance(swipe_id, int):
        return ([content], 0)
    if not 0 <= swipe_id < len(swipes):
        return ([content], 0)
    if swipes[swipe_id] != content:
        return ([content], 0)
    return (list(swipes), swipe_id)


def validate_new_alternate(content: object) -> str:
    """Validate a candidate alternate before it joins a deck.

    A new alternate must be a non-empty string; anything else is
    a ``ValueError``. Returns the content unchanged on success.
    """
    if not isinstance(content, str) or not content:
        raise ValueError("a swipe alternate must be a non-empty string")
    return content


def navigate(
    swipes: list[str],
    swipe_id: int,
    action: str,
    target: int | None = None,
) -> int:
    """Relative deck navigation; returns the new ``swipe_id``.

    ``next`` / ``prev`` move by one, CLAMPED to ``[0, len-1]``
    (like ``GenerationSession.swipe``); ``first`` goes to 0 and
    ``last`` to ``len - 1``; ``goto`` requires ``target``
    (``ValueError`` when ``None``) and clamps it into range.
    Unknown actions and empty decks raise ``ValueError``.
    """
    if not swipes:
        raise ValueError("cannot navigate an empty swipe deck")
    last = len(swipes) - 1
    if action == "next":
        return max(0, min(swipe_id + 1, last))
    if action == "prev":
        return max(0, min(swipe_id - 1, last))
    if action == "first":
        return 0
    if action == "last":
        return last
    if action == "goto":
        if target is None:
            raise ValueError("goto navigation requires a target index")
        return max(0, min(target, last))
    raise ValueError(f"unknown swipe navigation action: {action!r}")


def select_index(swipes: list[str], index: int) -> int:
    """Strict explicit index selection -- NO clamping, NO wrap.

    ``index`` must be a real ``int`` (bools rejected) with
    ``0 <= index < len(swipes)``; anything else raises
    ``ValueError``. Returns the index unchanged on success.
    """
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError("swipe index must be an int")
    if not 0 <= index < len(swipes):
        raise ValueError(f"swipe index out of range: {index}")
    return index


@dataclass(frozen=True)
class SwipeRegenSettings:
    """Per-chat swipe-regeneration settings (one JSON document).

    ``enabled``: whether swiping to a fresh alternate regenerates
    with parameter overrides. ``params``: a sampling-parameter
    bag, validated (and copied) by ``validate_params`` at
    construction -- canonical fields are type/range checked and
    unknown backend fields ride along JSON-safe.
    """

    enabled: bool = True
    params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("swipe regen 'enabled' must be a bool")
        object.__setattr__(self, "params", _validate_params(self.params))


_SETTINGS_KEYS = frozenset({"enabled", "params"})


def settings_from_data(data: object) -> SwipeRegenSettings:
    """Strict decode of a stored swipe-settings document.

    ``None`` yields the defaults. Anything that is not a dict,
    carries unknown keys, has a non-bool ``enabled``, or has a
    non-dict / invalid ``params`` bag raises ``ValueError``.
    """
    if data is None:
        return SwipeRegenSettings()
    if not isinstance(data, dict):
        raise ValueError("swipe settings must be an object")
    unknown = set(data) - _SETTINGS_KEYS
    if unknown:
        raise ValueError(f"unknown swipe settings keys: {sorted(unknown)}")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("swipe settings 'enabled' must be a bool")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("swipe settings 'params' must be an object")
    return SwipeRegenSettings(enabled=enabled, params=params)


def settings_to_data(settings: SwipeRegenSettings) -> dict:
    """Encode settings as a plain dict; BOTH keys always present."""
    return {"enabled": settings.enabled, "params": dict(settings.params)}


def resolve_params(base: dict | None, settings: SwipeRegenSettings) -> dict:
    """Merge swipe-regen overrides over a base parameter bag.

    Returns a NEW dict: a copy of ``base`` (or ``{}``), with
    ``settings.params`` overriding per-key (shallow) when the
    settings are enabled; a plain copy of ``base`` when disabled.
    Inputs are never mutated.
    """
    resolved = dict(base) if base is not None else {}
    if settings.enabled:
        resolved.update(settings.params)
    return resolved


def swipes_from_session(session: object) -> tuple[list[str], int]:
    """Adapt a ``GenerationSession``-like object into a deck.

    ``session`` is a ``runmal.generation.modes.GenerationSession``
    (or anything with ``.candidates`` -- each candidate carrying
    ``.content`` -- and ``.active_index``). Returns the candidate
    contents in order and the active index CLAMPED into range.
    An empty candidate list returns ``([], 0)``: there is no deck
    yet, and the caller decides what an empty deck means.
    """
    contents = [candidate.content for candidate in session.candidates]
    if not contents:
        return ([], 0)
    active = max(0, min(session.active_index, len(contents) - 1))
    return (contents, active)
