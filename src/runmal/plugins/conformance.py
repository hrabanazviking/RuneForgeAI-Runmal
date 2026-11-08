"""Plugin conformance kit (P-097): contract + sandbox, or not listed.

Roadmap line: "Plugin conformance kit: a plugin must pass
contract + sandbox tests to be listed (the node-kit pattern
from Yggdrasil)."

One gate over the P-081 contract and the P-082 sandbox:
:func:`check_manifest_data` runs a data-shaped submission
(a manifest dict, optionally with the handlers that would be
bound for it) through thirteen named checks and returns ONE
inspectable, deterministic report; :func:`check_citizen`
runs an in-tree citizen module through the same checks plus
the citizen-pattern cross-checks. A plugin is LISTABLE only
on a full pass (:func:`is_listable`); :func:`listable_ids`
is the listing gate as data for any listing road.
:func:`conformance_corpus` runs the kit over every shipped
citizen discovered in :mod:`runmal.plugins`.

The kit REUSES its oracles wherever they already speak: the
P-081 strict parser, surface rules and registry (a scratch
registry - the kit never touches the default registry and
never changes the empty boot registry), and the P-082 grant
policy and guarded context (behavioural denial probes that
refuse at the grant gate, before any file or network access:
the kit itself touches neither). What it adds is only what
those layers do not cover: per-name vocabulary naming, the
api-version verdict as a named check, settings storage
shape, sandbox denial behaviour, the citizen-pattern and
grants cross-checks, the corpus, and the listing gate.

Deterministic, local, no network: reports carry no
timestamps; the same submission yields a byte-identical
checksummed report core, twice. Failure strings carry stable
code prefixes and name plugin ids, grant names and check
names only - never payloads or secret values (P-027).

Honesty boundary (inherited from P-082, SECURITY_MODEL
section 8): this is an API-surface conformance claim for
trusted in-tree handlers bound at registration. It is NOT
an OS/process sandbox claim and does not confine code that
bypasses the plugin context it is handed.

Wiring: :func:`register_plugin` only (the kit citizen).
``build_registry`` / ``create_app`` are unchanged. No
migration: head stays 0041. No HTTP routes in this slice
(the P-095 precedent - the plugins router is shared with
in-flight slices; wiring the gate into a listing road is a
keeper / P-100 reconciliation decision). Settings-schema
INTERPRETATION is P-098; failure manners are P-099.
See docs/PLUGIN_CONFORMANCE_KIT_2026-11-07.md.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import pkgutil
import re
from collections.abc import Mapping

from runmal.plugins.api import (
    KNOWN_CAPABILITIES,
    KNOWN_PERMISSIONS,
    PLUGIN_EVENTS,
    PROMPT_STAGES,
    SUPPORTED_API_VERSIONS,
    UI_SLOTS,
)
from runmal.plugins.manifest import (
    ManifestError,
    PluginManifest,
    manifest_from_data,
    manifest_to_data,
)
from runmal.plugins.registry import (
    UI_PAYLOAD_MAX_BYTES,
    PluginHandlers,
    PluginRegistry,
    PluginState,
)
from runmal.sandbox.guard import Sandbox
from runmal.sandbox.policy import (
    RESOURCE_PERMISSIONS,
    GrantSet,
    SandboxError,
    SandboxErrorKind,
    grants_from_manifest,
)

PLUGIN_ID = "runmal.plugin-conformance"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "plugin-conformance-panel"
CONFORMANCE_FORMAT = "runmal-plugin-conformance"
CONFORMANCE_VERSION = 1

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

#: Citizen modules in roadmap order (P-084..P-095 + the kit
#: itself). Discovery adds any further citizen module the
#: tree carries (the P-096 road: see citizen_modules).
_KNOWN_CITIZEN_MODULES = (
    "runmal.plugins.summarise",
    "runmal.plugins.vector_storage",
    "runmal.plugins.translate",
    "runmal.plugins.image_generation",
    "runmal.plugins.web_search",
    "runmal.plugins.quick_replies",
    "runmal.plugins.regex_scripts",
    "runmal.plugins.tts",
    "runmal.plugins.stt",
    "runmal.plugins.expressions",
    "runmal.plugins.variables",
    "runmal.plugins.custody",
    "runmal.plugins.gallery",
    "runmal.plugins.conformance",
)

_CITIZEN_ATTRS = (
    "PLUGIN_ID", "manifest_data", "build_manifest",
    "register_plugin", "sandbox_grants",
)


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _checksum(payload) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Checks:
    """Ordered check accumulator: every check reports, none is silent."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, failures: list[str]) -> None:
        self.rows.append({"name": name, "passed": not failures,
                          "failures": list(failures)})

    def not_run(self, name: str, reason: str) -> None:
        self.add(name, [f"not_run: {reason}"])

    @property
    def passed(self) -> bool:
        return all(row["passed"] for row in self.rows)

    def flat_failures(self) -> list[str]:
        out: list[str] = []
        for row in self.rows:
            for failure in row["failures"]:
                out.append(f"{row['name']}: {failure}")
        return out


