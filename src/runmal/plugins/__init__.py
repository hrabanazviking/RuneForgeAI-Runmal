"""Plugin API v1 public surface (P-081).

The Samtal adapter pattern turned inward: a versioned protocol,
scoped manifest grants, a capability-discovery document and
fire-and-observe chat events, with plugins living OUTSIDE the core
packages -- chats, prompt and generation never grow a branch
naming any plugin (design section 0 / section 8 wiring rule).

This module re-exports the pure core -- the vocabularies
(:mod:`runmal.plugins.api`), the manifest as data
(:mod:`runmal.plugins.manifest`) and the event shapes
(:mod:`runmal.plugins.events`) -- eagerly, so importing the
package can never cycle. The registry, hooks and service names in
``__all__`` resolve lazily through module ``__getattr__`` from
their own modules, which keeps the pure core importable on its
own and lets each layer land independently.
"""

from __future__ import annotations

import importlib

from runmal.plugins.api import (
    FAILURE_LIMIT,
    KNOWN_CAPABILITIES,
    KNOWN_PERMISSIONS,
    PLUGIN_API_VERSION,
    PLUGIN_EVENTS,
    PROMPT_STAGES,
    RESERVED_PERMISSIONS,
    SUPPORTED_API_VERSIONS,
    UI_SLOTS,
    api_vocabulary,
)
from runmal.plugins.events import (
    CHAT_READ_PERMISSION,
    EVENT_CHAT_CREATED,
    EVENT_CHAT_DELETED,
    EVENT_CHAT_RENAMED,
    EVENT_GENERATION_AFTER,
    EVENT_GENERATION_BEFORE,
    EVENT_GENERATION_FAILED,
    EVENT_MESSAGE_CREATED,
    EVENT_MESSAGE_DELETED,
    EVENT_MESSAGE_EDITED,
    EVENT_MESSAGE_SWIPE_SELECTED,
    PLUGIN_EVENT_S107_VALUES,
    PluginEvent,
    chat_created_payload,
    chat_deleted_payload,
    chat_renamed_payload,
    generation_after_payload,
    generation_before_payload,
    generation_failed_payload,
    make_event,
    message_deleted_payload,
    message_payload,
    payload_for_receiver,
    swipe_selected_payload,
)
from runmal.plugins.manifest import (
    HookDecl,
    ManifestError,
    PluginManifest,
    UISlotDecl,
    manifest_from_data,
    manifest_to_data,
    validate_surface_requirements,
)

# Names owned by the registry / hooks layers, resolved on first
# access so this package's pure core never imports them eagerly.
_LAZY = {
    "PluginRegistry": "registry",
    "PluginState": "registry",
    "PluginRecord": "registry",
    "PluginFailure": "registry",
    "PluginHandlers": "registry",
    "PluginRegistrationError": "registry",
    "PluginCompatibilityError": "registry",
    "InvalidPluginTransition": "registry",
    "PromptHookContext": "hooks",
}

__all__ = [
    # Version + vocabularies (api.py).
    "PLUGIN_API_VERSION",
    "SUPPORTED_API_VERSIONS",
    "PLUGIN_EVENTS",
    "KNOWN_CAPABILITIES",
    "KNOWN_PERMISSIONS",
    "RESERVED_PERMISSIONS",
    "UI_SLOTS",
    "PROMPT_STAGES",
    "FAILURE_LIMIT",
    "api_vocabulary",
    # Manifest as data (manifest.py).
    "PluginManifest",
    "HookDecl",
    "UISlotDecl",
    "ManifestError",
    "manifest_from_data",
    "manifest_to_data",
    "validate_surface_requirements",
    # Events (events.py).
    "PluginEvent",
    "make_event",
    "EVENT_CHAT_CREATED",
    "EVENT_CHAT_RENAMED",
    "EVENT_CHAT_DELETED",
    "EVENT_MESSAGE_CREATED",
    "EVENT_MESSAGE_EDITED",
    "EVENT_MESSAGE_DELETED",
    "EVENT_MESSAGE_SWIPE_SELECTED",
    "EVENT_GENERATION_BEFORE",
    "EVENT_GENERATION_AFTER",
    "EVENT_GENERATION_FAILED",
    "PLUGIN_EVENT_S107_VALUES",
    "CHAT_READ_PERMISSION",
    "message_payload",
    "payload_for_receiver",
    "chat_created_payload",
    "chat_renamed_payload",
    "chat_deleted_payload",
    "message_deleted_payload",
    "swipe_selected_payload",
    "generation_before_payload",
    "generation_after_payload",
    "generation_failed_payload",
    # Registry + lifecycle (registry.py, lazy).
    "PluginRegistry",
    "PluginState",
    "PluginRecord",
    "PluginFailure",
    "PluginHandlers",
    "PluginRegistrationError",
    "PluginCompatibilityError",
    "InvalidPluginTransition",
    # Prompt hooks (hooks.py, lazy).
    "PromptHookContext",
]


def __getattr__(name: str):
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"runmal.plugins.{module_name}")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
