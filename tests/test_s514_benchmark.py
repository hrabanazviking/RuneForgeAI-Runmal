"""S514 — Voice benchmark harness: reproducible report with hardware,
versions, models, p50/p95; thresholds are imported, never rewritten."""

from __future__ import annotations

from runmal.voice import benchmark as bench
from runmal.voice.bargein import INTERRUPTION_STOP_BUDGET_MS
from runmal.voice.stt import STT_CONTRACT
from runmal.voice.tts import TTS_CONTRACT
from runmal.voice.vad import SEGMENTATION_CONTRACT


def test_report_has_all_sections_and_provenance(tmp_path):
    report = bench.run_benchmarks(real=False, workdir=tmp_path)
    assert report["hardware"]["python"]
    assert report["hardware"]["platform"]
    assert "faster-whisper" in report["packages"]
    for section in ("vad", "stt", "tts", "interruption"):
        assert section in report
    # Fixture STT is labeled honestly as fixture-only, not dressed as real.
    assert "fixture" in report["stt"]["status"]


def test_vad_section_scores_against_predeclared_contract(tmp_path):
    report = bench.run_benchmarks(real=False, workdir=tmp_path)
    assert report["vad"]["contract"] == SEGMENTATION_CONTRACT
    assert report["vad"]["pass"] is True
    assert report["vad"]["metrics"]["recall"] >= SEGMENTATION_CONTRACT["min_recall"]


def test_interruption_section_meets_predeclared_budget(tmp_path):
    report = bench.run_benchmarks(real=False, workdir=tmp_path)
    section = report["interruption"]
    assert section["budget_ms"] == INTERRUPTION_STOP_BUDGET_MS == 100
    assert section["fired"] and section["pass"]
    assert section["stop_latency_ms"] <= 100


def test_thresholds_are_the_imported_constants_not_copies(tmp_path):
    report = bench.run_benchmarks(real=False, workdir=tmp_path)
    assert report["stt"]["contract"]["max_wer"] == STT_CONTRACT["max_wer"]
    assert report["tts"]["contract"]["max_first_audio_p50_s"] == \
        TTS_CONTRACT["max_first_audio_p50_s"]
    # Running the harness must not mutate the contracts.
    assert STT_CONTRACT["max_wer"] == 0.25
    assert SEGMENTATION_CONTRACT["min_recall"] == 0.90


def test_markdown_render_records_everything(tmp_path):
    report = bench.run_benchmarks(real=False, workdir=tmp_path)
    text = bench.render_markdown(report)
    for needle in ("CPU:", "Python:", "VAD", "STT", "TTS", "Interruption",
                   "never rewrites"):
        assert needle in text


def test_cli_writes_report_file(tmp_path):
    out = tmp_path / "report.md"
    rc = bench.main(["--out", str(out), "--workdir", str(tmp_path / "work")])
    assert rc == 0
    assert "Voice Benchmark Report" in out.read_text()