def _name_list(data: dict, key: str, failures: list[str]) -> list:
    raw = data.get(key, [])
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        failures.append(f"malformed_declaration: {key} must be a list")
        return []
    out = []
    for item in raw:
        if not isinstance(item, str):
            failures.append(
                f"malformed_declaration: {key} entries must be strings "
                f"(data only, never code): {type(item).__name__}")
        else:
            out.append(item)
    return out


def _check_vocabulary(data: dict) -> list[str]:
    failures: list[str] = []
    for name in _name_list(data, "capabilities", failures):
        if name not in KNOWN_CAPABILITIES:
            failures.append(f"unknown_capability: {name!r}")
    for name in _name_list(data, "permissions", failures):
        if name not in KNOWN_PERMISSIONS:
            failures.append(f"unknown_permission: {name!r}")
    for name in _name_list(data, "events", failures):
        if name not in PLUGIN_EVENTS:
            failures.append(f"unknown_event: {name!r}")
    hooks = data.get("prompt_hooks", [])
    if isinstance(hooks, (list, tuple)):
        for hook in hooks:
            if isinstance(hook, dict) and "stage" in hook:
                if hook["stage"] not in PROMPT_STAGES:
                    failures.append(
                        f"unknown_prompt_stage: {hook['stage']!r}")
    slots = data.get("ui_slots", [])
    if isinstance(slots, (list, tuple)):
        for decl in slots:
            if isinstance(decl, dict) and "slot" in decl:
                if decl["slot"] not in UI_SLOTS:
                    failures.append(f"unknown_ui_slot: {decl['slot']!r}")
    return failures


