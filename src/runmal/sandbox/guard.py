"""Guarded plugin context (P-082).

A plugin handler receives only this facade -- :class:`Sandbox` -- and
nothing else.  Every resource a handler can reach goes through it,
under the grants derived from the plugin's manifest by
:mod:`runmal.sandbox.policy`:

- Files need the ``files.read`` / ``files.write`` grant, and every
  path must resolve inside the plugin root: ``..`` segments, absolute
  paths outside the root and symlink escapes all refuse with
  ``PATH_ESCAPE``.
- Network needs the ``network.access`` grant plus a host-supplied
  transport; there is no default transport, so a sandbox built
  without one refuses with ``NO_TRANSPORT``.  Only ``http`` and
  ``https`` URLs may be fetched.
- Secrets need the ``secrets.read`` grant plus a host-supplied
  provider; secrets are queried by name only, and secret values never
  appear in errors or in the audit log.
- :meth:`Sandbox.require_capability` gates plugin API surfaces on
  the manifest's declared capabilities.
- :meth:`Sandbox.run` failure-isolates a handler call in the P-081
  failure-rule shape: failures are recorded, and after
  ``FAILURE_LIMIT`` consecutive failures the sandbox is quarantined
  and refuses to run again until reset (P-099 refines this later).
- The audit log is metadata only: plugin id, resource, action,
  outcome and refusal kind -- never file contents, payload bodies or
  secret values.

Honesty boundary: this is an API-surface boundary per
``docs/SECURITY_MODEL.md`` section 8 and ADR-0008, for trusted
in-tree handlers bound at registration.  It is NOT an OS/process
sandbox and does not claim to confine code that bypasses the context
it is handed.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runmal.sandbox.policy import (
    GRANT_FILES_READ,
    GRANT_FILES_WRITE,
    GRANT_NETWORK,
    GRANT_SECRETS_READ,
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
]

#: Consecutive run failures that quarantine a sandbox (P-081 shape).
FAILURE_LIMIT = 3


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AuditEntry:
    """One audited decision: metadata only, never payload data."""

    plugin_id: str
    resource: str
    action: str
    outcome: str
    kind: str | None = None
    at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict view, with ``at`` as ISO-8601 text."""
        return {
            "plugin_id": self.plugin_id,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "kind": self.kind,
            "at": self.at.isoformat(),
        }


@dataclass(frozen=True)
class RunFailure:
    """One isolated handler failure, as recorded by :meth:`Sandbox.run`."""

    plugin_id: str
    error_type: str
    message: str
    at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class RunOutcome:
    """The result of one :meth:`Sandbox.run` call."""

    ok: bool
    value: Any = None
    failure: RunFailure | None = None
    kind: str | None = None


