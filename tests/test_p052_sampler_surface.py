"""P-052 Sampler surface complete battery.

Pins: the complete canonical catalogue as data (28 bag keys;
29 since P-060 added logit_bias),
SamplingParams validation + bag round-trip for every new sampler,
preset-bag validation parity, honest per-backend applicability
(declared only where the adapter forwards; dropped with reasons
elsewhere -- never faked), the Ollama forwarding of the samplers
its public options carry, the S208 profile accounting, and the
P-050 F3 stop-string merge (sampler stops first, template stops
appended, dedup, order preserved).
"""

import pytest

from runmal.backends.aesir import SAMPLERS as AESIR_SAMPLERS
from runmal.backends.aesir import UNSUPPORTED_SAMPLERS as AESIR_UNSUPPORTED
from runmal.backends.aesir import map_params as aesir_map_params
from runmal.backends.models import Capabilities, ModelInfo
from runmal.backends.negotiation import CANONICAL_CONTROLS, clamp_params, controls_dict
from runmal.backends.ollama import SAMPLERS as OLLAMA_SAMPLERS
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import SAMPLERS as OPENAI_SAMPLERS
from runmal.backends.openai_compat import UNSUPPORTED_SAMPLERS as OPENAI_UNSUPPORTED
from runmal.backends.params import SamplingParams
from runmal.backends.samplers import (
    SAMPLER_NAMES,
    SAMPLER_SPECS,
    merge_stop_strings,
    resolve_sampler_params,
    sampler_surface,
    spec_for,
)
from runmal.generation.compat import OLLAMA_PROFILE, OPENAI_PROFILE, filter_params
from runmal.presets.service import validate_params

NEW_KEYS = (
    "typical_p", "top_a", "tfs_z", "epsilon_cutoff", "eta_cutoff",
    "dry_multiplier", "dry_base", "dry_allowed_length",
    "dry_penalty_last_n", "dry_sequence_breakers", "xtc_probability",
    "xtc_threshold", "mirostat_mode", "mirostat_tau", "mirostat_eta",
    "dynamic_temperature_range", "dynamic_temperature_exponent",
)
FULL_PARAMS = SamplingParams(
    temperature=0.7, top_p=0.9, top_k=40, min_p=0.05,
    repetition_penalty=1.1, presence_penalty=0.2, frequency_penalty=0.1,
    typical_p=0.95, top_a=0.2, tfs_z=0.95, epsilon_cutoff=0.0003,
    eta_cutoff=0.0003, dry_multiplier=0.8, dry_base=1.75,
    dry_allowed_length=2, dry_penalty_last_n=0,
    dry_sequence_breakers=("\n",), xtc_probability=0.5,
    xtc_threshold=0.1, mirostat_mode=2, mirostat_tau=5.0,
    mirostat_eta=0.1, dynamic_temperature_range=0.4,
    dynamic_temperature_exponent=1.0, max_output_tokens=256,
    stop=("END",), seed=42, context_length=8192,
    logit_bias=((42, 1.5),),
)


def _model(supported, key="x", mid="m1"):
    return ModelInfo(model_id=mid, display_name=mid, backend_key=key,
                     capabilities=Capabilities(chat=True, supported_samplers=frozenset(supported)))


# ---------------- catalogue as data ----------------

def test_catalogue_is_complete_and_consistent():
    assert len(SAMPLER_NAMES) == 29  # 28 at P-052, + logit_bias (P-060)
    assert len(set(SAMPLER_NAMES)) == 29
    for key in NEW_KEYS:
        assert key in SAMPLER_NAMES
    # catalogue == SamplingParams fields (bag spelling) exactly
    import dataclasses
    fields = {f.name for f in dataclasses.fields(SamplingParams)}
    bag_names = {("max_tokens" if n == "max_output_tokens" else n) for n in fields}
    assert set(SAMPLER_NAMES) == bag_names
    assert tuple(CANONICAL_CONTROLS) == SAMPLER_NAMES
    groups = {s.group for s in SAMPLER_SPECS}
    assert {"core", "penalty", "dry", "xtc", "cutoff", "mirostat", "dynamic"} <= groups
    for spec in SAMPLER_SPECS:
        assert spec.description and spec.kind in ("float", "int", "strings", "bias_map")
    assert spec_for("dry_multiplier").group == "dry"
    with pytest.raises(ValueError):
        spec_for("nope")


