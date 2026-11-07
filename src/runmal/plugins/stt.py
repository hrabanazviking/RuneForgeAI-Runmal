"""Speech to Text plugin (P-091): the founding STT seam as a citizen.

Roadmap line: "P-091 TTS/STT as plugins too: the founding
voice stack refactored behind the same API (proof the API is
real)."

A first-class P-081 citizen wrapping the founding S503 seam
(:class:`runmal.voice.stt.STTBackend`) unchanged.
Transcription happens ONLY from the explicit
:meth:`SttPlugin.transcribe` action, called by trusted host
code holding the plugin instance with PCM it already holds.
No event ever transcribes: the citizen declares only
``chat.deleted``, housekeeping only -- it declares no
``message.*`` event, so it never receives message text.
Voice is not prompt text, so the citizen declares no prompt
hooks.

Wiring is instance-only (host wiring, trusted code): an
``STTBackend`` INSTANCE handed to :func:`register_plugin` or
the config. ``backend=None`` selects :class:`FakeSTTBackend`,
labelled ``fake`` at every surface it appears -- its scripted
transcript is never presented as a real transcription. The
citizen never calls ``build_stt_backend`` (in particular not
for the fake, whose factory form ignores ``text=`` /
``language=`` kwargs): a host wanting a scripted fake
constructs ``FakeSTTBackend(text=..., language=...)``
directly and hands the instance in.

Sandbox stance (P-082): the manifest declares only v1
surface permissions, so the derived resource grant set is
EMPTY (:func:`sandbox_grants` proves it); the wired backend
is trusted host wiring, never a sandbox grant and never
manifest data.

Wiring: :func:`register_plugin` is the one-call trusted
registration road. ``build_registry`` / ``create_app`` are
unchanged. No migration: per-chat latest results live in
memory on the plugin instance and are lost on restart,
stated plainly. The input PCM itself is never retained --
only its byte count and derived duration.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
from datetime import UTC, datetime

from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest
from runmal.voice import SAMPLE_RATE
from runmal.voice.stt import FakeSTTBackend, STTBackend

PLUGIN_ID = "runmal.stt"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "stt-panel"
DECLARED_EVENTS = ("chat.deleted",)
DEFAULT_SAMPLE_RATE = SAMPLE_RATE
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000
DEFAULT_MAX_AUDIO_BYTES = 3_200_000
MIN_MAX_AUDIO_BYTES = 3_200
MAX_AUDIO_BYTES_LIMIT = 16_000_000


class SttPluginError(RuntimeError):
    """A config, validation or backend failure of the STT citizen."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


