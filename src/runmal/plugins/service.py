"""Plugin host glue (P-081, design sections 6/8 + lead adjudication B).

The wiring seam is a module-level default-registry holder -- the
``generation/service.py`` ``_cancel_tokens`` precedent, chosen once
by the lead: ``create_app`` (or any host bootstrap) builds the
registry with :func:`build_registry` and installs it with
:func:`set_default_registry`; chats / generation / prompt wiring
reaches it through :func:`get_default_registry` and the
never-raising :func:`dispatch_event` helper.

Honest v1: :func:`build_registry` returns an EMPTY registry.
Zero in-tree plugins ship in P-081; citizens are P-084+.
"""

from __future__ import annotations

import runmal
from runmal.plugins.api import RESERVED_PERMISSIONS, api_vocabulary
from runmal.plugins.manifest import manifest_to_data
from runmal.plugins.registry import PluginRecord, PluginRegistry

_default_registry: PluginRegistry | None = None


def build_registry() -> PluginRegistry:
    """A fresh, empty registry (zero in-tree plugins in v1)."""
    return PluginRegistry()


def set_default_registry(registry: PluginRegistry | None):
    """Install (or clear, with None) the process default registry."""
    global _default_registry
    _default_registry = registry
    return registry


def get_default_registry() -> PluginRegistry | None:
    return _default_registry


def ensure_default_registry() -> PluginRegistry:
    """The default registry, built + installed lazily if unset."""
    global _default_registry
    if _default_registry is None:
        _default_registry = build_registry()
    return _default_registry


async def dispatch_event(name, *, chat_id=None, message_id=None,
                         data=None) -> None:
    """Host dispatch helper: fire-and-observe, never raises.

    No-op fast path when no default registry is installed or no
    ENABLED plugin subscribes -- host operations stay byte-
    identical to pre-P-081 behaviour (PLG-01).
    """
    registry = _default_registry
    if registry is None:
        return
    try:
        if not registry.has_enabled_subscriber(name):
            return
        await registry.dispatch_event(
            name, chat_id=chat_id, message_id=message_id, data=data)
    except Exception:
        # Dispatch is observation only; a wiring-level surprise
        # must never reach the host operation (PLG-01).
        return


def plugin_api_info(registry: PluginRegistry) -> dict:
    """The section 6 introspection document for one registry:
    the vocabulary half plus live counts -- the bridge
    ``/capabilities`` pattern turned inward."""
    info = api_vocabulary()
    return {
        "plugin_api_version": info["plugin_api_version"],
        "supported_api_versions": info["supported_api_versions"],
        "app_version": runmal.__version__,
        "events": info["events"],
        "capabilities": info["capabilities"],
        "permissions": info["permissions"],
        "ui_slots": info["ui_slots"],
        "prompt_stages": info["prompt_stages"],
        "failure_limit": info["failure_limit"],
        "registered": len(registry.keys()),
        "enabled": len(registry.enabled_records()),
    }


def failure_to_dict(failure) -> dict:
    """The detail-view failure shape: metadata only (PLG-05)."""
    return {
        "plugin_id": failure.plugin_id,
        "surface": failure.surface,
        "hook": failure.hook,
        "error_type": failure.error_type,
        "message": failure.message,
        "at": failure.at.isoformat(),
    }


def record_to_dict(record: PluginRecord) -> dict:
    """The section 8 list-row shape for one record."""
    manifest = record.manifest
    last_error = None
    if record.last_error is not None:
        failure = record.last_error
        last_error = {
            "surface": failure.surface,
            "hook": failure.hook,
            "error_type": failure.error_type,
            "at": failure.at.isoformat(),
        }
    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "api_version": manifest.api_version,
        "state": record.state.value,
        "capabilities": list(manifest.capabilities),
        "permissions": list(manifest.permissions),
        "events": list(manifest.events),
        "prompt_hooks": len(manifest.prompt_hooks),
        "ui_slots": len(manifest.ui_slots),
        "consecutive_failures": record.consecutive_failures,
        "last_error": last_error,
    }


def record_detail_to_dict(record: PluginRecord,
                          registry: PluginRegistry) -> dict:
    """The section 8 detail shape: the list row + the manifest
    verbatim + the retained failure log + this plugin's own UI
    contributions. Reserved permissions (``chat.write``) are
    flagged: in the vocabulary, honoured by no v1 surface."""
    detail = record_to_dict(record)
    detail["manifest"] = manifest_to_data(record.manifest)
    detail["failure_log"] = [
        failure_to_dict(failure) for failure in record.failure_log]
    detail["ui_contributions"] = [
        row for row in registry.ui_contributions()
        if row["plugin_id"] == record.manifest.id]
    detail["reserved_permissions"] = [
        name for name in record.manifest.permissions
        if name in RESERVED_PERMISSIONS]
    return detail