def test_surface_without_model_is_undeclared_not_guessed():
    rows = sampler_surface()
    assert [r["name"] for r in rows] == list(SAMPLER_NAMES)
    assert all(r["supported"] is None for r in rows)


def test_surface_with_model_uses_declared_truth():
    model = _model({"temperature", "dry_multiplier"})
    rows = {r["name"]: r for r in sampler_surface(model)}
    assert rows["temperature"]["supported"] is True
    assert rows["dry_multiplier"]["supported"] is True
    assert rows["xtc_probability"]["supported"] is False
    assert "does not declare" in rows["xtc_probability"]["detail"]
    ctrl = {c["name"]: c for c in controls_dict(model)["controls"] if c["kind"] == "sampler"}
    assert set(ctrl) == set(SAMPLER_NAMES)
    assert ctrl["dry_base"]["supported"] is False


# ---------------- SamplingParams validation ----------------

def test_full_params_bag_roundtrip():
    bag = FULL_PARAMS.to_bag()
    assert set(bag) == set(SAMPLER_NAMES)
    assert bag["dry_sequence_breakers"] == ["\n"]
    assert bag["logit_bias"] == {"42": 1.5}
    assert bag["stop"] == ["END"] and bag["max_tokens"] == 256
    assert SamplingParams.from_bag(bag) == FULL_PARAMS


@pytest.mark.parametrize("kwargs", [
    {"typical_p": 0}, {"typical_p": 1.5}, {"top_a": -0.1},
    {"tfs_z": 2.0}, {"epsilon_cutoff": -1}, {"eta_cutoff": 1.5},
    {"dry_multiplier": -0.5}, {"dry_base": 0.5},
    {"dry_allowed_length": -1}, {"dry_penalty_last_n": -2},
    {"dry_sequence_breakers": ("",)}, {"dry_sequence_breakers": ["\n"]},
    {"xtc_probability": 1.5}, {"xtc_threshold": -0.1},
    {"mirostat_mode": 3}, {"mirostat_mode": 1.5},
    {"mirostat_tau": 0}, {"mirostat_eta": -0.1},
    {"dynamic_temperature_range": -0.1},
    {"dynamic_temperature_exponent": 0},
])
def test_new_sampler_validation_rejects(kwargs):
    with pytest.raises(ValueError):
        SamplingParams(**kwargs)


def test_new_sampler_validation_accepts_edges():
    SamplingParams(typical_p=1, top_a=0, tfs_z=1, dry_multiplier=0,
                   dry_base=1, mirostat_mode=0, xtc_probability=0)


# ---------------- preset bag parity ----------------

def test_preset_bag_accepts_complete_set():
    bag = {k: FULL_PARAMS.to_bag()[k] for k in NEW_KEYS}
    assert validate_params(bag) == bag


@pytest.mark.parametrize("key,value", [
    ("dry_base", 0.5), ("xtc_threshold", 2), ("mirostat_mode", 9),
    ("dry_sequence_breakers", ["ok", ""]), ("typical_p", 0),
])
def test_preset_bag_rejects_out_of_range(key, value):
    with pytest.raises(ValueError):
        validate_params({key: value})


# ---------------- honesty: per-backend applicability ----------------

def test_backend_accounting_covers_catalogue():
    assert set(AESIR_SAMPLERS) | set(AESIR_UNSUPPORTED) == set(SAMPLER_NAMES)
    assert not (set(AESIR_SAMPLERS) & set(AESIR_UNSUPPORTED))
    assert set(OPENAI_SAMPLERS) | set(OPENAI_UNSUPPORTED) == set(SAMPLER_NAMES)
    assert not (set(OPENAI_SAMPLERS) & set(OPENAI_UNSUPPORTED))
    # No backend declares DRY/XTC: no adapter forwards them today.
    for declared in (AESIR_SAMPLERS, OPENAI_SAMPLERS, OLLAMA_SAMPLERS):
        assert not any(k.startswith(("dry_", "xtc_")) for k in declared)


