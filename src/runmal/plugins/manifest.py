"""Plugin manifest: a plugin as data, and nothing else (P-081, design section 1).

A manifest is JSON-able data (PLG-02): it round-trips exactly
through :func:`manifest_from_data` / :func:`manifest_to_data` (the
house ``*_from_data`` idiom). No code travels in a manifest, a pack
or an HTTP request in v1 -- handlers are Python callables bound at
registration time by trusted in-tree code, and they live in the
registry, never here.

:func:`manifest_from_data` is strict, in the house validate style:
unknown top-level keys reject, unknown capability / permission /
event / slot names reject (closed vocabularies in
:mod:`runmal.plugins.api` -- fail loud, bridge scopes kin), ids and
versions must match their grammars, and every value is
type-checked. Anything outside the shape raises
:class:`ManifestError`. One deliberate exception to strictness
lives at parse time: ``api_version`` compatibility is NOT judged
here. Any int parses, so the registry can produce the section 6
compatibility verdict; a non-int ``api_version`` (e.g. ``"1"``) is
a malformed manifest and fails here -- the two failure classes
stay distinct.

Surface-requires-capability cross-checks (a prompt hook without
``prompt.inject``, a UI contribution without ``ui.contribute``, a
``generation.*`` event without ``generation.observe``) are likewise
NOT parse-time checks. They are pure-manifest checks, and they
live in :func:`validate_surface_requirements` for the registry to
enforce at ``register()`` time -- the placement the design itself
fixes (section 1's closing cross-check paragraph and PLG-03:
"undeclared binding rejects loudly at registration"). Parse time
cannot enforce them: the section 1 canonical example declares a
``ui_slots`` contribution while its capabilities / permissions
carry neither ``ui.slots`` nor ``ui.contribute``, and that example
must parse and round-trip exactly (PLG-02, battery test 1).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from runmal.plugins.api import (
    KNOWN_CAPABILITIES,
    KNOWN_PERMISSIONS,
    PLUGIN_EVENTS,
    PROMPT_STAGES,
    UI_SLOTS,
)


class ManifestError(ValueError):
    """A manifest (or one of its declarations) is outside the section 1 shape."""


# Plugin id: the namespace for slot ids, UI contribution ids and
# provenance. 2..64 chars, lowercase, dots / dashes / underscores
# after the first character.
_PLUGIN_ID = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")
# Hook and UI contribution ids, unique within their plugin.
_LOCAL_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
# Strict MAJOR.MINOR.PATCH numeric triple (loose semver;
# pre-release suffixes reject in v1).
_VERSION = re.compile(r"\d+\.\d+\.\d+")

_FIELDS = frozenset(
    {
        "id",
        "name",
        "version",
        "api_version",
        "description",
        "author",
        "capabilities",
        "permissions",
        "events",
        "prompt_hooks",
        "ui_slots",
        "settings",
        "enabled_by_default",
    }
)
_HOOK_FIELDS = frozenset({"id", "stage", "priority"})
_UI_FIELDS = frozenset({"id", "slot", "label", "order", "payload"})
_SETTINGS_FIELDS = frozenset({"schema", "defaults"})

#: Priority / order a declaration takes when it names none.
DEFAULT_PRIORITY = 100


def _is_int(value: object) -> bool:
    """True for a real int; bools are not ints in this grammar."""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_local_id(value: object, what: str) -> str:
    if not isinstance(value, str) or not _LOCAL_ID.fullmatch(value):
        raise ManifestError(f"invalid {what} id: {value!r}")
    return value


@dataclass(frozen=True)
class HookDecl:
    """One declared prompt hook: ``{id, stage, priority}`` (section 1)."""

    id: str
    stage: str
    priority: int = DEFAULT_PRIORITY

    def __post_init__(self) -> None:
        _check_local_id(self.id, "prompt hook")
        if self.stage not in PROMPT_STAGES:
            raise ManifestError(f"unknown prompt stage: {self.stage!r}")
        if not _is_int(self.priority) or not 0 <= self.priority <= 999:
            raise ManifestError(
                f"prompt hook priority must be an int in 0..999: {self.priority!r}"
            )


@dataclass(frozen=True)
class UISlotDecl:
    """One declared UI contribution: ``{id, slot, label, order, payload}``.

    The contribution IS this data (section 5): no callable is bound
    for it in v1. ``payload`` is an opaque JSON-able dict the host
    passes through verbatim; its 4096-byte canonical-JSON cap is a
    registration-time check (section 5), not a parse-time one.
    """

    id: str
    slot: str
    label: str
    order: int = DEFAULT_PRIORITY
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_local_id(self.id, "ui slot contribution")
        if self.slot not in UI_SLOTS:
            raise ManifestError(f"unknown ui slot: {self.slot!r}")
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 120:
            raise ManifestError("ui slot label must be a string of 1..120 chars")
        if not _is_int(self.order):
            raise ManifestError(f"ui slot order must be an int: {self.order!r}")
        if not isinstance(self.payload, dict):
            raise ManifestError("ui slot payload must be an object")
        try:
            json.dumps(self.payload)
        except (TypeError, ValueError) as exc:
            raise ManifestError(f"ui slot payload is not JSON-able: {exc}") from exc


@dataclass(frozen=True)
class PluginManifest:
    """A validated plugin manifest (section 1). Data only.

    ``settings`` is stored verbatim: ``None`` when the manifest
    named none, otherwise the ``{schema, defaults}`` dict as
    supplied. P-081 validates only that both members are JSON-able
    dicts; interpreting the schema is P-098's contract.
    """

    id: str
    name: str
    version: str
    api_version: int
    description: str = ""
    author: str = ""
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    prompt_hooks: tuple[HookDecl, ...] = ()
    ui_slots: tuple[UISlotDecl, ...] = ()
    settings: dict | None = None
    enabled_by_default: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _PLUGIN_ID.fullmatch(self.id):
            raise ManifestError(f"invalid plugin id: {self.id!r}")
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 120:
            raise ManifestError("plugin name must be a string of 1..120 chars")
        if not isinstance(self.version, str) or not _VERSION.fullmatch(self.version):
            raise ManifestError(f"invalid plugin version: {self.version!r}")
        if not _is_int(self.api_version):
            raise ManifestError(
                f"plugin api_version must be an int: {self.api_version!r}"
            )
        if not isinstance(self.description, str):
            raise ManifestError("plugin description must be a string")
        if not isinstance(self.author, str):
            raise ManifestError("plugin author must be a string")
        for capability in self.capabilities:
            if not isinstance(capability, str) or capability not in KNOWN_CAPABILITIES:
                raise ManifestError(f"unknown capability: {capability!r}")
        for permission in self.permissions:
            if not isinstance(permission, str) or permission not in KNOWN_PERMISSIONS:
                raise ManifestError(f"unknown permission: {permission!r}")
        for event in self.events:
            if not isinstance(event, str) or event not in PLUGIN_EVENTS:
                raise ManifestError(f"unknown plugin event: {event!r}")
        hook_ids = [hook.id for hook in self.prompt_hooks]
        if len(set(hook_ids)) != len(hook_ids):
            raise ManifestError("duplicate prompt hook id within plugin")
        ui_ids = [decl.id for decl in self.ui_slots]
        if len(set(ui_ids)) != len(ui_ids):
            raise ManifestError("duplicate ui slot contribution id within plugin")
        if self.settings is not None:
            _check_settings(self.settings)
        if not isinstance(self.enabled_by_default, bool):
            raise ManifestError("enabled_by_default must be a bool")


def _check_settings(settings: object) -> dict:
    """Validate the optional settings block; returns it as a dict copy."""
    if not isinstance(settings, dict):
        raise ManifestError("settings must be an object")
    unknown = set(settings) - _SETTINGS_FIELDS
    if unknown:
        raise ManifestError(
            f"unknown settings keys: {sorted(unknown, key=repr)}"
        )
    for key, value in settings.items():
        if not isinstance(value, dict):
            raise ManifestError(f"settings.{key} must be an object")
    try:
        json.dumps(settings)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"settings are not JSON-able: {exc}") from exc
    return dict(settings)


def _name_list(
    data: dict, key: str, vocabulary: frozenset[str], what: str
) -> tuple[str, ...]:
    """One closed-vocabulary name list: validated, duplicates collapsed.

    Order is preserved from the manifest; the first occurrence of a
    name wins (section 1, stated for capabilities and applied to
    permissions and events alike).
    """
    raw = data.get(key, [])
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ManifestError(f"plugin {key} must be a list")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in vocabulary:
            raise ManifestError(f"unknown {what}: {item!r}")
        if item not in out:
            out.append(item)
    return tuple(out)


def _hook_list(data: dict) -> tuple[HookDecl, ...]:
    raw = data.get("prompt_hooks", [])
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ManifestError("plugin prompt_hooks must be a list")
    hooks: list[HookDecl] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError(f"prompt hook must be an object: {item!r}")
        unknown = set(item) - _HOOK_FIELDS
        if unknown:
            raise ManifestError(
                f"unknown prompt hook keys: {sorted(unknown, key=repr)}"
            )
        for required in ("id", "stage"):
            if required not in item:
                raise ManifestError(f"prompt hook missing {required!r}")
        hooks.append(
            HookDecl(
                id=item["id"],
                stage=item["stage"],
                priority=item.get("priority", DEFAULT_PRIORITY),
            )
        )
    ids = [hook.id for hook in hooks]
    if len(set(ids)) != len(ids):
        raise ManifestError("duplicate prompt hook id within plugin")
    return tuple(hooks)


def _ui_list(data: dict) -> tuple[UISlotDecl, ...]:
    raw = data.get("ui_slots", [])
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ManifestError("plugin ui_slots must be a list")
    decls: list[UISlotDecl] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError(f"ui slot contribution must be an object: {item!r}")
        unknown = set(item) - _UI_FIELDS
        if unknown:
            raise ManifestError(
                f"unknown ui slot keys: {sorted(unknown, key=repr)}"
            )
        for required in ("id", "slot", "label"):
            if required not in item:
                raise ManifestError(f"ui slot contribution missing {required!r}")
        decls.append(
            UISlotDecl(
                id=item["id"],
                slot=item["slot"],
                label=item["label"],
                order=item.get("order", DEFAULT_PRIORITY),
                payload=item.get("payload", {}),
            )
        )
    ids = [decl.id for decl in decls]
    if len(set(ids)) != len(ids):
        raise ManifestError("duplicate ui slot contribution id within plugin")
    return tuple(decls)


def manifest_from_data(data: object) -> PluginManifest:
    """Validate supplied ``data`` into a :class:`PluginManifest`.

    Strict (see the module docstring): anything outside the
    section 1 shape raises :class:`ManifestError`. ``api_version``
    compatibility is deliberately not judged here -- any int
    parses; the registry produces the compatibility verdict.
    """
    if not isinstance(data, dict):
        raise ManifestError("plugin manifest must be an object")
    unknown = set(data) - _FIELDS
    if unknown:
        raise ManifestError(
            f"unknown manifest keys: {sorted(unknown, key=repr)}"
        )
    for required in ("id", "name", "version", "api_version"):
        if required not in data:
            raise ManifestError(f"plugin manifest missing required field: {required}")
    settings = data.get("settings")
    if settings is not None:
        settings = _check_settings(settings)
    return PluginManifest(
        id=data["id"],
        name=data["name"],
        version=data["version"],
        api_version=data["api_version"],
        description=data.get("description", ""),
        author=data.get("author", ""),
        capabilities=_name_list(data, "capabilities", KNOWN_CAPABILITIES, "capability"),
        permissions=_name_list(data, "permissions", KNOWN_PERMISSIONS, "permission"),
        events=_name_list(data, "events", PLUGIN_EVENTS, "plugin event"),
        prompt_hooks=_hook_list(data),
        ui_slots=_ui_list(data),
        settings=settings,
        enabled_by_default=data.get("enabled_by_default", False),
    )


def manifest_to_data(manifest: PluginManifest) -> dict:
    """Serialise ``manifest`` with every key, always (house style).

    Exact round-trip: ``manifest_to_data(manifest_from_data(d))``
    equals ``d`` for a valid manifest ``d`` that names every key,
    as the section 1 canonical example does.
    """
    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "api_version": manifest.api_version,
        "description": manifest.description,
        "author": manifest.author,
        "capabilities": list(manifest.capabilities),
        "permissions": list(manifest.permissions),
        "events": list(manifest.events),
        "prompt_hooks": [
            {"id": hook.id, "stage": hook.stage, "priority": hook.priority}
            for hook in manifest.prompt_hooks
        ],
        "ui_slots": [
            {
                "id": decl.id,
                "slot": decl.slot,
                "label": decl.label,
                "order": decl.order,
                "payload": dict(decl.payload),
            }
            for decl in manifest.ui_slots
        ],
        "settings": dict(manifest.settings) if manifest.settings is not None else None,
        "enabled_by_default": manifest.enabled_by_default,
    }


def validate_surface_requirements(manifest: PluginManifest) -> None:
    """The section 1 surface-requires-capability/permission cross-checks.

    Pure-manifest checks, enforced by the registry at ``register()``
    time (PLG-03), NOT by :func:`manifest_from_data` -- see the
    module docstring for why parse time is the wrong home for them.
    Raises :class:`ManifestError` naming every unmet requirement;
    the registry translates that into its registration error.
    """
    problems: list[str] = []
    capabilities = set(manifest.capabilities)
    permissions = set(manifest.permissions)
    if manifest.events:
        if "chat.events" not in capabilities:
            problems.append("declared events require capability 'chat.events'")
        if any(name.startswith("generation.") for name in manifest.events):
            if "generation.observe" not in capabilities:
                problems.append(
                    "generation.* events require capability 'generation.observe'"
                )
    if manifest.prompt_hooks:
        if "prompt.hooks" not in capabilities:
            problems.append(
                "declared prompt hooks require capability 'prompt.hooks'"
            )
        for hook in manifest.prompt_hooks:
            if hook.stage == "slots" and "prompt.inject" not in permissions:
                problems.append(
                    f"prompt hook {hook.id!r} (stage 'slots') requires "
                    "permission 'prompt.inject'"
                )
            if hook.stage == "messages" and "prompt.modify" not in permissions:
                problems.append(
                    f"prompt hook {hook.id!r} (stage 'messages') requires "
                    "permission 'prompt.modify'"
                )
    if manifest.ui_slots:
        if "ui.slots" not in capabilities:
            problems.append(
                "declared ui slots require capability 'ui.slots'"
            )
        if "ui.contribute" not in permissions:
            problems.append(
                "declared ui slots require permission 'ui.contribute'"
            )
    if problems:
        raise ManifestError("; ".join(problems))
