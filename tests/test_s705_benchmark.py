"""S705 (roadmap): adapter performance benchmark — instrument tests.

The predeclared bar lives in docs/BENCHMARKS.md (declared before the
run). These tests verify the INSTRUMENT: identical streams through both
adapters, sane metrics, and correct bar evaluation on known numbers.
The measured verdict itself is recorded in the ledger from the
purplelongship run, not asserted here (timing asserts would be flaky).
"""

from __future__ import annotations

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.benchmark import (
    AdapterStats,
    _transport,
    aesir_payload,
    benchmark_adapter,
    evaluate_bars,
    ollama_payload,
    run_benchmark,
    token_texts,
)
from runmal.backends.ollama import OllamaChatBackend


def test_payloads_carry_identical_token_texts():
    texts = token_texts(8)
    assert ollama_payload(texts).count(b"tok") >= 8
    assert aesir_payload(texts).count(b"tok") >= 8
    assert texts[3] == "tok3 "


async def test_benchmark_adapter_identical_streams():
    texts = token_texts(32)
    ollama = OllamaChatBackend(transport=_transport(ollama_payload(texts), "application/x-ndjson"))
    aesir = AesirChatBackend(transport=_transport(aesir_payload(texts), "text/event-stream"))
    o = await benchmark_adapter(ollama, texts, runs=3)
    a = await benchmark_adapter(aesir, texts, runs=3)
    assert o.text_sha == a.text_sha  # same words through both seams
    assert o.tokens_per_stream == a.tokens_per_stream == 32
    for stats in (o, a):
        assert stats.ttft_ms_median >= 0
        assert stats.total_ms_median > 0
        assert stats.tokens_per_sec_median > 0


def _stats(total: float, ttft: float, rate: float, sha: str = "x") -> AdapterStats:
    return AdapterStats(
        backend_key="b",
        runs=15,
        tokens_per_stream=256,
        ttft_ms_median=ttft,
        total_ms_median=total,
        tokens_per_sec_median=rate,
        text_sha=sha,
    )


def test_evaluate_bars_pass_and_fail_paths():
    bars = evaluate_bars(_stats(10.0, 1.0, 50_000), _stats(12.0, 2.0, 60_000))
    assert all(b.passed for b in bars)
    bars = evaluate_bars(_stats(10.0, 1.0, 50_000), _stats(40.0, 30.0, 60_000))
    by_name = {b.name: b for b in bars}
    assert not by_name["aesir_total_vs_ollama"].passed
    assert not by_name["aesir_ttft_vs_ollama"].passed
    assert by_name["aesir_throughput"].passed
    bars = evaluate_bars(_stats(10.0, 1.0, 50_000, "a"), _stats(10.0, 1.0, 50_000, "b"))
    assert not {b.name: b for b in bars}["identical_token_streams"].passed


async def test_run_benchmark_report_shape():
    report = await run_benchmark(runs=2, tokens=16)
    assert set(report["adapters"]) == {"ollama", "aesir"}
    assert report["config"]["python"]
    assert len(report["bars"]) == 5
    assert isinstance(report["passed"], bool)
