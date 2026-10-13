"""TTS backend registry (ADR-0005): multi-backend, user-selectable.

Rúnmál is not locked to one speech engine. This registry is the
single place that knows the TTS backends, their install plans, and
their admission class:

* ``default_shipped`` — CosyVoice (admitted; Chatterbox is
  default-class by ruling but HELD at admission — its pinned tree
  requires soxr, LGPL-2.1-or-later, via librosa/transformers; see
  the registry note). Their trees are part of what Rúnmál ships;
  the S504 gate binds them (the default shipped tree must audit
  green).
* ``user_installed`` — Kitten and Piper. Adapter code ships (it is
  ours, Apache-2.0); the engines install ONLY through the user's
  explicit one-button action (:mod:`runmal.voice.install`), carry the
  honest user-install notice, and their audit verdicts display as
  information — never as a block (Volmarr's policy-scope ruling,
  2026-10-13).

Kokoro is REMOVED from the product: the misaki → espeakng-loader /
phonemizer-fork chain (GPL-3.0 eSpeak-NG) can never pass the gate,
and better engines exist (docs/TTS_ENGINE_SURVEY.md).

Every adapter sits behind the :class:`~runmal.voice.tts.TTSBackend`
seam and refuses to construct — :class:`BackendUnavailable` — when
its runtime is not installed, so no code path ever silently installs
or silently falls back.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from runmal.voice.install import InstallPlan, vendor_dir
from runmal.voice.tts import AudioChunk, FakeTTSBackend, TTSBackend, VoiceInfo, split_text_into_chunks


class BackendUnavailable(RuntimeError):
    """The backend's runtime is not installed (install is a user act)."""


#: PerTh watermark library pinned to a fixed commit (survey finding:
#: upstream chatterbox-tts leaves resemble-perth unpinned).
PERTH_GIT = "https://github.com/resemble-ai/Perth"
PERTH_COMMIT = "ff1c8ac55a976971245cdd53c18d6131ca00d993"

#: CosyVoice upstream pinned commit (FunAudioLLM/CosyVoice).
COSYVOICE_GIT = "https://github.com/FunAudioLLM/CosyVoice"
COSYVOICE_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"

#: Curated pip set for Chatterbox — its full Requires-Dist MINUS
#: ``pykakasi==2.3.0`` (GPL-3.0, Japanese-only path, never imported by
#: the English pipeline) and minus ``gradio`` (demo UI only). Installed
#: with --no-deps so nothing unlisted can enter the tree. Mirrors the
#: ``voice-chatterbox`` extra in pyproject.toml (a test guards drift).
#: NOTE: the set is a faithful record of the backend's tree, but the
#: plan is HELD (enable=False) — see the registry note: librosa's
#: presence makes its pinned transformers import soxr (LGPL-2.1+).
CHATTERBOX_PACKAGES: tuple[str, ...] = (
    "chatterbox-tts==0.1.7",
    "numpy>=1.24,<2.0",
    "librosa==0.11.0",
    "s3tokenizer",
    "torch==2.6.0",
    "torchaudio==2.6.0",
    "transformers==5.2.0",
    "diffusers==0.29.0",
    f"resemble-perth @ git+{PERTH_GIT}@{PERTH_COMMIT}",
    "conformer==0.3.2",
    "safetensors==0.5.3",
    "spacy-pkuseg",
    "pyloudnorm",
    "omegaconf",
)

def _torch_cpu_refs() -> tuple[str, str]:
    """CPU builds of torch/torchaudio 2.6.0 as direct wheel URLs.

    The PyPI default builds are CUDA builds whose ``nvidia-*``
    companion wheels declare NO license metadata (audit: unknown —
    the tree could never pass) and do not run without them
    (libcudnn). The CPU builds are self-contained BSD-3 wheels.
    GPU torch stays available as a user's own install choice
    (interoperability principle). Wheel tags follow the RUNNING
    interpreter — the install machinery installs into the app env.
    """
    tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    base = "https://download.pytorch.org/whl/cpu"
    return (
        f"torch @ {base}/torch-2.6.0%2Bcpu-{tag}-{tag}-linux_x86_64.whl",
        f"torchaudio @ {base}/torchaudio-2.6.0%2Bcpu-{tag}-{tag}-linux_x86_64.whl",
    )


