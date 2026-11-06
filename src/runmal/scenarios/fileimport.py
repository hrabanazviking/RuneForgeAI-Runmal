"""Scenario file import (P-026): Voxta-shaped and native files in.

Parses a scenario file into the typed contract in
``filemodels``: name, description, scenario text, flow and
style, template and system prompt, roles, bootstrap messages,
impersonation and narrator, memory-book references, initial
flags and variables, contexts, and parent / thumbnail refs.

Clean-room basis: the Voxta shape is as recorded in P-003's
census (VX-28..VX-44 + VX-60) from public documentation.
The native shape is Runmal's own. No SillyTavern/Voxta
source was read.

Defensive import summary: size is capped at
``MAX_SCENARIO_BYTES`` before decoding, undecodable or
non-JSON input is refused with a typed ``ScenarioParseError``,
a file must be a JSON object with a non-empty name, and
malformed roles / bootstrap messages / contexts / flags /
variables are refused rather than guessed at. Values that
carry machinery Runmal does not map in this slice are not
dropped: top-level Voxta scripting / event / action / tool /
button / control / HUD / app / asset / template keys are
reported as unmappable and carried verbatim in
``unmappable_values`` for hand-back on Voxta export, and
every other unconsumed top-level key is carried in ``extra``
(and listed in the report's ``carried``). Unknown flow,
style, system-prompt mode and bootstrap-kind values fall
back with a warning, never silently.
"""

from __future__ import annotations

import copy
import json

from .filemodels import (
    BOOTSTRAP_KINDS,
    FLOWS,
    KIND_ACTION,
    KIND_APP,
    KIND_ASSET,
    KIND_BUTTON,
    KIND_CONTROL,
    KIND_EVENT,
    KIND_HUD,
    KIND_SCRIPTING,
    KIND_TEMPLATE,
    KIND_TOOL,
    MAX_SCENARIO_BYTES,
    SOURCE_NATIVE,
    SOURCE_VOXTA,
    STYLES,
    BootstrapMessage,
    ScenarioContext,
    ScenarioFile,
    ScenarioImportReport,
    ScenarioParseError,
    ScenarioRole,
    UnmappableElement,
)

__all__ = ["parse_scenario_file"]


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(k) for k in value]
    return []


#: Keys whose presence marks a file as native even without
#: an explicit ``source_format`` marker.
_STRONG_NATIVE_KEYS = frozenset(
    {
        "scenario_text",
        "system_prompt_text",
        "system_prompt_mode",
        "bootstrap_messages",
        "memory_book_refs",
        "initial_flags",
        "initial_variables",
        "impersonation_name",
        "impersonation_description",
        "narrator_name",
        "narrator_voice",
        "parent_ref",
        "thumbnail_ref",
    }
)

#: Voxta top-level keys carrying machinery this slice does
#: not map, in report order, mapped to their report kind.
_VOXTA_UNMAPPABLE = {
    "scripts": KIND_SCRIPTING,
    "scripting": KIND_SCRIPTING,
    "events": KIND_EVENT,
    "actions": KIND_ACTION,
    "tools": KIND_TOOL,
    "buttons": KIND_BUTTON,
    "controls": KIND_CONTROL,
    "hud": KIND_HUD,
    "hudWidgets": KIND_HUD,
    "apps": KIND_APP,
    "appConfig": KIND_APP,
    "assets": KIND_ASSET,
    "templateScripts": KIND_TEMPLATE,
}

#: Voxta top-level keys consumed by the mapping (mapped
#: primary / alias keys, plus ``source_format`` and the
#: unmappable keys); anything else is carried in ``extra``.
_VOXTA_CONSUMED = frozenset(
    {
        "name",
        "description",
        "scenario",
        "scenarioText",
        "chatFlow",
        "flow",
        "chatStyle",
        "style",
        "roles",
        "systemPrompt",
        "scenarioTemplate",
        "template",
        "bootstrapMessages",
        "bootstrap",
        "impersonation",
        "narrator",
        "memoryBooks",
        "memory_books",
        "books",
        "flags",
        "initialFlags",
        "variables",
        "initialVariables",
        "contexts",
        "parent",
        "parentScenario",
        "thumbnail",
        "source_format",
    }
    | set(_VOXTA_UNMAPPABLE)
)

