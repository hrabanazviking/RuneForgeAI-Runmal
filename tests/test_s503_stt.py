"""S503 — STT service: seam, fake backend, WER math, benchmark hook, and a
tagged-optional real faster-whisper run against the fixed flite corpus
under the PREDECLARED STT_CONTRACT thresholds."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from runmal.voice.audio import floats_to_pcm16
from runmal.voice.corpus import CORPUS_TEXTS, build_flite_corpus
from runmal.voice.stt import (
    STT_CONTRACT,
    CorpusItem,
    FakeSTTBackend,
    FasterWhisperSTT,
    benchmark_stt,
    word_error_rate,
)


def test_fake_backend_tiles_word_timestamps_over_duration():
    backend = FakeSTTBackend("one two three four")
    transcript = backend.transcribe(floats_to_pcm16([0.0] * 16000))  # 1 s
    assert transcript.text == "one two three four"
    assert len(transcript.words) == 4
    assert transcript.words[0].start_s == 0.0
    assert transcript.words[-1].end_s == pytest.approx(1.0)
    assert backend.model_info().supports_word_timestamps
    assert backend.health_check()


def test_wer_exact_values():
    assert word_error_rate("hello world", "hello world") == 0.0
    assert word_error_rate("hello world", "hello there world") == 0.5
    assert word_error_rate("the cat sat", "the dog sat") == pytest.approx(1 / 3)
    assert word_error_rate("Hello, World!", "hello world") == 0.0
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "ghost") == 1.0


def test_benchmark_hook_aggregates_honestly():
    backend = FakeSTTBackend("hello world this is a test of the voice system")
    pcm = floats_to_pcm16([0.0] * 32000)
    result = benchmark_stt(backend, [CorpusItem("greeting", pcm, CORPUS_TEXTS[0][1])])
    assert result.wer == 0.0
    assert result.items[0]["words"] == 10
    assert result.meets_contract() == {"wer": True, "rtf_p50": True}
    bad = benchmark_stt(FakeSTTBackend("totally different words here"),
                        [CorpusItem("greeting", pcm, CORPUS_TEXTS[0][1])])
    assert bad.wer > STT_CONTRACT["max_wer"]
    assert bad.meets_contract()["wer"] is False


def _real_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _real_whisper_available(),
                    reason="tagged optional: faster-whisper/ffmpeg not installed")
def test_real_faster_whisper_meets_predeclared_contract(tmp_path: Path):
    corpus = build_flite_corpus(tmp_path)
    assert len(corpus) == len(CORPUS_TEXTS)
    backend = FasterWhisperSTT("small", cache_dir=tmp_path / "models")
    result = benchmark_stt(backend, corpus)
    contract = result.meets_contract()
    assert contract["wer"], f"WER {result.wer:.3f} over contract; items={result.items}"
    assert contract["rtf_p50"], f"RTF p50 {result.rtf_p50:.3f} over contract"
    transcript_words = sum(item["words"] for item in result.items)
    assert transcript_words > 0  # word timestamps actually produced output
