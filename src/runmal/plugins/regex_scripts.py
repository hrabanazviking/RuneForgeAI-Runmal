"""Regex Scripts plugin (P-090): ST-shaped find/replace rules.

Roadmap line: "Regex scripts: ST-shaped find/replace rules
(importable format) applied at declared stages, with a safe regex
dialect and timeout discipline."

Limitations (honest, standing):

- Each rule's substitution runs in a forked child process and
  the timeout terminates that child: a timed-out rule costs
  one child process; the parent and later rules are
  unaffected. Process spawn per rule is the cost of that
  guarantee. If a child cannot be started (e.g. fork is
  unavailable), the rule falls back to running in-process
  with only a cooperative per-match deadline check, which
  cannot interrupt a single catastrophic match.
- The safe-dialect scan is a heuristic first defence, not a
  proof: ``(a|aa)+$`` passes the scan and is caught only by
  the timeout.
- The timeout budget is per rule.
- No cache: the prompt hook re-reads the store on each assembly.
- No HTTP routes / UI in this slice (the P-088 precedent); the
  hook applies the ``prompt_assembly`` stage only, other stages
  apply via explicit :func:`apply_scripts` calls only, and no
  such caller ships.
- ST-shaped, not ST-compatible: unknown ST fields are refused,
  placement codes are Runmal's own, and trim semantics are as
  defined in this module.
- Single-process file store; last-writer-wins across processes
  (the P-089 standing limitation).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.prompt.composer import ComposedMessage
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.regex-scripts"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
HOOK_ID = "regex-scripts-messages"
SLOT_LOCAL_ID = "regex-scripts"
UI_LOCAL_ID = "regex-scripts-panel"
STORE_SCHEMA = "runmal-p090-regex-scripts-v1"
STORE_DIR_NAME = "regex_scripts"
STAGES = frozenset({"user_input", "ai_output", "prompt_assembly", "display"})
STAGE_ORDER = ("user_input", "ai_output", "prompt_assembly", "display")
MAX_NAME_CHARS = 120
MAX_PATTERN_CHARS = 512
MAX_REPLACE_CHARS = 4096
MAX_TRIM_STRINGS = 32
MAX_TRIM_CHARS = 200
MAX_SCRIPTS_PER_USER = 200
MAX_IMPORT_ROWS = 500
MAX_INPUT_CHARS = 65536
MAX_OUTPUT_CHARS = 262144
PER_RULE_TIMEOUT_SECONDS = 0.25
MAX_PER_RULE_TIMEOUT_SECONDS = 1.0
MAX_QUANTIFIER_BOUND = 1000
DECLARED_EVENTS = ("chat.created", "chat.deleted")
SCOPES = frozenset({"user", "chat"})

_CANONICAL_FIELDS = frozenset({
    "id", "name", "pattern", "flags", "replace_string", "trim_strings",
    "stages", "enabled", "scope", "chat_id", "created_at", "updated_at",
})
_ALIAS_FIELDS = frozenset({
    "scriptName", "findRegex", "replaceString", "trimStrings",
    "placement", "disabled", "markdownOnly", "promptOnly",
})
_STAGE_ALIASES = {
    "user_input": "user_input", "ai_output": "ai_output",
    "prompt_assembly": "prompt_assembly", "display": "display",
    "prompt": "prompt_assembly", "markdown": "display",
    "md_display": "display",
}
_INT_STAGES = {1: "user_input", 2: "ai_output", 3: "prompt_assembly"}
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACE_RE = re.compile(r"\{(?:(\d+)(?:,(\d*))?|,(\d*))\}")
_INLINE_FLAGS_RE = re.compile(r"\(\?([A-Za-z]*)(?:-([A-Za-z]*))?([\):])")


# -- Errors ---------------------------------------------------------------


class RegexScriptError(ValueError):
    """Base refusal for this module; carries a ``.code``."""

    default_code = "regex_script_error"

    def __init__(self, message: str = "", *, code: str | None = None,
                 field: str | None = None) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = code or self.default_code
        self.field = field


class RegexScriptValidationError(RegexScriptError):
    default_code = "validation_error"


class UnknownFieldError(RegexScriptValidationError):
    default_code = "unknown_field"

    def __init__(self, message: str = "", *, unknown_keys=(), **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.unknown_keys = tuple(sorted(str(k) for k in unknown_keys))
        self.keys = self.unknown_keys


class UnsafeRegexError(RegexScriptError):
    default_code = "unsafe_regex"


class InvalidRegexError(RegexScriptError):
    default_code = "invalid_pattern"


class RegexScriptNotFoundError(RegexScriptError):
    default_code = "not_found"


class RegexScriptStoreCorruptError(RegexScriptError):
    default_code = "store_corrupt"


def _val(message: str, *, field: str | None = None,
         code: str = "validation_error") -> RegexScriptValidationError:
    return RegexScriptValidationError(message, code=code, field=field)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _check_uuid(value, field_name: str) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if not isinstance(value, str):
        raise _val(f"{field_name} must be a UUID string: {value!r}",
                   field=field_name)
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise _val(f"invalid {field_name}: {value!r}",
                   field=field_name) from None


def _normalize_flags(raw, *, field_name: str = "flags") -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise _val(f"flags must be a string: {raw!r}", field=field_name)
    seen: set[str] = set()
    for ch in raw:
        if ch in "ims":
            seen.add(ch)
        elif ch in "gu":
            continue
        else:
            raise _val(f"unsupported regex flag: {ch!r}",
                       field="flags", code="unsupported_flag")
    return "".join(ch for ch in "ims" if ch in seen)


def _flag_bits(flags: str) -> int:
    bits = 0
    if "i" in flags:
        bits |= re.IGNORECASE
    if "m" in flags:
        bits |= re.MULTILINE
    if "s" in flags:
        bits |= re.DOTALL
    return bits


# -- Safe dialect ---------------------------------------------------------


def _scan_pattern(pattern: str) -> None:
    """Single-pass token scan; raises UnsafeRegexError.

    Frames track, per group: whether any quantifier has occurred
    inside the frame at any depth, and the most recent atom
    (kind, whether it was a group whose body contained a
    quantifier, whether it is already quantified).
    """

    def new_frame() -> dict:
        return {"contains": False, "last_kind": None,
                "last_group_contains": False, "last_quantified": False}

    stack: list[dict] = [new_frame()]
    named: set[str] = set()
    i, n = 0, len(pattern)

    def set_atom(kind: str, group_contains: bool = False) -> None:
        top = stack[-1]
        top["last_kind"] = kind
        top["last_group_contains"] = group_contains
        top["last_quantified"] = False

    while i < n:
        c = pattern[i]
        top = stack[-1]
        if c == "\\":
            if i + 1 >= n:
                break
            nxt = pattern[i + 1]
            if nxt in "123456789":
                raise UnsafeRegexError(
                    f"backreference \\{nxt} is not allowed",
                    code="backreference")
            set_atom("simple")
            i += 2
            continue
        if c == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n:
                if pattern[j] == "\\":
                    j += 2
                    continue
                if pattern[j] == "]":
                    break
                j += 1
            set_atom("simple")
            i = j + 1 if j < n else n
            continue
        if c == "(":
            if pattern.startswith("(?<=", i) or pattern.startswith("(?<!", i):
                raise UnsafeRegexError("lookbehind is not allowed",
                                       code="lookbehind")
            if pattern.startswith("(?P=", i):
                raise UnsafeRegexError("backreference is not allowed",
                                       code="backreference")
            if pattern.startswith("(?P<", i):
                gt = pattern.find(">", i + 4)
                if gt == -1:
                    raise UnsafeRegexError(
                        "unsupported group construct",
                        code="unsupported_group_construct")
                name = pattern[i + 4:gt]
                if not _NAME_RE.fullmatch(name):
                    raise UnsafeRegexError(
                        "unsupported group construct",
                        code="unsupported_group_construct")
                if name in named:
                    raise UnsafeRegexError(
                        "unsupported group construct",
                        code="unsupported_group_construct")
                named.add(name)
                stack.append(new_frame())
                i = gt + 1
                continue
            if pattern.startswith("(?:", i) or pattern.startswith("(?=", i) \
                    or pattern.startswith("(?!", i):
                stack.append(new_frame())
                i += 3
                continue
            if pattern.startswith("(?", i):
                match = _INLINE_FLAGS_RE.match(pattern, i)
                if match is not None:
                    first = match.group(1) or ""
                    second = match.group(2)
                    letters_ok = all(ch in "ims" for ch in first) and (
                        second is None or all(ch in "ims" for ch in second))
                    has_letters = bool(first) or bool(second)
                    if letters_ok and has_letters:
                        if match.group(3) == ")":
                            top["last_kind"] = None
                            top["last_quantified"] = False
                            i = match.end()
                            continue
                        stack.append(new_frame())
                        i = match.end()
                        continue
                raise UnsafeRegexError(
                    "unsupported group construct",
                    code="unsupported_group_construct")
            stack.append(new_frame())
            i += 1
            continue
        if c == ")":
            if len(stack) > 1:
                frame = stack.pop()
                parent = stack[-1]
                if frame["contains"]:
                    parent["contains"] = True
                parent["last_kind"] = "group"
                parent["last_group_contains"] = frame["contains"]
                parent["last_quantified"] = False
            else:
                set_atom("simple")
            i += 1
            continue
        if c in "*+?" or c == "{":
            quant_end = None
            if c == "{":
                brace = _BRACE_RE.match(pattern, i)
                if brace is None:
                    set_atom("simple")
                    i += 1
                    continue
                # Quantifier forms Python treats as repeats:
                # {m}, {m,}, {m,n}, {,n} and {,} (the {,n} form is
                # {0,n}); {} with neither digits nor a comma is a
                # literal and never reaches this branch.
                lo_raw, hi_a, hi_b = (brace.group(1), brace.group(2),
                                      brace.group(3))
                has_comma = "," in brace.group(0)
                lo = int(lo_raw) if lo_raw else 0
                hi_raw = hi_b if hi_b is not None else hi_a
                if has_comma:
                    hi = int(hi_raw) if hi_raw not in (None, "") else None
                else:
                    hi = lo
                if lo > MAX_QUANTIFIER_BOUND or (
                        hi is not None and hi > MAX_QUANTIFIER_BOUND):
                    raise UnsafeRegexError(
                        "quantifier bound is too large",
                        code="quantifier_bound_too_large")
                quant_end = brace.end()
            else:
                quant_end = i + 1
            if top["last_kind"] is None:
                i = quant_end
                continue
            if top["last_quantified"]:
                raise UnsafeRegexError("nested quantifier is not allowed",
                                       code="nested_quantifier")
            if top["last_kind"] == "group" and top["last_group_contains"]:
                raise UnsafeRegexError("nested quantifier is not allowed",
                                       code="nested_quantifier")
            top["contains"] = True
            top["last_quantified"] = True
            if quant_end < n and pattern[quant_end] == "?":
                quant_end += 1
            i = quant_end
            continue
        if c == "|":
            top["last_kind"] = None
            top["last_quantified"] = False
            i += 1
            continue
        if c in "^$":
            top["last_kind"] = None
            top["last_quantified"] = False
            i += 1
            continue
        set_atom("simple")
        i += 1


def validate_pattern(pattern, flags: str = "") -> re.Pattern:
    """Compile ``pattern`` under the safe dialect, or refuse."""
    if not isinstance(pattern, str):
        raise _val(f"pattern must be a string: {pattern!r}", field="pattern")
    if pattern == "":
        raise _val("pattern must not be empty", field="pattern",
                   code="pattern_empty")
    if len(pattern) > MAX_PATTERN_CHARS:
        raise _val(f"pattern exceeds {MAX_PATTERN_CHARS} chars",
                   field="pattern", code="pattern_too_long")
    flags_norm = _normalize_flags(flags)
    _scan_pattern(pattern)
    try:
        return re.compile(pattern, _flag_bits(flags_norm))
    except re.error as exc:
        raise InvalidRegexError(str(exc)[:200],
                                code="invalid_pattern") from exc


# -- Replacement ----------------------------------------------------------


def _parse_replacement(template, group_count: int, group_names) -> list:
    names = set(group_names or ())
    tokens: list = []
    literal: list[str] = []

    def flush() -> None:
        if literal:
            tokens.append(("lit", "".join(literal)))
            literal.clear()

    def bad(message: str) -> RegexScriptValidationError:
        return _val(message, field="replace_string", code="bad_substitution")

    def unknown(message: str) -> RegexScriptValidationError:
        return _val(message, field="replace_string",
                    code="unknown_group_reference")

    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if ch != "$":
            literal.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            raise bad("lone trailing $ in replace_string")
        nxt = template[i + 1]
        if nxt == "$":
            literal.append("$")
            i += 2
            continue
        if nxt == "&":
            flush()
            tokens.append(("group", 0))
            i += 2
            continue
        if nxt.isdigit():
            j = i + 1
            while j < n and template[j].isdigit():
                j += 1
            number = int(template[i + 1:j])
            if number != 0 and number > group_count:
                raise unknown(f"unknown group reference: ${number}")
            flush()
            tokens.append(("group", number))
            i = j
            continue
        if nxt == "<":
            end = template.find(">", i + 2)
            if end == -1:
                raise bad("unterminated $< in replace_string")
            name = template[i + 2:end]
            if not name:
                raise bad("empty $<> in replace_string")
            if name not in names:
                raise unknown(f"unknown group reference: $<{name}>")
            flush()
            tokens.append(("group", name))
            i = end + 1
            continue
        if nxt == "{":
            end = template.find("}", i + 2)
            if end == -1:
                raise bad("unterminated ${ in replace_string")
            inner = template[i + 2:end]
            if not inner:
                raise bad("empty ${} in replace_string")
            flush()
            if inner.isdigit():
                number = int(inner)
                if number != 0 and number > group_count:
                    raise unknown(f"unknown group reference: ${{{number}}}")
                tokens.append(("group", number))
            else:
                if inner not in names:
                    raise unknown(f"unknown group reference: ${{{inner}}}")
                tokens.append(("group", inner))
            i = end + 1
            continue
        raise bad(f"bad substitution at $ in replace_string: ${nxt}")
    flush()
    return tokens


def validate_replacement(template, group_count, group_names) -> list:
    """Validate a replacement template; returns parsed tokens."""
    if not isinstance(template, str):
        raise _val(f"replace_string must be a string: {template!r}",
                   field="replace_string")
    if not isinstance(group_count, int) or isinstance(group_count, bool) \
            or group_count < 0:
        raise _val(f"group_count must be a non-negative int: {group_count!r}",
                   field="replace_string")
    return _parse_replacement(template, group_count, group_names)


def _expand_tokens(tokens, match: re.Match) -> str:
    parts: list[str] = []
    for kind, value in tokens:
        if kind == "lit":
            parts.append(value)
        else:
            try:
                piece = match.group(value)
            except Exception:
                piece = None
            parts.append(piece if piece is not None else "")
    return "".join(parts)




# -- Script documents -----------------------------------------------------


@dataclass(frozen=True)
class RegexScript:
    """One canonical regex script document."""

    id: str
    name: str
    pattern: str
    flags: str = ""
    replace_string: str = ""
    trim_strings: tuple = ()
    stages: tuple = ("user_input", "ai_output")
    enabled: bool = True
    scope: str = "user"
    chat_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.trim_strings, list):
            object.__setattr__(self, "trim_strings", tuple(self.trim_strings))
        if isinstance(self.stages, list):
            object.__setattr__(self, "stages", tuple(self.stages))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "pattern": self.pattern,
            "flags": self.flags,
            "replace_string": self.replace_string,
            "trim_strings": list(self.trim_strings),
            "stages": list(self.stages),
            "enabled": self.enabled,
            "scope": self.scope,
            "chat_id": self.chat_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_document(self) -> dict:
        return self.to_dict()


def _parse_find_regex(value):
    """Return (pattern_body, slash_flags_or_None) for findRegex."""
    if not isinstance(value, str):
        raise _val(f"pattern must be a string: {value!r}", field="pattern")
    if len(value) >= 2 and value.startswith("/"):
        last = value.rfind("/")
        if last > 0:
            body = value[1:last].replace("\\/", "/")
            return body, value[last + 1:]
    return value, None


def _decode_placement_value(item) -> str:
    if isinstance(item, bool) or not isinstance(item, (str, int)):
        raise _val(f"unsupported placement: {item!r}", field="placement",
                   code="unsupported_placement")
    if isinstance(item, int):
        stage = _INT_STAGES.get(item)
        if stage is None:
            raise _val(f"unsupported placement: {item!r}", field="placement",
                       code="unsupported_placement")
        return stage
    lowered = item.strip().lower()
    if lowered.lstrip("-").isdigit():
        raise _val(f"unsupported placement: {item!r}", field="placement",
                   code="unsupported_placement")
    stage = _STAGE_ALIASES.get(lowered)
    if stage is None:
        raise _val(f"unsupported placement: {item!r}", field="placement",
                   code="unsupported_placement")
    return stage


def _ordered_stages(stages) -> list:
    wanted = set(stages)
    return [stage for stage in STAGE_ORDER if stage in wanted]


def _decode_placement_list(value) -> list:
    items = value if isinstance(value, list) else [value]
    return _ordered_stages(_decode_placement_value(item) for item in items)


def _stages_from_placement(value, markdown_only: bool, prompt_only: bool) -> list:
    present = value is not None and not (isinstance(value, list) and not value)
    if present:
        stages = _decode_placement_list(value)
        if markdown_only:
            stages = [s for s in stages if s != "prompt_assembly"]
        if prompt_only:
            stages = [s for s in stages if s != "display"]
        if not stages:
            raise _val("stage set is empty after placement filters",
                       field="stages", code="stage_set_empty")
        return stages
    if prompt_only and markdown_only:
        return ["prompt_assembly", "display"]
    if prompt_only:
        return ["prompt_assembly"]
    if markdown_only:
        return ["display"]
    return ["user_input", "ai_output"]


def _decode_canonical_stages(value) -> list:
    if not isinstance(value, list):
        raise _val(f"stages must be a list: {value!r}", field="stages")
    if not value:
        raise _val("stage set is empty", field="stages",
                   code="stage_set_empty")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in STAGES:
            raise _val(f"unsupported placement: {item!r}", field="stages",
                       code="unsupported_placement")
        if item not in out:
            out.append(item)
    return [stage for stage in STAGE_ORDER if stage in out]


def _script_body(data, *, strict_canonical: bool = False) -> dict:
    if not isinstance(data, dict):
        raise _val("script must be an object")
    allowed = _CANONICAL_FIELDS if strict_canonical else (
        _CANONICAL_FIELDS | _ALIAS_FIELDS)
    unknown = sorted(set(data) - allowed, key=repr)
    if unknown:
        raise UnknownFieldError(
            f"script has unknown keys: {unknown}",
            unknown_keys=[str(k) for k in unknown])

    def merged(canon: str, alias: str | None):
        has_c = canon in data
        has_a = alias is not None and not strict_canonical and alias in data
        if has_c and has_a and data[canon] != data[alias]:
            raise _val(f"conflicting values for {canon!r} and {alias!r}",
                       field=canon, code="conflicting_alias")
        if has_c:
            return True, data[canon]
        if has_a:
            return True, data[alias]
        return False, None

    # name
    _, name_raw = merged("name", "scriptName")
    if not isinstance(name_raw, str):
        raise _val(f"name must be a string: {name_raw!r}", field="name")
    name = name_raw.strip()
    if not 1 <= len(name) <= MAX_NAME_CHARS:
        raise _val(f"name must be 1..{MAX_NAME_CHARS} chars", field="name")

    # pattern + flags
    slash_flags = None
    if not strict_canonical and "findRegex" in data:
        alias_body, slash_flags = _parse_find_regex(data["findRegex"])
        if "pattern" in data and data["pattern"] != alias_body:
            raise _val("conflicting values for 'pattern' and 'findRegex'",
                       field="pattern", code="conflicting_alias")
        pattern_raw = alias_body
    elif "pattern" in data:
        pattern_raw = data["pattern"]
    else:
        pattern_raw = None
    if pattern_raw is None:
        raise _val("pattern must not be empty", field="pattern",
                   code="pattern_empty")
    if not isinstance(pattern_raw, str):
        raise _val(f"pattern must be a string: {pattern_raw!r}",
                   field="pattern")
    flags_norm = _normalize_flags(data.get("flags", ""))
    if slash_flags is not None:
        slash_norm = _normalize_flags(slash_flags)
        flags_norm = "".join(
            ch for ch in "ims" if ch in set(flags_norm) | set(slash_norm))
    compiled = validate_pattern(pattern_raw, flags_norm)

    # replace_string (validated against the compiled pattern)
    _, replace_raw = merged("replace_string", "replaceString")
    if replace_raw is None:
        replace_raw = ""
    if not isinstance(replace_raw, str):
        raise _val(f"replace_string must be a string: {replace_raw!r}",
                   field="replace_string")
    if len(replace_raw) > MAX_REPLACE_CHARS:
        raise _val(f"replace_string exceeds {MAX_REPLACE_CHARS} chars",
                   field="replace_string")
    validate_replacement(replace_raw, compiled.groups, compiled.groupindex)

    # trim_strings
    _, trims_raw = merged("trim_strings", "trimStrings")
    if trims_raw is None:
        trims_raw = []
    if not isinstance(trims_raw, list):
        raise _val(f"trim_strings must be a list: {trims_raw!r}",
                   field="trim_strings")
    if len(trims_raw) > MAX_TRIM_STRINGS:
        raise _val(f"too many trim_strings (max {MAX_TRIM_STRINGS})",
                   field="trim_strings")
    trims: list[str] = []
    for item in trims_raw:
        if not isinstance(item, str) or not 1 <= len(item) <= MAX_TRIM_CHARS:
            raise _val(f"trim_strings entries must be strings of "
                       f"1..{MAX_TRIM_CHARS} chars: {item!r}",
                       field="trim_strings")
        trims.append(item)

    # markdownOnly / promptOnly (import-only, never stored)
    markdown_only = False
    prompt_only = False
    if not strict_canonical:
        for key, attr in (("markdownOnly", "markdown_only"),
                          ("promptOnly", "prompt_only")):
            if key in data:
                value = data[key]
                if not isinstance(value, bool):
                    raise _val(f"{key} must be a bool: {value!r}", field=key)
                if attr == "markdown_only":
                    markdown_only = value
                else:
                    prompt_only = value

    # stages
    has_stages = "stages" in data
    has_placement = not strict_canonical and "placement" in data
    if has_stages and has_placement:
        canonical_stages = _decode_canonical_stages(data["stages"])
        placement_stages = _stages_from_placement(
            data.get("placement"), markdown_only, prompt_only)
        if canonical_stages != placement_stages:
            raise _val("conflicting values for 'stages' and 'placement'",
                       field="stages", code="conflicting_alias")
        stages = canonical_stages
    elif has_stages:
        stages = _decode_canonical_stages(data["stages"])
    elif has_placement or not strict_canonical and (
            "markdownOnly" in data or "promptOnly" in data):
        stages = _stages_from_placement(
            data.get("placement") if has_placement else None,
            markdown_only, prompt_only)
    else:
        stages = ["user_input", "ai_output"]

    # enabled / disabled
    has_enabled = "enabled" in data
    has_disabled = not strict_canonical and "disabled" in data
    enabled = True
    if has_enabled:
        if not isinstance(data["enabled"], bool):
            raise _val(f"enabled must be a bool: {data['enabled']!r}",
                       field="enabled")
        enabled = data["enabled"]
    if has_disabled:
        if not isinstance(data["disabled"], bool):
            raise _val(f"disabled must be a bool: {data['disabled']!r}",
                       field="disabled")
        from_disabled = not data["disabled"]
        if has_enabled and enabled != from_disabled:
            raise _val("'disabled' and 'enabled' disagree",
                       field="enabled", code="contradictory_field")
        enabled = from_disabled

    # scope / chat_id
    scope = data.get("scope", "user")
    if not isinstance(scope, str) or scope not in SCOPES:
        raise _val(f"unknown scope: {scope!r}", field="scope")
    chat_raw = data.get("chat_id")
    if scope == "chat":
        chat_id = _check_uuid(chat_raw, "chat_id")
    else:
        if chat_raw is not None:
            raise _val("a user-scope script must not name a chat_id",
                       field="chat_id")
        chat_id = None

    # id
    script_id = None
    if data.get("id") is not None:
        script_id = _check_uuid(data["id"], "id")

    return {
        "id": script_id,
        "name": name,
        "pattern": pattern_raw,
        "flags": flags_norm,
        "replace_string": replace_raw,
        "trim_strings": trims,
        "stages": stages,
        "enabled": enabled,
        "scope": scope,
        "chat_id": chat_id,
    }


def script_from_data(data) -> dict:
    """A validated script body dict (canonical keys; id may be None)."""
    return _script_body(data)


def script_from_document(data) -> RegexScript:
    """A stored canonical document -> RegexScript (strict canonical)."""
    if not isinstance(data, dict):
        raise _val("script document must be an object")
    unknown = sorted(set(data) - _CANONICAL_FIELDS, key=repr)
    if unknown:
        raise UnknownFieldError(
            f"script has unknown keys: {unknown}",
            unknown_keys=[str(k) for k in unknown])
    missing = sorted(_CANONICAL_FIELDS - set(data))
    if missing:
        raise _val(f"script document is missing keys: {missing}",
                   field=missing[0], code="missing_field")
    body = _script_body(data, strict_canonical=True)
    if body["id"] is None:
        raise _val("script document id must be a UUID", field="id")
    for stamp in ("created_at", "updated_at"):
        if not isinstance(data[stamp], str) or not data[stamp]:
            raise _val(f"{stamp} must be a non-empty string", field=stamp)
    return RegexScript(
        id=body["id"], name=body["name"], pattern=body["pattern"],
        flags=body["flags"], replace_string=body["replace_string"],
        trim_strings=tuple(body["trim_strings"]),
        stages=tuple(body["stages"]), enabled=body["enabled"],
        scope=body["scope"], chat_id=body["chat_id"],
        created_at=data["created_at"], updated_at=data["updated_at"])


def script_to_data(script) -> dict:
    """A RegexScript (or script dict) -> its canonical dict."""
    if isinstance(script, RegexScript):
        return script.to_dict()
    if isinstance(script, dict):
        if "created_at" in script or "updated_at" in script:
            return script_from_document(script).to_dict()
        return script_from_data(script)
    raise _val(f"unsupported script value: {type(script).__name__}")


def script_to_document(script) -> dict:
    return script_to_data(script)



# -- Application ----------------------------------------------------------


class _RuleTimeoutError(Exception):
    """Internal: one rule exceeded its timeout budget."""


# The design name for the internal timeout signal.
_RuleTimeout = _RuleTimeoutError


class _SpawnError(Exception):
    """Internal: the per-rule child process could not be started."""


def _expand_match(tokens, trims, match: re.Match) -> str:
    """Expand one match: replacement tokens, then trim strings in order."""
    substituted = _expand_tokens(tokens, match)
    for trim in trims:
        if trim:
            substituted = substituted.replace(trim, "")
    return substituted


def _make_expansion_fn(tokens, trims, counter_list):
    """Build the counting ``Pattern.sub`` expansion function for one rule.

    ``counter_list`` is a one-element list mutated in place so the
    caller can read the match count after substitution.
    """
    def expand(match: re.Match) -> str:
        counter_list[0] += 1
        return _expand_match(tokens, trims, match)

    return expand


def _make_expand(tokens, trims, counter, deadline):
    """Deadline-checking expansion function for the in-process fallback."""
    def expand(match: re.Match) -> str:
        if time.perf_counter() > deadline:
            raise _RuleTimeoutError("rule exceeded its timeout budget")
        counter["count"] += 1
        return _expand_match(tokens, trims, match)

    return expand


def _sub_child(conn, pattern_source, flags_int, replace_template,
               trim_strings_tuple, text) -> None:
    """Child-process worker: run one substitution, report over ``conn``.

    Sends ``("ok", new_text, match_count)`` or
    ``("error", exc_class_name, detail)``; exceptions are reported
    through the pipe, never raised across it.
    """
    try:
        compiled = re.compile(pattern_source, flags_int)
        tokens = validate_replacement(
            replace_template, compiled.groups, compiled.groupindex)
        counter_list = [0]
        expand = _make_expansion_fn(
            tokens, tuple(trim_strings_tuple), counter_list)
        new_text = compiled.sub(expand, text)
        payload = ("ok", new_text, counter_list[0])
    except BaseException as exc:  # noqa: BLE001 - reported, never raised
        payload = ("error", type(exc).__name__, str(exc)[:500])
    try:
        conn.send(payload)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_sub_process(pattern_source, flags_int, replace_template, trims,
                     text, timeout_s):
    """Run one substitution in a forked child process, bounded in time.

    Returns the child's ``("ok", new_text, match_count)`` or
    ``("error", exc_class_name, detail)`` payload. Raises
    :class:`_RuleTimeoutError` when the deadline passes (the child
    is terminated and everything it produced is discarded) and
    :class:`_SpawnError` when the child cannot be started at all.
    """
    try:
        ctx = multiprocessing.get_context("fork")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
    except Exception as exc:
        raise _SpawnError(f"could not create pipe: {exc}") from exc
    proc = ctx.Process(
        target=_sub_child,
        args=(child_conn, pattern_source, flags_int, replace_template,
              tuple(trims), text))
    try:
        proc.start()
    except Exception as exc:
        parent_conn.close()
        child_conn.close()
        raise _SpawnError(f"could not start child process: {exc}") from exc
    child_conn.close()
    try:
        if not parent_conn.poll(timeout_s):
            proc.terminate()
            proc.join(1.0)
            if proc.is_alive():
                proc.kill()
                proc.join(1.0)
            raise _RuleTimeoutError(f"rule timed out after {timeout_s}s")
        try:
            payload = parent_conn.recv()
        except EOFError:
            proc.join(1.0)
            return ("error", "ChildProcessDied",
                    f"child exited without a result (exitcode={proc.exitcode})")
        proc.join(1.0)
        if proc.is_alive():
            proc.terminate()
            proc.join(1.0)
        return payload
    finally:
        parent_conn.close()


@dataclass(frozen=True)
class RegexApplicationRow:
    script_id: str
    name: str
    stage: str
    status: str
    match_count: int = 0
    duration_ms: int = 0
    detail_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "script_id": self.script_id,
            "name": self.name,
            "stage": self.stage,
            "status": self.status,
            "match_count": self.match_count,
            "duration_ms": self.duration_ms,
            "detail_code": self.detail_code,
        }


def _coerce_script(obj) -> RegexScript:
    if isinstance(obj, RegexScript):
        return obj
    if isinstance(obj, dict):
        if "created_at" in obj or "updated_at" in obj:
            return script_from_document(obj)
        body = script_from_data(obj)
        return RegexScript(
            id=body["id"] or "", name=body["name"], pattern=body["pattern"],
            flags=body["flags"], replace_string=body["replace_string"],
            trim_strings=tuple(body["trim_strings"]),
            stages=tuple(body["stages"]), enabled=body["enabled"],
            scope=body["scope"], chat_id=body["chat_id"])
    return RegexScript(
        id=str(getattr(obj, "id", "")), name=str(getattr(obj, "name", "")),
        pattern=str(getattr(obj, "pattern", "")),
        flags=str(getattr(obj, "flags", "") or ""),
        replace_string=str(getattr(obj, "replace_string", "") or ""),
        trim_strings=tuple(getattr(obj, "trim_strings", ()) or ()),
        stages=tuple(getattr(obj, "stages", ()) or ()),
        enabled=bool(getattr(obj, "enabled", True)),
        scope=str(getattr(obj, "scope", "user") or "user"),
        chat_id=getattr(obj, "chat_id", None),
        created_at=str(getattr(obj, "created_at", "") or ""),
        updated_at=str(getattr(obj, "updated_at", "") or ""))


def _finish_row(script, stage, started, status, count=0, detail=None):
    return RegexApplicationRow(
        script_id=script.id, name=script.name, stage=stage, status=status,
        match_count=count,
        duration_ms=int(round((time.perf_counter() - started) * 1000)),
        detail_code=detail)


def apply_scripts(text, stage, scripts, *,
                  timeout_s: float = PER_RULE_TIMEOUT_SECONDS):
    """Apply ``scripts`` to ``text`` at ``stage``, in order. Pure."""
    if not isinstance(stage, str) or stage not in STAGES:
        raise _val(f"unknown stage: {stage!r}", field="stage")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) \
            or not 0 < float(timeout_s) <= MAX_PER_RULE_TIMEOUT_SECONDS:
        raise _val(f"timeout_s must be in (0, "
                   f"{MAX_PER_RULE_TIMEOUT_SECONDS}]: {timeout_s!r}",
                   field="timeout_s")
    if not isinstance(text, str):
        raise _val(f"text must be a string: {text!r}", field="text")
    if len(text) > MAX_INPUT_CHARS:
        raise _val(f"input exceeds {MAX_INPUT_CHARS} chars", field="text",
                   code="input_too_large")

    current = text
    rows: list[RegexApplicationRow] = []
    for raw in scripts:
        started = time.perf_counter()
        try:
            script = _coerce_script(raw)
        except Exception as exc:
            script_id = raw.get("id") if isinstance(raw, dict) else ""
            script_name = raw.get("name") if isinstance(raw, dict) else ""
            rows.append(RegexApplicationRow(
                script_id=str(script_id or ""), name=str(script_name or ""),
                stage=stage, status="failed",
                duration_ms=int(round((time.perf_counter() - started) * 1000)),
                detail_code=type(exc).__name__))
            continue

        if not script.enabled:
            rows.append(_finish_row(script, stage, started, "skipped_disabled"))
            continue
        if stage not in tuple(script.stages):
            rows.append(_finish_row(script, stage, started, "skipped_wrong_stage"))
            continue
        try:
            compiled = validate_pattern(script.pattern, script.flags)
            tokens = validate_replacement(
                script.replace_string, compiled.groups, compiled.groupindex)
        except RegexScriptError as exc:
            rows.append(_finish_row(script, stage, started, "refused_unsafe", detail=exc.code))
            continue
        except Exception as exc:
            rows.append(_finish_row(script, stage, started, "failed", detail=type(exc).__name__))
            continue

        flags_int = _flag_bits(_normalize_flags(script.flags))
        try:
            outcome = _run_sub_process(
                script.pattern, flags_int, script.replace_string,
                tuple(script.trim_strings), current, float(timeout_s))
        except _RuleTimeoutError:
            rows.append(_finish_row(script, stage, started, "timed_out"))
            continue
        except _SpawnError:
            outcome = None
        if outcome is not None:
            if outcome[0] == "error":
                rows.append(_finish_row(script, stage, started, "failed",
                                        detail=outcome[1]))
                continue
            result, match_count = outcome[1], outcome[2]
        else:
            # Fallback: the child could not be started (e.g. fork is
            # unavailable). Run in-process with only the cooperative
            # per-match deadline check; see the module docstring.
            counter = {"count": 0}
            deadline = started + float(timeout_s)
            expand = _make_expand(tokens, list(script.trim_strings),
                                  counter, deadline)
            try:
                result = compiled.sub(expand, current)
            except _RuleTimeoutError:
                rows.append(_finish_row(script, stage, started, "timed_out",
                                        count=counter["count"]))
                continue
            except Exception as exc:
                rows.append(_finish_row(script, stage, started, "failed",
                                        count=counter["count"],
                                        detail=type(exc).__name__))
                continue
            match_count = counter["count"]
        if len(result) > MAX_OUTPUT_CHARS:
            rows.append(_finish_row(script, stage, started, "refused_output_growth",
                               count=match_count))
            continue
        if match_count == 0:
            rows.append(_finish_row(script, stage, started, "no_match"))
            continue
        current = result
        rows.append(_finish_row(script, stage, started, "applied", count=match_count))
    return current, tuple(rows)


# -- Durable per-user store (P-089 idiom) ---------------------------------


def _normalize_user_id(user_id) -> str:
    return _check_uuid(user_id, "user_id")


def store_path(user_id, base_dir=None) -> Path:
    """The owner's store file; user id UUID-normalised first."""
    normalized = _normalize_user_id(user_id)
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{normalized}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "scripts": []}