#: Native top-level keys consumed by the mapping.
_NATIVE_CONSUMED = frozenset(
    {
        "name",
        "description",
        "scenario_text",
        "flow",
        "style",
        "template_text",
        "system_prompt_text",
        "system_prompt_mode",
        "roles",
        "bootstrap_messages",
        "impersonation_name",
        "impersonation_description",
        "narrator_name",
        "narrator_voice",
        "memory_book_refs",
        "initial_flags",
        "initial_variables",
        "contexts",
        "parent_ref",
        "thumbnail_ref",
        "source_format",
    }
)

#: Report ``mapped`` names, in their fixed order.
_MAPPED_ORDER = (
    "name",
    "description",
    "scenario_text",
    "flow",
    "style",
    "template_text",
    "system_prompt_text",
    "roles",
    "bootstrap_messages",
    "impersonation",
    "narrator",
    "memory_book_refs",
    "initial_flags",
    "initial_variables",
    "contexts",
    "parent_ref",
    "thumbnail_ref",
)

_SYSTEM_PROMPT_MODES = ("", "replace", "extend")


def _pick(data: dict, *keys: str):
    """First present, non-None value among ``keys``."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    for key in keys:
        if key in data:
            return data[key]
    return None


def _bool_or_true(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return bool(value)


def _normalize_flow(value: str, warnings: list[str]) -> str:
    norm = value.strip().lower()
    if not norm:
        return "chat"
    if norm in FLOWS:
        return norm
    warnings.append(f"unknown flow {norm!r}; fell back to 'chat'")
    return "chat"


def _normalize_style(value: str, warnings: list[str]) -> str:
    norm = value.strip().lower()
    if not norm:
        return ""
    if norm in STYLES:
        return norm
    warnings.append(f"unknown style {norm!r}; style dropped")
    return ""


def _validate_mode(mode: str, warnings: list[str]) -> str:
    if mode in _SYSTEM_PROMPT_MODES:
        return mode
    warnings.append(f"unknown system prompt mode {mode!r}; mode dropped")
    return ""


def _parse_bootstrap_kind(
    raw_kind: str, warnings: list[str]
) -> str:
    kind = raw_kind.strip().lower() or "message"
    if kind not in BOOTSTRAP_KINDS:
        warnings.append(
            f"bootstrap message kind {kind!r} is not natively "
            "mapped; carried as 'message'"
        )
        return "message"
    return kind


def _parse_bootstrap_block(
    text_block: str, warnings: list[str]
) -> list[BootstrapMessage]:
    warnings.append(
        "bootstrap block form: line types are not declared "
        "in the file and were not inferred"
    )
    messages = []
    for line in text_block.splitlines():
        line = line.strip()
        if not line:
            continue
        messages.append(
            BootstrapMessage(
                kind="message", text=line, role="", raw={"text": line}
            )
        )
    return messages


def _coerce_object(data: bytes | str | dict) -> dict:
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_SCENARIO_BYTES:
            raise ScenarioParseError("scenario file too large")
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScenarioParseError(
                "scenario file is not UTF-8"
            ) from exc
        return _loads_object(text)
    if isinstance(data, str):
        if len(data.encode("utf-8")) > MAX_SCENARIO_BYTES:
            raise ScenarioParseError("scenario file too large")
        return _loads_object(data)
    if isinstance(data, dict):
        return data
    raise ScenarioParseError("scenario file must be a JSON object")


def _loads_object(text: str) -> dict:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScenarioParseError(
            "scenario file is not valid JSON"
        ) from exc
    if not isinstance(obj, dict):
        raise ScenarioParseError("scenario file must be a JSON object")
    return obj


def _require_name(data: dict) -> str:
    name = _as_str(data.get("name")).strip()
    if not name:
        raise ScenarioParseError("scenario file has no name")
    return name


def _mapped_list(present: set[str]) -> list[str]:
    return [field for field in _MAPPED_ORDER if field in present]


def _parse_voxta(data: dict, raw: dict) -> ScenarioFile:
    warnings: list[str] = []
    present: set[str] = set()
    if "name" in data:
        present.add("name")
    if "description" in data:
        present.add("description")
    if "scenario" in data or "scenarioText" in data:
        present.add("scenario_text")
    if "chatFlow" in data or "flow" in data:
        present.add("flow")
    if "chatStyle" in data or "style" in data:
        present.add("style")
    if "scenarioTemplate" in data or "template" in data:
        present.add("template_text")
    if "systemPrompt" in data:
        present.add("system_prompt_text")
    if "roles" in data:
        present.add("roles")
    if "bootstrapMessages" in data or "bootstrap" in data:
        present.add("bootstrap_messages")
    if "impersonation" in data:
        present.add("impersonation")
    if "narrator" in data:
        present.add("narrator")
    if (
        "memoryBooks" in data
        or "memory_books" in data
        or "books" in data
    ):
        present.add("memory_book_refs")
    if "flags" in data or "initialFlags" in data:
        present.add("initial_flags")
    if "variables" in data or "initialVariables" in data:
        present.add("initial_variables")
    if "contexts" in data:
        present.add("contexts")
    if "parent" in data or "parentScenario" in data:
        present.add("parent_ref")
    if "thumbnail" in data:
        present.add("thumbnail_ref")

    name = _require_name(data)
    description = _as_str(data.get("description"))
    scenario_text = _as_str(_pick(data, "scenario", "scenarioText"))

    if "flow" in present:
        flow = _normalize_flow(
            _as_str(_pick(data, "chatFlow", "flow")), warnings
        )
    else:
        flow = "chat"

    if "style" in present:
        style = _normalize_style(
            _as_str(_pick(data, "chatStyle", "style")), warnings
        )
    else:
        style = ""

    template_text = _as_str(
        _pick(data, "scenarioTemplate", "template")
    )

    system_prompt_text = ""
    system_prompt_mode = ""
    if "systemPrompt" in data:
        sp = data["systemPrompt"]
        if isinstance(sp, str):
            system_prompt_text = sp
        elif isinstance(sp, dict):
            system_prompt_text = _as_str(sp.get("text"))
            mode = _as_str(sp.get("mode")).strip().lower()
            system_prompt_mode = _validate_mode(mode, warnings)

    roles: list[ScenarioRole] = []
    if "roles" in data:
        roles_value = data["roles"]
        if not isinstance(roles_value, list):
            raise ScenarioParseError("roles must be a list")
        for entry in roles_value:
            if not isinstance(entry, dict):
                raise ScenarioParseError(
                    "role entries must be objects"
                )
            roles.append(
                ScenarioRole(
                    name=_as_str(
                        entry.get("name") or entry.get("role")
                    ),
                    character_name=_as_str(
                        entry.get("characterName")
                        or entry.get("character")
                    ),
                    enabled_on_start=_bool_or_true(
                        entry.get("enabledOnStart")
                    ),
                    can_speak=_bool_or_true(entry.get("canSpeak")),
                    raw=copy.deepcopy(entry),
                )
            )

    bootstrap_messages: list[BootstrapMessage] = []
    if "bootstrapMessages" in data or "bootstrap" in data:
        boot = _pick(data, "bootstrapMessages", "bootstrap")
        if isinstance(boot, list):
            for entry in boot:
                if not isinstance(entry, dict):
                    raise ScenarioParseError(
                        "bootstrap message entries must be objects"
                    )
                kind = _parse_bootstrap_kind(
                    _as_str(entry.get("kind") or entry.get("type")),
                    warnings,
                )
                bootstrap_messages.append(
                    BootstrapMessage(
                        kind=kind,
                        text=_as_str(entry.get("text")),
                        role=_as_str(entry.get("role")),
                        raw=copy.deepcopy(entry),
                    )
                )
        elif isinstance(boot, str):
            bootstrap_messages = _parse_bootstrap_block(
                boot, warnings
            )
        else:
            raise ScenarioParseError(
                "bootstrap messages must be a list or a string"
            )

    impersonation_name = ""
    impersonation_description = ""
    if "impersonation" in data:
        imp = data["impersonation"]
        if isinstance(imp, str):
            impersonation_name = imp
        elif isinstance(imp, dict):
            impersonation_name = _as_str(imp.get("name"))
            impersonation_description = _as_str(
                imp.get("description")
            )

    narrator_name = ""
    narrator_voice = ""
    if "narrator" in data:
        nar = data["narrator"]
        if isinstance(nar, str):
            narrator_name = nar
        elif isinstance(nar, dict):
            narrator_name = _as_str(nar.get("name"))
            narrator_voice = _as_str(nar.get("voice"))

    memory_book_refs: list[str] = []
    if "memory_book_refs" in present:
        books = _pick(data, "memoryBooks", "memory_books", "books")
        if isinstance(books, list):
            for entry in books:
                if isinstance(entry, str):
                    memory_book_refs.append(entry)
                elif isinstance(entry, dict):
                    ref = _as_str(
                        entry.get("name") or entry.get("id")
                    )
                    if ref:
                        memory_book_refs.append(ref)
        elif isinstance(books, str):
            memory_book_refs = [books]
        elif isinstance(books, dict):
            ref = _as_str(books.get("name") or books.get("id"))
            if ref:
                memory_book_refs = [ref]
        else:
            warnings.append(
                f"memory books value ignored: "
                f"{type(books).__name__}"
            )

    initial_flags: dict = {}
    if "initial_flags" in present:
        flags_value = _pick(data, "flags", "initialFlags")
        if isinstance(flags_value, dict):
            initial_flags = copy.deepcopy(flags_value)
        elif isinstance(flags_value, list):
            initial_flags = {
                entry: True
                for entry in flags_value
                if isinstance(entry, str)
            }
        else:
            raise ScenarioParseError(
                "flags must be an object or a list"
            )

    initial_variables: dict = {}
    if "initial_variables" in present:
        vars_value = _pick(data, "variables", "initialVariables")
        if isinstance(vars_value, dict):
            initial_variables = copy.deepcopy(vars_value)
        else:
            raise ScenarioParseError("variables must be an object")

    contexts: list[ScenarioContext] = []
    if "contexts" in data:
        contexts_value = data["contexts"]
        if not isinstance(contexts_value, list):
            raise ScenarioParseError("contexts must be a list")
        for entry in contexts_value:
            if not isinstance(entry, dict):
                raise ScenarioParseError(
                    "context entries must be objects"
                )
            contexts.append(
                ScenarioContext(
                    key=_as_str(entry.get("key")),
                    text=_as_str(
                        entry.get("text") or entry.get("content")
                    ),
                    condition=_as_str(entry.get("condition")),
                    role=_as_str(entry.get("role")),
                    position=_as_str(entry.get("position")),
                    raw=copy.deepcopy(entry),
                )
            )

    parent_ref = ""
    if "parent_ref" in present:
        parent = _pick(data, "parent", "parentScenario")
        if isinstance(parent, str):
            parent_ref = parent
        elif isinstance(parent, dict):
            parent_ref = _as_str(
                parent.get("name")
                or parent.get("id")
                or parent.get("ref")
            )

    thumbnail_ref = ""
    if "thumbnail_ref" in present:
        thumb = data.get("thumbnail")
        if isinstance(thumb, str):
            thumbnail_ref = thumb
        elif isinstance(thumb, dict):
            thumbnail_ref = _as_str(
                thumb.get("url")
                or thumb.get("ref")
                or thumb.get("id")
            )

    unmappable: list[UnmappableElement] = []
    unmappable_values: dict = {}
    for key, kind in _VOXTA_UNMAPPABLE.items():
        if key in data:
            unmappable.append(
                UnmappableElement(
                    path=key,
                    kind=kind,
                    name=key,
                    reason=(
                        f"{key} carries machinery Rúnmál does "
                        "not map in this slice; carried verbatim "
                        "for hand-back on Voxta export"
                    ),
                )
            )
            unmappable_values[key] = copy.deepcopy(data[key])

    extra = {
        key: copy.deepcopy(value)
        for key, value in data.items()
        if key not in _VOXTA_CONSUMED
    }

    report = ScenarioImportReport(
        source_format=SOURCE_VOXTA,
        mapped=_mapped_list(present),
        carried=sorted(extra),
        unmappable=unmappable,
        warnings=warnings,
    )
    return ScenarioFile(
        name=name,
        description=description,
        scenario_text=scenario_text,
        flow=flow,
        style=style,
        template_text=template_text,
        system_prompt_text=system_prompt_text,
        system_prompt_mode=system_prompt_mode,
        roles=roles,
        bootstrap_messages=bootstrap_messages,
        impersonation_name=impersonation_name,
        impersonation_description=impersonation_description,
        narrator_name=narrator_name,
        narrator_voice=narrator_voice,
        memory_book_refs=memory_book_refs,
        initial_flags=initial_flags,
        initial_variables=initial_variables,
        contexts=contexts,
        parent_ref=parent_ref,
        thumbnail_ref=thumbnail_ref,
        extra=extra,
        unmappable_values=unmappable_values,
        raw=raw,
        source_format=SOURCE_VOXTA,
        report=report,
    )


def _parse_native(data: dict, raw: dict) -> ScenarioFile:
    warnings: list[str] = []
    present: set[str] = set()
    if "name" in data:
        present.add("name")
    if "description" in data:
        present.add("description")
    if "scenario_text" in data:
        present.add("scenario_text")
    if "flow" in data:
        present.add("flow")
    if "style" in data:
        present.add("style")
    if "template_text" in data:
        present.add("template_text")
    if "system_prompt_text" in data or "system_prompt_mode" in data:
        present.add("system_prompt_text")
    if "roles" in data:
        present.add("roles")
    if "bootstrap_messages" in data:
        present.add("bootstrap_messages")
    if (
        "impersonation_name" in data
        or "impersonation_description" in data
    ):
        present.add("impersonation")
    if "narrator_name" in data or "narrator_voice" in data:
        present.add("narrator")
    if "memory_book_refs" in data:
        present.add("memory_book_refs")
    if "initial_flags" in data:
        present.add("initial_flags")
    if "initial_variables" in data:
        present.add("initial_variables")
    if "contexts" in data:
        present.add("contexts")
    if "parent_ref" in data:
        present.add("parent_ref")
    if "thumbnail_ref" in data:
        present.add("thumbnail_ref")

    name = _require_name(data)
    description = _as_str(data.get("description"))
    scenario_text = _as_str(data.get("scenario_text"))

    if "flow" in data:
        flow = _normalize_flow(_as_str(data.get("flow")), warnings)
    else:
        flow = "chat"

    if "style" in data:
        style = _normalize_style(
            _as_str(data.get("style")), warnings
        )
    else:
        style = ""

    template_text = _as_str(data.get("template_text"))
    system_prompt_text = _as_str(data.get("system_prompt_text"))
    mode = _as_str(data.get("system_prompt_mode")).strip().lower()
    system_prompt_mode = _validate_mode(mode, warnings)

    roles: list[ScenarioRole] = []
    if "roles" in data:
        roles_value = data["roles"]
        if not isinstance(roles_value, list):
            raise ScenarioParseError("roles must be a list")
        for entry in roles_value:
            if not isinstance(entry, dict):
                raise ScenarioParseError(
                    "role entries must be objects"
                )
            roles.append(
                ScenarioRole(
                    name=_as_str(entry.get("name")),
                    character_name=_as_str(
                        entry.get("character_name")
                    ),
                    enabled_on_start=_bool_or_true(
                        entry.get("enabled_on_start")
                    ),
                    can_speak=_bool_or_true(
                        entry.get("can_speak")
                    ),
                    raw=copy.deepcopy(entry),
                )
            )

    bootstrap_messages: list[BootstrapMessage] = []
    if "bootstrap_messages" in data:
        boot = data["bootstrap_messages"]
        if isinstance(boot, list):
            for entry in boot:
                if not isinstance(entry, dict):
                    raise ScenarioParseError(
                        "bootstrap message entries must be objects"
                    )
                kind = _parse_bootstrap_kind(
                    _as_str(entry.get("kind")), warnings
                )
                bootstrap_messages.append(
                    BootstrapMessage(
                        kind=kind,
                        text=_as_str(entry.get("text")),
                        role=_as_str(entry.get("role")),
                        raw=copy.deepcopy(entry),
                    )
                )
        elif isinstance(boot, str):
            bootstrap_messages = _parse_bootstrap_block(
                boot, warnings
            )
        else:
            raise ScenarioParseError(
                "bootstrap messages must be a list or a string"
            )

    impersonation_name = _as_str(data.get("impersonation_name"))
    impersonation_description = _as_str(
        data.get("impersonation_description")
    )
    narrator_name = _as_str(data.get("narrator_name"))
    narrator_voice = _as_str(data.get("narrator_voice"))

    memory_book_refs: list[str] = []
    if "memory_book_refs" in data:
        books = data["memory_book_refs"]
        if not isinstance(books, list):
            raise ScenarioParseError(
                "memory_book_refs must be a list"
            )
        for entry in books:
            ref = _as_str(entry)
            if ref:
                memory_book_refs.append(ref)

    initial_flags: dict = {}
    if "initial_flags" in data:
        flags_value = data["initial_flags"]
        if not isinstance(flags_value, dict):
            raise ScenarioParseError(
                "initial_flags must be an object"
            )
        initial_flags = copy.deepcopy(flags_value)

    initial_variables: dict = {}
    if "initial_variables" in data:
        vars_value = data["initial_variables"]
        if not isinstance(vars_value, dict):
            raise ScenarioParseError(
                "initial_variables must be an object"
            )
        initial_variables = copy.deepcopy(vars_value)

    contexts: list[ScenarioContext] = []
    if "contexts" in data:
        contexts_value = data["contexts"]
        if not isinstance(contexts_value, list):
            raise ScenarioParseError("contexts must be a list")
        for entry in contexts_value:
            if not isinstance(entry, dict):
                raise ScenarioParseError(
                    "context entries must be objects"
                )
            contexts.append(
                ScenarioContext(
                    key=_as_str(entry.get("key")),
                    text=_as_str(entry.get("text")),
                    condition=_as_str(entry.get("condition")),
                    role=_as_str(entry.get("role")),
                    position=_as_str(entry.get("position")),
                    raw=copy.deepcopy(entry),
                )
            )

    parent_ref = _as_str(data.get("parent_ref"))
    thumbnail_ref = _as_str(data.get("thumbnail_ref"))

    extra = {
        key: copy.deepcopy(value)
        for key, value in data.items()
        if key not in _NATIVE_CONSUMED
    }

    report = ScenarioImportReport(
        source_format=SOURCE_NATIVE,
        mapped=_mapped_list(present),
        carried=sorted(extra),
        unmappable=[],
        warnings=warnings,
    )
    return ScenarioFile(
        name=name,
        description=description,
        scenario_text=scenario_text,
        flow=flow,
        style=style,
        template_text=template_text,
        system_prompt_text=system_prompt_text,
        system_prompt_mode=system_prompt_mode,
        roles=roles,
        bootstrap_messages=bootstrap_messages,
        impersonation_name=impersonation_name,
        impersonation_description=impersonation_description,
        narrator_name=narrator_name,
        narrator_voice=narrator_voice,
        memory_book_refs=memory_book_refs,
        initial_flags=initial_flags,
        initial_variables=initial_variables,
        contexts=contexts,
        parent_ref=parent_ref,
        thumbnail_ref=thumbnail_ref,
        extra=extra,
        unmappable_values={},
        raw=raw,
        source_format=SOURCE_NATIVE,
        report=report,
    )


def parse_scenario_file(data: bytes | str | dict) -> ScenarioFile:
    """Parse a scenario file (Voxta-shaped or native)."""
    obj = _coerce_object(data)
    raw = copy.deepcopy(obj)
    if (
        obj.get("source_format") == SOURCE_NATIVE
        or set(obj) & _STRONG_NATIVE_KEYS
    ):
        return _parse_native(obj, raw)
    return _parse_voxta(obj, raw)
