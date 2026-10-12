"""Canonical sampling parameters (S301).

Ranges reuse the canonical validation of presets/service.py (S207), extended
with the remaining BACKEND_CONTRACT section 4 fields. None means unset.
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

    def to_bag(self) -> dict:
        """Canonical S207-style bag; skips unset fields."""
        out: dict = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            key = "max_tokens" if f.name == "max_output_tokens" else f.name
            out[key] = list(value) if f.name == "stop" else value
        return out

    @classmethod
    def from_bag(cls, bag: dict) -> SamplingParams:
        kwargs: dict = {}
        for key, value in (bag or {}).items():
            name = "max_output_tokens" if key == "max_tokens" else key
            if name == "stop" and isinstance(value, list):
                value = tuple(value)
            if name in {f.name for f in fields(cls)}:
                kwargs[name] = value
        return cls(**kwargs)