#: Curated pip set for CosyVoice — its upstream requirements MINUS the
#: proprietary ``ttsfrd`` (the open WeTextProcessing frontend ships
#: instead) and MINUS ``librosa`` (the runtime never imports it — grep
#: evidence, 2026-10-13 — and its mere presence makes transformers 5.x
#: hard-import ``soxr``; python-soxr declares LGPL-2.1-or-later,
#: forbidden in the shipped tree). The runtime itself comes from the
#: pinned git checkout. Mirrors the ``voice-cosyvoice`` extra in
#: pyproject.toml (a test guards drift).
COSYVOICE_PACKAGES: tuple[str, ...] = (
    "conformer",
    "diffusers",
    "HyperPyYAML",
    "inflect",
    "lightning",
    "matplotlib",
    # 1.32 is the last monolithic line: 1.40 splits the hub into
    # modelscope-hub, which requires `cryptography` (dual-license
    # SPDX expression outside the reviewed permissive set).
    "modelscope==1.32.0",
    "networkx",
    "numpy",
    "omegaconf",
    "onnxruntime",
    "protobuf",
    # Matcha-TTS (the vendored submodule) imports PIL on the flow path.
    "pillow",
    "pydantic",
    "rich",
    # Lazy-loaded by transformers when AutoModel reads the weights —
    # invisible to an import smoke test; the real build proved it.
    "safetensors",
    # cosyvoice/hifigan imports scipy.signal at module level on the
    # model-load path (proven by the real build on purplelongship).
    "scipy",
    "soundfile",
    "tensorboard",
    # Pinned to the version the closure was proven against: newer 5.x
    # raises its tokenizers floor past 0.22.1 (the newest tokenizers
    # transformers 5.2 accepts and faster-whisper's tree also allows).
    "transformers==5.2.0",
    "WeTextProcessing",
    "wget",
    "x-transformers",
    *_torch_cpu_refs(),
    # Proven dependency closure (purplelongship, 2026-10-13): the
    # upstream requirements name the direct packages only; these are
    # what the runtime actually imports, each one audit-passed.
    "einops",  # x-transformers
    "huggingface-hub>=1.3.0,<2.0",  # transformers 5.x constraint
    "tokenizers==0.22.1",  # transformers 5.x constraint (<=0.23.0)
    # Pinned <0.18: ruamel 0.18 changed the Loader API HyperPyYAML
    # composes (max_depth) — proven by the real build, 2026-10-13.
    "ruamel.yaml==0.17.21",  # HyperPyYAML
    "openai-whisper",  # cosyvoice.cli.frontend speech tokenizer
    "tiktoken",  # openai-whisper
    "more-itertools",  # openai-whisper / inflect
    "numba",  # openai-whisper
    "llvmlite",  # numba
    "pynini",  # WeTextProcessing runtime
    # HyperPyYAML's substrate (it composes PyYAML + ruamel at import).
    "pyyaml",
    "importlib_resources",  # WeTextProcessing runtime
    "regex",  # transformers
    "requests",  # modelscope / huggingface-hub
    "urllib3",  # requests / modelscope
    "charset-normalizer",  # requests
    "sympy",  # torch / transformers
    "mpmath",  # sympy
    "typeguard",  # inflect
)

#: Kitten TTS runtime wheel (user-installed only). KittenTTS is not on
#: PyPI; upstream distributes a wheel from its GitHub releases.
KITTEN_WHEEL = (
    "https://github.com/KittenML/KittenTTS/releases/download/0.8.1/"
    "kittentts-0.8.1-py3-none-any.whl"
)


