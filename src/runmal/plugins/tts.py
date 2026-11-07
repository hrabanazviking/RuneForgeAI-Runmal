"""Text to Speech plugin (P-091): the founding TTS seam as a citizen.

Roadmap line: "P-091 TTS/STT as plugins too: the founding
voice stack refactored behind the same API (proof the API is
real)."

A first-class P-081 citizen wrapping the founding S504 seam
(:class:`runmal.voice.tts.TTSBackend`) unchanged. Synthesis
happens ONLY from the explicit :meth:`TtsPlugin.synthesize`
and :meth:`TtsPlugin.audition` actions, called by trusted
host code holding the plugin instance. No event ever
synthesizes: the declared ``message.created`` event only
RECORDS observation metadata (counts and lengths, never the
message text), and ``chat.deleted`` only clears per-chat
state. Voice is not prompt text, so the citizen declares no
prompt hooks.

Wiring is instance-only (host wiring, trusted code): a
``TTSBackend`` INSTANCE handed to :func:`register_plugin` or
the config. ``backend=None`` selects :class:`FakeTTSBackend`,
labelled ``fake`` at every surface it appears -- never
presented as CosyVoice or as real speech. The citizens never
call ``build_*_backend`` / ``resolve_*`` and never accept a
backend key string.

Sandbox stance (P-082): the manifest declares only v1
surface permissions, so the derived resource grant set is
EMPTY (:func:`sandbox_grants` proves it); the wired backend
is trusted host wiring, never a sandbox grant and never
manifest data.

Wiring: :func:`register_plugin` is the one-call trusted
registration road. ``build_registry`` / ``create_app`` are
unchanged. No migration: per-chat latest results and
observation metadata live in memory on the plugin instance
and are lost on restart, stated plainly.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import inspect
import math
from collections.abc import Mapping
from datetime import UTC, datetime

from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest
from runmal.voice.tts import FakeTTSBackend, TTSBackend, VoiceInfo

PLUGIN_ID = "runmal.tts"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "tts-panel"
DECLARED_EVENTS = ("message.created", "chat.deleted")
DEFAULT_SPEAKING_RATE = 1.0
MIN_SPEAKING_RATE = 0.5
MAX_SPEAKING_RATE = 2.0
DEFAULT_MAX_TEXT_CHARS = 2000
MAX_TEXT_CHARS_LIMIT = 4000
AUDITION_SAMPLE_TEXT = "Hello, I am ready when you are."

_VOICE_FIELDS = frozenset(
    {"voice_id", "language", "backend_key", "name", "prompt_text", "prompt_wav"})


class TtsPluginError(RuntimeError):
    """A config, validation or backend failure of the TTS citizen."""


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
        raise TtsPluginError("chat_id is required")
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or not value.strip():
        raise TtsPluginError(f"invalid chat_id: {value!r}")
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
    for name in ("synthesize", "synthesize_all", "model_info"):
        if not callable(getattr(value, name, None)):
            raise TtsPluginError(
                "backend must be handed in as a TTSBackend instance "
                f"exposing callable {name!r}, never as a backend key: {value!r}")
    return value


def _check_speaking_rate(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsPluginError(f"speaking_rate must be a number: {value!r}")
    rate = float(value)
    if not math.isfinite(rate) or not MIN_SPEAKING_RATE <= rate <= MAX_SPEAKING_RATE:
        raise TtsPluginError(
            f"speaking_rate must be finite and in "
            f"{MIN_SPEAKING_RATE}..{MAX_SPEAKING_RATE}: {value!r}")
    return rate


def _check_max_text_chars(value) -> int:
    if not _is_int(value) or not 1 <= value <= MAX_TEXT_CHARS_LIMIT:
        raise TtsPluginError(
            f"max_text_chars must be an int in 1..{MAX_TEXT_CHARS_LIMIT}: {value!r}")
    return value


def _validate_text(text, max_chars: int) -> str:
    if not isinstance(text, str) or not text.strip():
        raise TtsPluginError("text must be a non-empty string")
    if len(text) > max_chars:
        raise TtsPluginError(
            f"text exceeds max_text_chars ({max_chars}): {len(text)} chars")
    return text


@dataclasses.dataclass(frozen=True)
class TtsPluginConfig:
    """Plugin-global config: the wired backend + citizen caps.

    ``backend=None`` selects a fresh :class:`FakeTTSBackend`
    per plugin instance. A backend is always an INSTANCE
    handed in by trusted host wiring, never a key string.
    """

    backend: object = None
    speaking_rate: float = DEFAULT_SPEAKING_RATE
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS

    def __post_init__(self) -> None:
        _check_backend(self.backend)
        _check_speaking_rate(self.speaking_rate)
        _check_max_text_chars(self.max_text_chars)

    @property
    def effective_backend(self):
        return self.backend if self.backend is not None else FakeTTSBackend()


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Text to Speech",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Founding TTS seam as a plugin citizen: explicit synthesis only, through a host-wired TTSBackend (FakeTTSBackend by default and labelled fake). Events never synthesize.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [{"id": UI_LOCAL_ID, "slot": "settings.panel", "label": "Text to Speech", "order": 90, "payload": {"kind": "panel", "route": "tts"}}],
        "settings": {
            "schema": {
                "speaking_rate": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                "max_text_chars": {"type": "integer", "minimum": 1, "maximum": 4000},
            },
            "defaults": {"speaking_rate": 1.0, "max_text_chars": 2000},
        },
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest=None) -> TtsPluginConfig:
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
        rate = _check_speaking_rate(defaults.get("speaking_rate", DEFAULT_SPEAKING_RATE))
    except TtsPluginError:
        rate = DEFAULT_SPEAKING_RATE
    try:
        max_chars = _check_max_text_chars(defaults.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
    except TtsPluginError:
        max_chars = DEFAULT_MAX_TEXT_CHARS
    return TtsPluginConfig(speaking_rate=rate, max_text_chars=max_chars)


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


def _voice_to_dict(voice) -> dict:
    try:
        return {
            "voice_id": voice.voice_id,
            "language": voice.language,
            "backend_key": voice.backend_key,
            "name": voice.name,
            "prompt_text": voice.prompt_text,
            "prompt_wav": voice.prompt_wav,
        }
    except AttributeError as exc:
        raise TtsPluginError(f"backend returned malformed voice info: {exc}") from exc


def _chunk_to_dict(chunk) -> dict:
    try:
        pcm_raw = chunk.pcm
        text = chunk.text
        index = chunk.index
        sample_rate = chunk.sample_rate
        is_final = chunk.is_final
        timings_raw = chunk.word_timings
    except AttributeError as exc:
        raise TtsPluginError(f"backend returned a malformed audio chunk: {exc}") from exc
    if isinstance(pcm_raw, bytes):
        pcm = pcm_raw
    elif isinstance(pcm_raw, (bytearray, memoryview)):
        pcm = bytes(pcm_raw)
    else:
        raise TtsPluginError(
            f"chunk pcm must be bytes-like: {type(pcm_raw).__name__}")
    if not isinstance(text, str):
        raise TtsPluginError(f"chunk text must be a string: {text!r}")
    if not _is_int(index):
        raise TtsPluginError(f"chunk index must be an int: {index!r}")
    if not _is_int(sample_rate) or sample_rate < 1:
        raise TtsPluginError(f"chunk sample_rate must be a positive int: {sample_rate!r}")
    if not isinstance(is_final, bool):
        raise TtsPluginError(f"chunk is_final must be a bool: {is_final!r}")
    try:
        timings = [[str(w), float(s), float(e)] for w, s, e in timings_raw]
    except (TypeError, ValueError) as exc:
        raise TtsPluginError(f"backend returned malformed word timings: {exc}") from exc
    duration = getattr(chunk, "duration_s", None)
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        duration = (len(pcm) // 2) / sample_rate
    else:
        duration = float(duration)
    return {
        "index": index,
        "text": text,
        "sample_rate": sample_rate,
        "pcm_bytes": len(pcm),
        "duration_s": duration,
        "is_final": is_final,
        "word_timings": timings,
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }


class TtsPlugin:
    """The citizen: explicit synthesis through one wired backend.

    One plugin instance drives one backend instance for its
    whole life. Per-chat latest results and observation
    metadata live on the instance (in memory; lost on
    restart). Instance actions do not consult registry state:
    only event dispatch is enable-gated, by the registry.
    """

    def __init__(self, config: TtsPluginConfig | None = None) -> None:
        self.config = config if config is not None else config_from_manifest(build_manifest())
        self._backend = self.config.effective_backend
        self._backend_key = str(getattr(self._backend, "backend_key", "") or getattr(self._backend, "name", "") or "")
        self._last_by_chat: dict[str, dict] = {}
        self._observed: dict[str, dict] = {}

    @property
    def manifest(self):
        return build_manifest()

    @property
    def backend(self):
        return self._backend

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    # -- backend roads (every backend call is wrapped) ---------
    def _wrap(self, operation: str, exc: Exception) -> TtsPluginError:
        return TtsPluginError(
            f"TTS backend {self._backend_key!r} failed during {operation}: {exc}")

    async def _model_info_raw(self):
        try:
            return await _await_if_needed(self._backend.model_info())
        except TtsPluginError:
            raise
        except Exception as exc:
            raise self._wrap("model_info", exc) from exc

    def _provenance(self, info) -> tuple[str, str, int]:
        try:
            backend_key = str(info.backend_key)
            model_id = str(info.model_id)
            native = int(getattr(info, "native_sample_rate", 24000))
        except (AttributeError, TypeError, ValueError) as exc:
            raise TtsPluginError(f"backend returned malformed model info: {exc}") from exc
        return backend_key, model_id, native

    async def _voices_raw(self):
        try:
            voices = await _await_if_needed(self._backend.voices())
        except TtsPluginError:
            raise
        except Exception as exc:
            raise self._wrap("voices", exc) from exc
        try:
            return list(voices)
        except TypeError as exc:
            raise TtsPluginError(f"backend returned malformed voices: {exc}") from exc

    async def _synthesize_chunks(self, text, resolved, rate: float):
        try:
            if rate != 1.0:
                raw = self._backend.synthesize(text, resolved, speaking_rate=rate)
            else:
                raw = self._backend.synthesize_all(text, resolved)
            raw = await _await_if_needed(raw)
            return list(raw)
        except TtsPluginError:
            raise
        except Exception as exc:
            raise self._wrap("synthesize", exc) from exc

    async def _audition_chunks(self, resolved, text):
        try:
            audition = getattr(self._backend, "audition", None)
            if callable(audition):
                raw = audition(resolved) if text is None else audition(resolved, text)
            else:
                sample = text if text is not None else AUDITION_SAMPLE_TEXT
                raw = self._backend.synthesize_all(sample, resolved)
            raw = await _await_if_needed(raw)
            return list(raw)
        except TtsPluginError:
            raise
        except Exception as exc:
            raise self._wrap("audition", exc) from exc

    # -- voice resolution ---------------------------------------
    async def _resolve_voice(self, voice) -> VoiceInfo:
        if isinstance(voice, VoiceInfo):
            if not isinstance(voice.voice_id, str) or not voice.voice_id:
                raise TtsPluginError(f"voice_id must be a non-empty string: {voice.voice_id!r}")
            return voice
        if isinstance(voice, Mapping):
            unknown = set(voice) - _VOICE_FIELDS
            if unknown:
                raise TtsPluginError(f"unknown voice fields: {sorted(unknown)!r}")
            if "voice_id" not in voice:
                raise TtsPluginError("voice mapping requires voice_id")
            voice_id = voice["voice_id"]
            if not isinstance(voice_id, str) or not voice_id or len(voice_id) > 200:
                raise TtsPluginError(f"voice_id must be a non-empty string of at most 200 chars: {voice_id!r}")
            fields = {}
            for key, value in voice.items():
                if not isinstance(value, str):
                    raise TtsPluginError(f"voice field {key!r} must be a string: {value!r}")
                fields[key] = value
            return VoiceInfo(**fields)
        if isinstance(voice, str):
            if not voice.strip() or len(voice) > 200:
                raise TtsPluginError(f"voice must be a non-empty string of at most 200 chars: {voice!r}")
            return VoiceInfo(voice_id=voice, backend_key=self._backend_key)
        if voice is None:
            voices = await self._voices_raw()
            if not voices:
                raise TtsPluginError("no voice given and the wired backend offers no voices")
            return voices[0]
        raise TtsPluginError(f"unsupported voice argument: {type(voice).__name__}")

    # -- result building -----------------------------------------
    async def _result_from_chunks(self, *, kind: str, text: str, resolved, rate: float, raw_chunks, chat_id) -> dict:
        chunk_dicts = [_chunk_to_dict(chunk) for chunk in raw_chunks]
        info = await self._model_info_raw()
        backend_key, model_id, native = self._provenance(info)
        return {
            "plugin_id": PLUGIN_ID,
            "kind": kind,
            "performed": True,
            "performed_at": _now_iso(),
            "chat_id": chat_id,
            "text": text,
            "text_chars": len(text),
            "voice": _voice_to_dict(resolved),
            "backend": backend_key,
            "model": model_id,
            "road": "fake" if backend_key == "fake-tts" else backend_key,
            "speaking_rate": rate,
            "native_sample_rate": native,
            "chunk_count": len(chunk_dicts),
            "total_pcm_bytes": sum(c["pcm_bytes"] for c in chunk_dicts),
            "total_duration_s": sum(c["duration_s"] for c in chunk_dicts),
            "chunks": chunk_dicts,
        }

    # -- the explicit actions -------------------------------------
    async def synthesize(self, text, voice=None, chat_id=None, *, speaking_rate: float | None = None) -> dict:
        """Synthesize ``text`` for ``voice`` through the wired backend.

        Validation (chat id, text, rate, voice) all runs BEFORE
        the backend is touched. The text is passed verbatim.
        When the effective speaking rate is not 1.0 the citizen
        materialises ``backend.synthesize(..., speaking_rate=...)``
        itself, because the seam's ``synthesize_all`` cannot
        forward a rate. On success the result becomes the chat's
        latest (when ``chat_id`` is given); on any failure
        nothing is stored and a prior success is preserved.
        """
        chat_id = _check_chat_id(chat_id, allow_none=True)
        _validate_text(text, self.config.max_text_chars)
        rate = _check_speaking_rate(speaking_rate) if speaking_rate is not None else float(self.config.speaking_rate)
        resolved = await self._resolve_voice(voice)
        raw_chunks = await self._synthesize_chunks(text, resolved, rate)
        result = await self._result_from_chunks(
            kind="synthesize", text=text, resolved=resolved, rate=rate,
            raw_chunks=raw_chunks, chat_id=chat_id)
        if chat_id is not None:
            self._last_by_chat[chat_id] = copy.deepcopy(result)
        return result

    async def audition(self, voice=None, *, text: str | None = None, chat_id=None) -> dict:
        """Audition a voice: the backend's own sample line by default.

        With ``text=None`` the wired backend's ``audition`` road
        supplies its own default sample; the result names
        :data:`AUDITION_SAMPLE_TEXT` as the sample text (the
        seam default) and carries ``speaking_rate`` 1.0 -- the
        audition road has no rate. A duck-typed backend without
        a callable ``audition`` falls back to ``synthesize_all``
        on the sample text.
        """
        chat_id = _check_chat_id(chat_id, allow_none=True)
        if text is not None:
            _validate_text(text, self.config.max_text_chars)
        resolved = await self._resolve_voice(voice)
        raw_chunks = await self._audition_chunks(resolved, text)
        sample = text if text is not None else AUDITION_SAMPLE_TEXT
        result = await self._result_from_chunks(
            kind="audition", text=sample, resolved=resolved, rate=1.0,
            raw_chunks=raw_chunks, chat_id=chat_id)
        result["sample_text"] = sample
        if chat_id is not None:
            self._last_by_chat[chat_id] = copy.deepcopy(result)
        return result

    async def list_voices(self) -> dict:
        """Full voice dicts from ``backend.voices()``, in backend order."""
        voices = await self._voices_raw()
        info = await self._model_info_raw()
        backend_key, _model_id, _native = self._provenance(info)
        return {
            "plugin_id": PLUGIN_ID,
            "backend": backend_key,
            "road": "fake" if backend_key == "fake-tts" else backend_key,
            "voices": [_voice_to_dict(voice) for voice in voices],
        }

    async def model_info(self) -> dict:
        """Provenance from ``backend.model_info()`` (voice ids as strings)."""
        info = await self._model_info_raw()
        backend_key, model_id, native = self._provenance(info)
        try:
            voice_ids = [str(v) for v in info.voices]
        except (AttributeError, TypeError) as exc:
            raise TtsPluginError(f"backend returned malformed model info: {exc}") from exc
        return {
            "plugin_id": PLUGIN_ID,
            "backend": backend_key,
            "model": model_id,
            "road": "fake" if backend_key == "fake-tts" else backend_key,
            "voices": voice_ids,
            "native_sample_rate": native,
        }

    # -- status / housekeeping (never call the backend) ----------
    def speech_status(self, chat_id) -> dict:
        chat_id = _check_chat_id(chat_id, allow_none=False)
        latest = self._last_by_chat.get(chat_id)
        observed = self._observed.get(chat_id)
        return {
            "plugin_id": PLUGIN_ID,
            "chat_id": chat_id,
            "backend_key": self._backend_key,
            "has_result": latest is not None,
            "latest": copy.deepcopy(latest) if latest is not None else None,
            "observed": copy.deepcopy(observed) if observed is not None else None,
        }

    def last_result(self, chat_id) -> dict | None:
        chat_id = _check_chat_id(chat_id, allow_none=False)
        latest = self._last_by_chat.get(chat_id)
        return copy.deepcopy(latest) if latest is not None else None

    def clear_chat(self, chat_id) -> None:
        self._last_by_chat.pop(chat_id, None)
        self._observed.pop(chat_id, None)

    # -- events ----------------------------------------------------
    async def on_event(self, event) -> None:
        """Metadata-only observation + housekeeping. NEVER raises,
        NEVER calls the backend, NEVER synthesizes.

        ``message.created`` records count / last message id /
        role / content_chars only -- the message text is never
        stored. ``chat.deleted`` clears that chat's state.
        Every other name is a no-op.
        """
        try:
            name = getattr(event, "name", None)
            if name == "message.created":
                chat_id = _event_chat_id(event)
                if chat_id is None:
                    return None
                data = getattr(event, "data", None)
                if not isinstance(data, dict):
                    data = {}
                message_id = getattr(event, "message_id", None)
                if message_id is None:
                    message_id = data.get("message_id")
                role = data.get("role")
                if not isinstance(role, str):
                    role = None
                content_chars = data.get("content_chars")
                if not _is_int(content_chars):
                    content = data.get("content")
                    content_chars = len(content) if isinstance(content, str) else None
                previous = self._observed.get(chat_id)
                count = previous["messages_observed"] + 1 if previous else 1
                self._observed[chat_id] = {
                    "chat_id": chat_id,
                    "messages_observed": count,
                    "last_message_id": message_id,
                    "last_role": role,
                    "last_content_chars": content_chars,
                    "last_observed_at": _now_iso(),
                }
            elif name == "chat.deleted":
                chat_id = _event_chat_id(event)
                if chat_id is not None:
                    self.clear_chat(chat_id)
        except Exception:
            return None
        return None


def register_plugin(registry: PluginRegistry, backend=None, *, config: TtsPluginConfig | None = None, enable: bool = False) -> tuple[PluginRecord, TtsPlugin]:
    """Register the citizen into ``registry`` (trusted code only).

    An explicit ``backend`` argument beats ``config.backend``;
    with neither, the manifest-derived config wires the
    labelled :class:`FakeTTSBackend`. Construction failure of
    a real backend happens in the host's wiring expression,
    before this function is called -- it is never caught here
    and never swapped for the fake.
    """
    if config is None:
        config = config_from_manifest(build_manifest())
    if backend is not None:
        config = dataclasses.replace(config, backend=backend)
    plugin = TtsPlugin(config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "AUDITION_SAMPLE_TEXT",
    "DECLARED_EVENTS",
    "DEFAULT_MAX_TEXT_CHARS",
    "DEFAULT_SPEAKING_RATE",
    "MAX_SPEAKING_RATE",
    "MAX_TEXT_CHARS_LIMIT",
    "MIN_SPEAKING_RATE",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "UI_LOCAL_ID",
    "VERSION",
    "TtsPlugin",
    "TtsPluginConfig",
    "TtsPluginError",
    "build_manifest",
    "config_from_manifest",
    "manifest_data",
    "register_plugin",
    "sandbox_grants",
]
