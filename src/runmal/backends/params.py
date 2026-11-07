"""Canonical sampling parameters (S301, completed P-052).

Ranges reuse the canonical validation of presets/service.py (S207), extended
with the remaining BACKEND_CONTRACT section 4 fields and, since P-052, the
complete common sampler set (DRY, XTC, typical/top-a/tail-free, epsilon/eta,
Mirostat, dynamic temperature -- the catalogue is data in
:mod:`runmal.backends.samplers`). None means unset.
``to_bag()`` emits S207 bag key names (``max_tokens`` for max_output_tokens).
"""

from __future__ import annotations

from dataclasses import dataclass, fields


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@dataclass(frozen=True)
class SamplingParams:
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    repetition_penalty: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    typical_p: float | None = None
    top_a: float | None = None
    tfs_z: float | None = None
    epsilon_cutoff: float | None = None
    eta_cutoff: float | None = None
    dry_multiplier: float | None = None
    dry_base: float | None = None
    dry_allowed_length: int | None = None
    dry_penalty_last_n: int | None = None
    dry_sequence_breakers: tuple[str, ...] | None = None
    xtc_probability: float | None = None
    xtc_threshold: float | None = None
    mirostat_mode: int | None = None
    mirostat_tau: float | None = None
    mirostat_eta: float | None = None
    dynamic_temperature_range: float | None = None
    dynamic_temperature_exponent: float | None = None
    max_output_tokens: int | None = None
    stop: tuple[str, ...] | None = None
    seed: int | None = None
    context_length: int | None = None

    def __post_init__(self) -> None:
        checks = [
            ("temperature", self.temperature, _is_num, lambda v: v >= 0),
            ("top_p", self.top_p, _is_num, lambda v: 0 < v <= 1),
            ("top_k", self.top_k, _is_int, lambda v: v >= 0),
            ("min_p", self.min_p, _is_num, lambda v: 0 <= v <= 1),
            ("repetition_penalty", self.repetition_penalty, _is_num, lambda v: v >= 0),
            ("presence_penalty", self.presence_penalty, _is_num, lambda v: -2 <= v <= 2),
            ("frequency_penalty", self.frequency_penalty, _is_num, lambda v: -2 <= v <= 2),
            ("max_output_tokens", self.max_output_tokens, _is_int, lambda v: v >= 1),
            ("typical_p", self.typical_p, _is_num, lambda v: 0 < v <= 1),
            ("top_a", self.top_a, _is_num, lambda v: 0 <= v <= 1),
            ("tfs_z", self.tfs_z, _is_num, lambda v: 0 <= v <= 1),
            ("epsilon_cutoff", self.epsilon_cutoff, _is_num, lambda v: 0 <= v <= 1),
            ("eta_cutoff", self.eta_cutoff, _is_num, lambda v: 0 <= v <= 1),
            ("dry_multiplier", self.dry_multiplier, _is_num, lambda v: v >= 0),
            ("dry_base", self.dry_base, _is_num, lambda v: v >= 1),
            ("dry_allowed_length", self.dry_allowed_length, _is_int, lambda v: v >= 0),
            ("dry_penalty_last_n", self.dry_penalty_last_n, _is_int, lambda v: v >= 0),
            ("xtc_probability", self.xtc_probability, _is_num, lambda v: 0 <= v <= 1),
            ("xtc_threshold", self.xtc_threshold, _is_num, lambda v: 0 <= v <= 1),
            ("mirostat_mode", self.mirostat_mode, _is_int, lambda v: 0 <= v <= 2),
            ("mirostat_tau", self.mirostat_tau, _is_num, lambda v: v > 0),
            ("mirostat_eta", self.mirostat_eta, _is_num, lambda v: v > 0),
            ("dynamic_temperature_range", self.dynamic_temperature_range, _is_num, lambda v: v >= 0),
            ("dynamic_temperature_exponent", self.dynamic_temperature_exponent, _is_num, lambda v: v > 0),
            ("seed", self.seed, _is_int, lambda v: v >= 0),
            ("context_length", self.context_length, _is_int, lambda v: v >= 1),
        ]
        for name, value, type_ok, range_ok in checks:
            if value is None:
                continue
            if not type_ok(value):
                raise ValueError(f"param {name!r} has wrong type")
            if not range_ok(value):
                raise ValueError(f"param {name!r} out of range")
        if self.stop is not None:
            if not isinstance(self.stop, tuple) or not all(
                isinstance(s, str) for s in self.stop
            ):
                raise ValueError("param 'stop' must be a tuple of strings")
        if self.dry_sequence_breakers is not None:
            if not isinstance(self.dry_sequence_breakers, tuple) or not all(
                isinstance(s, str) and s for s in self.dry_sequence_breakers
            ):
                raise ValueError(
                    "param 'dry_sequence_breakers' must be a tuple of "
                    "non-empty strings")

    def with_merged_stops(self, extra) -> SamplingParams:
        """Return a copy with ``extra`` stop strings merged in (P-052).

        The P-050 F3 merge: this params' own stops keep their
        position, template stops append, duplicates are removed
        (see :func:`runmal.backends.samplers.merge_stop_strings`).
        """
        from dataclasses import replace as _replace

        from runmal.backends.samplers import merge_stop_strings

        merged = merge_stop_strings(self.stop or (), extra or ())
        return _replace(self, stop=merged or None)

    def to_bag(self) -> dict:
        """Canonical S207-style bag; skips unset fields."""
        out: dict = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            key = "max_tokens" if f.name == "max_output_tokens" else f.name
            out[key] = list(value) if f.name in ("stop", "dry_sequence_breakers") else value
        return out

    @classmethod
    def from_bag(cls, bag: dict) -> SamplingParams:
        kwargs: dict = {}
        for key, value in (bag or {}).items():
            name = "max_output_tokens" if key == "max_tokens" else key
            if name in ("stop", "dry_sequence_breakers") and isinstance(value, list):
                value = tuple(value)
            if name in {f.name for f in fields(cls)}:
                kwargs[name] = value
        return cls(**kwargs)