class Sandbox:
    """The guarded context one plugin handler is handed.

    ``manifest`` is the P-081 manifest as plain data; the grants are
    derived from it unless ``grants`` is given, and given grants may
    never exceed the manifest (a wider set, or another plugin's set,
    is an escalation and refuses).  ``root`` is the plugin's file
    root; ``network_transport`` and ``secret_provider`` are the
    host's network and secret backends -- neither has a default.
    """

    def __init__(
        self,
        manifest: object,
        *,
        root: str | Path | None = None,
        grants: GrantSet | None = None,
        network_transport: Callable[..., Any] | None = None,
        secret_provider: Mapping[str, str] | Callable[[str], str | None] | None = None,
    ) -> None:
        derived = grants_from_manifest(manifest)
        if grants is not None and (
            grants.plugin_id != derived.plugin_id
            or grants.resources - derived.resources
        ):
            raise SandboxError(
                SandboxErrorKind.ESCALATION,
                f"plugin {derived.plugin_id!r} grants exceed its manifest; "
                "grants come from the manifest only",
            )
        self._grants = grants if grants is not None else derived
        self._root = Path(root).resolve() if root is not None else None
        self._network_transport = network_transport
        self._secret_provider = secret_provider
        self._audit: list[AuditEntry] = []
        self._failures: list[RunFailure] = []
        self._consecutive = 0

    @property
    def plugin_id(self) -> str:
        return self._grants.plugin_id

    @property
    def grants(self) -> GrantSet:
        return self._grants

    @property
    def quarantined(self) -> bool:
        return self._consecutive >= FAILURE_LIMIT

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive

    def audit_log(self) -> list[AuditEntry]:
        """Return a copy of the audit log (metadata only)."""
        return list(self._audit)

    def failures(self) -> list[RunFailure]:
        """Return a copy of the recorded run failures."""
        return list(self._failures)

    def _allow(self, resource: str, action: str) -> None:
        self._audit.append(
            AuditEntry(
                plugin_id=self.plugin_id,
                resource=resource,
                action=action,
                outcome="allow",
            )
        )

    def _deny(self, resource: str, action: str, error: SandboxError) -> SandboxError:
        self._audit.append(
            AuditEntry(
                plugin_id=self.plugin_id,
                resource=resource,
                action=action,
                outcome="deny",
                kind=error.kind.value,
            )
        )
        return error

    def _require(self, grant: str, resource: str, action: str) -> None:
        if not self._grants.allows(grant):
            raise self._deny(
                resource,
                action,
                SandboxError(
                    SandboxErrorKind.PERMISSION_DENIED,
                    f"plugin {self.plugin_id!r} lacks grant {grant!r}",
                ),
            )

    def require_capability(self, capability: str) -> None:
        """Gate an API surface on a declared manifest capability."""
        if capability not in self._grants.capabilities:
            raise self._deny(
                "capability",
                capability,
                SandboxError(
                    SandboxErrorKind.CAPABILITY_DENIED,
                    f"plugin {self.plugin_id!r} lacks capability {capability!r}",
                ),
            )
        self._allow("capability", capability)

    def _resolve_inside_root(self, path: str | Path, action: str) -> Path:
        if self._root is None:
            raise self._deny(
                "files",
                action,
                SandboxError(
                    SandboxErrorKind.PATH_ESCAPE,
                    f"plugin {self.plugin_id!r} has no plugin root; "
                    f"path {path} refused",
                ),
            )
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        resolved = Path(os.path.realpath(candidate))
        if resolved != self._root and self._root not in resolved.parents:
            raise self._deny(
                "files",
                action,
                SandboxError(
                    SandboxErrorKind.PATH_ESCAPE,
                    f"plugin {self.plugin_id!r} path {path} escapes its root",
                ),
            )
        return resolved

    def read_file(self, path: str | Path) -> bytes:
        """Read a file inside the plugin root, under ``files.read``."""
        self._require(GRANT_FILES_READ, "files", "read")
        resolved = self._resolve_inside_root(path, "read")
        data = resolved.read_bytes()
        self._allow("files", "read")
        return data

    def write_file(self, path: str | Path, data: bytes | bytearray) -> int:
        """Write a file inside the plugin root, under ``files.write``."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(
                f"write_file data must be bytes, not {type(data).__name__}"
            )
        self._require(GRANT_FILES_WRITE, "files", "write")
        resolved = self._resolve_inside_root(path, "write")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(bytes(data))
        self._allow("files", "write")
        return len(data)

    def fetch(self, url: str, *, method: str = "GET") -> Any:
        """Fetch ``url`` through the host transport, under ``network.access``."""
        self._require(GRANT_NETWORK, "network", "fetch")
        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise self._deny(
                "network",
                "fetch",
                SandboxError(
                    SandboxErrorKind.PERMISSION_DENIED,
                    f"plugin {self.plugin_id!r} may not fetch scheme "
                    f"{scheme!r}; only http and https",
                ),
            )
        if self._network_transport is None:
            raise self._deny(
                "network",
                "fetch",
                SandboxError(
                    SandboxErrorKind.NO_TRANSPORT,
                    f"plugin {self.plugin_id!r} has no host network transport",
                ),
            )
        result = self._network_transport(method.upper(), url)
        self._allow("network", "fetch")
        return result

    def get_secret(self, name: str) -> str:
        """Return secret ``name`` from the host provider, by name only."""
        self._require(GRANT_SECRETS_READ, "secrets", "get")
        provider = self._secret_provider
        value: str | None
        if provider is None:
            value = None
        elif isinstance(provider, Mapping):
            value = provider.get(name)
        elif callable(provider):
            value = provider(name)
        else:
            value = None
        if value is None:
            raise self._deny(
                "secrets",
                "get",
                SandboxError(
                    SandboxErrorKind.SECRET_NOT_FOUND,
                    f"plugin {self.plugin_id!r} secret {name!r} not found",
                ),
            )
        self._allow("secrets", "get")
        return value

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> RunOutcome:
        """Run ``fn`` failure-isolated; quarantine after FAILURE_LIMIT."""
        if self.quarantined:
            self._audit.append(
                AuditEntry(
                    plugin_id=self.plugin_id,
                    resource="run",
                    action="run",
                    outcome="deny",
                    kind=SandboxErrorKind.QUARANTINED.value,
                )
            )
            return RunOutcome(ok=False, kind=SandboxErrorKind.QUARANTINED.value)
        try:
            value = fn(*args, **kwargs)
        except Exception as exc:
            failure = RunFailure(
                plugin_id=self.plugin_id,
                error_type=type(exc).__name__,
                message=str(exc)[:200],
            )
            self._failures.append(failure)
            self._consecutive += 1
            return RunOutcome(ok=False, failure=failure)
        self._consecutive = 0
        return RunOutcome(ok=True, value=value)

    def reset_failures(self) -> None:
        """Clear the consecutive-failure counter, lifting quarantine."""
        self._consecutive = 0
