"""Logit bias & stop sequences as honest per-preset controls (P-060).

Roadmap line: *Logit bias & stop sequences: per-preset,
backend-honest.*

Until P-060 ``stop`` was a canonical sampler (P-052) but
``logit_bias`` had no canonical home at all: a preset could only
carry it as an opaque unknown key that every typed path
(``SamplingParams``, capability negotiation, the wire adapters)
silently dropped. P-060 gives both controls one honest home:

- ``logit_bias`` is the 29th canonical control (P-052 catalogue
  as data, kind ``bias_map``). The typed form is
  :class:`runmal.backends.params.SamplingParams`' tuple of
  (token_id, bias) pairs; the bag/preset form is a JSON object
  ``{decimal-token-id-string: bias}`` with bias in [-100, 100] —
  the range the public OpenAI-shaped wire defines.
- This module is the validated value object over that data
  (:class:`LogitBias`), the strict stop-sequence validator, and
  :func:`resolve_generation_controls`, the per-preset resolution
  path: sampler/preset stops merge with instruct-template stops
  under the P-050 F3 precedent, then the merged params degrade
  to a model's declared capabilities with structured warnings
  (INV-005) — an unsupported bias or stop is warned and cleared,
  never silently dropped and never pretended honoured.

Wire truth, proven from Runmal's own adapter code (not assumed):
the OpenAI-compatible adapter and the OpenRouter adapter forward
``logit_bias`` + ``stop`` on their OpenAI-shaped wires (P-060
adds the forwarding); Ollama's native options carry ``stop``
and publish no logit-bias option, so bias greys there; Aesir's
OpenAI chat route serves neither (both are named in its
``UNSUPPORTED_SAMPLERS``, P-009 D2) and its native-generate
ledger row does not claim logit_bias either — native service
is unverified in-tree, so the ledger says so (P-053 carve-out).

Token-id honesty: a bias entry names a TOKEN ID. No in-tree
tokenizer maps arbitrary preset text to token ids for these
backends, so text-keyed bias is never resolved by inventing
ids: :func:`plan_text_bias` resolves text entries ONLY through
a caller-supplied token map, and every entry it cannot resolve
stays in the plan as an unresolved record carrying the reason
``tokenizer_unavailable`` (or ``not_in_token_map``) as data.

Caps below (entry counts, stop count/length) are LOCAL sanity
limits of this layer, named as such — they are not claims about
any backend's limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.backends.models import ModelInfo
from runmal.backends.params import SamplingParams

#: Local sanity caps (this layer's limits, not backend claims).
MAX_BIAS_ENTRIES = 512
MAX_STOP_SEQUENCES = 64
MAX_STOP_LENGTH = 512

#: Bias range of the public OpenAI-shaped wire.
BIAS_MIN = -100.0
BIAS_MAX = 100.0

#: Reason codes for unresolved text-keyed bias entries.
REASON_TOKENIZER_UNAVAILABLE = "tokenizer_unavailable"
REASON_NOT_IN_TOKEN_MAP = "not_in_token_map"


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@dataclass(frozen=True)
class LogitBias:
    """Validated logit-bias entries, canonical (sorted by id)."""

    entries: tuple[tuple[int, float], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise ValueError("logit_bias entries must be a tuple of pairs")
        if len(self.entries) > MAX_BIAS_ENTRIES:
            raise ValueError(
                f"logit_bias carries at most {MAX_BIAS_ENTRIES} entries "
                "(local sanity cap)")
        seen: set[int] = set()
        for pair in self.entries:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("logit_bias entries must be (token_id, bias) pairs")
            token_id, bias = pair
            if not _is_int(token_id) or token_id < 0:
                raise ValueError("logit_bias token ids must be non-negative ints")
            if token_id in seen:
                raise ValueError(f"logit_bias duplicate token id: {token_id}")
            seen.add(token_id)
            if not _is_num(bias) or not BIAS_MIN <= bias <= BIAS_MAX:
                raise ValueError("logit_bias values must be numbers in [-100, 100]")
        object.__setattr__(self, "entries", tuple(sorted(self.entries)))

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def to_data(self) -> dict:
        """Bag/preset form: {decimal token-id string: bias}."""
        return {str(tid): bias for tid, bias in self.entries}

    @classmethod
    def from_data(cls, data: object) -> LogitBias:
        """Strict inverse of to_data; anything else raises ValueError."""
        if not isinstance(data, dict):
            raise ValueError("logit_bias data must be an object of token-id -> bias")
        pairs = []
        for raw_id, bias in data.items():
            if not isinstance(raw_id, str) or not raw_id.isdigit():
                raise ValueError(
                    f"logit_bias keys must be decimal token-id strings, got {raw_id!r}")
            pairs.append((int(raw_id), bias))
        return cls(tuple(pairs))

    def to_params(self) -> SamplingParams:
        return SamplingParams(logit_bias=self.entries or None)

    @classmethod
    def from_params(cls, params: SamplingParams) -> LogitBias:
        return cls(params.logit_bias or ())


@dataclass(frozen=True)
class UnresolvedTextBias:
    """One text-keyed bias entry that could not be honestly resolved."""

    text: str
    bias: float
    reason_code: str
    reason: str

    def to_dict(self) -> dict:
        return {"text": self.text, "bias": self.bias,
                "reason_code": self.reason_code, "reason": self.reason}


@dataclass(frozen=True)
class TextBiasPlan:
    """The honest outcome of planning text-keyed bias entries."""

    resolved: LogitBias
    unresolved: tuple[UnresolvedTextBias, ...] = ()

    def to_dict(self) -> dict:
        return {"resolved": self.resolved.to_data(),
                "unresolved": [u.to_dict() for u in self.unresolved]}


def plan_text_bias(entries, token_map=None) -> TextBiasPlan:
    """Plan text-keyed bias entries without ever inventing token ids.

    ``entries`` is a mapping of text -> bias (or an iterable of
    (text, bias) pairs). Resolution happens ONLY through the
    caller-supplied ``token_map`` (text -> token id): with no map,
    every entry is unresolved with ``tokenizer_unavailable`` —
    no in-tree tokenizer serves these backends, and this layer
    says so in data instead of guessing ids. With a map, entries
    whose text is absent stay unresolved (``not_in_token_map``).
    Bias values are validated exactly like token-id entries.
    """
    if hasattr(entries, "items"):
        pairs = list(entries.items())
    else:
        pairs = list(entries or ())
    resolved: list[tuple[int, float]] = []
    unresolved: list[UnresolvedTextBias] = []
    for text, bias in pairs:
        if not isinstance(text, str) or not text:
            raise ValueError("text bias entries need non-empty string keys")
        if not _is_num(bias) or not BIAS_MIN <= bias <= BIAS_MAX:
            raise ValueError("text bias values must be numbers in [-100, 100]")
        if token_map is None:
            unresolved.append(UnresolvedTextBias(
                text=text, bias=bias,
                reason_code=REASON_TOKENIZER_UNAVAILABLE,
                reason=("no tokenizer/token map is available in-tree for "
                        "this backend; token ids are not invented")))
        elif text not in token_map:
            unresolved.append(UnresolvedTextBias(
                text=text, bias=bias,
                reason_code=REASON_NOT_IN_TOKEN_MAP,
                reason="the supplied token map has no id for this text"))
        else:
            token_id = token_map[text]
            if not _is_int(token_id) or token_id < 0:
                raise ValueError("token map ids must be non-negative ints")
            resolved.append((token_id, bias))
    return TextBiasPlan(resolved=LogitBias(tuple(resolved)),
                        unresolved=tuple(unresolved))


def validate_stop_sequences(stops) -> tuple[str, ...]:
    """Strict P-060 stop validation; returns the stops as a tuple.

    Every entry must be a non-empty string (an empty stop would
    halt generation immediately and is never a real stop). Count
    and length caps are this layer's local sanity limits.
    """
    if isinstance(stops, str):
        stops = (stops,)
    out = tuple(stops or ())
    if len(out) > MAX_STOP_SEQUENCES:
        raise ValueError(
            f"stop sequences carry at most {MAX_STOP_SEQUENCES} entries "
            "(local sanity cap)")
    for value in out:
        if not isinstance(value, str) or not value:
            raise ValueError("stop sequences must be non-empty strings")
        if len(value) > MAX_STOP_LENGTH:
            raise ValueError(
                f"stop sequences carry at most {MAX_STOP_LENGTH} characters "
                "each (local sanity cap)")
    return out


def resolve_generation_controls(
    params: SamplingParams,
    model: ModelInfo | None = None,
    template_stops=(),
) -> tuple[SamplingParams, list[str]]:
    """The P-060 per-preset resolution for bias + stops.

    Stop sequences: the preset/sampler stops merge with the
    instruct template's stops under the P-050 F3 precedent
    (sampler stops first, template stops appended, duplicates
    removed, order preserved, empties dropped by the merge).
    Logit bias rides the same params untouched until degradation.

    Then, when a model is given, the merged params degrade to
    the model's declared capabilities via the S310 negotiation
    path: on a backend that does not declare ``logit_bias`` or
    ``stop``, those controls are cleared WITH structured
    warnings — never silently dropped, never faked (INV-005).
    With no model, support is undeclared and nothing is cleared.
    """
    from runmal.backends.samplers import resolve_sampler_params

    if params.stop is not None:
        validate_stop_sequences(params.stop)
    validate_stop_sequences(template_stops or ())
    return resolve_sampler_params(params, model, template_stops)