def _dist_names(packages: tuple[str, ...]) -> tuple[str, ...]:
    """Distribution names for a curated pip set — the per-backend
    audit scope (``tree_packages``): the tree a backend ships is the
    set its install plan installs, judged on its own contents
    (ADR-0005 per-backend admission, mirroring the STT registry)."""
    names: list[str] = []
    for entry in packages:
        if " @ " in entry:  # direct reference: "name @ url"
            names.append(entry.split(" @ ", 1)[0].strip())
        elif "://" in entry:  # bare wheel URL
            names.append(entry.rsplit("/", 1)[-1].split("-")[0])
        else:
            names.append(re.split(r"[<>=!~\[]", entry, maxsplit=1)[0].strip())
    return tuple(names)


@dataclass(frozen=True)
class TTSBackendSpec:
    key: str
    display_name: str
    default_shipped: bool
    plan: InstallPlan
    #: Distributions the per-backend audit display scopes to.
    tree_packages: tuple[str, ...] = ()
    first_audio_p50_s: float | None = None  # predeclared (docs/BENCHMARKS.md)
    rtf_p50: float | None = None


def _plan(key: str, **kw) -> InstallPlan:
    return InstallPlan(key=key, kind="tts", **kw)


TTS_REGISTRY: dict[str, TTSBackendSpec] = {
    "cosyvoice": TTSBackendSpec(
        key="cosyvoice",
        display_name="CosyVoice 2 (0.5B)",
        default_shipped=True,
        plan=_plan(
            "cosyvoice",
            pip_packages=COSYVOICE_PACKAGES,
            git_checkout=(COSYVOICE_GIT, COSYVOICE_COMMIT, "CosyVoice"),
            probe_import="cosyvoice",
            warmup="runmal.voice.backends:warm_cosyvoice",
            note="Apache-2.0 code + weights; WeTextProcessing frontend (never ttsfrd).",
        ),
        tree_packages=_dist_names(COSYVOICE_PACKAGES),
        first_audio_p50_s=1.5,
        rtf_p50=1.0,
    ),
    "chatterbox": TTSBackendSpec(
        key="chatterbox",
        display_name="Chatterbox",
        default_shipped=True,
        plan=_plan(
            "chatterbox",
            pip_packages=CHATTERBOX_PACKAGES,
            probe_import="chatterbox",
            warmup="runmal.voice.backends:warm_chatterbox",
            enable=False,
            note="HELD at admission (purplelongship evidence, 2026-10-13): "
                 "chatterbox.tts imports librosa at module level, and its "
                 "own pinned transformers 5.2 hard-imports soxr whenever "
                 "librosa is present; python-soxr declares "
                 "LGPL-2.1-or-later — forbidden in the shipped tree. "
                 "Registered fail-closed until Volmarr rules "
                 "(user-installed reclassification, a patch fork, or "
                 "dropping the backend). MIT code + weights; curated "
                 "install excludes GPL pykakasi (Japanese-only) — English "
                 "path never imports it. Output carries the upstream "
                 "PerTh watermark.",
        ),
        tree_packages=_dist_names(CHATTERBOX_PACKAGES),
        first_audio_p50_s=4.0,
        rtf_p50=1.0,
    ),
    "kitten": TTSBackendSpec(
        key="kitten",
        display_name="Kitten TTS",
        default_shipped=False,
        plan=_plan(
            "kitten",
            pip_packages=(KITTEN_WHEEL, "soundfile"),
            probe_import="kittentts",
            warmup="runmal.voice.backends:warm_kitten",
            note="User-installed. Its tree phonemizes via eSpeak-NG "
                 "(GPL-3.0) — the audit verdict is shown as information.",
        ),
        tree_packages=_dist_names((KITTEN_WHEEL, "soundfile")),
    ),
    "piper": TTSBackendSpec(
        key="piper",
        display_name="Piper",
        default_shipped=False,
        plan=_plan(
            "piper",
            pip_packages=("piper-tts==1.8.0",),
            probe_import="piper",
            note="User-installed. piper-tts is GPL-3.0-or-later — the "
                 "audit verdict is shown as information.",
        ),
        tree_packages=_dist_names(("piper-tts==1.8.0",)),
    ),
}

