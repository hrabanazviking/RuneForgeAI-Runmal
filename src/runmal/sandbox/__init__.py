"""Plugin sandbox: declared grants, guarded context (P-082).

Plugins are data plus declared capabilities; this package is the
enforcement half of that sentence. :func:`grants_from_manifest`
derives the closed resource grant set from a P-081-shaped
manifest, and :class:`Sandbox` is the only context a plugin
handler is handed: files, network and secrets are reachable only
through it, only under a declared grant, and every refusal is
typed, audited and isolated from the chat path.

Honesty boundary (ADR-0008, ``docs/SECURITY_MODEL.md`` section
8): an API-surface boundary for trusted in-tree handlers, not an
OS/process sandbox.
"""

from __future__ import annotations

from runmal.sandbox.guard import (
    FAILURE_LIMIT,
    AuditEntry,
    RunFailure,
    RunOutcome,
    Sandbox,
)
from runmal.sandbox.policy import (
    GRANT_FILES_READ,
    GRANT_FILES_WRITE,
    GRANT_NETWORK,
    GRANT_SECRETS_READ,
    KNOWN_CAPABILITIES,
    RESOURCE_PERMISSIONS,
    SURFACE_PERMISSIONS,
    GrantSet,
    SandboxError,
    SandboxErrorKind,
    grants_from_manifest,
)

__all__ = [
    "FAILURE_LIMIT",
    "AuditEntry",
    "RunFailure",
    "RunOutcome",
    "Sandbox",
    "GRANT_FILES_READ",
    "GRANT_FILES_WRITE",
    "GRANT_NETWORK",
    "GRANT_SECRETS_READ",
    "KNOWN_CAPABILITIES",
    "RESOURCE_PERMISSIONS",
    "SURFACE_PERMISSIONS",
    "GrantSet",
    "SandboxError",
    "SandboxErrorKind",
    "grants_from_manifest",
]
