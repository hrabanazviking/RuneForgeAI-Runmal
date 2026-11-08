"""Plugin API vocabularies and version constants (P-081, design sections 1/3/5/6).

Pure data, standard library only: this module is the single source
for every closed vocabulary the plugin API v1 speaks -- the event
names, the capabilities, the permissions, the UI slots and the
prompt stages -- plus the API version itself. It imports nothing
from the rest of :mod:`runmal`, so it can never take part in an
import cycle: ``manifest``, ``events``, ``hooks``, ``registry`` and
``service`` all import from here, and this module imports from none
of them. Read it as the audit-friendly contract: if a name is not
in one of these frozensets, v1 does not speak it, and a manifest
naming it rejects loudly (the bridge scopes grammar is the kin:
exact names, no prefix games, a grant can never quietly widen).

Version policy (design section 6): the API version is an int major.
:data:`PLUGIN_API_VERSION` is the version this host speaks;
:data:`SUPPORTED_API_VERSIONS` is the set a manifest's
``api_version`` may name at registration. A future v2 host keeps 1
in the supported set while it can honour the v1 contracts; removing
a version from the set is the breaking act, and is what the version
exists to make explicit. Plugin versions (a manifest's own
``version`` field) play no part in compatibility.
"""

from __future__ import annotations

#: The plugin API version this host speaks (design section 6).
PLUGIN_API_VERSION: int = 1

#: Manifest ``api_version`` values accepted at registration time.
#: Compatibility is judged only there, never at parse time and
#: never per dispatch (design section 6).
SUPPORTED_API_VERSIONS: frozenset[int] = frozenset({PLUGIN_API_VERSION})

#: Chat / generation event names a plugin may declare (design
#: section 3). Frozen for api v1: adding a name is an api-version
#: event, never a plugin's choice. The chat names reuse the S107
#: chats/service.py EVENT_* vocabulary; ``runmal.plugins.events``
#: carries the per-name constants and the stated mapping for the
#: one renamed event (``message.created``).
PLUGIN_EVENTS: frozenset[str] = frozenset(
    {
        "chat.created",
        "chat.renamed",
        "chat.deleted",
        "message.created",
        "message.edited",
        "message.deleted",
        "message.swipe_selected",
        "generation.before",
        "generation.after",
        "generation.failed",
    }
)

#: Capabilities a manifest may declare (design section 1). A
#: capability says which host surfaces the plugin may use at all;
#: the matching permission says what it may do on that surface.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "chat.events",
        "prompt.hooks",
        "ui.slots",
        "generation.observe",
    }
)

#: Permissions a manifest may declare (design section 1).
#: ``chat.read`` lets message text ride in event payloads (the
#: section 3 redaction rule); ``prompt.inject`` gates the slots
#: prompt stage; ``prompt.modify`` gates the messages prompt stage;
#: ``ui.contribute`` gates UI slot contributions. ``chat.write``
#: is RESERVED: it is in the vocabulary so P-083 permission cards
#: can name it, but no v1 surface honours it -- declaring it grants
#: nothing, and plugins cannot create, edit or delete messages
#: in v1. (``generation.observe`` is a capability, not a
#: permission, and deliberately does not appear here.)
KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    {
        "chat.read",
        "prompt.inject",
        "prompt.modify",
        "ui.contribute",
        "chat.write",
    }
)

#: Permissions that are in the vocabulary but honoured by no v1
#: surface (design section 1). The registry detail view flags
#: these "reserved".
RESERVED_PERMISSIONS: frozenset[str] = frozenset({"chat.write"})

#: Named UI slots a plugin may contribute to (design section 5).
#: Adding a slot name is an api-version event, never a plugin's
#: choice: a contribution naming a slot outside this set rejects
#: at registration.
UI_SLOTS: frozenset[str] = frozenset(
    {
        "chat.header",
        "chat.sidebar",
        "chat.toolbar",
        "message.actions",
        "settings.panel",
        "home.panel",
    }
)

#: Prompt hook stages (design section 4): ``slots`` runs
#: pre-compose (additive, gated by ``prompt.inject``); ``messages``
#: runs post-compose (transforming, gated by ``prompt.modify``).
#: Stages always run slots-before-messages.
PROMPT_STAGES: frozenset[str] = frozenset({"slots", "messages"})

#: Consecutive handler failures at which an ENABLED plugin is
#: flipped to ERRORED by the host (design section 2 failure rule;
#: the substrate P-099 refines). Reported by the section 6
#: introspection document.
FAILURE_LIMIT: int = 3


def api_vocabulary() -> dict:
    """The vocabulary half of the section 6 introspection document.

    Everything a consumer needs to learn what v1 speaks, as plain
    JSON-able data with sorted lists. ``runmal.plugins.service``
    merges this with the live counts (app version, registered /
    enabled plugin counts) to build the full ``plugin_api_info``
    document -- the bridge ``/capabilities`` pattern (S610) turned
    inward.
    """
    return {
        "plugin_api_version": PLUGIN_API_VERSION,
        "supported_api_versions": sorted(SUPPORTED_API_VERSIONS),
        "events": sorted(PLUGIN_EVENTS),
        "capabilities": sorted(KNOWN_CAPABILITIES),
        "permissions": sorted(KNOWN_PERMISSIONS),
        "ui_slots": sorted(UI_SLOTS),
        "prompt_stages": sorted(PROMPT_STAGES),
        "failure_limit": FAILURE_LIMIT,
    }
