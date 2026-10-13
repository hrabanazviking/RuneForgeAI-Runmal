"""S504 — TTS service seam + PER-BACKEND LICENSE GATE (ADR-0005).

The audit is executable policy over each backend's OWN tree:
eSpeak-carrying trees fail, permissive trees pass. The gate BINDS
only the default shipped tree (CosyVoice + Chatterbox + the base
voice tree); user-installed backends (Kitten, Piper) get their
verdict displayed as information, never as a block. Plus the registry
model (admission classes, curated --no-deps install sets, PREDECLARED
thresholds), the pyproject↔curated-set drift guard, fail-closed
backend construction, sentence streaming, cancellation, audition,
and fixed-corpus synthesis.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

from runmal.voice.license_audit import (
    audit_distributions,
    audit_snapshot,
    classify_license,
)
from runmal.voice.tts import (
    TTS_CORPUS_TEXTS,
    FakeTTSBackend,
    VoiceInfo,
    split_text_into_chunks,
)

FAKE_VOICE = VoiceInfo("fake-voice", backend_key="fake-tts")


# ------------------------------------------------------------ the gate

def test_license_classifier():
    assert classify_license("Apache-2.0") == "permissive"
    assert classify_license("MIT") == "permissive"
    assert classify_license("BSD-3-Clause") == "permissive"
    assert classify_license("GPL-3.0") == "forbidden"
    assert classify_license("LGPL-2.1") == "forbidden"
    assert classify_license("") == "unknown"
    assert classify_license("Some Custom License") == "unknown"


def test_gate_rejects_espeak_carrying_tree():
    # The removed Kokoro wrapper tree: permissive top level, GPL in
    # the roots — exactly why Kokoro could never ship (ADR-0005).
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


def test_gate_passes_a_permissive_backend_tree():
    report = audit_distributions({
        "onnxruntime": "MIT",
        "numpy": "BSD-3-Clause",
        "transformers": "Apache-2.0",
        "safetensors": "Apache-2.0",
        "regex": "Apache-2.0",
    })
    assert report.passed, report.summary()


def test_gate_binds_only_the_default_shipped_tree():
    # A user-installed tree may legitimately contain forbidden
    # carriers (Kitten phonemizes via eSpeak-NG): the audit still
    # computes its verdict honestly — FAIL — and that verdict is
    # information for the user's own choice...
    user_tree = audit_snapshot({
        "kittentts": "Apache-2.0", "espeakng-loader": "MIT"})
    assert not user_tree.passed
    assert user_tree.violations  # ...with reasons the UI can display
    assert user_tree.checked == 2
    # ...while the default shipped tree is judged on its OWN contents
    # and must pass on them alone.
    default_tree = audit_snapshot({
        "numpy": "BSD-3-Clause", "onnxruntime": "MIT",
        "transformers": "Apache-2.0", "safetensors": "Apache-2.0"})
    assert default_tree.passed, default_tree.summary()


# ------------------------------------------------------------ registry

def test_declared_license_reads_expression_not_full_text():
    # PEP 639: the SPDX expression wins; a full license BODY in the
    # License field is not an expression and must never be classified
    # (an MIT body would read unknown; a PSF body mentioning GPL in
    # prose would read forbidden — both are reader artifacts).
    from email.message import Message

    from runmal.voice.license_audit import _declared_license

    pep639 = Message()
    pep639["License-Expression"] = "MIT"
    pep639["License"] = "MIT License\n\nCopyright (c) someone\n\nPermission..."
    assert _declared_license(pep639) == "MIT"

    full_text_only = Message()
    full_text_only["License"] = (
        "Copyright (c) someone\n\nPermission is hereby granted, free "
        "of charge, to any person obtaining a copy of this software "
        "and associated documentation files, without restriction...")
    assert _declared_license(full_text_only) == ""

    classifier_fallback = Message()
    classifier_fallback["Classifier"] = \
        "License :: OSI Approved :: Apache Software License"
    assert _declared_license(classifier_fallback) == "Apache Software License"

    short_form = Message()
    short_form["License"] = "BSD-3-Clause"
    assert _declared_license(short_form) == "BSD-3-Clause"

    # A license BODY headed by its short expression: the first line
    # is the declaration (tiktoken's wheel is shaped exactly so).
    headed_body = Message()
    headed_body["License"] = (
        "MIT License\n\nCopyright (c) 2023\n\nPermission is hereby "
        "granted, free of charge, to any person obtaining a copy of "
        "this software and associated documentation files...")
    assert _declared_license(headed_body) == "MIT License"

    # A prose heading is NOT an expression: classifiers still win
    # (matplotlib's wheel is shaped exactly so).
    prose_headed = Message()
    prose_headed["License"] = (
        "License agreement for matplotlib versions 1.3.0 and later\n"
        "=========================================================\n"
        " 1. This LICENSE AGREEMENT is between the Matplotlib "
        "Development Team ...")
    prose_headed["Classifier"] = \
        "License :: OSI Approved :: Python Software Foundation License"
    assert _declared_license(prose_headed) == \
        "Python Software Foundation License"


def test_registry_tree_packages_scope_each_backend():
    from runmal.voice.backends import TTS_REGISTRY

    cosy = set(TTS_REGISTRY["cosyvoice"].tree_packages)
    chat = set(TTS_REGISTRY["chatterbox"].tree_packages)
    assert "torch" in cosy and "torch" in chat
    assert "transformers" in cosy and "transformers" in chat
    assert "resemble-perth" in chat
    assert "pykakasi" not in chat and "misaki" not in cosy | chat
    assert set(TTS_REGISTRY["kitten"].tree_packages) == {"kittentts", "soundfile"}
    assert set(TTS_REGISTRY["piper"].tree_packages) == {"piper-tts"}

def test_registry_admission_classes_and_defaults():
    from runmal.voice.backends import (
        DEFAULT_TTS_BACKEND,
        KNOWN_TTS_BACKENDS,
        TTS_REGISTRY,
    )

    assert DEFAULT_TTS_BACKEND == "cosyvoice"
    assert TTS_REGISTRY["cosyvoice"].default_shipped
    assert TTS_REGISTRY["chatterbox"].default_shipped
    assert not TTS_REGISTRY["kitten"].default_shipped
    assert not TTS_REGISTRY["piper"].default_shipped
    assert set(KNOWN_TTS_BACKENDS) == {
        "cosyvoice", "chatterbox", "kitten", "piper", "fake-tts"}
    assert "kokoro-onnx" not in KNOWN_TTS_BACKENDS  # removed, ADR-0005


def test_predeclared_thresholds_are_the_benchmarks_md_values():
    # Declared in docs/BENCHMARKS.md on 2026-10-13 BEFORE measurement;
    # a failed benchmark is evidence — these are never rewritten to pass.
    from runmal.voice.backends import TTS_REGISTRY

    assert TTS_REGISTRY["cosyvoice"].first_audio_p50_s == 1.5
    assert TTS_REGISTRY["cosyvoice"].rtf_p50 == 1.0
    assert TTS_REGISTRY["chatterbox"].first_audio_p50_s == 4.0
    assert TTS_REGISTRY["chatterbox"].rtf_p50 == 1.0
    # User-installed backends carry no binding thresholds.
    assert TTS_REGISTRY["kitten"].first_audio_p50_s is None
    assert TTS_REGISTRY["piper"].rtf_p50 is None


def test_chatterbox_curated_set_excludes_pykakasi_and_gradio():
    from runmal.voice.backends import CHATTERBOX_PACKAGES

    names = {re.split(r"[<>=!~ @\[]", p, maxsplit=1)[0].lower()
             for p in CHATTERBOX_PACKAGES}
    assert "pykakasi" not in names  # GPL-3.0, Japanese-only path
    assert "gradio" not in names  # demo UI only
    assert "chatterbox-tts" in names


def test_cosyvoice_install_never_touches_the_pypi_namesquat():
    from runmal.voice.backends import (
        COSYVOICE_COMMIT,
        COSYVOICE_GIT,
        TTS_REGISTRY,
    )

    plan = TTS_REGISTRY["cosyvoice"].plan
    # The runtime comes ONLY from the pinned FunAudioLLM git checkout;
    # PyPI 'cosyvoice' 0.0.8 is an unrelated GPL-claiming name-squat.
    assert plan.git_checkout == (COSYVOICE_GIT, COSYVOICE_COMMIT, "CosyVoice")
    assert COSYVOICE_COMMIT.startswith("074ca6dc")
    pip_names = {p.split("==")[0].split(">=")[0].lower()
                 for p in plan.pip_packages}
    assert "cosyvoice" not in pip_names
    assert "ttsfrd" not in pip_names  # proprietary frontend never ships


def _pyproject_extra(name: str) -> list[str]:
    text = Path("pyproject.toml").read_text()
    block = text.split(f"{name} = [", 1)[1].split("]", 1)[0]
    return re.findall(r'"([^"]+)"', block)


def test_pyproject_extras_mirror_curated_install_sets():
    # Drift guard: the declared extras and install.py's curated sets
    # are two writings of one list — they may never silently diverge.
    # Wheel tags (cp312/cp313) follow the running interpreter in the
    # registry sets and are pinned to cp312 in pyproject; normalize
    # the tag before comparing so only real divergence fails.
    from runmal.voice.backends import CHATTERBOX_PACKAGES, COSYVOICE_PACKAGES

    def norm(entries):
        return [re.sub(r"cp3\d+", "cp3XX", e) for e in entries]

    assert norm(_pyproject_extra("voice-cosyvoice")) == \
        norm(list(COSYVOICE_PACKAGES))
    assert norm(_pyproject_extra("voice-chatterbox")) == \
        norm(list(CHATTERBOX_PACKAGES))
    assert not any("misaki" in entry for entry in _pyproject_extra("voice"))


def test_cosyvoice_set_excludes_librosa_and_uses_cpu_torch():
    # librosa's presence makes transformers 5.x hard-import soxr
    # (LGPL-2.1-or-later) — and the CosyVoice runtime never imports
    # librosa (grep evidence, 2026-10-13). CUDA torch's nvidia-*
    # companions declare no license metadata; CPU builds are BSD-3.
    from runmal.voice.backends import COSYVOICE_PACKAGES

    names = {re.split(r"[<>=!~ @\[]", p, maxsplit=1)[0].lower()
             for p in COSYVOICE_PACKAGES}
    assert "librosa" not in names and "soxr" not in names
    torch_refs = [p for p in COSYVOICE_PACKAGES if p.startswith("torch @")]
    assert torch_refs and "%2Bcpu" in torch_refs[0]
    assert "modelscope==1.32.0" in COSYVOICE_PACKAGES


def test_chatterbox_held_fail_closed_at_admission():
    # Admission evidence (purplelongship, 2026-10-13): its pinned
    # tree needs soxr (LGPL-2.1-or-later) — the plan refuses to run
    # until Volmarr rules. The backend stays registered and visible.
    from runmal.voice.backends import TTS_REGISTRY

    plan = TTS_REGISTRY["chatterbox"].plan
    assert TTS_REGISTRY["chatterbox"].default_shipped  # class by ruling
    assert plan.enable is False
    assert "soxr" in plan.note and "LGPL" in plan.note


def test_classifier_recognizes_attested_permissive_spellings():
    # Setuptools-era spellings and SPDX compounds of licenses the
    # policy already accepts (purplelongship real-tree evidence).
    assert classify_license("Apache 2.0 License") == "permissive"
    assert classify_license("BSD 3-Clause License") == "permissive"
    assert classify_license("3-Clause BSD License") == "permissive"
    assert classify_license("Public Domain") == "permissive"
    assert classify_license("Apache-2.0 AND CNRI-Python") == "permissive"
    assert classify_license(
        "BSD-2-Clause AND Apache-2.0 WITH LLVM-exception") == "permissive"
    # Compounds never launder a forbidden component, and OR stays a
    # human-review question.
    assert classify_license("MIT AND GPL-3.0") == "forbidden"
    assert classify_license("LGPL-2.1-or-later") == "forbidden"
    assert classify_license("MIT OR GPL-3.0") == "forbidden"
    assert classify_license("Apache-2.0 OR Proprietary") == "unknown"


# ------------------------------------------------------- fail-closed

def test_unknown_backend_fails_closed_and_fake_fallback_is_explicit():
    from runmal.voice.backends import (
        BackendUnavailable,
        build_tts_backend,
        resolve_tts_backend,
    )

    with pytest.raises(BackendUnavailable):
        build_tts_backend("no-such-backend")
    with pytest.raises(BackendUnavailable):
        resolve_tts_backend("no-such-backend")  # no silent degradation
    fake = resolve_tts_backend("no-such-backend", fallback_fake=True)
    assert isinstance(fake, FakeTTSBackend)  # only when asked, loudly


def test_real_backends_fail_closed_when_runtime_absent(tmp_path, monkeypatch):
    import importlib.util

    from runmal.voice.backends import BackendUnavailable, build_tts_backend

    monkeypatch.setenv("RUNMAL_VENDOR_DIR", str(tmp_path / "vendor"))
    with pytest.raises(BackendUnavailable):
        build_tts_backend("cosyvoice")  # no vendor checkout -> refuse
    for key, module in (("chatterbox", "chatterbox"),
                        ("kitten", "kittentts"), ("piper", "piper")):
        if importlib.util.find_spec(module) is not None:
            continue  # runtime installed: the evidence path, not this test
        with pytest.raises(BackendUnavailable):
            build_tts_backend(key)


# ------------------------------------------------------------ the seam

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
    chunks = backend.synthesize_all(TTS_CORPUS_TEXTS[0], FAKE_VOICE)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].text.startswith("Hello, wanderer.")
    assert all(c.duration_s > 0 for c in chunks)
    assert all(c.sample_rate == 16000 for c in chunks)
    assert all(not c.is_final for c in chunks)  # content chunks only
    # The generator form yields the identical stream.
    assert list(backend.synthesize(TTS_CORPUS_TEXTS[0], FAKE_VOICE)) == chunks


def test_fake_tts_identity_and_voices():
    backend = FakeTTSBackend()
    assert backend.backend_key == backend.name == "fake-tts"
    assert backend.model_info().backend_key == "fake-tts"
    assert backend.voices()[0].voice_id == "fake-voice"


def test_fake_tts_cancellation_stops_stream():
    backend = FakeTTSBackend()
    cancel = threading.Event()
    cancel.set()
    seen = list(backend.synthesize_stream(TTS_CORPUS_TEXTS[1], FAKE_VOICE, cancel))
    assert seen == []  # pre-set event: nothing is produced


def test_fake_tts_cancellation_stops_mid_stream():
    backend = FakeTTSBackend()
    cancel = threading.Event()
    stream = backend.synthesize_stream(TTS_CORPUS_TEXTS[1], FAKE_VOICE, cancel)
    first = next(stream)
    assert first.index == 0
    cancel.set()
    assert list(stream) == []  # INV-003: production stops promptly


def test_audition_synthesizes_sample_line():
    chunks = FakeTTSBackend().audition(FAKE_VOICE)
    assert chunks and chunks[0].text.startswith("Hello, I am ready")


def test_fixed_corpus_synthesizes_with_fake_backend():
    backend = FakeTTSBackend()
    for text in TTS_CORPUS_TEXTS:
        chunks = backend.synthesize_all(text, FAKE_VOICE)
        assert chunks, text
        joined = " ".join(c.text for c in chunks)
        assert joined.split() == text.split()