#: The default TTS backend when the user has not chosen one.
DEFAULT_TTS_BACKEND = "cosyvoice"

#: All selectable backend keys (registry + the deterministic fake).
KNOWN_TTS_BACKENDS: tuple[str, ...] = tuple(TTS_REGISTRY) + ("fake-tts",)


def _require_importable(module: str, key: str) -> None:
    import importlib.util
    if importlib.util.find_spec(module) is None:
        raise BackendUnavailable(
            f"TTS backend '{key}' is not installed — installation is a "
            "user action in Settings → Voice (one-button install).")


class CosyVoiceTTS(TTSBackend):
    """CosyVoice 2 via its Python runtime, native streaming mode.

    The runtime is imported from the pinned git checkout in the
    vendor dir (the PyPI name ``cosyvoice`` is an unrelated package —
    never install it). Text normalization is the open
    WeTextProcessing frontend; ``ttsfrd`` is never installed.
    """

    name = "cosyvoice"

    def __init__(self, model_dir: str | None = None,
                 *, repo_dir: Path | None = None, runtime=None):
        if runtime is None:
            repo = repo_dir or (vendor_dir() / "CosyVoice")
            if not (repo / "cosyvoice").is_dir():
                raise BackendUnavailable(
                    "CosyVoice runtime not found in the vendor dir — "
                    "install it from Settings → Voice.")
            for entry in (str(repo), str(repo / "third_party" / "Matcha-TTS")):
                if entry not in sys.path:
                    sys.path.insert(0, entry)
            try:
                from cosyvoice.cli.cosyvoice import CosyVoice2
            except ImportError as exc:
                raise BackendUnavailable(
                    f"CosyVoice runtime not importable: {exc}") from exc
            resolved = model_dir or str(
                repo / "pretrained_models" / "CosyVoice2-0.5B")
            runtime = CosyVoice2(resolved, load_jit=False, load_trt=False)
        self._runtime = runtime

    def voices(self) -> list[VoiceInfo]:
        # CosyVoice 2 zero-shot: voices are prompt-defined; the app
        # ships one default profile voice (see profiles.DEFAULT_VOICE).
        return [VoiceInfo(voice_id="cosyvoice-zero-shot", name="CosyVoice zero-shot",
                          language="en", backend_key=self.name)]

    @staticmethod
    def _resolve_default_prompt() -> tuple[str, str] | None:
        """Resolve the app-level default zero-shot prompt.

        Order: ``RUNMAL_VOICE_PROMPT_WAV`` env override → the vendored
        default prompt asset. The prompt text comes from
        ``RUNMAL_VOICE_PROMPT_TEXT`` or the recorded corpus line.
        Returns ``None`` when no prompt wav exists (fail-closed)."""
        overridable = os.environ.get("RUNMAL_VOICE_PROMPT_WAV", "")
        asset = vendor_dir() / "models" / "default_prompt.wav"
        wav = overridable or (str(asset) if asset.exists() else "")
        if not wav:
            return None
        text = os.environ.get(
            "RUNMAL_VOICE_PROMPT_TEXT",
            "Hello, wanderer. The wind carried whispers of your arrival.")
        logging.getLogger(__name__).warning(
            "cosyvoice: voice carries no prompt — using the app default "
            "prompt asset %s", wav)
        return text, wav

    def synthesize(self, text: str, voice: VoiceInfo, *,
                   speaking_rate: float = 1.0) -> Iterator[AudioChunk]:
        prompt_text = getattr(voice, "prompt_text", "") or "You are a helpful assistant."
        prompt_wav = getattr(voice, "prompt_wav", "") or ""
        if not prompt_wav and voice.voice_id == "cosyvoice-zero-shot":
            resolved = self._resolve_default_prompt()
            if resolved is not None:
                prompt_text, prompt_wav = resolved
        if not prompt_wav:
            raise BackendUnavailable(
                "CosyVoice zero-shot synthesis needs a prompt wav: set "
                "one on the voice profile, or place the default prompt "
                "asset at <vendor>/models/default_prompt.wav.")
        stream = self._runtime.inference_zero_shot(
            text, prompt_text, prompt_wav, stream=True)
        for i, out in enumerate(stream):
            speech = out["tts_speech"]
            pcm = _tensor_to_pcm16(speech)
            yield AudioChunk(pcm=pcm, sample_rate=24000, index=i,
                             is_final=False)
        yield AudioChunk(pcm=b"", sample_rate=24000, index=-1, is_final=True)


