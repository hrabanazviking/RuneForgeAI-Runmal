"""Preset interop: ST-shaped preset files in/out (P-021).

Imports sampler/prompt preset files in the two public ST shapes
(text-completion and chat-completion, census ST-34 via P-002,
fixtures via P-005) plus Runmal's own native shape, into the
S207 preset system. Mirror spellings map onto the canonical
parameter bag; everything Runmal does not model rides losslessly
in ``raw`` (the complete original object) so a same-shape export
is a fixed point and unknown-but-valid fields survive verbatim.
The chat shape's ``prompts``/``prompt_order`` are carried intact
for their Part IV homes (P-049/P-051). Defensive throughout:
imported content is data, never code, and every rejection is a
typed :class:`PresetParseError`.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from runmal.presets.service import validate_params

MAX_PRESET_BYTES = 8 * 1024 * 1024
SOURCE_NATIVE = "native"
SOURCE_TEXT = "st-text"
SOURCE_CHAT = "st-chat"
_FORMATS = (SOURCE_NATIVE, SOURCE_TEXT, SOURCE_CHAT)
_VALID_ROLES = frozenset({"system", "user", "assistant"})
_FALLBACK_NAME = "Imported preset"


class PresetParseError(ValueError):
    """A preset file could not be imported."""


@dataclass
class ImportedPreset:
    name: str
    params: dict
    template_ref: str = ""
    source_format: str = SOURCE_NATIVE
    raw: dict | None = None
    prompts: list = field(default_factory=list)
    prompt_order: list = field(default_factory=list)


@dataclass
class PresetFileView:
    """The stored-preset view export_preset consumes (router-built)."""

    name: str
    params: dict
    template_ref: str = ""
    source_format: str = SOURCE_NATIVE
    raw: dict | None = None
    prompts: list = field(default_factory=list)
    prompt_order: list = field(default_factory=list)


_TEXT_MAP = {
    "temp": "temperature",
    "top_p": "top_p",
    "top_k": "top_k",
    "min_p": "min_p",
    "rep_pen": "repetition_penalty",
    "freq_pen": "frequency_penalty",
    "presence_pen": "presence_penalty",
    "genamt": "max_tokens",
    "context_length": "context_length",
    "seed": "seed",
}
_CHAT_MAP = {
    "temperature": "temperature",
    "top_p": "top_p",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty",
    "max_tokens": "max_tokens",
    "openai_max_context": "context_length",
    "seed": "seed",
}
_CHAT_FALLBACK = {"openai_max_tokens": "max_tokens"}
_TEXT_REVERSE = {v: k for k, v in _TEXT_MAP.items()}
_CHAT_REVERSE = {
    "temperature": "temperature",
    "top_p": "top_p",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty",
    "max_tokens": "max_tokens",
    "context_length": "openai_max_context",
    "seed": "seed",
}
_INT_FIELDS = frozenset({"top_k", "max_tokens", "context_length", "seed"})
_TEXT_STRONG = frozenset({
    "temp", "preset", "genamt", "rep_pen", "freq_pen",
    "presence_pen", "context_length", "min_p", "top_k",
})
_CHAT_STRONG = frozenset({
    "temperature", "frequency_penalty", "presence_penalty",
    "max_tokens", "openai_max_tokens", "openai_max_context",
    "chat_completion_source", "prompts", "prompt_order",
})


def _coerce(canonical: str, value: object) -> int | float:
    """Coerce one mapped value; booleans are never numbers."""
    if isinstance(value, bool):
        raise PresetParseError(f"param {canonical!r} must be a number")
    if canonical in _INT_FIELDS:
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    as_float = float(value)
                except ValueError:
                    as_float = None
                if as_float is not None and as_float.is_integer():
                    return int(as_float)
        raise PresetParseError(f"param {canonical!r} must be an integer")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    raise PresetParseError(f"param {canonical!r} must be a number")


def _build_bag(data: dict, mapping: dict, fallback: dict | None = None) -> dict:
    bag: dict = {}
    sources = list(mapping.items())
    if fallback:
        sources += list(fallback.items())
    seen: set[str] = set()
    for file_key, canonical in sources:
        if canonical in seen or file_key not in data:
            continue
        value = data[file_key]
        if value is None:
            continue
        seen.add(canonical)
        if canonical == "seed":
            seed = _coerce("seed", value)
            if seed == -1:
                continue  # the unset sentinel: kept in raw, not the bag
            if seed < 0:
                raise PresetParseError("param 'seed' out of range")
            bag["seed"] = seed
            continue
        bag[canonical] = _coerce(canonical, value)
    try:
        return validate_params(bag)
    except ValueError as exc:
        raise PresetParseError(str(exc)) from exc


def _validate_prompts(value: object) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PresetParseError("prompts must be a list")
    for entry in value:
        if not isinstance(entry, dict):
            raise PresetParseError("prompt entries must be objects")
        identifier = entry.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise PresetParseError("prompt entry without an identifier")
        role = entry.get("role")
        if role is not None and role not in _VALID_ROLES:
            raise PresetParseError(f"invalid prompt role: {role!r}")
    return copy.deepcopy(value)


def _validate_prompt_order(value: object) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PresetParseError("prompt_order must be a list")
    for entry in value:
        if isinstance(entry, str):
            continue
        if not isinstance(entry, dict):
            raise PresetParseError("prompt_order entries must be objects")
        identifier = entry.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise PresetParseError("prompt_order entry without an identifier")
        enabled = entry.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise PresetParseError("prompt_order enabled must be a boolean")
    return copy.deepcopy(value)


def _name_for(data: dict) -> str:
    for key in ("name", "preset"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return _FALLBACK_NAME


def _parse_native(data: dict) -> ImportedPreset:
    params_raw = data.get("params")
    if not isinstance(params_raw, dict):
        raise PresetParseError("native preset params must be an object")
    try:
        bag = validate_params(copy.deepcopy(params_raw))
    except ValueError as exc:
        raise PresetParseError(str(exc)) from exc
    prompts = _validate_prompts(data.get("prompts")) if "prompts" in data else []
    order = (
        _validate_prompt_order(data.get("prompt_order"))
        if "prompt_order" in data
        else []
    )
    embedded = data.get("raw")
    raw = copy.deepcopy(embedded) if isinstance(embedded, dict) else copy.deepcopy(data)
    template_ref = data.get("template_ref")
    return ImportedPreset(
        name=_name_for(data),
        params=bag,
        template_ref=template_ref if isinstance(template_ref, str) else "",
        source_format=SOURCE_NATIVE,
        raw=raw,
        prompts=prompts,
        prompt_order=order,
    )


def _parse_st(data: dict, source_format: str) -> ImportedPreset:
    if source_format == SOURCE_TEXT:
        bag = _build_bag(data, _TEXT_MAP)
        prompts: list = []
        order: list = []
    else:
        bag = _build_bag(data, _CHAT_MAP, _CHAT_FALLBACK)
        prompts = _validate_prompts(data.get("prompts"))
        order = _validate_prompt_order(data.get("prompt_order"))
    return ImportedPreset(
        name=_name_for(data),
        params=bag,
        template_ref="",
        source_format=source_format,
        raw=copy.deepcopy(data),
        prompts=prompts,
        prompt_order=order,
    )


def _parse_object(data: dict) -> ImportedPreset:
    if not data:
        raise PresetParseError("preset file is an empty object")
    if "params" in data:
        return _parse_native(data)
    if "prompts" in data or "prompt_order" in data:
        return _parse_st(data, SOURCE_CHAT)
    keys = set(data)
    if keys & _TEXT_STRONG:
        return _parse_st(data, SOURCE_TEXT)
    if keys & _CHAT_STRONG:
        return _parse_st(data, SOURCE_CHAT)
    if keys & {"top_p", "seed"}:
        return _parse_st(data, SOURCE_TEXT)
    raise PresetParseError("unrecognized preset file shape")


def parse_preset(data: bytes | str | dict) -> ImportedPreset:
    """Parse a preset file (bytes, text, or decoded object)."""
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_PRESET_BYTES:
            raise PresetParseError("preset file exceeds 8 MiB")
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PresetParseError("preset file is not UTF-8") from exc
        return parse_preset(text)
    if isinstance(data, str):
        if len(data.encode("utf-8")) > MAX_PRESET_BYTES:
            raise PresetParseError("preset file exceeds 8 MiB")
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise PresetParseError("preset file is not valid JSON") from exc
        if not isinstance(obj, dict):
            raise PresetParseError("preset file must be a JSON object")
        return _parse_object(obj)
    if isinstance(data, dict):
        return _parse_object(copy.deepcopy(data))
    raise PresetParseError(
        f"unsupported preset input: {type(data).__name__}"
    )


def _shape_of(raw: dict) -> str | None:
    if "params" in raw:
        return SOURCE_NATIVE
    if "prompts" in raw or "prompt_order" in raw or set(raw) & _CHAT_STRONG:
        return SOURCE_CHAT
    if set(raw) & _TEXT_STRONG:
        return SOURCE_TEXT
    return None


def _export_text(view, params: dict, raw: dict | None) -> dict:
    if raw is not None and _shape_of(raw) == SOURCE_TEXT:
        out = copy.deepcopy(raw)
        for canonical, file_key in _TEXT_REVERSE.items():
            if canonical in params:
                out[file_key] = params[canonical]
            elif canonical == "seed" and out.get("seed") == -1:
                continue  # restore the unset sentinel verbatim
            else:
                out.pop(file_key, None)
        out["preset"] = view.name
        return out
    out = {}
    for canonical, file_key in _TEXT_REVERSE.items():
        if canonical in params:
            out[file_key] = params[canonical]
    out["preset"] = view.name
    return out


def _export_chat(view, params: dict, raw: dict | None) -> dict:
    if raw is not None and _shape_of(raw) == SOURCE_CHAT:
        out = copy.deepcopy(raw)
        for canonical in (
            "temperature", "top_p", "frequency_penalty",
            "presence_penalty", "max_tokens", "seed",
        ):
            if canonical in params:
                out[canonical] = params[canonical]
            else:
                out.pop(canonical, None)
        if "max_tokens" in params:
            out["openai_max_tokens"] = params["max_tokens"]
        else:
            out.pop("openai_max_tokens", None)
        if "context_length" in params:
            out["openai_max_context"] = params["context_length"]
        else:
            out.pop("openai_max_context", None)
            out.pop("context_length", None)
        if view.prompts:
            out["prompts"] = copy.deepcopy(view.prompts)
        if view.prompt_order:
            out["prompt_order"] = copy.deepcopy(view.prompt_order)
        return out
    out = {}
    for canonical, file_key in _CHAT_REVERSE.items():
        if canonical in params:
            out[file_key] = params[canonical]
    if view.prompts:
        out["prompts"] = copy.deepcopy(view.prompts)
    if view.prompt_order:
        out["prompt_order"] = copy.deepcopy(view.prompt_order)
    return out


def _export_native(view, params: dict, raw: dict | None) -> dict:
    out: dict = {
        "name": view.name,
        "params": dict(params),
        "template_ref": view.template_ref or "",
    }
    if view.prompts:
        out["prompts"] = copy.deepcopy(view.prompts)
    if view.prompt_order:
        out["prompt_order"] = copy.deepcopy(view.prompt_order)
    if raw is not None and _shape_of(raw) != SOURCE_NATIVE:
        out["raw"] = copy.deepcopy(raw)
    return out


def export_preset(view, format: str | None = None) -> bytes:
    """Export a preset view as a file object (JSON bytes).

    Same-shape export starts from the carried raw and overlays the
    current canonical bag in the shape's own spellings, so unknown
    fields survive and removed keys stay removed. A target shape
    emits only set keys. Same-shape re-export is a fixed point.
    """
    fmt = format if format is not None else (
        getattr(view, "source_format", None) or SOURCE_NATIVE
    )
    if fmt not in _FORMATS:
        raise ValueError(f"unknown preset format: {fmt!r}")
    params = dict(getattr(view, "params", None) or {})
    raw = getattr(view, "raw", None)
    if not isinstance(raw, dict):
        raw = None
    if fmt == SOURCE_TEXT:
        obj = _export_text(view, params, raw)
    elif fmt == SOURCE_CHAT:
        obj = _export_chat(view, params, raw)
    else:
        obj = _export_native(view, params, raw)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
