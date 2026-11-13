"""Voice affects as carried data (P-109, Part VII - DERIVED scope).

VX-12 (Voxta census): voices carry emotion - anger, whispering,
laughing - with proper prosody and affects. The engine half of
that row needs a TTS seam that accepts an affect; verified at
dfdd07c, no such seam exists: ``VoiceInfo`` carries no affect
field and no backend consumes one (P-105's scout recorded the
same). This module builds the DATA half, honestly labelled:

- a CLOSED vocabulary: ``neutral`` (the baseline - no affect
  intended) plus exactly the three affects the census row names;
- strict validation at write doors, tolerant reads with the
  fallback NAMED (S512 law: never an error on read, never a
  silently honoured unknown value);
- the consumption truth as data: every view this module builds
  states ``consumed: False`` - a carried affect changes no
  synthesis byte until a backend seam exists (a later slice).

Storage is the existing free surfaces only: the character voice
profile's ``params`` dict (key ``affect``; absence IS neutral -
one representation) and the P-101 session settings snapshot.
No migration, no new store.
"""

from __future__ import annotations

#: The closed affect vocabulary (VX-12): the baseline plus the
#: three affects the census row names. Additions are a design
#: act, not data entry - this tuple is the only list.
AFFECTS: tuple[str, ...] = ("neutral", "anger", "whispering", "laughing")

#: The baseline affect: no affect intended.
DEFAULT_AFFECT = "neutral"

#: The character voice profile params key carrying the affect.
PARAM_KEY = "affect"

#: Source labels for a resolved affect (where the value came from).
SOURCE_PROFILE = "profile"
SOURCE_DEFAULT = "default"
SOURCE_FALLBACK = "fallback"

_CONSUMPTION_NOTE = (
    "no TTS backend accepts or renders an affect yet: VoiceInfo "
    "carries no affect field, so a carried affect is data only "
    "and synthesis is unchanged by it"
)


def consumption_view() -> dict:
    """The consumption truth, as data (never prose-only)."""
    return {
        "consumed_by_backends": False,
        "voice_info_field": False,
        "note": _CONSUMPTION_NOTE,
    }


def normalize_affect(value: object) -> str:
    """Strict write-door validation: the canonical member of
    the vocabulary, or ValueError. Case/whitespace tolerant in
    form, closed in membership."""
    text = str(value or "").strip().lower()
    if text not in AFFECTS:
        raise ValueError(
            f"unknown voice affect: {value!r} "
            f"(vocabulary: {', '.join(AFFECTS)})"
        )
    return text


def affect_from_params(params: dict | None) -> tuple[str, str]:
    """Tolerant read: ``(affect, source)`` from a profile params
    dict. Missing/empty = neutral via default; a stored value
    outside the vocabulary = neutral via fallback, NAMED as
    such. Never raises (S512 read law)."""
    if not isinstance(params, dict):
        return DEFAULT_AFFECT, SOURCE_DEFAULT
    raw = params.get(PARAM_KEY, "")
    text = str(raw or "").strip().lower()
    if not text:
        return DEFAULT_AFFECT, SOURCE_DEFAULT
    if text in AFFECTS:
        return text, SOURCE_PROFILE
    return DEFAULT_AFFECT, SOURCE_FALLBACK


def with_affect(params: dict | None, affect: object) -> dict:
    """Strict write helper: a NEW params dict carrying the
    affect. Neutral removes the key - absence is neutral's one
    representation. Unknown affects raise (normalize_affect)."""
    canonical = normalize_affect(affect)
    out = dict(params) if isinstance(params, dict) else {}
    if canonical == DEFAULT_AFFECT:
        out.pop(PARAM_KEY, None)
    else:
        out[PARAM_KEY] = canonical
    return out


def affect_view(affect: str, source: str) -> dict:
    """One resolved affect as surface data, honestly labelled."""
    return {
        "affect": affect,
        "source": source,
        "consumed": False,
        "consumption": consumption_view(),
    }


def vocabulary_view() -> dict:
    """The whole vocabulary + truth, for the founding road."""
    return {
        "affects": list(AFFECTS),
        "default": DEFAULT_AFFECT,
        "consumed": False,
        "consumption": consumption_view(),
    }
