"""S310 (roadmap): capability negotiation.

Controls are enabled/disabled/degraded from the model's DECLARED
Capabilities (S301/S305) — never from provider-name conditionals. Proof:
two backends with different keys but identical capabilities negotiate
identically.
"""

from __future__ import annotations

import json

import httpx

from runmal.backends.models import Capabilities, ModelInfo
from runmal.backends.negotiation import (
    clamp_params,
    controls_dict,
    filter_for_model,
    negotiate_controls,
    profile_from_capabilities,
)
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenQuality

CAPS = Capabilities(
    chat=True, streaming=True, vision=False, tools=False,
    context_length=8192, max_output_tokens=1024,
    token_count_quality=TokenQuality.ESTIMATED,
    supported_samplers=frozenset({"temperature", "top_p", "max_tokens", "stop"}),
)


def model(backend_key: str) -> ModelInfo:
    return ModelInfo(model_id="m-1", display_name="M", backend_key=backend_key,
                     capabilities=CAPS)


def test_controls_come_from_declared_capabilities():
    controls = {c.name: c for c in negotiate_controls(model("anything"))}
    assert controls["temperature"].supported is True
    assert controls["top_k"].supported is False
    assert "does not declare" in controls["top_k"].detail
    assert controls["vision"].supported is False
    assert controls["chat"].supported is True
    assert controls["context_length"].detail == "8192"
    assert controls["max_output_tokens"].supported is True
    payload = controls_dict(model("anything"))
    json.dumps(payload)  # UI-consumable: must serialize as-is
    assert payload["backend_key"] == "anything"


def test_identical_capabilities_negotiate_identically_across_providers():
    bag = {"temperature": 0.7, "top_k": 40, "max_tokens": 128, "min_p": 0.1}
    results = {}
    for key in ("ollama", "openrouter", "aesir", "fake"):
        result = filter_for_model(bag, model(key))
        results[key] = (
            tuple(sorted(result.params)),
            tuple(sorted(d.param for d in result.dropped)),
        )
    # No provider-name conditionals: the outcome depends on capabilities only.
    assert len(set(results.values())) == 1
    kept, dropped = results["ollama"]
    assert kept == ("max_tokens", "temperature")
    assert dropped == ("min_p", "top_k")


def test_clamp_params_degrades_with_warnings():
    params = SamplingParams(temperature=0.5, top_k=40,
                            max_output_tokens=99999, context_length=10 ** 9)
    clamped, warnings = clamp_params(params, model("x"))
    assert clamped.temperature == 0.5
    assert clamped.top_k is None
    assert clamped.max_output_tokens == 1024
    assert clamped.context_length == 8192
    assert any("top_k" in w for w in warnings)
    assert any("clamped" in w and "max_tokens" in w for w in warnings)
    assert any("context_length clamped" in w for w in warnings)


def test_profile_from_capabilities_uses_adapter_wire_names():
    profile = profile_from_capabilities(
        model("ollama"), wire_names={"max_tokens": "num_predict"})
    assert profile.name == "ollama:m-1"
    assert profile.wire_names["max_tokens"] == "num_predict"
    assert "top_k" in profile.unsupported
    result = filter_for_model({"temperature": 1.0, "max_tokens": 5}, model("ollama"),
                              wire_names={"max_tokens": "num_predict"})
    assert result.params == {"temperature": 1.0, "num_predict": 5}
    assert result.mapped[0].dest == "num_predict"


async def test_negotiation_on_real_adapter_model_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"models": []}')

    backend = OllamaChatBackend(transport=httpx.MockTransport(handler))
    info = backend.default_model
    controls = {c.name: c for c in negotiate_controls(info)}
    # The Ollama adapter declares its sampler set; negotiation follows it.
    assert controls["temperature"].supported is True
    assert controls["repetition_penalty"].supported is True
    assert controls["frequency_penalty"].supported is False
    clamped, warnings = clamp_params(
        SamplingParams(frequency_penalty=0.5, temperature=0.2), info)
    assert clamped.frequency_penalty is None
    assert clamped.temperature == 0.2
    assert any("frequency_penalty" in w for w in warnings)
