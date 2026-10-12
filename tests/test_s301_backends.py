"""S301 (roadmap): ChatBackend interfaces + fake contract suite."""

from __future__ import annotations

import asyncio

import pytest

from runmal.backends import (
    AuthenticationFailed,
    BackendError,
    ChatMessage,
    Done,
    ErrorEvent,
    FakeChatBackend,
    GenerationCancelled,
    RateLimited,
    SamplingParams,
    TextDelta,
    UsageUpdate,
    contract,
)


async def test_fake_passes_full_contract():
    backend = FakeChatBackend(api_key=contract.CANARY)
    await contract.run_all(backend)


async def test_fake_deterministic_and_usage():
    backend = FakeChatBackend(chunks=("a", "b"), usage=UsageUpdate(total_tokens=3))
    events = [e async for e in backend.chat_stream(
        [ChatMessage("user", "hi")], SamplingParams(), asyncio.Event())]
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["a", "b"]
    assert isinstance(events[-1], Done) and events[-1].usage.total_tokens == 3


async def test_fake_failure_injection_and_cancel_midstream():
    failing = FakeChatBackend(fail_with=AuthenticationFailed("bad key"))
    with pytest.raises(AuthenticationFailed):
        [e async for e in failing.chat_stream([], SamplingParams(), asyncio.Event())]
    cancel = asyncio.Event()
    backend = FakeChatBackend(chunks=("x", "y", "z"))

    async def run():
        seen = []
        async for e in backend.chat_stream([], SamplingParams(), cancel):
            seen.append(e)
            cancel.set()
        return seen

    with pytest.raises(GenerationCancelled):
        await run()


def test_event_to_dict_shapes():
    assert TextDelta("hi").to_dict() == {"type": "text_delta", "text": "hi"}
    assert UsageUpdate(1, 2, 3).to_dict()["type"] == "usage"
    assert Done("stop").to_dict() == {"type": "done", "reason": "stop", "usage": None}
    err = ErrorEvent("rate_limited", "slow", True)
    assert err.to_dict()["type"] == "error" and err.to_dict()["retryable"] is True


def test_error_hierarchy_attrs():
    err = RateLimited("slow", retry_after_s=2.5)
    assert isinstance(err, BackendError)
    assert err.code == "rate_limited" and err.retryable is True
    assert err.retry_after_s == 2.5
    assert AuthenticationFailed("x").retryable is False
    assert "SECRET" not in str(AuthenticationFailed("x").to_event_dict())


def test_sampling_params_validation_and_bag():
    params = SamplingParams(temperature=0.7, max_output_tokens=64, stop=("a",))
    assert params.to_bag() == {"temperature": 0.7, "max_tokens": 64, "stop": ["a"]}
    assert SamplingParams.from_bag(params.to_bag()) == params
    for bad in ({"temperature": -1}, {"top_p": 0}, {"top_k": -1},
                {"max_output_tokens": 0}, {"seed": -1}, {"stop": ("a", 1)},
                {"presence_penalty": 3}):
        with pytest.raises(ValueError):
            SamplingParams(**bad)


def test_filter_params_capability_truth():
    backend = FakeChatBackend()
    filtered, warnings = backend.filter_params(
        SamplingParams(temperature=0.5, top_k=40, min_p=0.1))
    assert filtered.temperature == 0.5
    assert filtered.top_k is None and filtered.min_p is None
    assert any("top_k" in w for w in warnings)
    kept, no_warnings = backend.filter_params(SamplingParams(seed=7))
    assert kept.seed == 7 and no_warnings == []