async def _await_if_needed(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _check_chat_id(value, *, allow_none: bool):
    if value is None:
        if allow_none:
            return None
        raise SttPluginError("chat_id is required")
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or not value.strip():
        raise SttPluginError(f"invalid chat_id: {value!r}")
    return value


def _event_chat_id(event):
    chat_id = getattr(event, "chat_id", None)
    if not chat_id:
        data = getattr(event, "data", None)
        if isinstance(data, dict):
            chat_id = data.get("chat_id")
    if isinstance(chat_id, str) and chat_id:
        return chat_id
    return None


def _check_backend(value):
    if value is None:
        return None
    for name in ("transcribe", "model_info"):
        if not callable(getattr(value, name, None)):
            raise SttPluginError(
                "backend must be handed in as an STTBackend instance "
                f"exposing callable {name!r}, never as a backend key: {value!r}")
    return value


def _check_max_audio_bytes(value) -> int:
    if not _is_int(value) or not MIN_MAX_AUDIO_BYTES <= value <= MAX_AUDIO_BYTES_LIMIT:
        raise SttPluginError(
            f"max_audio_bytes must be an int in "
            f"{MIN_MAX_AUDIO_BYTES}..{MAX_AUDIO_BYTES_LIMIT}: {value!r}")
    return value


def _check_sample_rate(value) -> int:
    if not _is_int(value) or not MIN_SAMPLE_RATE <= value <= MAX_SAMPLE_RATE:
        raise SttPluginError(
            f"sample_rate must be an int in "
            f"{MIN_SAMPLE_RATE}..{MAX_SAMPLE_RATE}: {value!r}")
    return value


@dataclasses.dataclass(frozen=True)
class SttPluginConfig:
    """Plugin-global config: the wired backend + the audio cap.

    ``backend=None`` selects a fresh :class:`FakeSTTBackend`
    per plugin instance. A backend is always an INSTANCE
    handed in by trusted host wiring, never a key string.
    ``health_check`` is deliberately NOT required of the
    backend: the ABC provides it, and :meth:`SttPlugin.health`
    defines the fallback for a duck backend without one.
    """

    backend: object = None
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES

    def __post_init__(self) -> None:
        _check_backend(self.backend)
        _check_max_audio_bytes(self.max_audio_bytes)

    @property
    def effective_backend(self):
        return self.backend if self.backend is not None else FakeSTTBackend()


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Speech to Text",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Founding STT seam as a plugin citizen: explicit transcription only, through a host-wired STTBackend (FakeSTTBackend by default and labelled fake). No event transcribes.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [{"id": UI_LOCAL_ID, "slot": "settings.panel", "label": "Speech to Text", "order": 91, "payload": {"kind": "panel", "route": "stt"}}],
        "settings": {
            "schema": {"max_audio_bytes": {"type": "integer", "minimum": 3200, "maximum": 16000000}},
            "defaults": {"max_audio_bytes": 3200000},
        },
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest=None) -> SttPluginConfig:
    """Config from the manifest's settings defaults.

    Lenient by design (the P-088 pattern): a missing or
    invalid value falls back to the module constant. A
    manifest can never carry a backend, a backend key, or
    code (data only, PLG-02), so the returned config's
    ``backend`` is always ``None``.
    """
    if manifest is None:
        manifest = build_manifest()
    defaults: dict = {}
    settings = manifest.get("settings") if isinstance(manifest, dict) else getattr(manifest, "settings", None)
    if isinstance(settings, dict):
        raw = settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    try:
        cap = _check_max_audio_bytes(defaults.get("max_audio_bytes", DEFAULT_MAX_AUDIO_BYTES))
    except SttPluginError:
        cap = DEFAULT_MAX_AUDIO_BYTES
    return SttPluginConfig(max_audio_bytes=cap)


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