def _check_identity(data: dict) -> list[str]:
    failures: list[str] = []
    plugin_id = data.get("id")
    if not isinstance(plugin_id, str) or not _ID_RE.fullmatch(plugin_id or ""):
        failures.append(f"invalid_plugin_id: {plugin_id!r}")
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 120:
        failures.append("invalid_name: name must be a string of 1..120 chars")
    version = data.get("version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version or ""):
        failures.append(f"invalid_version: {version!r}")
    api_version = data.get("api_version")
    if not _is_int(api_version):
        failures.append(f"invalid_api_version: {api_version!r} is not an int")
    elif api_version not in SUPPORTED_API_VERSIONS:
        failures.append(
            f"unsupported_api_version: {api_version} "
            f"(supported: {sorted(SUPPORTED_API_VERSIONS)})")
    return failures


def _check_surface(manifest: PluginManifest) -> list[str]:
    """The validate_surface_requirements rules, one failure per rule."""
    failures: list[str] = []
    caps = set(manifest.capabilities)
    perms = set(manifest.permissions)
    if manifest.events and "chat.events" not in caps:
        failures.append(
            "surface_requirement: declared events require "
            "capability 'chat.events'")
    if any(n.startswith("generation.") for n in manifest.events):
        if "generation.observe" not in caps:
            failures.append(
                "surface_requirement: generation.* events require "
                "capability 'generation.observe'")
    if manifest.prompt_hooks:
        if "prompt.hooks" not in caps:
            failures.append(
                "surface_requirement: declared prompt hooks require "
                "capability 'prompt.hooks'")
        for hook in manifest.prompt_hooks:
            if hook.stage == "slots" and "prompt.inject" not in perms:
                failures.append(
                    f"surface_requirement: prompt hook {hook.id!r} "
                    "(stage 'slots') requires permission 'prompt.inject'")
            if hook.stage == "messages" and "prompt.modify" not in perms:
                failures.append(
                    f"surface_requirement: prompt hook {hook.id!r} "
                    "(stage 'messages') requires permission 'prompt.modify'")
    if manifest.ui_slots:
        if "ui.slots" not in caps:
            failures.append(
                "surface_requirement: declared ui slots require "
                "capability 'ui.slots'")
        if "ui.contribute" not in perms:
            failures.append(
                "surface_requirement: declared ui slots require "
                "permission 'ui.contribute'")
    return failures


def _check_ui(manifest: PluginManifest) -> list[str]:
    failures: list[str] = []
    seen: set[str] = set()
    for decl in manifest.ui_slots:
        if decl.id in seen:
            failures.append(f"duplicate_ui_contribution_id: {decl.id!r}")
        seen.add(decl.id)
        if decl.slot not in UI_SLOTS:
            failures.append(f"unknown_ui_slot: {decl.slot!r}")
        if not isinstance(decl.label, str) or not 1 <= len(decl.label) <= 120:
            failures.append(
                f"ui_label_invalid: contribution {decl.id!r} label must "
                "be a string of 1..120 chars")
        if not _is_int(decl.order):
            failures.append(
                f"ui_order_invalid: contribution {decl.id!r} order must "
                "be an int")
        if not isinstance(decl.payload, dict):
            failures.append(
                f"ui_payload_invalid: contribution {decl.id!r} payload "
                "must be an object")
            continue
        try:
            size = len(_canonical_bytes(decl.payload))
        except (TypeError, ValueError) as exc:
            failures.append(
                f"ui_payload_invalid: contribution {decl.id!r} payload "
                f"is not JSON-able: {exc}")
            continue
        if size > UI_PAYLOAD_MAX_BYTES:
            failures.append(
                f"ui_payload_too_large: contribution {decl.id!r} payload "
                f"is {size} canonical bytes (> {UI_PAYLOAD_MAX_BYTES})")
    return failures


def _check_settings(data: dict) -> list[str]:
    failures: list[str] = []
    if "settings" not in data or data.get("settings") is None:
        return failures
    settings = data["settings"]
    if not isinstance(settings, dict):
        return ["settings_shape: settings must be an object"]
    unknown = set(settings) - {"schema", "defaults"}
    if unknown:
        failures.append(
            f"settings_shape: unknown settings keys: "
            f"{sorted(unknown, key=repr)}")
    for key in ("schema", "defaults"):
        if key in settings:
            if not isinstance(settings[key], dict):
                failures.append(
                    f"settings_shape: settings.{key} must be an object")
                continue
            try:
                json.dumps(settings[key])
            except (TypeError, ValueError) as exc:
                failures.append(
                    f"settings_shape: settings.{key} is not "
                    f"JSON-able: {exc}")
    return failures


def _check_handlers(manifest: PluginManifest,
                    handlers: PluginHandlers) -> list[str]:
    """Mirror registry._check_handlers, naming every problem."""
    failures: list[str] = []
    declared = {hook.id for hook in manifest.prompt_hooks}
    bound = dict(handlers.prompt_hooks or {})
    for hook_id in sorted(set(bound) - declared):
        failures.append(f"undeclared_hook_handler: {hook_id!r}")
    for hook_id in sorted(declared - set(bound)):
        failures.append(f"missing_hook_handler: {hook_id!r}")
    for hook_id, fn in bound.items():
        if not callable(fn):
            failures.append(f"hook_handler_not_callable: {hook_id!r}")
    on_event = handlers.on_event
    if isinstance(on_event, Mapping):
        for name in on_event:
            if name not in manifest.events:
                failures.append(f"undeclared_event_handler: {name!r}")
            elif not callable(on_event[name]):
                failures.append(f"event_handler_not_callable: {name!r}")
    elif on_event is not None and not callable(on_event):
        failures.append("event_handler_not_callable: on_event")
    for attr in ("on_enable", "on_disable"):
        fn = getattr(handlers, attr)
        if fn is not None and not callable(fn):
            failures.append(f"lifecycle_handler_not_callable: {attr}")
    return failures


def _check_sandbox_denials(data: dict, manifest: PluginManifest,
                           grants: GrantSet) -> list[str]:
    """Behavioural probes: every ungranted road must refuse.

    All probes deny at the sandbox grant gate, before any
    file, network or secret access happens - the kit touches
    none of them. The sandbox is built with no root, no
    transport and no secret provider.
    """
    failures: list[str] = []
    sandbox = Sandbox(data)

    def denied(label: str, fn) -> None:
        try:
            fn()
        except SandboxError:
            return
        except Exception as exc:  # wrong refusal shape is a failure too
            failures.append(
                f"sandbox_{label}_wrong_refusal: "
                f"{type(exc).__name__}: {exc}")
            return
        failures.append(f"sandbox_{label}_not_denied")

    denied("fetch", lambda: sandbox.fetch("https://example.invalid/probe"))
    denied("read_file", lambda: sandbox.read_file("conformance-probe.txt"))
    denied("write_file",
           lambda: sandbox.write_file("conformance-probe.txt", b"probe"))
    denied("get_secret", lambda: sandbox.get_secret("conformance-probe"))
    declared = set(manifest.capabilities)
    for capability in sorted(KNOWN_CAPABILITIES - declared):
        try:
            sandbox.require_capability(capability)
        except SandboxError as exc:
            if exc.kind is not SandboxErrorKind.CAPABILITY_DENIED:
                failures.append(
                    f"sandbox_capability_wrong_refusal: {capability!r} "
                    f"refused as {exc.kind.value}")
        except Exception as exc:
            failures.append(
                f"sandbox_capability_wrong_refusal: {capability!r} "
                f"{type(exc).__name__}: {exc}")
        else:
            failures.append(
                f"sandbox_undeclared_capability_allowed: {capability!r}")
    for capability in sorted(declared):
        try:
            sandbox.require_capability(capability)
        except Exception as exc:
            failures.append(
                f"sandbox_declared_capability_denied: {capability!r} "
                f"{type(exc).__name__}: {exc}")
    try:
        grants.expanded("network.access")
    except SandboxError as exc:
        if exc.kind is not SandboxErrorKind.ESCALATION:
            failures.append(
                f"sandbox_escalation_wrong_refusal: {exc.kind.value}")
    except Exception as exc:
        failures.append(
            f"sandbox_escalation_wrong_refusal: "
            f"{type(exc).__name__}: {exc}")
    else:
        failures.append("sandbox_escalation_not_refused")
    wider = sorted(set(RESOURCE_PERMISSIONS) - set(grants.resources))
    if wider:
        wide = GrantSet(plugin_id=grants.plugin_id,
                        resources=frozenset({wider[0]}))
        try:
            Sandbox(data, grants=wide)
        except SandboxError as exc:
            if exc.kind is not SandboxErrorKind.ESCALATION:
                failures.append(
                    f"sandbox_wider_grants_wrong_refusal: {exc.kind.value}")
        except Exception as exc:
            failures.append(
                f"sandbox_wider_grants_wrong_refusal: "
                f"{type(exc).__name__}: {exc}")
        else:
            failures.append("sandbox_wider_grants_accepted")
    if not any(e.outcome == "deny" for e in sandbox.audit_log()):
        failures.append("sandbox_audit_missing_denies")
    return failures


def _report(source: str, plugin_id, checks: _Checks) -> dict:
    core = {"plugin_id": plugin_id, "source": source,
            "checks": checks.rows}
    return {
        "format": CONFORMANCE_FORMAT,
        "conformance_version": CONFORMANCE_VERSION,
        "source": source,
        "plugin_id": plugin_id,
        "passed": checks.passed,
        "listable": checks.passed,
        "checks": checks.rows,
        "failures": checks.flat_failures(),
        "content_sha256": _checksum(core),
    }


def check_manifest_data(data: dict, *,
                        handlers: PluginHandlers | None = None) -> dict:
    """Run the contract + sandbox checks over one submission.

    ``data`` is a manifest as plain data (the PLG-02 shape).
    ``handlers`` is the PluginHandlers that would be bound
    for it; with none supplied, an empty binding is checked -
    so a manifest declaring prompt hooks fails
    handlers_binding, exactly as the registry would refuse
    it, while a data plugin declaring no code surfaces can
    pass on data alone. The submission dict is never mutated.
    """
    if not isinstance(data, dict):
        raise TypeError(
            f"manifest data must be a dict, not {type(data).__name__}")
    handlers = handlers if handlers is not None else PluginHandlers()
    checks = _Checks()
    plugin_id = data.get("id") if isinstance(data.get("id"), str) else None
    checks.add("vocabulary", _check_vocabulary(data))
    checks.add("identity", _check_identity(data))
    manifest: PluginManifest | None = None
    try:
        manifest = manifest_from_data(copy.deepcopy(data))
    except ManifestError as exc:
        checks.add("manifest_parses", [f"manifest_parse: {exc}"])
    else:
        checks.add("manifest_parses", [])
    if manifest is None:
        for name in ("round_trip", "surface_requirements",
                     "ui_contributions"):
            checks.not_run(name, "manifest did not parse")
    else:
        try:
            again = manifest_from_data(manifest_to_data(manifest))
            stable = manifest_to_data(again) == manifest_to_data(manifest)
        except ManifestError as exc:
            checks.add("round_trip", [f"round_trip_failed: {exc}"])
        else:
            checks.add("round_trip",
                       [] if stable else ["round_trip_unstable"])
        checks.add("surface_requirements", _check_surface(manifest))
        checks.add("ui_contributions", _check_ui(manifest))
    checks.add("settings_shape", _check_settings(data))
    if manifest is not None:
        checks.add("handlers_binding", _check_handlers(manifest, handlers))
        checks.add("registration",
                   _check_registration(data, manifest, handlers))
    else:
        # Fixed check order (design section 3): the two checks
        # that need a parsed manifest report not_run in their
        # own slots, after settings_shape - never before it.
        checks.not_run("handlers_binding", "manifest did not parse")
        checks.not_run("registration", "manifest did not parse")
    grants: GrantSet | None = None
    try:
        grants = grants_from_manifest(copy.deepcopy(data))
    except SandboxError as exc:
        checks.add("grants_derived",
                   [f"grants_derivation_failed: {exc}"])
    else:
        checks.add("grants_derived", [])
    if grants is None:
        # Derivation refused (an unknown name) - the resource
        # scan still runs on the raw declarations, so a
        # smuggled resource grant is named even when another
        # declaration already refused the whole manifest.
        raw_permissions = data.get("permissions")
        smuggled = []
        if isinstance(raw_permissions, (list, tuple)):
            smuggled = sorted({n for n in raw_permissions
                               if n in RESOURCE_PERMISSIONS})
        if smuggled:
            checks.add("grants_empty_resources", [
                f"resource_grant_present: {name!r} is not grantable "
                "in plugin api v1" for name in smuggled])
        else:
            checks.not_run("grants_empty_resources",
                           "grants did not derive")
        checks.not_run("sandbox_denials", "grants did not derive")
    else:
        checks.add("grants_empty_resources", [
            f"resource_grant_present: {name!r} is not grantable "
            "in plugin api v1"
            for name in sorted(grants.resources)])
        if manifest is None:
            checks.not_run("sandbox_denials", "manifest did not parse")
        else:
            checks.add("sandbox_denials",
                       _check_sandbox_denials(data, manifest, grants))
    return _report("manifest", plugin_id, checks)


def _check_registration(data: dict, manifest: PluginManifest,
                        handlers: PluginHandlers) -> list[str]:
    failures: list[str] = []
    from runmal.plugins import service as plugin_service
    before_obj = plugin_service.get_default_registry()
    before_keys = (list(before_obj.keys())
                   if before_obj is not None else None)
    snapshot = copy.deepcopy(data)
    scratch = PluginRegistry()
    try:
        record = scratch.register(manifest, handlers)
    except Exception as exc:
        failures.append(
            f"registration_failed: {type(exc).__name__}: {exc}")
        return failures
    if record.state is not PluginState.REGISTERED:
        failures.append(
            f"registration_state: landed {record.state.value}, "
            "expected 'registered'")
    if scratch.keys() != [manifest.id]:
        failures.append(
            f"registration_keys: scratch registry holds "
            f"{scratch.keys()}, expected [{manifest.id!r}]")
    contributions = scratch.ui_contributions()
    if len(contributions) != len(manifest.ui_slots):
        failures.append(
            f"registration_ui_contributions: registry reports "
            f"{len(contributions)}, manifest declares "
            f"{len(manifest.ui_slots)}")
    if data != snapshot:
        failures.append("submission_mutated: registration changed "
                        "the submitted manifest data")
    after_obj = plugin_service.get_default_registry()
    after_keys = (list(after_obj.keys())
                  if after_obj is not None else None)
    if after_obj is not before_obj or after_keys != before_keys:
        failures.append("boot_registry_mutated: the default registry "
                        "changed during a scratch registration")
    return failures


def check_manifest(manifest_or_data, *,
                   handlers: PluginHandlers | None = None) -> dict:
    """Check a PluginManifest or its plain-data shape."""
    if isinstance(manifest_or_data, PluginManifest):
        data = manifest_to_data(manifest_or_data)
    else:
        data = manifest_or_data
    return check_manifest_data(data, handlers=handlers)


def _resolve_module(module_or_path):
    if isinstance(module_or_path, str):
        return importlib.import_module(module_or_path)
    return module_or_path


def check_citizen(module_or_path) -> dict:
    """Check one in-tree citizen module end to end.

    Runs the manifest checks with the handlers the citizen's
    own register_plugin binds, plus the citizen_pattern
    cross-checks: the module exposes the pattern, its
    build_manifest matches its manifest_data, its claimed
    sandbox_grants equal the grants its manifest derives,
    and its register_plugin lands REGISTERED in a scratch
    registry under its declared PLUGIN_ID.
    """
    module = _resolve_module(module_or_path)
    pattern_failures: list[str] = []
    for attr in _CITIZEN_ATTRS:
        if not hasattr(module, attr):
            pattern_failures.append(
                f"citizen_pattern_missing: module lacks {attr}")
    data = None
    handlers = None
    if not pattern_failures:
        data = module.manifest_data()
        try:
            scratch = PluginRegistry()
            _record, plugin = module.register_plugin(scratch)
            handlers = plugin.handlers()
        except Exception as exc:
            pattern_failures.append(
                f"citizen_registration_failed: "
                f"{type(exc).__name__}: {exc}")
    if data is None:
        checks = _Checks()
        checks.add("citizen_pattern", pattern_failures or
                   ["citizen_pattern_missing: no manifest data"])
        plugin_id = getattr(module, "PLUGIN_ID", None)
        return _report("citizen",
                       plugin_id if isinstance(plugin_id, str) else None,
                       checks)
    report = check_manifest_data(data, handlers=handlers)
    # Citizen cross-checks beyond a bare submission.
    if getattr(module, "PLUGIN_ID", None) != data.get("id"):
        pattern_failures.append(
            f"citizen_id_mismatch: PLUGIN_ID "
            f"{getattr(module, 'PLUGIN_ID', None)!r} != manifest id "
            f"{data.get('id')!r}")
    try:
        built = manifest_to_data(module.build_manifest())
        parsed = manifest_to_data(manifest_from_data(
            copy.deepcopy(data)))
        if built != parsed:
            pattern_failures.append(
                "citizen_build_mismatch: build_manifest() differs "
                "from manifest_data()")
    except Exception as exc:
        pattern_failures.append(
            f"citizen_build_failed: {type(exc).__name__}: {exc}")
    try:
        claimed = module.sandbox_grants()
        derived = grants_from_manifest(copy.deepcopy(data))
        claimed_key = (claimed.plugin_id, claimed.resources,
                       claimed.surface_permissions, claimed.capabilities)
        derived_key = (derived.plugin_id, derived.resources,
                       derived.surface_permissions, derived.capabilities)
        if claimed_key != derived_key:
            pattern_failures.append(
                f"sandbox_grants_mismatch: module claims resources "
                f"{sorted(claimed.resources)} / capabilities "
                f"{sorted(claimed.capabilities)}, manifest derives "
                f"resources {sorted(derived.resources)} / "
                f"capabilities {sorted(derived.capabilities)}")
    except Exception as exc:
        pattern_failures.append(
            f"sandbox_grants_failed: {type(exc).__name__}: {exc}")
    rows = list(report["checks"]) + [
        {"name": "citizen_pattern", "passed": not pattern_failures,
         "failures": pattern_failures}]
    checks = _Checks()
    checks.rows = rows
    return _report("citizen", report["plugin_id"], checks)


def citizen_modules() -> list[tuple[str, str]]:
    """(module path, plugin id) for every citizen in the tree.

    The known roadmap-order modules come first (a broken one
    is loud, never silently dropped); discovery then adds
    any further module under runmal.plugins exposing the
    citizen pattern, sorted by plugin id - so a citizen that
    lands after this kit (the P-096 road) joins the corpus
    unchanged on the merged tree.
    """
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for path in _KNOWN_CITIZEN_MODULES:
        module = importlib.import_module(path)
        ordered.append((path, module.PLUGIN_ID))
        seen.add(path)
    import runmal.plugins as pkg
    extras: list[tuple[str, str]] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        path = f"runmal.plugins.{info.name}"
        if path in seen:
            continue
        try:
            module = importlib.import_module(path)
        except Exception:
            continue
        if all(hasattr(module, attr) for attr in _CITIZEN_ATTRS) and \
                isinstance(getattr(module, "PLUGIN_ID"), str):
            extras.append((path, module.PLUGIN_ID))
    extras.sort(key=lambda row: row[1])
    return ordered + extras


def conformance_corpus() -> dict:
    """Check every shipped citizen; the corpus document."""
    reports = [check_citizen(path) for path, _id in citizen_modules()]
    passed = [r["plugin_id"] for r in reports if r["passed"]]
    failed = [r["plugin_id"] for r in reports if not r["passed"]]
    core = {"citizens": [
        {"plugin_id": r["plugin_id"], "passed": r["passed"],
         "content_sha256": r["content_sha256"]} for r in reports]}
    return {
        "format": CONFORMANCE_FORMAT,
        "conformance_version": CONFORMANCE_VERSION,
        "kind": "conformance_corpus",
        "citizens": reports,
        "passed": passed,
        "failed": failed,
        "listable": list(passed),
        "all_passed": not failed,
        "content_sha256": _checksum(core),
    }


def is_listable(report: dict) -> bool:
    """A plugin is listable only on a full pass."""
    return bool(report.get("passed"))


def listable_ids(reports) -> list[str]:
    """The listing gate as data: ids of fully passing reports."""
    return [r["plugin_id"] for r in reports if is_listable(r)]


# -- The kit citizen ---------------------------------------------------------


def manifest_data() -> dict:
    """The kit citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Plugin Conformance",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Conformance kit: contract + sandbox "
                       "checks a plugin must pass to be listed.",
        "author": "Rúnmál",
        "capabilities": ["ui.slots"],
        "permissions": ["ui.contribute"],
        "events": [],
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "settings.panel",
                "label": "Plugin Conformance",
                "order": 100,
                "payload": {"kind": "panel",
                            "route": "plugin-conformance"},
            }
        ],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest() -> PluginManifest:
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The kit citizen's P-082 resource grants: empty."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class ConformancePlugin:
    """The kit citizen: a settings-panel contribution only.

    Holds no state - the kit functions are pure host wiring
    in the register_plugin trust class.
    """

    @property
    def manifest(self) -> PluginManifest:
        return build_manifest()

    def handlers(self):
        return PluginHandlers()


def register_plugin(registry: PluginRegistry, *,
                    enable: bool = False):
    """Register the kit citizen into ``registry`` (trusted code only)."""
    plugin = ConformancePlugin()
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "CONFORMANCE_FORMAT", "CONFORMANCE_VERSION", "PLUGIN_ID",
    "PLUGIN_VERSION", "UI_LOCAL_ID", "VERSION",
    "ConformancePlugin", "build_manifest", "check_citizen",
    "check_manifest", "check_manifest_data", "citizen_modules",
    "conformance_corpus", "is_listable", "listable_ids",
    "manifest_data", "register_plugin", "sandbox_grants",
]
