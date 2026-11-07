"""Complete sampler surface (P-052).

Until P-052 the canonical sampler vocabulary stopped at the S301
set (temperature, top-p/k, min-p, the three penalties, limits,
stop, seed). The newer common samplers -- the DRY repetition
family, the XTC family, typical-p, top-a, tail-free sampling,
epsilon/eta cutoffs, Mirostat and dynamic temperature -- had no
canonical home at all: a preset could only carry them as opaque
unknown keys that every typed path (``SamplingParams``, capability
negotiation, the compatibility profiles) silently dropped.

This module makes the complete set DATA:

- :data:`SAMPLER_SPECS` -- every canonical sampler as a
  :class:`SamplerSpec` (bag name, group, value kind, range,
  one-line public description), in presentation order. The
  vocabulary is exactly the field set of
  :class:`runmal.backends.params.SamplingParams` plus the two
  bag-only limit keys (``max_tokens``, ``context_length``).
- :func:`sampler_surface` -- the surface for one model (or no
  model): each sampler with its spec and its honest applicability.
  With a model, ``supported`` is the model's DECLARED capability
  truth (the same ``supported_samplers`` the negotiation layer
  consumes; the measured truth table is P-053 and is not built
  here). Without a model, ``supported`` is ``None`` -- undeclared,
  never guessed.
- :func:`merge_stop_strings` + :func:`resolve_sampler_params` --
  the P-050 F3 merge: an instruct template's stop strings merge
  with the sampler's own stops (sampler stops first, template
  stops appended, duplicates removed, order preserved), then the
  merged params degrade honestly to a model's declared
  capabilities when a model is given.

P-060 adds ``logit_bias`` to the catalogue: a per-token bias map
(token id -> bias in [-100, 100], the public OpenAI-shaped wire
range), carried as data like every other control and degraded by
the same honest negotiation path. Its spec kind is ``bias_map``.

Sampler semantics are the PUBLIC ones, from the public sampler
literature and public backend documentation (DRY: the public
DRY-sampling description; XTC: the public XTC-sampling
description; Mirostat / typical / tail-free / epsilon / eta /
dynamic temperature: the public llama.cpp and sampler-research
descriptions). No mirror source was read (clean-room log, P-052).
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.backends.models import ModelInfo
from runmal.backends.params import SamplingParams


@dataclass(frozen=True)
class SamplerSpec:
    name: str  # canonical bag key
    group: str  # core | penalty | dry | xtc | cutoff | mirostat | dynamic | limit | control
    kind: str  # float | int | strings | bias_map
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "group": self.group, "kind": self.kind,
            "minimum": self.minimum, "maximum": self.maximum,
            "description": self.description,
        }


def _spec(name, group, kind, lo, hi, desc):
    return SamplerSpec(name, group, kind, lo, hi, desc)


#: The complete canonical sampler vocabulary, presentation order.
SAMPLER_SPECS: tuple[SamplerSpec, ...] = (
    _spec("temperature", "core", "float", 0.0, None,
          "Sampling temperature; higher is more random."),
    _spec("top_p", "core", "float", 0.0, 1.0,
          "Nucleus sampling: keep the smallest set of tokens whose "
          "cumulative probability reaches top_p."),
    _spec("top_k", "core", "int", 0, None,
          "Keep only the top_k most likely tokens (0 disables)."),
    _spec("min_p", "core", "float", 0.0, 1.0,
          "Drop tokens below min_p times the top token probability."),
    _spec("typical_p", "cutoff", "float", 0.0, 1.0,
          "Typical sampling: keep tokens near the expected "
          "information content."),
    _spec("top_a", "cutoff", "float", 0.0, 1.0,
          "Top-a sampling: drop tokens below a * (top probability)^2."),
    _spec("tfs_z", "cutoff", "float", 0.0, 1.0,
          "Tail-free sampling strength (1.0 disables)."),
    _spec("epsilon_cutoff", "cutoff", "float", 0.0, 1.0,
          "Epsilon sampling: drop tokens below this probability."),
    _spec("eta_cutoff", "cutoff", "float", 0.0, 1.0,
          "Eta sampling cutoff, relative to the distribution entropy."),
    _spec("repetition_penalty", "penalty", "float", 0.0, None,
          "Penalty applied to tokens already present in the context."),
    _spec("presence_penalty", "penalty", "float", -2.0, 2.0,
          "Penalty for tokens present at all in the context so far."),
    _spec("frequency_penalty", "penalty", "float", -2.0, 2.0,
          "Penalty scaled by how often a token already appeared."),
    _spec("dry_multiplier", "dry", "float", 0.0, None,
          "DRY repetition penalty strength (0 disables DRY)."),
    _spec("dry_base", "dry", "float", 1.0, None,
          "DRY penalty growth base for longer repeated sequences."),
    _spec("dry_allowed_length", "dry", "int", 0, None,
          "DRY: repetitions up to this length are not penalised."),
    _spec("dry_penalty_last_n", "dry", "int", 0, None,
          "DRY: only the last N tokens are scanned (0 = whole context)."),
    _spec("dry_sequence_breakers", "dry", "strings", None, None,
          "DRY: strings that break a repetition sequence."),
    _spec("xtc_probability", "xtc", "float", 0.0, 1.0,
          "XTC: probability that the XTC removal step applies."),
    _spec("xtc_threshold", "xtc", "float", 0.0, 1.0,
          "XTC: probability threshold for removing near-top tokens."),
    _spec("mirostat_mode", "mirostat", "int", 0, 2,
          "Mirostat mode: 0 off, 1 Mirostat, 2 Mirostat 2.0."),
    _spec("mirostat_tau", "mirostat", "float", 0.0, None,
          "Mirostat target entropy (surprisal)."),
    _spec("mirostat_eta", "mirostat", "float", 0.0, None,
          "Mirostat learning rate."),
    _spec("dynamic_temperature_range", "dynamic", "float", 0.0, None,
          "Dynamic temperature: entropy-scaled range around the "
          "base temperature (0 disables)."),
    _spec("dynamic_temperature_exponent", "dynamic", "float", 0.0, None,
          "Dynamic temperature: exponent of the entropy mapping."),
    _spec("max_tokens", "limit", "int", 1, None,
          "Maximum tokens to generate."),
    _spec("stop", "control", "strings", None, None,
          "Stop sequences: generation halts when one is produced."),
    _spec("logit_bias", "control", "bias_map", -100.0, 100.0,
          "Logit bias: per-token bias by token id, added to the "
          "token's logit before sampling (-100..100)."),
    _spec("seed", "control", "int", 0, None,
          "Random seed for reproducible sampling."),
    _spec("context_length", "limit", "int", 1, None,
          "Requested context length."),
)

SAMPLER_NAMES: tuple[str, ...] = tuple(s.name for s in SAMPLER_SPECS)
_SPECS_BY_NAME: dict[str, SamplerSpec] = {s.name: s for s in SAMPLER_SPECS}


def spec_for(name: str) -> SamplerSpec:
    try:
        return _SPECS_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown sampler: {name!r}") from exc


def sampler_surface(model: ModelInfo | None = None) -> list[dict]:
    """The complete surface, with honest per-model applicability.

    ``supported`` is True/False from the model's declared
    capabilities, or None when no model is given (undeclared --
    the surface never guesses a backend's truth; P-053 owns the
    measured table).
    """
    supported = None if model is None else model.capabilities.supported_samplers
    out: list[dict] = []
    for spec in SAMPLER_SPECS:
        row = spec.to_dict()
        if supported is None:
            row["supported"] = None
            row["detail"] = "no model selected; support is per-backend"
        else:
            row["supported"] = spec.name in supported
            row["detail"] = (
                "" if row["supported"]
                else f"{model.model_id} does not declare {spec.name}")
        out.append(row)
    return out


def merge_stop_strings(*sources) -> tuple[str, ...]:
    """Merge stop-string sources (P-050 F3).

    Earlier sources win position; duplicates are removed; empty
    strings are dropped (an empty stop would halt generation
    immediately and is never a real stop). Order is preserved so
    the merge is deterministic and diff-able.
    """
    seen: set[str] = set()
    out: list[str] = []
    for source in sources:
        if isinstance(source, str):
            source = (source,)  # a bare string is ONE stop, never chars
        for value in source or ():
            if not isinstance(value, str):
                raise ValueError("stop strings must be strings")
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
    return tuple(out)


def resolve_sampler_params(
    params: SamplingParams,
    model: ModelInfo | None = None,
    template_stops=(),
) -> tuple[SamplingParams, list[str]]:
    """The P-052 resolution path: merge stops, then degrade honestly.

    The instruct template's stop strings (P-050) merge into the
    sampler's own stops FIRST; then, when a model is given, the
    merged params are clamped to the model's declared
    capabilities via the S310 negotiation path -- unsupported
    samplers are cleared with structured warnings, never silently
    dropped and never pretended honoured (INV-005).
    """
    from dataclasses import replace

    from runmal.backends.negotiation import clamp_params

    merged = merge_stop_strings(params.stop or (), template_stops or ())
    if merged != (params.stop or ()):
        params = replace(params, stop=merged or None)
    if model is None:
        return params, []
    return clamp_params(params, model)