class ChatterboxTTS(TTSBackend):
    """Chatterbox via sentence-chunk streaming at the seam.

    Chatterbox has no native streaming API, so long text is split
    with :func:`split_text_into_chunks` and generated sentence by
    sentence — the first chunk reaches the user while the rest is
    still synthesizing. Output carries the upstream PerTh watermark
    (applied unconditionally by ``generate()``; shipped as upstream
    and recorded in the license matrix, never silently patched).
    """

    name = "chatterbox"

    def __init__(self, *, device: str = "cuda", model=None):
        if model is None:
            _require_importable("chatterbox", self.name)
            from chatterbox.tts import ChatterboxTTS as _Upstream
            model = _Upstream.from_pretrained(device=device)
        self._model = model

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(voice_id="chatterbox-default", name="Chatterbox default",
                          language="en", backend_key=self.name)]

    def synthesize(self, text: str, voice: VoiceInfo, *,
                   speaking_rate: float = 1.0) -> Iterator[AudioChunk]:
        prompt_wav = getattr(voice, "prompt_wav", "") or None
        index = 0
        for sentence in split_text_into_chunks(text) or [text]:
            wav = self._model.generate(sentence, audio_prompt_path=prompt_wav)
            pcm = _tensor_to_pcm16(wav)
            yield AudioChunk(pcm=pcm, sample_rate=int(self._model.sr),
                             index=index, is_final=False)
            index += 1
        yield AudioChunk(pcm=b"", sample_rate=int(self._model.sr),
                         index=index, is_final=True)


class KittenTTS(TTSBackend):
    """Kitten TTS adapter — USER-INSTALLED backend (ADR-0005).

    Ships as adapter code only. The engine installs solely through
    the user's one-button action; its tree phonemizes via eSpeak-NG,
    which the audit reports as information (the gate binds only what
    Rúnmál ships by default).
    """

    name = "kitten"

    def __init__(self, *, model=None):
        if model is None:
            _require_importable("kittentts", self.name)
            from kittentts import KittenTTS as _Upstream
            model = _Upstream("KittenML/kitten-tts-nano-0.8")
        self._model = model

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(voice_id="expr-voice-2-f", name="Kitten expr-voice-2-f",
                          language="en", backend_key=self.name)]

    def synthesize(self, text: str, voice: VoiceInfo, *,
                   speaking_rate: float = 1.0) -> Iterator[AudioChunk]:
        audio = self._model.generate(text, voice="expr-voice-2-f")
        pcm = _float_to_pcm16(audio)
        yield AudioChunk(pcm=pcm, sample_rate=24000, index=0, is_final=False)
        yield AudioChunk(pcm=b"", sample_rate=24000, index=1, is_final=True)


