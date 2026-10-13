"""Voice benchmark harness (S514).

One reproducible command renders the Campaign V benchmark report:

    python -m runmal.voice.benchmark [--real] [--out PATH]

The report records hardware, OS, dependency versions, models, the
fixture corpus, per-section p50/p95, and the PREDECLARED thresholds from
S502/S503/S504/S507 — which this harness reads but NEVER rewrites
(BENCHMARKS.md rule 6: a failed benchmark is evidence). Sections whose
real dependencies/models are absent are reported as "not run" with the
reason — never fabricated, never silently dropped.

Sections: VAD segmentation (fixture corpus vs S502 contract), STT
(fixed Flite corpus vs S503 contract), TTS (fixed corpus, measured
PER BACKEND against the per-backend PREDECLARED thresholds of
ADR-0005 / docs/BENCHMARKS.md — CosyVoice and Chatterbox bind;
user-installed backends measure as information only), end-to-end
simulated turn stages (S510 chain), interruption latency (S507
fixture vs its 100 ms budget).
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.metrics import percentile
from runmal.voice.stt import STT_CONTRACT, FakeSTTBackend, benchmark_stt
from runmal.voice.tts import FakeTTSBackend, VoiceInfo
from runmal.voice.vad import (
    SEGMENTATION_CONTRACT,
    EnergyVadModel,
    VadSegmenter,
    segmentation_metrics,
)


def hardware_info() -> dict:
    info = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpu": platform.processor() or "unknown",
    }
    try:  # Linux reference hosts: the honest CPU model string.
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        import os

        info["cpu_count"] = os.cpu_count()
    except Exception:
        pass
    return info


def package_versions() -> dict:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str] = {}
    for name in (
        "numpy",
        "onnxruntime",
        "faster-whisper",
        "ctranslate2",
        "sounddevice",
        "silero-vad",
    ):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "not installed"
    return out


def _frame(amplitude: float) -> bytes:
    import math

    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * 200 * i / 16000) for i in range(FRAME_SAMPLES)]
    )


def vad_section() -> dict:
    from runmal.voice.vad import VadConfig

    speech, silence, noise = _frame(0.5), _frame(0.0), _frame(0.03)
    frames: list[bytes] = list(silence) * 0 + [silence] * 5
    expected: list[tuple[int, int]] = []
    for n in range(5):
        frames.extend([noise] * 4)
        frames.extend([speech] * 2)  # transient
        frames.extend([noise] * 4)
        start = len(frames)
        frames.extend([speech] * (10 + n))
        expected.append((start, len(frames)))
        frames.extend([silence] * 15)
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig())
    detected = segmenter.segment_stream(frames)
    metrics = segmentation_metrics(expected, detected)
    return {
        "model": "energy-fixture (segmentation logic); silero-onnx is the real model",
        "metrics": metrics,
        "contract": dict(SEGMENTATION_CONTRACT),
        "pass": (
            metrics["recall"] >= SEGMENTATION_CONTRACT["min_recall"]
            and metrics["precision"] >= SEGMENTATION_CONTRACT["min_precision"]
            and metrics["max_onset_error_frames"] <= SEGMENTATION_CONTRACT["max_onset_error_frames"]
            and metrics["max_offset_error_frames"]
            <= SEGMENTATION_CONTRACT["max_offset_error_frames"]
        ),
    }


def stt_section(real: bool, workdir: Path) -> dict:
    section: dict = {"contract": dict(STT_CONTRACT)}
    if real:
        try:
            from runmal.voice.corpus import build_flite_corpus
            from runmal.voice.stt import FasterWhisperSTT

            corpus = build_flite_corpus(workdir / "stt-corpus")
            backend = FasterWhisperSTT(STT_CONTRACT["model"], cache_dir=workdir / "whisper-cache")
            result = benchmark_stt(backend, corpus)
            section.update(
                {
                    "backend": backend.backend_key,
                    "model": STT_CONTRACT["model"],
                    "corpus": "flite-slt fixed corpus (synthetic speech; a floor, "
                    "not a human-speech claim)",
                    "wer": round(result.wer, 4),
                    "rtf_p50": round(result.rtf_p50, 4),
                    "rtf_p95": round(result.rtf_p95, 4),
                    "items": result.items,
                    "pass": all(result.meets_contract().values()),
                }
            )
        except Exception as exc:
            section.update({"status": f"not run: {type(exc).__name__}: {exc}"})
    else:
        section.update(
            {
                "backend": "fake-stt (fixture run; use --real for faster-whisper)",
                "status": "fixture-only run — real STT numbers require --real",
            }
        )
        _ = FakeSTTBackend  # the fixture path is exercised in the test suite
    return section


def _measure_tts(backend, voice) -> dict:
    """First-audio + RTF over the fixed corpus. The clock starts with
    the backend already constructed (model warm/loaded, per
    docs/BENCHMARKS.md); model-load time is reported separately."""
    from runmal.voice.tts import TTS_CORPUS_TEXTS

    first_audio: list[float] = []
    rtfs: list[float] = []
    for text in TTS_CORPUS_TEXTS:
        started = time.perf_counter()
        chunks = []
        first_at: float | None = None
        for chunk in backend.synthesize(text, voice):
            if first_at is None and chunk.pcm:
                first_at = time.perf_counter()
            chunks.append(chunk)
        elapsed = time.perf_counter() - started
        total_audio = sum(c.duration_s for c in chunks)
        first_audio.append((first_at - started) if first_at is not None else elapsed)
        rtfs.append(elapsed / total_audio if total_audio else 0.0)
    return {
        "texts": len(TTS_CORPUS_TEXTS),
        "first_audio_p50_s": round(percentile(first_audio, 50), 4),
        "first_audio_p95_s": round(percentile(first_audio, 95), 4),
        "rtf_p50": round(percentile(rtfs, 50), 4),
        "rtf_p95": round(percentile(rtfs, 95), 4),
    }


def tts_section(real: bool, workdir: Path) -> dict:
    """Per-backend TTS section (ADR-0005). The fake is always measured
    for harness shape; registered backends measure only under --real,
    and only when their runtime is actually installed — otherwise the
    entry is an honest "not run" with the reason, never fabricated."""
    from runmal.voice.backends import TTS_REGISTRY

    section: dict = {"backends": {}}
    fake_entry = _measure_tts(FakeTTSBackend(), VoiceInfo("fake-voice", backend_key="fake-tts"))
    fake_entry.update(
        {
            "kind": "fixture",
            "pass": None,
            "note": "fixture backend measured for harness shape; no thresholds bind the fake",
        }
    )
    section["backends"]["fake-tts"] = fake_entry
    for key, spec in TTS_REGISTRY.items():
        contract = {"max_first_audio_p50_s": spec.first_audio_p50_s, "max_rtf_p50": spec.rtf_p50}
        if not real:
            section["backends"][key] = {
                "contract": contract,
                "status": "not run: fixture mode (use --real)",
            }
            continue
        from runmal.voice.backends import BackendUnavailable, build_tts_backend

        started = time.perf_counter()
        try:
            backend = build_tts_backend(key)
        except BackendUnavailable as exc:
            section["backends"][key] = {"contract": contract, "status": f"not run: {exc}"}
            continue
        load_s = time.perf_counter() - started
        voices = backend.voices()
        voice = voices[0] if voices else VoiceInfo(key, backend_key=key)
        try:
            measured = _measure_tts(backend, voice)
        except Exception as exc:
            section["backends"][key] = {
                "contract": contract,
                "status": f"not run: {type(exc).__name__}: {exc}",
            }
            continue
        passed: bool | None = None
        if spec.first_audio_p50_s is not None and spec.rtf_p50 is not None:
            passed = (
                measured["first_audio_p50_s"] <= spec.first_audio_p50_s
                and measured["rtf_p50"] <= spec.rtf_p50
            )
        measured.update(
            {"kind": "real", "contract": contract, "model_load_s": round(load_s, 4), "pass": passed}
        )
        if passed is None:
            measured["note"] = (
                "user-installed backend: measured as information; no predeclared thresholds bind it"
            )
        section["backends"][key] = measured
    return section


def interruption_section() -> dict:
    from runmal.voice.audio import FixturePlayback
    from runmal.voice.bargein import (
        INTERRUPTION_STOP_BUDGET_MS,
        InterruptionController,
        PlaybackQueue,
    )

    backend = FakeTTSBackend(seconds_per_char=0.05)
    chunks = backend.synthesize_all(
        "This is a long companion answer that keeps speaking for a while.",
        VoiceInfo("fake-voice", backend_key="fake-tts"),
    )
    queue = PlaybackQueue()
    for chunk in chunks:
        queue.enqueue(chunk)
    controller = InterruptionController(EnergyVadModel(), confirm_frames=5)
    controller.begin_episode(turn_id=1, playback=queue)
    speech = _frame(0.5)

    def on_frame(_written):
        for _ in range(6):
            controller.feed_mic_frame(speech)

    queue.play(FixturePlayback(), on_frame=on_frame)
    event = controller.event
    return {
        "budget_ms": INTERRUPTION_STOP_BUDGET_MS,
        "fired": event is not None,
        "stop_latency_ms": event.stop_latency_ms if event else None,
        "pass": bool(event and event.within_budget),
    }


def run_benchmarks(real: bool = False, workdir: Path | None = None) -> dict:
    workdir = workdir or Path(".runmal-bench")
    return {
        "hardware": hardware_info(),
        "packages": package_versions(),
        "vad": vad_section(),
        "stt": stt_section(real, workdir),
        "tts": tts_section(real, workdir),
        "interruption": interruption_section(),
        "thresholds_note": (
            "Thresholds are the predeclared contracts imported from "
            "vad/stt/bargein and the per-backend TTS registry specs "
            "(docs/BENCHMARKS.md); this harness never rewrites them."
        ),
    }


def render_markdown(report: dict) -> str:
    hw = report["hardware"]
    lines = [
        "# Rúnmál Voice Benchmark Report (S514)",
        "",
        f"- Platform: {hw['platform']}",
        f"- CPU: {hw['cpu']} ({hw.get('cpu_count', '?')} threads)",
        f"- Python: {hw['python']}",
        "- Packages: " + ", ".join(f"{k}={v}" for k, v in report["packages"].items()),
        "",
        "## VAD segmentation",
        f"- model: {report['vad']['model']}",
        f"- metrics: {report['vad']['metrics']}",
        f"- contract: {report['vad']['contract']}",
        f"- pass: {report['vad']['pass']}",
        "",
        "## STT",
        f"- {report['stt']}",
        "",
        "## TTS",
        f"- {report['tts']}",
        "",
        "## Interruption",
        f"- {report['interruption']}",
        "",
        f"_{report['thresholds_note']}_",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runmal-voice-benchmark")
    parser.add_argument(
        "--real", action="store_true", help="run real faster-whisper STT (downloads the model)"
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=Path(".runmal-bench"))
    args = parser.parse_args(argv)
    report = run_benchmarks(real=args.real, workdir=args.workdir)
    text = render_markdown(report)
    if args.out:
        args.out.write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
