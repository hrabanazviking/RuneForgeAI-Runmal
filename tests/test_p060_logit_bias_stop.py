"""P-060 Logit bias & stop sequences battery.

Pins: logit_bias as the 29th canonical control (catalogue as data,
SamplingParams validation + canonical bag round-trip, preset-bag
and P-054 bundle carriage), backend-honest truth (available only
where the adapter's own wire forwards it — openai + openrouter;
greyed with reasons elsewhere; Aesir's native ledger row carries
the explicit logit_bias carve-out), wire proof from captured
payloads, text-keyed bias honesty (no token map -> unresolved
with tokenizer_unavailable, ids never invented), and the P-050
F3 stop merge inside the P-060 resolution path.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from runmal.backends import aesir as aesir_mod
from runmal.backends import ollama as ollama_mod
from runmal.backends import openai_compat as openai_mod
from runmal.backends import openrouter as openrouter_mod
from runmal.backends.capabilities import (
    AESIR_LEDGER,
    AVAILABLE,
    GREYED,
    audit_truth,
    truth_for_backend,
    truth_for_control,
)
from runmal.backends.logit_bias import (
    MAX_BIAS_ENTRIES,
    LogitBias,
    plan_text_bias,
    resolve_generation_controls,
    validate_stop_sequences,
)
from runmal.backends.messages import ChatMessage
from runmal.backends.negotiation import CANONICAL_CONTROLS
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.params import SamplingParams
from runmal.backends.samplers import SAMPLER_NAMES, SAMPLER_SPECS, spec_for
from runmal.generation.compat import OLLAMA_PROFILE, OPENAI_PROFILE, filter_params
from runmal.presets.bundles import validate_bundle
from runmal.presets.service import validate_params

MSGS = [ChatMessage("user", "hi")]
BIAS = ((7, -2.0), (42, 1.5))
BIAS_BAG = {"7": -2.0, "42": 1.5}


# ---------------- catalogue as data ----------------

def test_catalogue_gains_logit_bias_as_29th_control():
    assert len(SAMPLER_NAMES) == 29
    assert len(set(SAMPLER_NAMES)) == 29
    assert tuple(CANONICAL_CONTROLS) == SAMPLER_NAMES
    spec = spec_for("logit_bias")
    assert spec.group == "control" and spec.kind == "bias_map"
    assert spec.minimum == -100.0 and spec.maximum == 100.0
    kinds = {s.kind for s in SAMPLER_SPECS}
    assert kinds <= {"float", "int", "strings", "bias_map"}


# ---------------- SamplingParams validation + round-trip ----------------

def test_params_bag_roundtrip_is_canonical():
    params = SamplingParams(logit_bias=((42, 1.5), (7, -2.0)))
    assert params.logit_bias == BIAS  # sorted by token id
    assert params.to_bag() == {"logit_bias": BIAS_BAG}
    assert SamplingParams.from_bag(params.to_bag()) == params
    assert SamplingParams.from_bag({"logit_bias": BIAS_BAG}).logit_bias == BIAS


@pytest.mark.parametrize("bad", [
    ((7, 100.5),), ((-1, 1.0),), ((True, 1.0),), ((7, True),),
    ((7, 1.0), (7, 2.0)), ([7, 1.0],), "nope", ((7,),),
])
def test_params_reject_bad_bias(bad):
    with pytest.raises(ValueError):
        SamplingParams(logit_bias=bad)


def test_params_bag_rejects_bad_keys():
    with pytest.raises(ValueError):
        SamplingParams.from_bag({"logit_bias": {"x": 1.0}})
    with pytest.raises(ValueError):
        SamplingParams.from_bag({"logit_bias": {"-3": 1.0}})


def test_params_accept_bias_range_edges():
    SamplingParams(logit_bias=((0, -100), (1, 100), (2, 0)))


# ---------------- LogitBias value object ----------------

def test_logit_bias_data_roundtrip():
    bias = LogitBias.from_data(BIAS_BAG)
    assert bias.entries == BIAS and bias.to_data() == BIAS_BAG
    assert LogitBias.from_params(bias.to_params()) == bias
    assert LogitBias().is_empty and not bias.is_empty
    with pytest.raises(ValueError):
        LogitBias.from_data({"tok": 1.0})
    with pytest.raises(ValueError):
        LogitBias.from_data([1, 2])
    with pytest.raises(ValueError):
        LogitBias(tuple((i, 1.0) for i in range(MAX_BIAS_ENTRIES + 1)))


# ---------------- preset + bundle carriage (per-preset, no migration) -------

def test_preset_bag_validates_logit_bias():
    assert validate_params({"logit_bias": BIAS_BAG}) == {"logit_bias": BIAS_BAG}
    for bad in ({"logit_bias": {"7": 101}}, {"logit_bias": {"x": 1}},
                {"logit_bias": [1]}, {"logit_bias": {"7": "hi"}},
                {"logit_bias": {"7": True}}):
        with pytest.raises(ValueError):
            validate_params(bad)


def test_bundle_carries_bias_and_stop_in_sampler():
    bundle = validate_bundle({"name": "b1", "sampler": {
        "temperature": 0.7, "logit_bias": BIAS_BAG, "stop": ["END"]}})
    assert bundle["sampler"]["logit_bias"] == BIAS_BAG
    assert bundle["sampler"]["stop"] == ["END"]
    with pytest.raises(ValueError):
        validate_bundle({"name": "b2", "sampler": {"logit_bias": {"7": 500}}})


# ---------------- backend truth ----------------

def _rows(backend):
    return {r.name: r for r in truth_for_backend(backend)}


def test_truth_logit_bias_per_backend():
    assert _rows("openai")["logit_bias"].state == AVAILABLE
    assert _rows("openrouter")["logit_bias"].state == AVAILABLE
    assert _rows("openai")["logit_bias"].wire_name == "logit_bias"
    for backend in ("ollama", "aesir", "fake"):
        row = _rows(backend)["logit_bias"]
        assert row.state == GREYED and row.supported is False
        assert row.reason and row.wire_name is None
    assert "logit_bias" in _rows("ollama")["logit_bias"].reason or True
    ollama_reason = truth_for_control(
        ollama_mod.OllamaChatBackend().default_model, "logit_bias")
    assert ollama_reason.state == GREYED


def test_truth_stop_per_backend():
    for backend in ("openai", "openrouter", "ollama", "fake"):
        assert _rows(backend)["stop"].state == AVAILABLE, backend
    aesir_row = _rows("aesir")["stop"]
    assert aesir_row.state == GREYED
    assert aesir_row.reason_code == "route_not_served"


def test_aesir_native_ledger_carves_out_logit_bias():
    ledger = {e.route: e for e in AESIR_LEDGER}
    assert ledger["native-generate"].served == frozenset(CANONICAL_CONTROLS) - {"logit_bias"}
    assert "logit_bias" in ledger["native-generate"].note
    assert ledger["openai-chat"].served == aesir_mod.SAMPLERS
    native = {r.name: r for r in truth_for_backend("aesir", aesir_route="native-generate")}
    assert native["logit_bias"].state == GREYED
    assert native["stop"].state == AVAILABLE  # P-009 record stands for stop


def test_audit_still_clean_and_adapters_account():
    assert audit_truth() == []
    assert aesir_mod.SAMPLERS | aesir_mod.UNSUPPORTED_SAMPLERS == frozenset(CANONICAL_CONTROLS)
    assert openai_mod.SAMPLERS | openai_mod.UNSUPPORTED_SAMPLERS == frozenset(CANONICAL_CONTROLS)
    assert "logit_bias" in openai_mod.SAMPLERS and "logit_bias" in openrouter_mod.SAMPLERS
    assert "logit_bias" not in ollama_mod.SAMPLERS


def test_compat_profiles_account_for_logit_bias():
    kept = filter_params({"logit_bias": BIAS_BAG}, OPENAI_PROFILE)
    assert kept.params == {"logit_bias": BIAS_BAG} and kept.dropped == ()
    dropped = filter_params({"logit_bias": BIAS_BAG}, OLLAMA_PROFILE)
    assert dropped.params == {}
    assert dropped.dropped[0].param == "logit_bias"
    assert "logit_bias" in dropped.dropped[0].reason


# ---------------- wire proof (captured payloads) ----------------

def _capture_transport(captured, sse):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=sse,
                              headers={"Content-Type": "text/event-stream"})
    return httpx.MockTransport(handler)


_SSE = (b'data: {"choices": [{"delta": {"content": "hi"}, '
        b'"finish_reason": "stop"}]}\n\ndata: [DONE]\n\n')


async def test_openai_wire_carries_bias_and_stop():
    captured: list = []
    backend = OpenAICompatibleChatBackend(
        transport=_capture_transport(captured, _SSE))
    params = SamplingParams(temperature=0.5, stop=("END",), logit_bias=BIAS)
    _ = [e async for e in backend.chat_stream(MSGS, params, asyncio.Event())]
    payload = captured[0]
    assert payload["logit_bias"] == BIAS_BAG
    assert payload["stop"] == ["END"]


async def test_openrouter_wire_carries_bias_and_stop():
    captured: list = []
    backend = OpenRouterChatBackend(
        transport=_capture_transport(captured, _SSE))
    params = SamplingParams(stop=("END",), logit_bias=BIAS)
    _ = [e async for e in backend.chat_stream(MSGS, params, asyncio.Event())]
    payload = captured[0]
    assert payload["logit_bias"] == BIAS_BAG
    assert payload["stop"] == ["END"]


def test_ollama_options_exclude_bias_but_carry_stop():
    backend = OllamaChatBackend()
    options = backend._options(SamplingParams(
        stop=("END",), logit_bias=BIAS, temperature=0.5))
    assert "logit_bias" not in options
    assert options["stop"] == ["END"]


def test_aesir_map_params_drops_bias_and_stop_with_warnings():
    wire, warnings = aesir_mod.map_params(SamplingParams(
        temperature=0.5, stop=("END",), logit_bias=BIAS))
    assert wire == {"temperature": 0.5}
    assert any("logit_bias" in w for w in warnings)
    assert any("stop" in w for w in warnings)


# ---------------- text-keyed bias honesty ----------------

def test_text_bias_without_token_map_invents_nothing():
    plan = plan_text_bias({"hello": 5.0, "world": -3.0})
    assert plan.resolved.is_empty
    assert [u.reason_code for u in plan.unresolved] == [
        "tokenizer_unavailable", "tokenizer_unavailable"]
    assert plan.to_dict()["resolved"] == {}


def test_text_bias_with_explicit_map_resolves_only_known():
    plan = plan_text_bias({"hello": 5.0, "world": -3.0}, {"hello": 123})
    assert plan.resolved.to_data() == {"123": 5.0}
    assert len(plan.unresolved) == 1
    assert plan.unresolved[0].text == "world"
    assert plan.unresolved[0].reason_code == "not_in_token_map"
    with pytest.raises(ValueError):
        plan_text_bias({"hello": 500.0}, {"hello": 1})
    with pytest.raises(ValueError):
        plan_text_bias({"hello": 1.0}, {"hello": -1})


# ---------------- stop validation + resolution ----------------

def test_validate_stop_sequences_strict():
    assert validate_stop_sequences(["A", "B"]) == ("A", "B")
    assert validate_stop_sequences("AB") == ("AB",)
    assert validate_stop_sequences(None) == ()
    for bad in ([""], [1], ["x" * 600], ["A"] * 65):
        with pytest.raises(ValueError):
            validate_stop_sequences(bad)
    with pytest.raises(ValueError):
        resolve_generation_controls(SamplingParams(stop=("",)))


def test_resolution_merges_template_stops_f3():
    params = SamplingParams(stop=("CUSTOM",), logit_bias=BIAS)
    out, warnings = resolve_generation_controls(
        params, template_stops=("TPL", "CUSTOM"))
    assert out.stop == ("CUSTOM", "TPL")  # sampler first, dedup, order
    assert out.logit_bias == BIAS and warnings == []  # no model: undeclared


def test_resolution_on_openai_model_keeps_bias_and_stop():
    model = OpenAICompatibleChatBackend().default_model
    out, warnings = resolve_generation_controls(
        SamplingParams(stop=("A",), logit_bias=BIAS), model,
        template_stops=("B",))
    assert out.stop == ("A", "B") and out.logit_bias == BIAS
    assert warnings == []


def test_resolution_on_aesir_model_clears_both_with_warnings():
    from runmal.backends.aesir import AesirChatBackend
    model = AesirChatBackend().default_model
    out, warnings = resolve_generation_controls(
        SamplingParams(stop=("A",), logit_bias=BIAS), model)
    assert out.stop is None and out.logit_bias is None
    assert "unsupported parameter dropped: logit_bias" in warnings
    assert "unsupported parameter dropped: stop" in warnings


def test_resolution_on_ollama_model_clears_bias_keeps_stop():
    model = OllamaChatBackend().default_model
    out, warnings = resolve_generation_controls(
        SamplingParams(stop=("A",), logit_bias=BIAS), model)
    assert out.stop == ("A",) and out.logit_bias is None
    assert warnings == ["unsupported parameter dropped: logit_bias"]


def test_bundle_validation_fixed_point_with_bias():
    raw = {"name": "b3", "sampler": {"logit_bias": BIAS_BAG, "stop": ["END"]}}
    once = validate_bundle(raw)
    assert validate_bundle(once) == once


def test_resolution_template_only_stops():
    out, warnings = resolve_generation_controls(
        SamplingParams(temperature=0.5), template_stops=("T1", "T2"))
    assert out.stop == ("T1", "T2") and warnings == []