def _word_to_dict(word) -> dict:
    try:
        return {
            "text": word.text,
            "start_s": float(word.start_s),
            "end_s": float(word.end_s),
            "probability": float(word.probability),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise SttPluginError(f"backend returned a malformed transcript word: {exc}") from exc


def _transcript_to_parts(transcript):
    """Validate + serialise a Transcript without adding rounding."""
    try:
        text = transcript.text
        language = transcript.language
        segments_raw = transcript.segments
        model_id = transcript.model_id
        backend_key = transcript.backend_key
    except AttributeError as exc:
        raise SttPluginError(f"backend returned a malformed transcript: {exc}") from exc
    if not isinstance(text, str) or not isinstance(language, str):
        raise SttPluginError("transcript text and language must be strings")
    try:
        segment_rows = list(segments_raw)
    except TypeError as exc:
        raise SttPluginError(f"backend returned malformed transcript segments: {exc}") from exc
    segments: list[dict] = []
    words: list[dict] = []
    for segment in segment_rows:
        try:
            seg_text = segment.text
            seg_start = float(segment.start_s)
            seg_end = float(segment.end_s)
            seg_words_raw = segment.words
        except (AttributeError, TypeError, ValueError) as exc:
            raise SttPluginError(f"backend returned a malformed transcript segment: {exc}") from exc
        if not isinstance(seg_text, str):
            raise SttPluginError(f"transcript segment text must be a string: {seg_text!r}")
        try:
            word_dicts = [_word_to_dict(word) for word in seg_words_raw]
        except TypeError as exc:
            raise SttPluginError(f"backend returned malformed segment words: {exc}") from exc
        segments.append({"text": seg_text, "start_s": seg_start, "end_s": seg_end, "words": word_dicts})
        words.extend(word_dicts)
    return text, language, segments, words, model_id, backend_key


class SttPlugin:
    """The citizen: explicit transcription through one wired backend.

    One plugin instance drives one backend instance for its
    whole life. Per-chat latest results live on the instance
    (in memory; lost on restart); the input PCM is never
    retained. Instance actions do not consult registry state:
    only event dispatch is enable-gated, by the registry.
    """

    def __init__(self, config: SttPluginConfig | None = None) -> None:
        self.config = config if config is not None else config_from_manifest(build_manifest())
        self._backend = self.config.effective_backend
        self._backend_key = str(getattr(self._backend, "backend_key", "") or "")
        self._last_by_chat: dict[str, dict] = {}

    @property
    def manifest(self):
        return build_manifest()

    @property
    def backend(self):
        return self._backend

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    # -- backend roads (backend calls are wrapped, except health) --
    def _wrap(self, operation: str, exc: Exception) -> SttPluginError:
        return SttPluginError(
            f"STT backend {self._backend_key!r} failed during {operation}: {exc}")

    async def _model_info_raw(self):
        try:
            return await _await_if_needed(self._backend.model_info())
        except SttPluginError:
            raise
        except Exception as exc:
            raise self._wrap("model_info", exc) from exc

    def _provenance(self, info) -> tuple[str, str, str, bool, bool]:
        try:
            backend_key = str(info.backend_key)
            model_id = str(info.model_id)
            language = str(info.language)
            supports_words = bool(info.supports_word_timestamps)
            supports_streaming = bool(info.supports_streaming)
        except (AttributeError, TypeError, ValueError) as exc:
            raise SttPluginError(f"backend returned malformed model info: {exc}") from exc
        return backend_key, model_id, language, supports_words, supports_streaming

    # -- the explicit action ---------------------------------------
    async def transcribe(self, pcm, sample_rate: int = DEFAULT_SAMPLE_RATE, chat_id=None) -> dict:
        """Transcribe PCM16 mono ``pcm`` through the wired backend.

        Validation (chat id, PCM shape and cap, sample rate)
        all runs BEFORE the backend is touched. The rate is
        passed through verbatim -- the citizen never resamples
        and never refuses a non-16000 rate itself; a backend
        with a hard rate requirement refuses with its own
        error, which is wrapped. On success the result becomes
        the chat's latest (when ``chat_id`` is given); on any
        failure nothing is stored and a prior success is
        preserved. The input PCM is never stored.
        """
        chat_id = _check_chat_id(chat_id, allow_none=True)
        if not isinstance(pcm, (bytes, bytearray, memoryview)):
            raise SttPluginError(f"pcm must be bytes-like: {type(pcm).__name__}")
        pcm_bytes = bytes(pcm)
        if not 2 <= len(pcm_bytes) <= self.config.max_audio_bytes:
            raise SttPluginError(
                f"pcm length must be in 2..{self.config.max_audio_bytes} bytes: {len(pcm_bytes)}")
        if len(pcm_bytes) % 2:
            raise SttPluginError(f"pcm length must be even (whole PCM16 frames): {len(pcm_bytes)}")
        rate = _check_sample_rate(sample_rate)
        try:
            transcript = await _await_if_needed(self._backend.transcribe(pcm_bytes, rate))
        except SttPluginError:
            raise
        except Exception as exc:
            raise self._wrap("transcribe", exc) from exc
        text, language, segments, words, t_model_id, t_backend_key = _transcript_to_parts(transcript)
        info = await self._model_info_raw()
        backend_key, info_model_id, _lang, supports_words, supports_streaming = self._provenance(info)
        result = {
            "plugin_id": PLUGIN_ID,
            "kind": "transcribe",
            "performed": True,
            "performed_at": _now_iso(),
            "chat_id": chat_id,
            "sample_rate": rate,
            "pcm_bytes": len(pcm_bytes),
            "duration_s": (len(pcm_bytes) // 2) / rate,
            "text": text,
            "language": language,
            "segments": segments,
            "words": words,
            "segment_count": len(segments),
            "word_count": len(words),
            "backend": backend_key,
            "model": t_model_id if isinstance(t_model_id, str) and t_model_id else info_model_id,
            "transcript_backend_key": t_backend_key,
            "transcript_model_id": t_model_id,
            "road": "fake" if backend_key == "fake-stt" else backend_key,
            "supports_word_timestamps": supports_words,
            "supports_streaming": supports_streaming,
        }
        if chat_id is not None:
            self._last_by_chat[chat_id] = copy.deepcopy(result)
        return result

    async def model_info(self) -> dict:
        """Provenance from ``backend.model_info()``."""
        info = await self._model_info_raw()
        backend_key, model_id, language, supports_words, supports_streaming = self._provenance(info)
        return {
            "plugin_id": PLUGIN_ID,
            "backend": backend_key,
            "model": model_id,
            "road": "fake" if backend_key == "fake-stt" else backend_key,
            "language": language,
            "supports_word_timestamps": supports_words,
            "supports_streaming": supports_streaming,
        }

    async def health(self) -> dict:
        """A health probe: reports failure in its dict, NEVER raises.

        With a callable ``health_check`` that call decides;
        without one, the probe IS ``model_info()``. ``model``
        is best-effort garnish from a ``model_info()`` call: if
        that call fails while the probe already reported
        healthy, ``model`` and ``error`` stay ``None``.
        """
        healthy = False
        model = None
        error = None
        try:
            health_check = getattr(self._backend, "health_check", None)
            if callable(health_check):
                try:
                    healthy = bool(await _await_if_needed(health_check()))
                except Exception as exc:
                    healthy = False
                    error = f"{type(exc).__name__}: {exc}"
                try:
                    info = await _await_if_needed(self._backend.model_info())
                    model = str(info.model_id)
                except Exception as exc:
                    if not healthy and error is None:
                        error = f"{type(exc).__name__}: {exc}"
            else:
                try:
                    info = await _await_if_needed(self._backend.model_info())
                    healthy = True
                    model = str(info.model_id)
                except Exception as exc:
                    healthy = False
                    error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            healthy = False
            if error is None:
                error = f"{type(exc).__name__}: {exc}"
        return {
            "plugin_id": PLUGIN_ID,
            "backend": self._backend_key,
            "healthy": healthy,
            "model": model,
            "error": error,
        }

    # -- status / housekeeping (never call the backend) ----------
    def transcription_status(self, chat_id) -> dict:
        chat_id = _check_chat_id(chat_id, allow_none=False)
        latest = self._last_by_chat.get(chat_id)
        return {
            "plugin_id": PLUGIN_ID,
            "chat_id": chat_id,
            "backend_key": self._backend_key,
            "has_result": latest is not None,
            "latest": copy.deepcopy(latest) if latest is not None else None,
        }

    def last_transcript(self, chat_id) -> dict | None:
        chat_id = _check_chat_id(chat_id, allow_none=False)
        latest = self._last_by_chat.get(chat_id)
        return copy.deepcopy(latest) if latest is not None else None

    def clear_chat(self, chat_id) -> None:
        self._last_by_chat.pop(chat_id, None)

    # -- events ----------------------------------------------------
    async def on_event(self, event) -> None:
        """Housekeeping only. NEVER raises, NEVER calls the backend,
        NEVER transcribes. Only ``chat.deleted`` does anything:
        it clears that chat's stored latest transcript. Every
        other name is a no-op."""
        try:
            if getattr(event, "name", None) == "chat.deleted":
                chat_id = _event_chat_id(event)
                if chat_id is not None:
                    self.clear_chat(chat_id)
        except Exception:
            return None
        return None


def register_plugin(registry: PluginRegistry, backend=None, *, config: SttPluginConfig | None = None, enable: bool = False) -> tuple[PluginRecord, SttPlugin]:
    """Register the citizen into ``registry`` (trusted code only).

    An explicit ``backend`` argument beats ``config.backend``;
    with neither, the manifest-derived config wires the
    labelled :class:`FakeSTTBackend`. Construction failure of
    a real backend happens in the host's wiring expression,
    before this function is called -- it is never caught here
    and never swapped for the fake.
    """
    if config is None:
        config = config_from_manifest(build_manifest())
    if backend is not None:
        config = dataclasses.replace(config, backend=backend)
    plugin = SttPlugin(config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS",
    "DEFAULT_MAX_AUDIO_BYTES",
    "DEFAULT_SAMPLE_RATE",
    "MAX_AUDIO_BYTES_LIMIT",
    "MAX_SAMPLE_RATE",
    "MIN_MAX_AUDIO_BYTES",
    "MIN_SAMPLE_RATE",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "UI_LOCAL_ID",
    "VERSION",
    "SttPlugin",
    "SttPluginConfig",
    "SttPluginError",
    "build_manifest",
    "config_from_manifest",
    "manifest_data",
    "register_plugin",
    "sandbox_grants",
]