class PiperTTS(TTSBackend):
    """Piper adapter — USER-INSTALLED backend (ADR-0005).

    Adapter code only; the GPL-3.0 ``piper-tts`` package installs
    solely through the user's one-button action. Needs a voice model
    (.onnx + .json) in the vendor models dir, downloaded by the user
    from Piper's voice catalogue.
    """

    name = "piper"

    def __init__(self, *, model_path: Path | None = None, voice_model=None):
        if voice_model is None:
            _require_importable("piper", self.name)
            from piper import PiperVoice
            model = model_path or self._default_model_path()
            if model is None or not Path(model).exists():
                raise BackendUnavailable(
                    "No Piper voice model (.onnx) in the vendor models "
                    "dir — download one from the Piper voice catalogue.")
            voice_model = PiperVoice.load(str(model))
        self._voice = voice_model

    @staticmethod
    def _default_model_path() -> Path | None:
        models = vendor_dir() / "models"
        candidates = sorted(models.glob("*.onnx")) if models.is_dir() else []
        return candidates[0] if candidates else None

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(voice_id="piper-voice", name="Piper voice",
                          language="en", backend_key=self.name)]

    def synthesize(self, text: str, voice: VoiceInfo, *,
                   speaking_rate: float = 1.0) -> Iterator[AudioChunk]:
        import io
        import wave
        index = 0
        for chunk in self._voice.synthesize(text):
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                chunk.set_wav_format(wav_file)
                wav_file.writeframes(chunk.audio_int16_bytes)
            raw = buf.getvalue()
            pcm = raw[44:] if raw[:4] == b"RIFF" else raw
            yield AudioChunk(pcm=pcm, sample_rate=chunk.sample_rate,
                             index=index, is_final=False)
            index += 1
        yield AudioChunk(pcm=b"", sample_rate=22050, index=index, is_final=True)


def _tensor_to_pcm16(tensor) -> bytes:
    """Torch tensor / array-like of float samples → little-endian PCM16."""
    try:
        import torch
        if isinstance(tensor, torch.Tensor):
            tensor = tensor.detach().cpu().numpy()
    except ImportError:
        pass
    return _float_to_pcm16(tensor)


def _float_to_pcm16(samples) -> bytes:
    import numpy as np
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    clipped = np.clip(arr, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


_FACTORIES = {
    "cosyvoice": CosyVoiceTTS,
    "chatterbox": ChatterboxTTS,
    "kitten": KittenTTS,
    "piper": PiperTTS,
    "fake-tts": FakeTTSBackend,
}


def build_tts_backend(key: str, **kwargs) -> TTSBackend:
    """Construct the backend for ``key`` or raise BackendUnavailable."""
    factory = _FACTORIES.get(key)
    if factory is None:
        raise BackendUnavailable(f"unknown TTS backend '{key}'")
    return factory(**kwargs)


def resolve_tts_backend(key: str, *, fallback_fake: bool = False) -> TTSBackend:
    """Construct ``key``; optionally degrade to the fake backend.

    Degradation is always explicit (``fallback_fake=True`` at the call
    site) — never silent.
    """
    try:
        return build_tts_backend(key)
    except BackendUnavailable:
        if fallback_fake:
            return FakeTTSBackend()
        raise


# ------------------------------------------------------------- warm-ups
# Install-time model downloads + import smoke tests (see InstallPlan.warmup).


def warm_cosyvoice() -> None:
    """Download CosyVoice2-0.5B into the vendor checkout via modelscope
    (the upstream-sanctioned channel) and smoke-test the import."""
    from modelscope import snapshot_download
    dest = vendor_dir() / "CosyVoice" / "pretrained_models"
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download("iic/CosyVoice2-0.5B", local_dir=str(dest / "CosyVoice2-0.5B"))


def warm_chatterbox() -> None:
    """Pull Chatterbox weights and prove the curated tree imports —
    critically, WITHOUT pykakasi present."""
    from chatterbox.tts import ChatterboxTTS as _Upstream
    _Upstream.from_pretrained(device="cpu")


def warm_kitten() -> None:
    """Pull the Kitten nano model and smoke-test the user-installed tree."""
    from kittentts import KittenTTS as _Upstream
    _Upstream("KittenML/kitten-tts-nano-0.8")
