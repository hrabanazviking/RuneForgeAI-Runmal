"""Capability negotiation (S310) — BACKEND_CONTRACT §5, INV-005.

Feature discovery (``Capabilities``/``ModelInfo``, S301/S305) consumed by
the prompt, sampler and UI layers. Every decision here is driven by the
model's DECLARED capabilities — never by provider-name conditionals: two
backends declaring identical capabilities negotiate identically, whatever
their keys are.

Consumption points:

- ``negotiate_controls`` / ``controls_dict`` — the UI renders controls
  from these descriptors: unsupported controls are disabled with a
  reason, not hidden by a provider ``if``.
- ``clamp_params`` — the sampler layer degrades a ``SamplingParams`` to
  what the model declares: unsupported fields cleared, numeric limits
  clamped, every change reported as a structured warning.
- ``profile_from_capabilities`` + ``filter_for_model`` — the S208
  compatibility filter, but with its static per-provider profile BUILT
  from declared capabilities (wire names are supplied by the adapter's
  own mapping, capability truth decides keep/drop).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from runmal.backends.models import ModelInfo
from runmal.backends.params import SamplingParams
from runmal.generation.compat import BackendProfile, CompatibilityResult, filter_params

# Canonical sampler/control names — the S207 bag vocabulary.
CANONICAL_CONTROLS: tuple[str, ...] = (
    "temperature", "top_p", "top_k", "min_p", "repetition_penalty",
    "presence_penalty", "frequency_penalty", "max_tokens", "stop",
    "seed", "context_length",
)
FEATURES: tuple[str, ...] = (
    "chat", "embeddings", "vision", "tools", "streaming", "structured_output",
)
_FIELD_FOR_KEY = {"max_tokens": "max_output_tokens"}


@dataclass(frozen=True)
class ControlDescriptor:
    """One negotiable control, as the UI/sampler layers consume it."""

    name: str
    kind: str  # "sampler" | "feature" | "limit"
    supported: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind,
                "supported": self.supported, "detail": self.detail}


def negotiate_controls(model: ModelInfo) -> list[ControlDescriptor]:
    """Describe every control from the model's declared capabilities."""
    caps = model.capabilities
    out: list[ControlDescriptor] = []
    for name in CANONICAL_CONTROLS:
        supported = name in caps.supported_samplers
        out.append(ControlDescriptor(
            name, "sampler", supported,
            "" if supported else f"{model.model_id} does not declare {name}"))
    for name in FEATURES:
        out.append(ControlDescriptor(name, "feature", bool(getattr(caps, name))))
    for name, value in (("context_length", caps.context_length),
                        ("max_output_tokens", caps.max_output_tokens)):
        out.append(ControlDescriptor(
            name, "limit", value is not None,
            "" if value is None else str(value)))
    return out


def controls_dict(model: ModelInfo) -> dict:
    """JSON-ready control surface for one model (UI consumption)."""
    return {
        "backend_key": model.backend_key,
        "model_id": model.model_id,
        "controls": [c.to_dict() for c in negotiate_controls(model)],
    }


def clamp_params(
    params: SamplingParams, model: ModelInfo
) -> tuple[SamplingParams, list[str]]:
    """Degrade `params` to the model's declared capabilities (INV-005).

    Unsupported sampler fields are cleared; declared numeric limits
    clamp. Every change is returned as a structured warning — nothing is
    silently dropped or silently honored.
    """
    caps = model.capabilities
    warnings: list[str] = []
    clears: dict = {}
    for key in sorted(params.to_bag()):
        if key == "context_length":
            continue  # a limit, not a sampler: handled by the clamp below
        if key not in caps.supported_samplers:
            clears[_FIELD_FOR_KEY.get(key, key)] = None
            warnings.append(f"unsupported parameter dropped: {key}")
    params = replace(params, **clears) if clears else params
    if (params.max_output_tokens is not None
            and caps.max_output_tokens is not None
            and params.max_output_tokens > caps.max_output_tokens):
        warnings.append(
            f"max_tokens clamped: {params.max_output_tokens} -> {caps.max_output_tokens}")
        params = replace(params, max_output_tokens=caps.max_output_tokens)
    if (params.context_length is not None
            and caps.context_length is not None
            and params.context_length > caps.context_length):
        warnings.append(
            f"context_length clamped: {params.context_length} -> {caps.context_length}")
        params = replace(params, context_length=caps.context_length)
    return params, warnings


def profile_from_capabilities(
    model: ModelInfo, wire_names: dict[str, str] | None = None
) -> BackendProfile:
    """Build an S208 compat profile from declared capabilities.

    ``wire_names`` (canonical -> provider wire name) comes from the
    adapter's own mapping; capability truth alone decides keep vs drop.
    """
    wire_names = wire_names or {}
    supported = model.capabilities.supported_samplers
    wire = {key: wire_names.get(key, key)
            for key in CANONICAL_CONTROLS if key in supported}
    unsupported = {
        key: f"model {model.model_id} does not declare '{key}' "
             f"(capability negotiation, S310)"
        for key in CANONICAL_CONTROLS if key not in supported
    }
    return BackendProfile(
        name=f"{model.backend_key}:{model.model_id}",
        wire_names=wire, unsupported=unsupported)


def filter_for_model(
    params_bag: dict, model: ModelInfo,
    wire_names: dict[str, str] | None = None,
) -> CompatibilityResult:
    """S208 filtering driven by the model's declared capabilities."""
    return filter_params(params_bag, profile_from_capabilities(model, wire_names))
