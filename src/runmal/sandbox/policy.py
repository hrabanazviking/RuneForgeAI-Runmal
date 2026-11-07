"""Plugin sandbox policy: declared grants, and nothing else (P-082).

A plugin is data plus declared capabilities (roadmap P-082). This
module turns a plugin manifest -- the P-081 manifest shape, taken
as plain data so this module never imports the in-flight
``runmal.plugins`` package -- into the closed set of resource
grants the plugin may exercise, and defines the typed refusal
every excess raises.

The grant rule is subtraction-only:

- A manifest's P-081 ``permissions`` (``chat.read``,
  ``prompt.inject``, ``prompt.modify``, ``ui.contribute`` and the
  reserved ``chat.write``) are *surface* permissions: they govern
  the Plugin API surfaces, and they grant NO resource access here.
- Resource access -- network, files, secrets -- is granted only by
  the sandbox resource permissions in
  :data:`RESOURCE_PERMISSIONS`. Those names are deliberately NOT
  part of the P-081 v1 manifest vocabulary, so a v1 manifest
  *cannot* declare them and every v1 plugin runs with an empty
  resource grant set: no plugin touches the network, the files or
  the secrets uninvited, because in v1 nothing is invited. When a
  future API version admits a resource permission into the
  manifest vocabulary, this policy already enforces it.
- Unknown permission or capability names in manifest data refuse
  loudly (the house closed-vocabulary rule: a grant can never
  quietly widen). Non-string declarations refuse too: a manifest
  is data, never code, so a callable smuggled into a declaration
  is a malformed manifest, not a grant.

Honesty boundary (``docs/SECURITY_MODEL.md`` section 8): this is
an API-surface boundary, not an OS/process sandbox. Plugin
handlers in v1 are trusted in-tree callables bound at
registration; the sandbox governs everything a handler can reach
*through the plugin context it is handed*. It does not claim to
confine arbitrary code that bypasses the context, and no doc in
this slice says otherwise.

Pure and stateless: no I/O, no globals mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SandboxErrorKind(StrEnum):
    MALFORMED_MANIFEST = "malformed_manifest"
    UNKNOWN_GRANT = "unknown_grant"
    PERMISSION_DENIED = "permission_denied"
    CAPABILITY_DENIED = "capability_denied"
    ESCALATION = "escalation"
    PATH_ESCAPE = "path_escape"
    NO_TRANSPORT = "no_transport"
    SECRET_NOT_FOUND = "secret_not_found"
    QUARANTINED = "quarantined"


class SandboxError(ValueError):
    """A sandbox refusal, typed and safe to surface verbatim.

    Messages name plugin ids, grant names, resource names and
    paths only -- never file contents, secret values or payload
    bodies (the P-027 error hygiene rule).
    """

    def __init__(self, kind: SandboxErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)


#: Resource permissions the sandbox enforces. Deliberately disjoint
#: from the P-081 v1 manifest permissions: see the module docstring.
RESOURCE_PERMISSIONS: frozenset[str] = frozenset(
    {
        "network.access",
        "files.read",
        "files.write",
        "secrets.read",
    }
)

#: The P-081 v1 surface permissions (design section 1 of P-081).
#: Recognised so a v1 manifest validates; they grant no resource
#: access in this policy.
SURFACE_PERMISSIONS: frozenset[str] = frozenset(
    {
        "chat.read",
        "prompt.inject",
        "prompt.modify",
        "ui.contribute",
        "chat.write",  # reserved in v1: declared, honoured nowhere
    }
)

#: The P-081 v1 capabilities (design section 1 of P-081).
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "chat.events",
        "prompt.hooks",
        "ui.slots",
        "generation.observe",
    }
)

#: Grant name for each guarded resource verb.
GRANT_NETWORK = "network.access"
GRANT_FILES_READ = "files.read"
GRANT_FILES_WRITE = "files.write"
GRANT_SECRETS_READ = "secrets.read"


@dataclass(frozen=True)
class GrantSet:
    """The immutable resource grants one plugin runs under.

    Frozen on purpose: there is no widening operation. The only
    way to get a larger set is a new manifest, re-derived through
    :func:`grants_from_manifest` -- never an in-place escalation.
    """

    plugin_id: str
    resources: frozenset[str] = frozenset()
    surface_permissions: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()

    def allows(self, grant: str) -> bool:
        return grant in self.resources

    def expanded(self, *grants: str) -> GrantSet:
        """Refuse: grant sets never widen after derivation."""
        raise SandboxError(
            SandboxErrorKind.ESCALATION,
            f"plugin {self.plugin_id!r} grant set cannot be widened "
            f"at runtime (asked for {sorted(grants)!r}); grants come "
            "from the manifest only",
        )


def _manifest_field(manifest: object, key: str, default):
    """Read *key* from a manifest dict or a duck-typed object."""
    if isinstance(manifest, dict):
        return manifest.get(key, default)
    return getattr(manifest, key, default)


def _name_tuple(manifest: object, key: str, plugin_id: str) -> tuple:
    raw = _manifest_field(manifest, key, ())
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise SandboxError(
            SandboxErrorKind.MALFORMED_MANIFEST,
            f"plugin {plugin_id!r} manifest {key} must be a list of names",
        )
    for item in raw:
        if not isinstance(item, str):
            raise SandboxError(
                SandboxErrorKind.MALFORMED_MANIFEST,
                f"plugin {plugin_id!r} manifest {key} entries must be "
                f"strings (data only, never code): {type(item).__name__}",
            )
    return tuple(raw)


def grants_from_manifest(manifest: object) -> GrantSet:
    """Derive the resource grants a manifest declares.

    Accepts the P-081 manifest as plain data (a dict in the
    ``manifest_to_data`` shape) or any duck-typed object carrying
    ``id`` / ``permissions`` / ``capabilities`` attributes (the
    landed ``PluginManifest`` qualifies). Strict: unknown names
    refuse with :attr:`SandboxErrorKind.UNKNOWN_GRANT`, so a typo
    can never silently become a grant or silently become nothing.
    """
    plugin_id = _manifest_field(manifest, "id", None)
    if not isinstance(plugin_id, str) or not plugin_id:
        raise SandboxError(
            SandboxErrorKind.MALFORMED_MANIFEST,
            "plugin manifest must carry a non-empty string 'id'",
        )
    permissions = _name_tuple(manifest, "permissions", plugin_id)
    capabilities = _name_tuple(manifest, "capabilities", plugin_id)
    resources: set[str] = set()
    surface: set[str] = set()
    for name in permissions:
        if name in RESOURCE_PERMISSIONS:
            resources.add(name)
        elif name in SURFACE_PERMISSIONS:
            surface.add(name)
        else:
            raise SandboxError(
                SandboxErrorKind.UNKNOWN_GRANT,
                f"plugin {plugin_id!r} declares unknown permission "
                f"{name!r}; the sandbox grants nothing for it",
            )
    for name in capabilities:
        if name not in KNOWN_CAPABILITIES:
            raise SandboxError(
                SandboxErrorKind.UNKNOWN_GRANT,
                f"plugin {plugin_id!r} declares unknown capability "
                f"{name!r}",
            )
    return GrantSet(
        plugin_id=plugin_id,
        resources=frozenset(resources),
        surface_permissions=frozenset(surface),
        capabilities=frozenset(capabilities),
    )