def test_ollama_declares_only_what_it_forwards():
    assert {"typical_p", "tfs_z", "mirostat_mode", "mirostat_tau", "mirostat_eta"} <= set(OLLAMA_SAMPLERS)
    backend = OllamaChatBackend()
    options = backend._options(SamplingParams(
        typical_p=0.9, tfs_z=0.9, mirostat_mode=2, mirostat_tau=5.0,
        mirostat_eta=0.1, dry_multiplier=0.8, xtc_probability=0.5))
    assert options == {"typical_p": 0.9, "tfs_z": 0.9, "mirostat": 2,
                       "mirostat_tau": 5.0, "mirostat_eta": 0.1}


def test_clamp_drops_new_samplers_with_warnings():
    model = _model({"temperature"})
    out, warnings = clamp_params(FULL_PARAMS, model)
    assert out.temperature == 0.7
    assert out.dry_multiplier is None and out.xtc_probability is None
    assert out.mirostat_mode is None and out.typical_p is None
    assert any("dry_multiplier" in w for w in warnings)
    assert any("xtc_threshold" in w for w in warnings)


def test_aesir_map_params_drops_new_with_warnings():
    wire, warnings = aesir_map_params(FULL_PARAMS)
    assert set(wire) == {"temperature", "top_p", "max_tokens", "seed"}
    assert any("dry_multiplier" in w for w in warnings)


def test_compat_profiles_account_for_new_keys():
    bag = FULL_PARAMS.to_bag()
    openai = filter_params(bag, OPENAI_PROFILE)
    dropped = {d.param for d in openai.dropped}
    assert set(NEW_KEYS) <= dropped
    assert all(d.reason for d in openai.dropped)
    ollama = filter_params(bag, OLLAMA_PROFILE)
    assert ollama.params["mirostat"] == 2 and ollama.params["typical_p"] == 0.95
    assert ollama.params["tfs_z"] == 0.95
    odropped = {d.param for d in ollama.dropped}
    assert {"dry_multiplier", "xtc_probability", "top_a"} <= odropped
    # every input accounted: kept + mapped + dropped == input keys
    for res in (openai, ollama):
        accounted = set(res.kept) | {m.source for m in res.mapped} | {d.param for d in res.dropped}
        assert accounted == set(bag)


# ---------------- stop-string merge (P-050 F3) ----------------

def test_merge_stop_strings_order_dedup_empty():
    assert merge_stop_strings(("A", "B"), ("B", "C")) == ("A", "B", "C")
    assert merge_stop_strings(("", "A"), ()) == ("A",)
    assert merge_stop_strings() == ()
    assert merge_stop_strings(None, ("X",)) == ("X",)
    with pytest.raises(ValueError):
        merge_stop_strings((1,))
    # a bare string is one stop, never iterated into characters
    assert merge_stop_strings("AB", ("C",)) == ("AB", "C")
    assert SamplingParams(stop=("A",)).with_merged_stops("BC").stop == ("A", "BC")


def test_with_merged_stops_keeps_sampler_first():
    params = SamplingParams(stop=("<|im_end|>",))
    merged = params.with_merged_stops(("<|im_end|>", "USER:"))
    assert merged.stop == ("<|im_end|>", "USER:")
    assert params.stop == ("<|im_end|>",)  # original untouched (frozen)


def test_resolve_merges_template_stops_then_clamps():
    from runmal.prompt.instruct import CHATML
    params = SamplingParams(stop=("CUSTOM",), dry_multiplier=0.8)
    out, warnings = resolve_sampler_params(params, template_stops=CHATML.stop_strings)
    assert out.stop == ("CUSTOM", "<|im_end|>", "<|im_start|>")
    assert out.dry_multiplier == 0.8 and warnings == []  # no model: no clamp
    model = _model({"temperature"})  # declares no stop support
    out2, warnings2 = resolve_sampler_params(params, model=model, template_stops=CHATML.stop_strings)
    assert out2.stop is None
    assert any(w == "unsupported parameter dropped: stop" for w in warnings2)
