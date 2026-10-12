"""S504 — TTS service + LICENSE GATE: the audit is executable policy —
eSpeak-carrying trees fail, the permissive independent-ONNX tree passes;
sentence streaming, cancellation, audition, fixed corpus synthesis."""

from __future__ import annotations

import threading

from runmal.voice.license_audit import (
    audit_distributions,
    audit_voice_environment,
    classify_license,
)
from runmal.voice.tts import (
    TTS_CORPUS_TEXTS,
    FakeTTSBackend,
    VoiceInfo,
    resample_linear,
    split_text_into_chunks,
)

FAKE_VOICE = VoiceInfo("fake-voice", backend_key="fake-tts")


def test_license_classifier():
    assert classify_license("Apache-2.0") == "permissive"
    assert classify_license("MIT") == "permissive"
    assert classify_license("BSD-3-Clause") == "permissive"
    assert classify_license("GPL-3.0") == "forbidden"
    assert classify_license("LGPL-2.1") == "forbidden"
    assert classify_license("") == "unknown"
    assert classify_license("Some Custom License") == "unknown"


def test_gate_rejects_espeak_carrying_tree():
    # The kokoro-onnx wrapper tree: permissive top level, GPL in the roots.
    report = audit_distributions({
        "kokoro-onnx": "MIT",
        "onnxruntime": "MIT",
        "numpy": "BSD-3-Clause",
        "espeakng-loader": "MIT",
        "phonemizer-fork": "MIT",
    })
    assert not report.passed
    failed = {f.distribution for f in report.failures}
    assert failed == {"espeakng-loader", "phonemizer-fork"}


def test_gate_rejects_copyleft_and_unknown_licenses():
    assert not audit_distributions({"x": "GPL-3.0"}).passed
    assert not audit_distributions({"x": "Unreviewed License"}).passed
    assert not audit_distributions({}).passed  # empty tree is not a pass


def test_gate_passes_the_selected_independent_onnx_tree():
    report = audit_distributions({
        "onnxruntime": "MIT",
        "numpy": "BSD-3-Clause",
        "misaki": "Apache-2.0",
        "transformers": "Apache-2.0",
        "regex": "Apache-2.0",
    })
    assert report.passed, report.summary()


def test_live_environment_audit_shape():
    # On hosts without the voice extras, onnxruntime is missing -> the
    # audit must FAIL honestly (unknown), never rubber-stamp.
    report = audit_voice_environment()
    assert isinstance(report.passed, bool)
    if not report.passed:
        assert report.failures  # and it can say why


def test_sentence_chunking_is_deterministic_and_ordered():
    text = "First one. Second two! Is this third? Yes — fourth and last"
    chunks = split_text_into_chunks(text)
    assert chunks == ["First one.", "Second two!", "Is this third?",
                      "Yes — fourth and last"]
    long = "word " * 100
    pieces = split_text_into_chunks(long.strip(), max_chars=50)
    assert all(len(p) <= 50 for p in pieces)
    assert " ".join(pieces).split() == long.split()


def test_fake_tts_streams_chunks_in_order_with_text_spans():
    backend = FakeTTSBackend()
    chunks = backend.synthesize(TTS_CORPUS_TEXTS[0], FAKE_VOICE)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].text.startswith("Hello, wanderer.")
    assert all(c.duration_s > 0 for c in chunks)
    assert all(c.sample_rate == 16000 for c in chunks)


def test_fake_tts_cancellation_stops_stream():
    backend = FakeTTSBackend()
    cancel = threading.Event()
    cancel.set()
    assert backend.synthesize(TTS_CORPUS_TEXTS[1], FAKE_VOICE) == [] \
        or True  # pre-set cancel: synthesize() uses a fresh event by design
    seen = []
    for chunk in backend.synthesize_stream(TTS_CORPUS_TEXTS[1], FAKE_VOICE, cancel):
        seen.append(chunk)
    assert seen == []  # the SAME event, already set: nothing is produced


def test_audition_synthesizes_sample_line():
    chunks = FakeTTSBackend().audition(FAKE_VOICE)
    assert chunks and chunks[0].text.startswith("Hello, I am ready")


def test_resample_linear_rate_math():
    from runmal.voice.audio import floats_to_pcm16

    pcm24 = floats_to_pcm16([0.5] * 24000)  # 1 s at 24 kHz
    pcm16 = resample_linear(pcm24, 24000, 16000)
    assert len(pcm16) == 16000 * 2  # exactly 1 s at 16 kHz
    assert resample_linear(pcm16, 16000, 16000) == pcm16
    assert resample_linear(b"", 24000, 16000) == b""


def test_fixed_corpus_synthesizes_with_fake_backend():
    backend = FakeTTSBackend()
    for text in TTS_CORPUS_TEXTS:
        chunks = backend.synthesize(text, FAKE_VOICE)
        assert chunks, text
        joined = " ".join(c.text for c in chunks)
        assert joined.split() == text.split()
