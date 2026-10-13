"""STT backend registry (ADR-0006): the ear is multi-backend too.

Mirrors the TTS registry (ADR-0005) under Volmarr's interoperability
principle: Rúnmál **ships** faster-whisper (small, int8 — the
laptop-verified default ear, contract in :mod:`runmal.voice.stt`),
and **registers** the well-known field as user-downloadable extras.
Each extra installs ONLY through the user's explicit one-button
action (:mod:`runmal.voice.install`); its per-backend audit verdict
displays as information and never blocks a user-chosen backend;
entries the forge has not real-model-verified carry the honest label
``user-installed — not forge-verified``.

Acceptance scope for the Campaign V landing: the registry + install
machinery + audit display proven end-to-end, the default backend
fully verified, and the mechanism proven with distil-whisper (same
faster-whisper runtime, a different model download). The remaining
extras ship registered-but-unverified with ``enable=False`` plans —
there is no code path that installs them until the forge ships a
verified recipe for each.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.voice.backends import BackendUnavailable
from runmal.voice.install import InstallPlan, vendor_dir
from runmal.voice.stt import FakeSTTBackend, FasterWhisperSTT, STTBackend


@dataclass(frozen=True)
class STTBackendSpec:
    key: str
    display_name: str
    default_shipped: bool
    verified: bool
    plan: InstallPlan
    tree_packages: tuple[str, ...] = ()


def _plan(key: str, **kw) -> InstallPlan:
    return InstallPlan(key=key, kind="stt", **kw)


def _registered(key: str, name: str, note: str) -> STTBackendSpec:
    """A registered-but-unverified extra: visible in settings, honest
    label, NO install recipe yet (the button explains; nothing runs)."""
    return STTBackendSpec(
        key=key,
        display_name=name,
        default_shipped=False,
        verified=False,
        plan=_plan(key, enable=False, probe_import="", note=note),
    )


STT_REGISTRY: dict[str, STTBackendSpec] = {
    "faster-whisper": STTBackendSpec(
        key="faster-whisper",
        display_name="faster-whisper (Whisper small, int8)",
        default_shipped=True,
        verified=True,
        plan=_plan(
            "faster-whisper",
            probe_import="faster_whisper",
            note="Default shipped ear. Forge-verified on "
            "purplelongship: WER 0.1111, RTF p50 0.8362.",
        ),
        tree_packages=("faster-whisper", "ctranslate2", "tokenizers", "onnxruntime"),
    ),
    "distil-whisper": STTBackendSpec(
        key="distil-whisper",
        display_name="Distil-Whisper (via faster-whisper)",
        default_shipped=False,
        verified=True,
        plan=_plan(
            "distil-whisper",
            probe_import="faster_whisper",
            warmup="runmal.voice.stt_backends:warm_distil_model",
            note="Same verified faster-whisper runtime; the "
            "one-button action downloads the distil-small.en "
            "model. The mechanism-proof extra for ADR-0006.",
        ),
        tree_packages=("faster-whisper", "ctranslate2", "tokenizers", "onnxruntime"),
    ),
    "whisper-cpp": _registered(
        "whisper-cpp",
        "whisper.cpp",
        "Registered — forge has not yet shipped a verified build "
        "recipe for the whisper.cpp binary + ggml models.",
    ),
    "openai-whisper": _registered(
        "openai-whisper",
        "OpenAI Whisper (reference implementation)",
        "Registered — reference PyTorch implementation; recipe not yet forge-verified.",
    ),
    "moonshine": _registered(
        "moonshine",
        "Moonshine",
        "Registered — Useful Sensors' Moonshine models; recipe not yet forge-verified.",
    ),
    "parakeet": _registered(
        "parakeet",
        "NVIDIA Parakeet",
        "Registered — NeMo toolkit tree is large; recipe not yet forge-verified.",
    ),
    "canary": _registered(
        "canary",
        "NVIDIA Canary",
        "Registered — NeMo toolkit tree is large; recipe not yet forge-verified.",
    ),
    "vosk": _registered(
        "vosk",
        "Vosk",
        "Registered — Kaldi-based offline recognizer; recipe not yet forge-verified.",
    ),
    "sherpa-onnx-stt": _registered(
        "sherpa-onnx-stt",
        "sherpa-ONNX STT models",
        "Registered — note the sherpa-ONNX runtime also bundles "
        "eSpeak-NG data for its TTS paths; audit-at-install will "
        "judge the real tree. Recipe not yet forge-verified.",
    ),
    "silero-stt": _registered(
        "silero-stt",
        "Silero STT",
        "Registered — torch-based models; recipe not yet forge-verified.",
    ),
}

#: The default STT backend when the user has not chosen one.
DEFAULT_STT_BACKEND = "faster-whisper"

KNOWN_STT_BACKENDS: tuple[str, ...] = tuple(STT_REGISTRY) + ("fake-stt",)


class DistilWhisperSTT(FasterWhisperSTT):
    """distil-whisper's distil-small.en served by the verified
    faster-whisper runtime — the one-button mechanism-proof extra."""

    backend_key = "distil-whisper"

    def __init__(self, model_size: str = "distil-small.en", **kwargs):
        super().__init__(model_size=model_size, **kwargs)


def build_stt_backend(key: str, **kwargs) -> STTBackend:
    """Construct the backend for ``key`` or raise BackendUnavailable."""
    if key == "fake-stt":
        return FakeSTTBackend()
    if key == "faster-whisper":
        try:
            return FasterWhisperSTT(**kwargs)
        except RuntimeError as exc:
            raise BackendUnavailable(str(exc)) from exc
    if key == "distil-whisper":
        try:
            return DistilWhisperSTT(**kwargs)
        except RuntimeError as exc:
            raise BackendUnavailable(str(exc)) from exc
    if key in STT_REGISTRY:
        raise BackendUnavailable(
            f"STT backend '{key}' is registered but not forge-verified — "
            "it has no install recipe yet and cannot be selected."
        )
    raise BackendUnavailable(f"unknown STT backend '{key}'")


def warm_distil_model() -> None:
    """Download distil-small.en through faster-whisper's own verified
    path into the vendor models dir (the one-button mechanism proof)."""
    DistilWhisperSTT(cache_dir=str(vendor_dir() / "models"))