def _load_doc(user_id, base_dir=None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegexScriptStoreCorruptError(
            f"regex script store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("scripts"), list):
        raise RegexScriptStoreCorruptError(
            "regex script store has an unknown shape")
    seen_ids: set[str] = set()
    for row in doc["scripts"]:
        try:
            stored = script_from_document(row)
        except RegexScriptError as exc:
            raise RegexScriptStoreCorruptError(
                f"stored regex script is invalid: {exc}") from exc
        if stored.id in seen_ids:
            raise RegexScriptStoreCorruptError(
                f"stored regex script id is duplicated: {stored.id}")
        seen_ids.add(stored.id)
    return doc


def _save_doc(user_id, doc: dict, base_dir=None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def create_script(user_id, data, *, base_dir=None) -> dict:
    body = script_from_data(data)
    doc = _load_doc(user_id, base_dir)
    if len(doc["scripts"]) >= MAX_SCRIPTS_PER_USER:
        raise _val(f"regex script limit reached ({MAX_SCRIPTS_PER_USER})",
                   code="store_limit")
    existing_ids = {row["id"] for row in doc["scripts"]
                    if isinstance(row, dict)}
    if body["id"] is not None:
        if body["id"] in existing_ids:
            raise _val(f"duplicate script id: {body['id']}", field="id",
                       code="duplicate_id")
        script_id = body["id"]
    else:
        script_id = str(uuid.uuid4())
    now = _now_iso()
    script = RegexScript(
        id=script_id, name=body["name"], pattern=body["pattern"],
        flags=body["flags"], replace_string=body["replace_string"],
        trim_strings=tuple(body["trim_strings"]),
        stages=tuple(body["stages"]), enabled=body["enabled"],
        scope=body["scope"], chat_id=body["chat_id"],
        created_at=now, updated_at=now)
    doc["scripts"].append(script.to_dict())
    _save_doc(user_id, doc, base_dir)
    return script.to_dict()


def list_scripts(user_id, *, base_dir=None) -> list[dict]:
    doc = _load_doc(user_id, base_dir)
    return [script_to_data(script_from_document(row))
            for row in doc["scripts"]]


def get_script(user_id, script_id, *, base_dir=None) -> dict | None:
    wanted = _check_uuid(script_id, "id")
    doc = _load_doc(user_id, base_dir)
    for row in doc["scripts"]:
        stored = script_from_document(row)
        if stored.id == wanted:
            return stored.to_dict()
    return None


def update_script(user_id, script_id, data, *, base_dir=None) -> dict | None:
    wanted = _check_uuid(script_id, "id")
    body = script_from_data(data)
    doc = _load_doc(user_id, base_dir)
    for index, row in enumerate(doc["scripts"]):
        stored = script_from_document(row)
        if stored.id != wanted:
            continue
        updated = RegexScript(
            id=wanted, name=body["name"], pattern=body["pattern"],
            flags=body["flags"], replace_string=body["replace_string"],
            trim_strings=tuple(body["trim_strings"]),
            stages=tuple(body["stages"]), enabled=body["enabled"],
            scope=body["scope"], chat_id=body["chat_id"],
            created_at=stored.created_at, updated_at=_now_iso())
        doc["scripts"][index] = updated.to_dict()
        _save_doc(user_id, doc, base_dir)
        return updated.to_dict()
    return None


def delete_script(user_id, script_id, *, base_dir=None) -> bool:
    wanted = _check_uuid(script_id, "id")
    doc = _load_doc(user_id, base_dir)
    kept = [row for row in doc["scripts"]
            if not (isinstance(row, dict) and row.get("id") == wanted)]
    if len(kept) == len(doc["scripts"]):
        return False
    doc["scripts"] = kept
    _save_doc(user_id, doc, base_dir)
    return True


@dataclass(frozen=True)
class ImportRefusal:
    index: int
    name: str | None
    error_type: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"index": self.index, "name": self.name,
                "error_type": self.error_type, "code": self.code,
                "message": self.message}


@dataclass(frozen=True)
class ImportReport:
    accepted: tuple = ()
    refused: tuple = ()

    def to_dict(self) -> dict:
        return {
            "accepted": [dict(row) for row in self.accepted],
            "refused": [row.to_dict() if isinstance(row, ImportRefusal)
                        else dict(row) for row in self.refused],
        }


def import_scripts(user_id, documents, *, base_dir=None) -> ImportReport:
    if not isinstance(documents, list):
        raise _val(f"documents must be a list: {documents!r}",
                   field="documents")
    if len(documents) > MAX_IMPORT_ROWS:
        raise _val(f"too many import rows (max {MAX_IMPORT_ROWS})",
                   field="documents", code="import_limit")
    doc = _load_doc(user_id, base_dir)
    known_ids = {row["id"] for row in doc["scripts"]
                 if isinstance(row, dict)}
    accepted: list[dict] = []
    refused: list[ImportRefusal] = []
    for index, row in enumerate(documents):
        raw_name = None
        if isinstance(row, dict):
            candidate = row.get("name", row.get("scriptName"))
            if isinstance(candidate, str):
                raw_name = candidate
        try:
            body = script_from_data(row)
            if body["id"] is not None and body["id"] in known_ids:
                raise _val(f"duplicate script id: {body['id']}", field="id",
                           code="duplicate_id")
            if len(doc["scripts"]) + len(accepted) >= MAX_SCRIPTS_PER_USER:
                raise _val(f"regex script limit reached "
                           f"({MAX_SCRIPTS_PER_USER})", code="store_limit")
        except RegexScriptError as exc:
            refused.append(ImportRefusal(
                index=index, name=raw_name, error_type=type(exc).__name__,
                code=exc.code, message=str(exc)))
            continue
        script_id = body["id"] or str(uuid.uuid4())
        now = _now_iso()
        script = RegexScript(
            id=script_id, name=body["name"], pattern=body["pattern"],
            flags=body["flags"], replace_string=body["replace_string"],
            trim_strings=tuple(body["trim_strings"]),
            stages=tuple(body["stages"]), enabled=body["enabled"],
            scope=body["scope"], chat_id=body["chat_id"],
            created_at=now, updated_at=now)
        accepted.append(script.to_dict())
        known_ids.add(script_id)
    if accepted:
        doc["scripts"].extend(accepted)
        _save_doc(user_id, doc, base_dir)
    return ImportReport(accepted=tuple(accepted), refused=tuple(refused))


def export_scripts(user_id, *, base_dir=None) -> list[dict]:
    return list_scripts(user_id, base_dir=base_dir)


def select_for_prompt(scripts: list, chat_id) -> list:
    """Scope filter for prompt assembly: user scope always,
    chat scope only for its own chat."""
    out: list = []
    for row in scripts:
        if not isinstance(row, dict):
            continue
        scope = row.get("scope", "user")
        if scope == "user":
            out.append(row)
        elif scope == "chat" and chat_id is not None \
                and row.get("chat_id") == chat_id:
            out.append(row)
    return out


# -- The P-081 citizen ------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Regex Scripts",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "ST-shaped find/replace rules applied at "
                       "declared stages, with a safe regex dialect "
                       "and timeout discipline.",
        "author": "Runmal",
        "capabilities": ["chat.events", "prompt.hooks", "ui.slots"],
        "permissions": ["chat.read", "prompt.inject", "prompt.modify",
                        "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [{"id": HOOK_ID, "stage": "messages", "priority": 90}],
        "ui_slots": [{"id": UI_LOCAL_ID, "slot": "settings.panel",
                      "label": "Regex Scripts", "order": 90,
                      "payload": {"kind": "panel",
                                  "route": "regex-scripts"}}],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest() -> PluginManifest:
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class RegexScriptsPlugin:
    """The citizen: a prompt_assembly messages hook over the
    owner's durable regex scripts. Chat events are a deliberate
    no-op: chat deletion never deletes user-owned scripts."""

    def __init__(self, base_dir=None, user_id=None) -> None:
        self._base_dir = base_dir
        self.base_dir = base_dir
        self._user_id = user_id
        self.user_id = user_id

    @property
    def manifest(self) -> PluginManifest:
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(
            on_event=self.on_event,
            prompt_hooks={HOOK_ID: self.regex_messages})

    async def on_event(self, event) -> None:
        return None

    async def regex_messages(self, ctx, messages):
        """Messages-stage hook: apply prompt_assembly scripts.

        Abstains (None) when no user is bound, when no selected
        script declares the prompt_assembly stage, or when no
        message changed. Store errors propagate typed.
        """
        if self._user_id is None:
            return None
        stored = list_scripts(self._user_id, base_dir=self._base_dir)
        selected = select_for_prompt(
            stored, getattr(ctx, "chat_id", None))
        if not any("prompt_assembly" in (row.get("stages") or [])
                   for row in selected):
            return None
        objects = [script_from_document(row) for row in selected]
        out: list = []
        changed = False
        for message in messages:
            content = getattr(message, "content", None)
            if not isinstance(content, str):
                out.append(message)
                continue
            new_text, _rows = apply_scripts(
                content, "prompt_assembly", objects)
            if new_text != content:
                out.append(ComposedMessage(
                    message.role, new_text, message.slot_id))
                changed = True
            else:
                out.append(message)
        if not changed:
            return None
        return out


def register_plugin(registry: PluginRegistry, *, base_dir=None,
                    user_id=None, enable: bool = False,
                    ) -> tuple[PluginRecord, RegexScriptsPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = RegexScriptsPlugin(base_dir=base_dir, user_id=user_id)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS",
    "HOOK_ID",
    "MAX_IMPORT_ROWS",
    "MAX_INPUT_CHARS",
    "MAX_NAME_CHARS",
    "MAX_OUTPUT_CHARS",
    "MAX_PATTERN_CHARS",
    "MAX_PER_RULE_TIMEOUT_SECONDS",
    "MAX_QUANTIFIER_BOUND",
    "MAX_REPLACE_CHARS",
    "MAX_SCRIPTS_PER_USER",
    "MAX_TRIM_CHARS",
    "MAX_TRIM_STRINGS",
    "PER_RULE_TIMEOUT_SECONDS",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "SCOPES",
    "SLOT_LOCAL_ID",
    "STAGES",
    "STAGE_ORDER",
    "STORE_DIR_NAME",
    "STORE_SCHEMA",
    "UI_LOCAL_ID",
    "VERSION",
    "ImportRefusal",
    "ImportReport",
    "InvalidRegexError",
    "RegexApplicationRow",
    "RegexScript",
    "RegexScriptError",
    "RegexScriptNotFoundError",
    "RegexScriptStoreCorruptError",
    "RegexScriptValidationError",
    "RegexScriptsPlugin",
    "UnknownFieldError",
    "UnsafeRegexError",
    "apply_scripts",
    "build_manifest",
    "create_script",
    "delete_script",
    "export_scripts",
    "get_script",
    "import_scripts",
    "list_scripts",
    "manifest_data",
    "register_plugin",
    "sandbox_grants",
    "script_from_data",
    "script_from_document",
    "script_to_data",
    "script_to_document",
    "select_for_prompt",
    "store_path",
    "update_script",
    "validate_pattern",
    "validate_replacement",
]
