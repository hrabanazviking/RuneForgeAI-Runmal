"""S702 (roadmap): Aesir sampling/capability mapping.

Acceptance: canonical controls map to Aesir wire names through the one
mapping path the adapter itself uses; unsupported controls are declared,
named in warnings, and never sent or pretended honored (INV-005).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from runmal.backends.aesir import (
    SAMPLERS,
    UNSUPPORTED_SAMPLERS,
    WIRE_NAMES,
    AesirChatBackend,
    map_params,
)
from runmal.backends.messages import ChatMessage
from runmal.backends.models import Capabilities, ModelInfo
from runmal.backends.negotiation import (
    CANONICAL_CONTROLS,
    clamp_params,
    controls_dict,
    filter_for_model,
    negotiate_controls,
    profile_from_capabilities,
)
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenQuality

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]

FULL_PARAMS = SamplingParams(
    temperature=0.7,
    top_p=0.9,
    top_k=40,
    min_p=0.05,
    repetition_penalty=1.1,
    presence_penalty=0.3,
    frequency_penalty=0.2,
    max_output_tokens=128,
    stop=("END",),
    seed=42,
    context_length=4096,
)


def test_every_canonical_control_is_accounted_for():
    # No third category: every canonical control is either mapped or
    # explicitly declared unsupported.
    assert set(SAMPLERS) | set(UNSUPPORTED_SAMPLERS) == set(CANONICAL_CONTROLS)
    assert not (set(SAMPLERS) & set(UNSUPPORTED_SAMPLERS))
    assert set(WIRE_NAMES) == set(SAMPLERS)


def test_map_params_maps_supported_and_names_dropped():
    wire, warnings = map_params(FULL_PARAMS)
    assert wire == {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": 1.1,  # the one rename
        "max_tokens": 128,
        "stop": ["END"],
        "seed": 42,
    }
    assert sorted(warnings) == [
        "unsupported parameter dropped: context_length",
        "unsupported parameter dropped: frequency_penalty",
        "unsupported parameter dropped: presence_penalty",
    ]


def test_map_params_empty_params():
    wire, warnings = map_params(SamplingParams())
    assert wire == {} and warnings == []


async def test_chat_stream_wire_never_carries_unsupported():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, content=(FIX / "aesir_chat.sse").read_bytes())

    b = AesirChatBackend(model="llama-3.1-8b-instruct", transport=httpx.MockTransport(handler))
    _ = [e async for e in b.chat_stream(MSGS, FULL_PARAMS, asyncio.Event())]
    for forbidden in ("presence_penalty", "frequency_penalty", "context_length"):
        assert forbidden not in captured
    assert captured["repeat_penalty"] == 1.1
    assert "repetition_penalty" not in captured


def _listed_model() -> ModelInfo:
    return ModelInfo(
        model_id="llama-3.1-8b-instruct",
        display_name="Llama 3.1 8B Instruct (Aesir local)",
        backend_key="aesir",
        capabilities=Capabilities(
            chat=True,
            streaming=True,
            context_length=8192,
            max_output_tokens=2048,
            token_count_quality=TokenQuality.ESTIMATED,
            supported_samplers=SAMPLERS,
        ),
    )


def test_negotiation_consumes_aesir_declarations():
    model = _listed_model()
    controls = {c.name: c for c in negotiate_controls(model)}
    for name in SAMPLERS:
        assert controls[name].supported, name
    for name in ("presence_penalty", "frequency_penalty"):
        assert not controls[name].supported
        assert "does not declare" in controls[name].detail
    surface = controls_dict(model)
    assert surface["backend_key"] == "aesir"

    clamped, warnings = clamp_params(
        SamplingParams(presence_penalty=0.5, max_output_tokens=99999), model
    )
    assert clamped.presence_penalty is None
    assert clamped.max_output_tokens == 2048
    assert any("presence_penalty" in w for w in warnings)
    assert any("clamped" in w for w in warnings)


def test_s208_filter_built_from_aesir_mapping():
    model = _listed_model()
    profile = profile_from_capabilities(model, WIRE_NAMES)
    result = filter_for_model(
        {"temperature": 0.5, "repetition_penalty": 1.2, "presence_penalty": 0.1},
        model,
        WIRE_NAMES,
    )
    assert result.params == {"temperature": 0.5, "repeat_penalty": 1.2}
    assert [d.param for d in result.dropped] == ["presence_penalty"]
    assert any(m.dest == "repeat_penalty" for m in result.mapped)
    assert profile.name == "aesir:llama-3.1-8b-instruct"
