"""Translate plugin (P-086): the third P-081 citizen.

Roadmap line: "Translate plugin: messages in/out via local
models by default; provider-pluggable." Built from the
roadmap line and Runmal's own contracts only -- P-081 Plugin
API v1, P-082 sandbox policy, the backend / generation seams.
Pattern: P-084 (``runmal.summarise``).

Two legal shapes, both used, because ``chat.write`` is
RESERVED and honoured by no v1 surface:

- IN: a ``messages``-stage prompt hook rewrites user-role
  ``ComposedMessage``s in flight. Stored originals untouched.
- OUT: observe ``message.created``, keep translations in an
  in-memory derived store, expose them via inspect functions
  plus a UI panel declaration. Stored originals untouched.

Honesty contract: the default road is DETERMINISTIC and
labelled ``deterministic-1`` -- a tiny authored lexicon plus
a ``[deterministic:<target>]`` marker, never presented as
real translation. The model road names its true provenance
(``backend_key`` + ``model_id``) and drives the generation
service with ``plugin_events=False`` so translation calls
never recursively dispatch plugin events. Source language is
always config/argument, never detected, never invented: if
it is unknown (``None``) every surface abstains.

Sandbox stance (P-082): only v1 surface permissions are
declared, so the derived resource grant set is EMPTY. Model
access is host wiring (a ``ChatBackend`` handed to trusted
registration code), the same trust class as P-084's
``session_factory``. No persistence without a migration, so
per-chat config and the derived store live on the plugin
instance and are lost on restart.

Wiring: :func:`register_plugin` is the only registration
road. ``build_registry`` / ``create_app`` are unchanged.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from runmal.backends.messages import ChatMessage
from runmal.db.models import Chat
from runmal.generation.service import generate_events, new_request_id
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.translate"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
HOOK_ID = "translate-in"
UI_LOCAL_ID = "translation-panel"
DETERMINISTIC_VERSION = "deterministic-1"
DEFAULT_TARGET_IN = "en"
DEFAULT_TARGET_OUT = "en"
MAX_TEXT_CHARS = 4000
MAX_CHARS = MAX_TEXT_CHARS
MAX_HOOK_USER_MESSAGES = 8
DECLARED_EVENTS = ("chat.created", "chat.deleted", "message.created", "message.edited", "message.deleted")
OUT_EVENTS = frozenset({"message.created"})
INVALIDATE_EVENTS = frozenset({"message.edited", "message.deleted"})
_ORIGINAL_GENERATE_EVENTS = generate_events
_PUNCT = ".,!?;:"
_LANG_RE = re.compile(r"[a-zA-Z]{2,3}(-[a-zA-Z0-9]+)*")
_LEXICONS: dict[str, dict[str, str]] = {
    "es": {"hello": "hola", "world": "mundo", "friend": "amigo", "good": "bueno", "morning": "mañana", "night": "noche", "yes": "sí", "no": "no", "please": "por favor", "thanks": "gracias", "cat": "gato", "dog": "perro"},
    "fr": {"hello": "bonjour", "world": "monde", "friend": "ami", "good": "bon", "morning": "matin", "night": "nuit", "yes": "oui", "no": "non", "please": "s'il vous plaît", "thanks": "merci", "cat": "chat", "dog": "chien"},
    "de": {"hello": "hallo", "world": "welt", "friend": "freund", "good": "gut", "morning": "morgen", "night": "nacht", "yes": "ja", "no": "nein", "please": "bitte", "thanks": "danke", "cat": "katze", "dog": "hund"},
}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_lang(value, *, allow_none: bool = False):
    """Validate a language code; returns the normalised code.

    ``str`` matching ``[a-z]{2,3}(-[a-zA-Z0-9]+)*`` (``en``,
    ``es``, ``pt-BR``). The primary subtag is lower-cased;
    later subtags are kept verbatim. Anything else raises
    ``ValueError`` (house style), except ``None`` when
    ``allow_none`` is set, which returns ``None``.
    """
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"language code must be a string: {value!r}")
    if not isinstance(value, str):
        raise ValueError(f"language code must be a string: {value!r}")
    stripped = value.strip()
    if not _LANG_RE.fullmatch(stripped):
        raise ValueError(f"invalid language code: {value!r}")
    parts = stripped.split("-")
    return parts[0].lower() + (("-" + "-".join(parts[1:])) if len(parts) > 1 else "")


class TranslationError(RuntimeError):
    """A model-road translation failed; nothing is stored."""


@dataclass(frozen=True)
class TranslationResult:
    original: str
    translated_text: str
    source_lang: str
    target_lang: str
    road: str
    provider: str
    model: str | None = None

    def to_dict(self) -> dict:
        return {"original": self.original, "translated_text": self.translated_text, "source_lang": self.source_lang, "target_lang": self.target_lang, "road": self.road, "provider": self.provider, "model": self.model}


@runtime_checkable
class Translator(Protocol):
    async def translate(self, text: str, *, source: str, target: str) -> TranslationResult:
        ...

class DeterministicTranslator:
    """The default road, honestly labelled ``deterministic-1``.

    Pure string work; no model, no backend, no invention.
    Lexicons are keyed by TARGET language over English source
    words; unknown words pass through unchanged and a
    non-English source with no table still gets the marker
    plus pass-through -- honest, never faked fluency.
    """

    provider = DETERMINISTIC_VERSION
    version = DETERMINISTIC_VERSION
    road = "deterministic"
    model = None

    async def translate(self, text: str, *, source: str, target: str) -> TranslationResult:
        source_n = _check_lang(source)
        target_n = _check_lang(target)
        if not isinstance(text, str):
            raise ValueError(f"text must be a string: {text!r}")
        if source_n == target_n:
            body = text
            translated = text
        else:
            lexicon = _LEXICONS.get(target_n, {})
            out_tokens: list[str] = []
            for token in text.split():
                core, punct = token, ""
                if token and token[-1] in _PUNCT:
                    core, punct = token[:-1], token[-1]
                if not core:
                    out_tokens.append(token)
                    continue
                sub = lexicon.get(core.lower())
                if sub is None:
                    out_tokens.append(core + punct)
                else:
                    if core[:1].isupper() and sub:
                        sub = sub[:1].upper() + sub[1:]
                    out_tokens.append(sub + punct)
            body = " ".join(out_tokens)
            translated = f"[deterministic:{target_n}] " + body
        return TranslationResult(original=text, translated_text=translated, source_lang=source_n, target_lang=target_n, road=self.road, provider=self.provider, model=None)


class _CallableTranslator:
    """Wrap a plain callable as a Translator (road ``custom``)."""

    road = "custom"
    provider = "callable"
    model = None

    def __init__(self, func) -> None:
        self._func = func

    async def translate(self, text: str, *, source: str, target: str) -> TranslationResult:
        try:
            result = self._func(text, source=source, target=target)
        except TypeError:
            result = self._func(text, source, target)
        if inspect.isawaitable(result):
            result = await result
        return _coerce_result(result, text=text, source=source, target=target, road=self.road, provider=self.provider, model=None)

def _coerce_result(result, *, text, source, target, road, provider, model):
    if isinstance(result, TranslationResult):
        return result
    if isinstance(result, str):
        return TranslationResult(original=text, translated_text=result, source_lang=source, target_lang=target, road=road, provider=provider, model=model)
    if isinstance(result, dict):
        return TranslationResult(original=result.get("original", text), translated_text=result.get("translated_text", result.get("text", "")), source_lang=result.get("source_lang", source), target_lang=result.get("target_lang", target), road=result.get("road", road), provider=result.get("provider", provider), model=result.get("model", model))
    raise TypeError(f"translator returned an unsupported result: {type(result).__name__}")


async def _invoke_translator(translator, text, *, source, target):
    translate_attr = getattr(translator, "translate", None)
    if callable(translate_attr):
        result = translate_attr(text, source=source, target=target)
        if inspect.isawaitable(result):
            result = await result
        road = getattr(translator, "road", "custom")
        provider = getattr(translator, "provider", getattr(translator, "version", "callable"))
        model = getattr(translator, "model", None)
        if not isinstance(model, str):
            model = None if model is None else str(model)
        return _coerce_result(result, text=text, source=source, target=target, road=str(road), provider=str(provider), model=model)
    if callable(translator):
        return await _CallableTranslator(translator).translate(text, source=source, target=target)
    raise ValueError("translator must expose .translate or be callable")


class ModelTranslator:
    """Model road through the generation service (host wiring)."""

    road = "model"

    def __init__(self, backend, *, model_id: str | None = None) -> None:
        if backend is None or not callable(getattr(backend, "chat_stream", None)):
            raise ValueError("backend must expose .chat_stream")
        self.backend = backend
        self.provider = getattr(backend, "backend_key", None) or "unknown"
        default_model = getattr(backend, "default_model", None)
        default_id = getattr(default_model, "model_id", None) if default_model is not None else None
        self.model = model_id or default_id
        self.model_id = self.model

    async def translate(self, text: str, *, source: str, target: str) -> TranslationResult:
        source_n = _check_lang(source)
        target_n = _check_lang(target)
        if not isinstance(text, str):
            raise ValueError(f"text must be a string: {text!r}")
        if source_n == target_n:
            return TranslationResult(original=text, translated_text=text, source_lang=source_n, target_lang=target_n, road=self.road, provider=self.provider, model=self.model)
        messages = [ChatMessage("system", f"Translate the user's text from {source_n} to {target_n}. Output only the translation, no commentary."), ChatMessage("user", text)]
        from runmal.generation import service as generation_service
        svc_fn = generation_service.generate_events
        mod_fn = globals().get("generate_events")
        if mod_fn is not None and svc_fn is _ORIGINAL_GENERATE_EVENTS and mod_fn is not _ORIGINAL_GENERATE_EVENTS:
            gen_fn = mod_fn
        else:
            gen_fn = svc_fn
        parts: list[str] = []
        finish = None
        error_code = None
        try:
            async for event in gen_fn(generation_service.new_request_id(), messages=messages, backend=self.backend, plugin_events=False):
                kind = event.get("type")
                if kind == "token":
                    parts.append(event.get("text", ""))
                elif kind == "error":
                    error_code = event.get("code") or "backend_error"
                elif kind == "done":
                    finish = event.get("finish_reason")
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"generation failed: {exc}") from exc
        out = "".join(parts)
        if error_code is not None:
            raise TranslationError(f"generation failed: {error_code}")
        if finish in (None, "cancelled", "error"):
            raise TranslationError(f"generation did not finish cleanly: {finish}")
        if not out or not out.strip():
            raise TranslationError("generation produced no text")
        return TranslationResult(original=text, translated_text=out, source_lang=source_n, target_lang=target_n, road=self.road, provider=self.provider, model=self.model)

async def translate_text(translator, text: str, *, source: str, target: str) -> TranslationResult:
    """Pure entry: validate, call the translator, label honestly.

    ``source == target`` returns the text unchanged through the
    translator's own road labelling: the translator is called
    anyway, so provenance names who decided.
    """
    if not isinstance(text, str):
        raise ValueError(f"text must be a string: {text!r}")
    source_n = _check_lang(source)
    target_n = _check_lang(target)
    if translator is None:
        raise ValueError("translator must expose .translate or be callable")
    result = await _invoke_translator(translator, text, source=source_n, target=target_n)
    updates: dict = {}
    if result.original != text:
        updates["original"] = text
    if result.source_lang != source_n:
        updates["source_lang"] = source_n
    if result.target_lang != target_n:
        updates["target_lang"] = target_n
    if source_n == target_n and result.translated_text != text:
        updates["translated_text"] = text
    if updates:
        result = dataclasses.replace(result, **updates)
    return result


@dataclass(frozen=True)
class TranslateConfig:
    """Plugin-global config, cf. P-084 ``SummariseConfig``."""

    default_target_in: str = DEFAULT_TARGET_IN
    default_target_out: str = DEFAULT_TARGET_OUT
    max_chars: int = MAX_TEXT_CHARS
    translator: object = None
    backend: object = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "default_target_in", _check_lang(self.default_target_in))
        object.__setattr__(self, "default_target_out", _check_lang(self.default_target_out))
        if not _is_int(self.max_chars) or self.max_chars < 1:
            raise ValueError(f"max_chars must be an int >= 1: {self.max_chars!r}")
        if self.translator is not None:
            if not callable(getattr(self.translator, "translate", None)) and not callable(self.translator):
                raise ValueError("translator must expose .translate or be callable")
        if self.backend is not None:
            if not callable(getattr(self.backend, "chat_stream", None)):
                raise ValueError("backend must expose .chat_stream")

    @property
    def effective_translator(self):
        if self.translator is not None:
            if callable(getattr(self.translator, "translate", None)):
                return self.translator
            return _CallableTranslator(self.translator)
        if self.backend is not None:
            return ModelTranslator(self.backend)
        return DeterministicTranslator()


@dataclass(frozen=True)
class ChatTranslateConfig:
    """Per-chat config; ``source_lang=None`` abstains everywhere."""

    enabled: bool = False
    in_enabled: bool = True
    out_enabled: bool = True
    source_lang: str | None = None
    target_in: str | None = None
    target_out: str | None = None

    def __post_init__(self) -> None:
        for name in ("enabled", "in_enabled", "out_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a bool: {getattr(self, name)!r}")
        object.__setattr__(self, "source_lang", _check_lang(self.source_lang, allow_none=True))
        object.__setattr__(self, "target_in", _check_lang(self.target_in, allow_none=True))
        object.__setattr__(self, "target_out", _check_lang(self.target_out, allow_none=True))

def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Translate",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Per-chat translation: user messages translated in flight; assistant messages translated into a derived, inspectable view. Originals never change.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "prompt.hooks", "ui.slots"],
        "permissions": ["chat.read", "prompt.modify", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [{"id": HOOK_ID, "stage": "messages", "priority": 100}],
        "ui_slots": [{"id": UI_LOCAL_ID, "slot": "chat.sidebar", "label": "Translation", "order": 110, "payload": {"kind": "panel", "route": "translation"}}],
        "settings": {"schema": {"target_in": {"type": "string"}, "target_out": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1}}, "defaults": {"target_in": "en", "target_out": "en", "max_chars": MAX_TEXT_CHARS}},
        "enabled_by_default": False,
    }


def build_manifest() -> PluginManifest:
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest) -> TranslateConfig:
    """Lenient like P-084: invalid values fall back to constants."""
    defaults: dict = {}
    settings = manifest.get("settings") if isinstance(manifest, dict) else getattr(manifest, "settings", None)
    if isinstance(settings, dict):
        raw = settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    def _lang(key, fallback):
        try:
            return _check_lang(defaults.get(key, fallback))
        except ValueError:
            return fallback
    target_in = _lang("target_in", DEFAULT_TARGET_IN)
    target_out = _lang("target_out", DEFAULT_TARGET_OUT)
    max_chars = defaults.get("max_chars", MAX_TEXT_CHARS)
    if not _is_int(max_chars) or max_chars < 1:
        max_chars = MAX_TEXT_CHARS
    return TranslateConfig(default_target_in=target_in, default_target_out=target_out, max_chars=max_chars)


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))

class TranslatePlugin:
    """The citizen: IN prompt transform + OUT derived view.

    ``session_factory`` is host bootstrap wiring; with no
    factory the OUT event surface is inert, while the IN hook
    (in-memory config only) still works / abstains cleanly.
    """

    def __init__(self, session_factory=None, config: TranslateConfig | None = None) -> None:
        self._session_factory = session_factory
        self.config = config or config_from_manifest(build_manifest())
        self._chat_configs: dict[str, ChatTranslateConfig] = {}
        self._translations: dict[tuple[str, str], dict] = {}

    @property
    def manifest(self) -> PluginManifest:
        return build_manifest()

    def bind_session_factory(self, session_factory) -> None:
        self._session_factory = session_factory

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event, prompt_hooks={HOOK_ID: self.translate_in})

    # -- per-chat config -------------------------------------
    def set_chat_config(self, chat_id, cfg: ChatTranslateConfig | None = None, **overrides) -> None:
        if cfg is None and "config" in overrides:
            cfg = overrides.pop("config")
        if cfg is None:
            cfg = ChatTranslateConfig(**overrides) if overrides else ChatTranslateConfig()
        elif isinstance(cfg, dict):
            cfg = ChatTranslateConfig(**{**cfg, **overrides})
        elif overrides:
            cfg = dataclasses.replace(cfg, **overrides)
        self._chat_configs[str(chat_id)] = cfg

    def get_chat_config(self, chat_id) -> ChatTranslateConfig:
        return self._chat_configs.get(str(chat_id), ChatTranslateConfig())

    def clear_chat_config(self, chat_id) -> None:
        key = str(chat_id)
        self._chat_configs.pop(key, None)
        for store_key in [k for k in self._translations if k[0] == key]:
            del self._translations[store_key]

    def _chat_settings(self, chat_id):
        cfg = self.get_chat_config(chat_id)
        target_in = cfg.target_in if cfg.target_in is not None else self.config.default_target_in
        target_out = cfg.target_out if cfg.target_out is not None else self.config.default_target_out
        return (cfg.enabled, cfg.in_enabled, cfg.out_enabled, cfg.source_lang, target_in, target_out)

    # -- inspect API ------------------------------------------
    def translations_for(self, chat_id) -> list[dict]:
        key = str(chat_id)
        return [dict(row) for row in self._translations.values() if row.get("chat_id") == key]

    def translation_for_message(self, chat_id, message_id) -> dict | None:
        row = self._translations.get((str(chat_id), str(message_id)))
        return dict(row) if row is not None else None

    def latest_translation(self, chat_id) -> dict | None:
        rows = self.translations_for(chat_id)
        return rows[-1] if rows else None

    def translation_status(self, chat_id) -> dict:
        enabled, in_enabled, out_enabled, source_lang, target_in, target_out = self._chat_settings(chat_id)
        rows = self.translations_for(chat_id)
        return {"plugin_id": PLUGIN_ID, "chat_id": str(chat_id), "config": {"enabled": enabled, "in_enabled": in_enabled, "out_enabled": out_enabled, "source_lang": source_lang, "target_in": target_in, "target_out": target_out}, "count": len(rows), "latest": rows[-1] if rows else None}

    async def translate_text(self, text: str, *, source: str, target: str) -> TranslationResult:
        return await translate_text(self.config.effective_translator, text, source=source, target=target)

    # -- IN hook ----------------------------------------------
    async def translate_in(self, ctx, messages):
        """Messages-stage hook: translate user messages in flight.

        Any failed step returns ``None`` (abstain): the original
        composition flows unchanged. Translator failure is an
        abstention, never a broken prompt.
        """
        try:
            chat_id = getattr(ctx, "chat_id", None)
            if chat_id is None:
                return None
            enabled, in_enabled, _out, source_lang, target_in, _tout = self._chat_settings(chat_id)
            if not enabled or not in_enabled:
                return None
            if source_lang is None or source_lang == target_in:
                return None
            max_chars = self.config.max_chars
            translated_count = 0
            changed = False
            new_messages: list = []
            for msg in messages:
                if getattr(msg, "role", None) == "user" and getattr(msg, "content", None) and len(msg.content) <= max_chars and translated_count < MAX_HOOK_USER_MESSAGES:
                    try:
                        result = await self.translate_text(msg.content, source=source_lang, target=target_in)
                    except Exception:
                        return None
                    new_messages.append(dataclasses.replace(msg, content=result.translated_text))
                    translated_count += 1
                    changed = True
                else:
                    new_messages.append(msg)
            if not changed:
                return None
            return new_messages
        except Exception:
            return None

    # -- OUT path ---------------------------------------------
    async def on_event(self, event) -> None:
        name = getattr(event, "name", None)
        data = getattr(event, "data", None)
        if not isinstance(data, dict):
            data = {}
        def _id(attr, key):
            return getattr(event, attr, None) or data.get(key)
        if name in INVALIDATE_EVENTS:
            chat_id, message_id = _id("chat_id", "chat_id"), _id("message_id", "message_id")
            if chat_id and message_id:
                self._translations.pop((str(chat_id), str(message_id)), None)
            return
        if name == "chat.deleted":
            chat_id = _id("chat_id", "chat_id")
            if chat_id:
                self.clear_chat_config(chat_id)
            return
        if name == "chat.created":
            return
        if name not in OUT_EVENTS:
            return
        # message.created only: unbound inertness gates here alone.
        if self._session_factory is None:
            return
        chat_id, message_id = _id("chat_id", "chat_id"), _id("message_id", "message_id")
        if not chat_id or not message_id:
            return
        if data.get("role") != "assistant":
            return
        content = data.get("content")
        if not isinstance(content, str):
            return
        enabled, _in, out_enabled, source_lang, _tin, target_out = self._chat_settings(chat_id)
        if not enabled or not out_enabled:
            return
        if source_lang is None or source_lang == target_out:
            return
        if not (0 < len(content) <= self.config.max_chars):
            return
        try:
            async with self._session_factory() as session:
                chat = await session.get(Chat, chat_id)
                if chat is None:
                    return
                _owner_id = chat.user_id
        except Exception:
            return
        try:
            result = await self.translate_text(content, source=source_lang, target=target_out)
        except Exception:
            return
        record = result.to_dict()
        record["chat_id"] = str(chat_id)
        record["message_id"] = str(message_id)
        self._translations[(str(chat_id), str(message_id))] = record

def register_plugin(registry: PluginRegistry, session_factory=None, *, config: TranslateConfig | None = None, enable: bool = False) -> tuple[PluginRecord, TranslatePlugin]:
    """Register the citizen into ``registry`` (trusted code only).

    Returns the record and the plugin instance. ``enable=True``
    performs the owner's enable verb immediately; the default
    leaves the plugin REGISTERED, receiving and contributing
    nothing until enabled.
    """
    plugin = TranslatePlugin(session_factory, config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = ["DECLARED_EVENTS", "DEFAULT_TARGET_IN", "DEFAULT_TARGET_OUT", "DETERMINISTIC_VERSION", "HOOK_ID", "INVALIDATE_EVENTS", "MAX_HOOK_USER_MESSAGES", "MAX_TEXT_CHARS", "OUT_EVENTS", "PLUGIN_ID", "PLUGIN_VERSION", "UI_LOCAL_ID", "VERSION", "ChatTranslateConfig", "DeterministicTranslator", "ModelTranslator", "TranslateConfig", "TranslatePlugin", "TranslationError", "TranslationResult", "Translator", "build_manifest", "config_from_manifest", "manifest_data", "register_plugin", "sandbox_grants", "translate_text"]
