"""Adapter performance benchmark (S705) — Rúnmál-side cutover cost.

Replays IDENTICAL recorded token streams through the Ollama and Aesir
chat adapters over in-process fixture transports and measures the cost
this repo owns: time-to-first-normalized-token, total stream time, and
normalized tokens/sec. It does NOT measure live engine throughput (the
Ollama or Aesir servers are different programs; see the S705 section of
docs/BENCHMARKS.md, where the acceptance bar was declared before this
tool was run).

Run: ``python -m runmal.backends.benchmark [--runs 15] [--tokens 256]
[--json-out PATH]`` — exit code 0 when every predeclared bar passes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass

import httpx

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.events import TextDelta
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend

DEFAULT_RUNS = 15
DEFAULT_TOKENS = 256

# Predeclared bars (docs/BENCHMARKS.md, S705 — declared 2026-10-13
# before any run; do not edit to fit results).
BAR_TOTAL_RATIO = 1.5
BAR_TTFT_SLACK_MS = 5.0
BAR_MIN_TOKENS_PER_SEC = 20_000.0

_MSGS = [ChatMessage(role="user", content="benchmark prompt")]


def token_texts(count: int) -> tuple[str, ...]:
    return tuple(f"tok{i} " for i in range(count))


def ollama_payload(tokens: tuple[str, ...]) -> bytes:
    lines = [
        json.dumps({"message": {"role": "assistant", "content": t}, "done": False}) for t in tokens
    ]
    lines.append(
        json.dumps(
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 9,
                "eval_count": len(tokens),
            }
        )
    )
    return ("\n".join(lines) + "\n").encode()


def aesir_payload(tokens: tuple[str, ...]) -> bytes:
    lines = []
    for t in tokens:
        lines.append(
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": t},
                            "finish_reason": None,
                        }
                    ]
                }
            )
        )
    lines.append(
        "data: "
        + json.dumps(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": len(tokens),
                    "total_tokens": 9 + len(tokens),
                },
            }
        )
    )
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


def _transport(payload: bytes, content_type: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, content=payload, headers={"Content-Type": content_type})
        return httpx.Response(
            200,
            content=b'{"models": [], "data": []}',
            headers={"Content-Type": "application/json"},
        )

    return httpx.MockTransport(handler)


@dataclass(frozen=True)
class AdapterStats:
    backend_key: str
    runs: int
    tokens_per_stream: int
    ttft_ms_median: float
    total_ms_median: float
    tokens_per_sec_median: float
    text_sha: str

    def to_dict(self) -> dict:
        return {
            "backend_key": self.backend_key,
            "runs": self.runs,
            "tokens_per_stream": self.tokens_per_stream,
            "ttft_ms_median": round(self.ttft_ms_median, 4),
            "total_ms_median": round(self.total_ms_median, 4),
            "tokens_per_sec_median": round(self.tokens_per_sec_median, 1),
            "text_sha": self.text_sha,
        }


async def benchmark_adapter(backend, tokens: tuple[str, ...], runs: int) -> AdapterStats:
    import hashlib

    from runmal.backends.params import SamplingParams

    ttfts: list[float] = []
    totals: list[float] = []
    rates: list[float] = []
    text_hash = ""
    for _ in range(runs):
        start = time.perf_counter()
        ttft: float | None = None
        seen: list[str] = []
        async for event in backend.chat_stream(list(_MSGS), SamplingParams(), asyncio.Event()):
            if isinstance(event, TextDelta):
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                seen.append(event.text)
        total_ms = (time.perf_counter() - start) * 1000
        ttfts.append(ttft if ttft is not None else total_ms)
        totals.append(total_ms)
        rates.append(len(seen) / (total_ms / 1000) if total_ms > 0 else 0.0)
        text_hash = hashlib.sha256("".join(seen).encode()).hexdigest()
    return AdapterStats(
        backend_key=backend.backend_key,
        runs=runs,
        tokens_per_stream=len(tokens),
        ttft_ms_median=statistics.median(ttfts),
        total_ms_median=statistics.median(totals),
        tokens_per_sec_median=statistics.median(rates),
        text_sha=text_hash,
    )


@dataclass(frozen=True)
class BarResult:
    name: str
    threshold: str
    actual: str
    passed: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "actual": self.actual,
            "passed": self.passed,
        }


def evaluate_bars(ollama: AdapterStats, aesir: AdapterStats) -> list[BarResult]:
    ratio = (
        aesir.total_ms_median / ollama.total_ms_median
        if ollama.total_ms_median > 0
        else float("inf")
    )
    ttft_delta = aesir.ttft_ms_median - ollama.ttft_ms_median
    return [
        BarResult(
            "aesir_total_vs_ollama",
            f"ratio <= {BAR_TOTAL_RATIO}",
            f"ratio {ratio:.3f} (aesir {aesir.total_ms_median:.3f} ms, "
            f"ollama {ollama.total_ms_median:.3f} ms)",
            ratio <= BAR_TOTAL_RATIO,
        ),
        BarResult(
            "aesir_ttft_vs_ollama",
            f"aesir ttft <= ollama ttft + {BAR_TTFT_SLACK_MS} ms",
            f"delta {ttft_delta:+.3f} ms (aesir {aesir.ttft_ms_median:.3f} ms, "
            f"ollama {ollama.ttft_ms_median:.3f} ms)",
            ttft_delta <= BAR_TTFT_SLACK_MS,
        ),
        BarResult(
            "ollama_throughput",
            f">= {BAR_MIN_TOKENS_PER_SEC:,.0f} tokens/sec",
            f"{ollama.tokens_per_sec_median:,.0f} tokens/sec",
            ollama.tokens_per_sec_median >= BAR_MIN_TOKENS_PER_SEC,
        ),
        BarResult(
            "aesir_throughput",
            f">= {BAR_MIN_TOKENS_PER_SEC:,.0f} tokens/sec",
            f"{aesir.tokens_per_sec_median:,.0f} tokens/sec",
            aesir.tokens_per_sec_median >= BAR_MIN_TOKENS_PER_SEC,
        ),
        BarResult(
            "identical_token_streams",
            "both adapters yield byte-identical token text",
            "sha256 equal" if ollama.text_sha == aesir.text_sha else "MISMATCH",
            ollama.text_sha == aesir.text_sha,
        ),
    ]


def host_config() -> dict:
    cpu = platform.processor() or ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    commit = "unknown"
    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            or "unknown"
        )
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "cpu": cpu,
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "commit": commit,
    }


async def run_benchmark(runs: int = DEFAULT_RUNS, tokens: int = DEFAULT_TOKENS) -> dict:
    texts = token_texts(tokens)
    ollama = OllamaChatBackend(transport=_transport(ollama_payload(texts), "application/x-ndjson"))
    aesir = AesirChatBackend(transport=_transport(aesir_payload(texts), "text/event-stream"))
    ollama_stats = await benchmark_adapter(ollama, texts, runs)
    aesir_stats = await benchmark_adapter(aesir, texts, runs)
    bars = evaluate_bars(ollama_stats, aesir_stats)
    return {
        "config": host_config(),
        "adapters": {
            "ollama": ollama_stats.to_dict(),
            "aesir": aesir_stats.to_dict(),
        },
        "bars": [b.to_dict() for b in bars],
        "passed": all(b.passed for b in bars),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runmal-benchmark")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--tokens", type=int, default=DEFAULT_TOKENS)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    report = asyncio.run(run_benchmark(runs=args.runs, tokens=args.tokens))
    print(json.dumps(report, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
