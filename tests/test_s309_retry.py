"""S309 (roadmap): error taxonomy + retry contract (BACKEND_CONTRACT §7).

Retries are bounded, cancellation-aware, and allowed ONLY before visible
output. After output begins there is NO silent continuation — not on the
same backend, not on a fallback. Every attempt carries the same request
identity, so a persisting consumer records exactly one assistant turn.
"""

from __future__ import annotations

import asyncio

import pytest

from runmal.backends.errors import (
    AuthenticationFailed,
    BackendUnavailable,
    GenerationCancelled,
    RateLimited,
)
from runmal.backends.events import TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.backends.retry import AttemptRecord, RetryPolicy, stream_with_retry
from runmal.generation.service import generate_events

MSGS = [ChatMessage("user", "hi")]
PARAMS = SamplingParams()


class FlakyBackend(FakeChatBackend):
    """Fails pre-output `fail_times` times, then streams normally."""

    def __init__(self, fail_times: int, error, **kwargs):
        super().__init__(**kwargs)
        self._fail_times = fail_times
        self._error = error
        self.calls = 0

    async def chat_stream(self, messages, params, cancel):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._error
        async for event in super().chat_stream(messages, params, cancel):
            yield event


class SleepLog:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def collect(backend, **kwargs):
    kwargs.setdefault("request_id", "req-309")
    kwargs.setdefault("cancel", asyncio.Event())
    return [event async for event in stream_with_retry(
        backend, MSGS, PARAMS, kwargs.pop("cancel"), **kwargs)]


async def test_retry_recovers_before_output_with_bounded_backoff():
    sleep = SleepLog()
    backend = FlakyBackend(2, RateLimited("slow", retry_after_s=30.0),
                           chunks=("Hello", " world"))
    policy = RetryPolicy(max_attempts=3, base_delay_s=0.5, max_delay_s=2.0)
    events = await collect(backend, policy=policy, sleep=sleep)
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(texts) == "Hello world"
    assert backend.calls == 3
    # retry_after_s=30 is honored but CAPPED at max_delay_s (bounded §7).
    assert sleep.delays == [2.0, 2.0]


async def test_non_retryable_error_is_not_retried():
    backend = FlakyBackend(5, AuthenticationFailed("bad key"))
    with pytest.raises(AuthenticationFailed):
        await collect(backend, policy=RetryPolicy(max_attempts=3), sleep=SleepLog())
    assert backend.calls == 1


async def test_no_retry_after_visible_output_begins():
    # fail_after=1: one TextDelta is yielded, THEN the failure hits.
    backend = FakeChatBackend(chunks=("part1", "part2"),
                              fail_with=RateLimited("rl"), fail_after=1)
    seen: list = []
    with pytest.raises(RateLimited):
        async for event in stream_with_retry(
                backend, MSGS, PARAMS, asyncio.Event(),
                request_id="req-309", policy=RetryPolicy(max_attempts=5),
                sleep=SleepLog()):
            seen.append(event)
    assert [e.text for e in seen if isinstance(e, TextDelta)] == ["part1"]


async def test_no_silent_cross_provider_continuation_after_output():
    primary = FakeChatBackend(chunks=("from-primary", "more"),
                               fail_with=BackendUnavailable("down"), fail_after=1)
    fallback = FakeChatBackend(chunks=("from-fallback",))
    seen: list = []
    with pytest.raises(BackendUnavailable):
        async for event in stream_with_retry(
                primary, MSGS, PARAMS, asyncio.Event(),
                request_id="req-309", policy=RetryPolicy(max_attempts=2),
                fallback=fallback, sleep=SleepLog()):
            seen.append(event)
    # Only the primary's first chunk — the fallback NEVER continues an
    # answer that already started (INV-004).
    assert [e.text for e in seen if isinstance(e, TextDelta)] == ["from-primary"]


async def test_fallback_only_before_output_and_identity_is_shared():
    records: list[AttemptRecord] = []
    persisted: list[tuple[str, str]] = []
    primary = FlakyBackend(99, BackendUnavailable("down"))
    fallback = FakeChatBackend(chunks=("fallback answer",))
    events = await collect(
        primary, policy=RetryPolicy(max_attempts=2), fallback=fallback,
        sleep=SleepLog(), on_attempt=records.append)
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "fallback answer"
    # One persisted turn per request identity, despite 3 attempts.
    persisted.append((records[0].dedupe_key(), text))
    assert len(persisted) == 1
    assert {r.request_id for r in records} == {"req-309"}
    assert [(r.phase, r.attempt) for r in records] == [
        ("primary", 1), ("primary", 2), ("fallback", 1)]
    assert {r.backend_key for r in records} == {"fake"}


async def test_attempts_are_bounded_and_last_error_raises():
    sleep = SleepLog()
    backend = FlakyBackend(99, RateLimited("rl", retry_after_s=0.1))
    policy = RetryPolicy(max_attempts=3, base_delay_s=0.05, max_delay_s=1.0)
    with pytest.raises(RateLimited):
        await collect(backend, policy=policy, sleep=sleep)
    assert backend.calls == 3
    assert sleep.delays == [0.1, 0.1]


async def test_cancellation_during_backoff_aborts():
    cancel = asyncio.Event()
    backend = FlakyBackend(99, RateLimited("rl", retry_after_s=60.0))
    policy = RetryPolicy(max_attempts=3, base_delay_s=30.0, max_delay_s=60.0)
    task = asyncio.create_task(_collect_cancellable(backend, cancel, policy))
    await asyncio.sleep(0.05)
    cancel.set()
    with pytest.raises(GenerationCancelled):
        await asyncio.wait_for(task, timeout=2.0)
    assert backend.calls == 1


async def _collect_cancellable(backend, cancel, policy):
    return [event async for event in stream_with_retry(
        backend, MSGS, PARAMS, cancel, request_id="req-309", policy=policy)]


async def test_generate_events_with_retry_policy_single_turn():
    backend = FlakyBackend(1, BackendUnavailable("down"),
                           chunks=("seam ", "ok"))
    events = [event async for event in generate_events(
        "s309-seam", messages=MSGS, backend=backend,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0,
                                 max_delay_s=0.0))]
    tokens = [e for e in events if e["type"] == "token"]
    assert "".join(t["text"] for t in tokens) == "seam ok"
    assert events[-1] == {"type": "done", "finish_reason": "stop"}
    assert backend.calls == 2


def test_policy_validation_bounds():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=99)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay_s=5.0, max_delay_s=1.0)
