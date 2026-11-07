"""Permission cards: what a plugin asks for, in plain words (P-083).

A permission card is the manager's honesty surface: before any
install or update is granted, the card renders the manifest's
declared capabilities, permissions, events, hooks and UI slots
VERBATIM (P-081 design section 10), each permission with a
plain-language statement of what granting it actually does in
v1, reserved permissions flagged as honoured by nothing today,
and -- for an update -- the diff against the installed version,
so a grant decision is made on exactly what changed.

The card is pure data built from the manifest alone: no
registry, no store, no I/O. The grant rule it serves: an
install/update proceeds only when the caller's granted set
equals the declared permission set exactly -- the card is what
was shown, the grant is what was approved, and the manager
refuses any gap between the two.
"""

from __future__ import annotations

from runmal.plugins.api import RESERVED_PERMISSIONS
from runmal.plugins.manifest import PluginManifest, manifest_to_data

#: Plain-language effect of each v1 permission, stated from the
#: P-081 semantics (api.py) in this slice's own words.
PERMISSION_EFFECTS: dict[str, str] = {
    "chat.read": (
        "Message text may ride in the chat events this plugin "
        "subscribes to. Without it, events carry metadata only."),
    "prompt.inject": (
        "The plugin may add prompt slots before composition, "
        "through its declared prompt hooks. Hooks are code, so "
        "a data-only pack cannot use this permission."),
    "prompt.modify": (
        "The plugin may rewrite the composed message list, "
        "through its declared prompt hooks. Hooks are code, so "
        "a data-only pack cannot use this permission."),
    "ui.contribute": (
        "The plugin's declared UI slot contributions (panels, "
        "labels) may appear in the named slots while it is "
        "enabled."),
    "chat.write": (
        "RESERVED: declared for future use. No v1 surface "
        "honours it -- granting it gives the plugin nothing "
        "today, and plugins cannot create, edit or delete "
        "messages in v1."),
}

#: Plain-language note per capability.
CAPABILITY_NOTES: dict[str, str] = {
    "chat.events": "Subscribes to the declared chat events.",
    "prompt.hooks": "Runs the declared prompt hooks.",
    "ui.slots": "Contributes to the declared UI slots.",
    "generation.observe": "Observes generation start, finish and failure events.",
}


def _permission_rows(manifest: PluginManifest,
                     granted: set[str] | None) -> list[dict]:
    rows = []
    for name in manifest.permissions:
        rows.append({
            "name": name,
            "effect": PERMISSION_EFFECTS.get(name, ""),
            "reserved": name in RESERVED_PERMISSIONS,
            "granted": (None if granted is None else name in granted),
        })
    return rows


def _honesty_notes(manifest: PluginManifest) -> list[str]:
    """Notes for declarations that are inert or reserved, so a
    card never overstates what a grant buys."""
    notes: list[str] = []
    permissions = set(manifest.permissions)
    for name in sorted(permissions & set(RESERVED_PERMISSIONS)):
        notes.append(
            f"permission {name!r} is reserved in v1: it is "
            "honoured by no surface and grants nothing today")
    if "prompt.inject" in permissions and not any(
            hook.stage == "slots" for hook in manifest.prompt_hooks):
        notes.append(
            "permission 'prompt.inject' is declared but no "
            "slots-stage prompt hook uses it in this manifest")
    if "prompt.modify" in permissions and not any(
            hook.stage == "messages" for hook in manifest.prompt_hooks):
        notes.append(
            "permission 'prompt.modify' is declared but no "
            "messages-stage prompt hook uses it in this manifest")
    if "ui.contribute" in permissions and not manifest.ui_slots:
        notes.append(
            "permission 'ui.contribute' is declared but the "
            "manifest contributes to no UI slot")
    if "chat.read" in permissions and not manifest.events:
        notes.append(
            "permission 'chat.read' is declared but the "
            "manifest subscribes to no event that carries text")
    if manifest.prompt_hooks:
        notes.append(
            "this manifest declares prompt hooks, which are "
            "code: it can be registered by trusted in-tree code "
            "but never installed from a data-only pack")
    return notes


def _changes(manifest: PluginManifest,
             previous: PluginManifest) -> dict:
    def diff(old, new):
        return sorted(set(new) - set(old)), sorted(set(old) - set(new))
    p_added, p_removed = diff(previous.permissions, manifest.permissions)
    c_added, c_removed = diff(previous.capabilities, manifest.capabilities)
    e_added, e_removed = diff(previous.events, manifest.events)
    return {
        "from_version": previous.version,
        "to_version": manifest.version,
        "permissions_added": p_added,
        "permissions_removed": p_removed,
        "capabilities_added": c_added,
        "capabilities_removed": c_removed,
        "events_added": e_added,
        "events_removed": e_removed,
    }


def permission_card(manifest: PluginManifest, *,
                    granted=None,
                    previous: PluginManifest | None = None) -> dict:
    """The permission card for one manifest, as plain data.

    ``granted``: the permission set a caller has approved, or
    None when no grant decision is in view (each row's
    ``granted`` is then None). ``previous``: the installed
    manifest an update would replace, or None; when given,
    ``changes`` carries the declaration diff.
    """
    granted_set = None if granted is None else set(granted)
    data = manifest_to_data(manifest)
    return {
        "plugin_id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "api_version": manifest.api_version,
        "description": manifest.description,
        "author": manifest.author,
        "capabilities": [
            {"name": name,
             "note": CAPABILITY_NOTES.get(name, "")}
            for name in manifest.capabilities
        ],
        "permissions": _permission_rows(manifest, granted_set),
        "permission_names": list(manifest.permissions),
        "events": list(manifest.events),
        "prompt_hooks": [
            {"id": hook.id, "stage": hook.stage,
             "priority": hook.priority}
            for hook in manifest.prompt_hooks
        ],
        "ui_slots": [
            {"id": decl.id, "slot": decl.slot, "label": decl.label}
            for decl in manifest.ui_slots
        ],
        "settings_declared": manifest.settings is not None,
        "enabled_by_default": manifest.enabled_by_default,
        "requires_grant": bool(manifest.permissions),
        "notes": _honesty_notes(manifest),
        "changes": (
            None if previous is None else _changes(manifest, previous)),
        "manifest": data,
    }
