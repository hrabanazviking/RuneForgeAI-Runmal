"""S208 acceptance: per-backend compatibility filtering.

Unit tests with fixtures: a full canonical bag is translated to the
Ollama-native and OpenAI-shaped profiles deterministically; unsupported,
dropped, and mapped lists are explicit; nothing vanishes silently.
"""

import pytest

from runmal.generation.compat import (
    OLLAMA_PROFILE,
    OPENAI_PROFILE,
    filter_for_backend,
    filter_params,
)

FULL_BAG = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_tokens": 512,
    "frequency_penalty": 0.2,
    "presence_penalty": -0.1,
    "repetition_penalty": 1.1,
    "stop": ["<|end|>"],
    "seed": 42,
}


def test_openai_profile_passes_and_drops():
    r = filter_params(FULL_BAG, OPENAI_PROFILE)
    assert r.backend == "openai"
    assert r.params == {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 512,
        "frequency_penalty": 0.2,
        "presence_penalty": -0.1,
        "stop": ["<|end|>"],
        "seed": 42,
    }
    assert r.mapped == ()
    assert r.kept == (
        "frequency_penalty",
        "max_tokens",
        "presence_penalty",
        "seed",
        "stop",
        "temperature",
        "top_p",
    )
    assert [d.param for d in r.dropped] == ["repetition_penalty", "top_k"]
    assert all(d.reason for d in r.dropped)


def test_ollama_profile_maps_and_drops():
    r = filter_params(FULL_BAG, OLLAMA_PROFILE)
    assert r.backend == "ollama"
    assert r.params == {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "seed": 42,
        "stop": ["<|end|>"],
        "num_predict": 512,
        "repeat_penalty": 1.1,
    }
    assert [(m.source, m.dest) for m in r.mapped] == [
        ("max_tokens", "num_predict"),
        ("repetition_penalty", "repeat_penalty"),
    ]
    assert [d.param for d in r.dropped] == [
        "frequency_penalty",
        "presence_penalty",
    ]


def test_every_input_param_is_accounted_for():
    for profile in (OPENAI_PROFILE, OLLAMA_PROFILE):
        r = filter_params(FULL_BAG, profile)
        accounted = (
            set(r.kept) | {m.source for m in r.mapped} | {d.param for d in r.dropped}
        )
        assert accounted == set(FULL_BAG)
        assert len(r.params) == len(r.kept) + len(r.mapped)


def test_unknown_params_dropped_explicitly():
    r = filter_params({"temperature": 0.5, "vendor_magic": True}, OPENAI_PROFILE)
    assert r.params == {"temperature": 0.5}
    assert [(d.param, d.reason) for d in r.dropped] == [
        ("vendor_magic", "unknown parameter is not forwarded")
    ]


def test_empty_bag():
    r = filter_for_backend({}, "ollama")
    assert r.params == {} and r.mapped == () and r.dropped == ()


def test_deterministic_output():
    bag = dict(FULL_BAG)
    a = filter_params(bag, OLLAMA_PROFILE)
    b = filter_params(dict(reversed(list(bag.items()))), OLLAMA_PROFILE)
    assert a == b


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        filter_for_backend({}, "aesir")


def test_values_pass_through_unchanged():
    bag = {"stop": ["a", "b"], "temperature": 0.0}
    r = filter_params(bag, OPENAI_PROFILE)
    assert r.params["stop"] == ["a", "b"]  # same values, no coercion
    assert r.params["temperature"] == 0.0
