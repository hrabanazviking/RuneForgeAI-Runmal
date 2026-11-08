"""Local plugin packs: one manifest as data, sealed (P-083).

A pack is the carrying format for a plugin the owner installs
from a LOCAL source -- a file a friend-instance sent, a pack
Part XII's sovereign hub will carry, a copy kept on disk. It
follows the P-045 lorebook-pack discipline exactly: a single
JSON envelope around the UNCHANGED native payload (here, a
P-081 plugin manifest), a SHA-256 over the payload's canonical
NORMALISED form, and provenance that is carried verbatim and
never interpreted.

Data only, always (P-081 section 11 / VX-42): no code travels
in a pack, ever. A pack's manifest may declare UI slot
contributions (data, honoured handler-free) and event
subscriptions (recorded; delivery needs a handler, and handlers
are bound only by trusted in-tree code). A manifest declaring
prompt hooks can never be installed from a pack -- hooks are
code, and code is not in packs; the manager refuses it with
that reason stated plainly (DataOnlyPackError there, the shape
rule lives here as :func:`pack_data_only_problem`).

Checksum identity is defined over what an install would
actually register -- ``manifest_to_data`` of the parsed
manifest, canonical JSON (sorted keys, compact separators) --
never over raw file bytes: re-serialising a pack (whitespace,
key order, a default spelled out vs omitted) does not mint a
false "different plugin" (the P-045 rule).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import runmal
from runmal.plugins.manifest import (
    ManifestError,
    PluginManifest,
    manifest_from_data,
    manifest_to_data,
)

#: Envelope identity (the P-045 format/kind/schema discipline).
PACK_FORMAT = "runmal-plugin-pack"
PACK_VERSION = 1
PACK_KIND = "plugin"
PACK_SCHEMA = "runmal-p083-plugin-pack-v1"

#: A manifest is a declaration, not a data store: the canonical
#: byte cap for the envelope's plugin member.
PACK_MAX_BYTES = 262144

_ENVELOPE_FIELDS = frozenset(
    {
        "format",
        "pack_version",
        "kind",
        "schema",
        "provenance",
        "plugin",
        "content_sha256",
    }
)


class PackError(ValueError):
    """A pack is outside the envelope shape, or its checksum
    does not match its contents. Nothing is installed from a
    pack that raises this."""


@dataclass(frozen=True)
class ParsedPack:
    """A validated pack: the manifest it carries, its stated
    provenance (verbatim, uninterpreted), and the verified
    content checksum."""

    manifest: PluginManifest
    provenance: dict = field(default_factory=dict)
    content_sha256: str = ""

    @property
    def plugin_id(self) -> str:
        return self.manifest.id


def canonical_manifest_bytes(manifest_data: dict) -> bytes:
    """Canonical JSON bytes of a manifest-data dict."""
    return json.dumps(
        manifest_data, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def manifest_checksum(manifest: PluginManifest) -> str:
    """The content identity of a manifest: SHA-256 over the
    canonical bytes of its normalised data form."""
    return hashlib.sha256(
        canonical_manifest_bytes(manifest_to_data(manifest))
    ).hexdigest()


def build_pack(manifest, *, note: str | None = None,
               exported_at: str | None = None) -> dict:
    """Mint a pack envelope around a manifest.

    ``manifest`` may be a :class:`PluginManifest` or manifest
    data (parsed strictly either way). Provenance is the
    P-045 shape: facts known are stated, a field whose fact is
    unknown is omitted, and a caller ``note`` rides only when
    one was supplied.
    """
    if not isinstance(manifest, PluginManifest):
        manifest = manifest_from_data(manifest)
    provenance: dict = {
        "provenance_version": 1,
        "source_kind": "plugin_pack_export",
        "exported_at": exported_at or datetime.now(UTC).isoformat(),
        "app_version": runmal.__version__,
    }
    if note is not None:
        provenance["note"] = note
    return {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "kind": PACK_KIND,
        "schema": PACK_SCHEMA,
        "provenance": provenance,
        "plugin": manifest_to_data(manifest),
        "content_sha256": manifest_checksum(manifest),
    }


def parse_pack(data: object) -> ParsedPack:
    """Validate ``data`` as a plugin pack, strictly.

    Envelope shape first (unknown keys, wrong format / kind /
    schema / pack_version all reject), then the manifest
    through the P-081 strict parser, then the checksum over
    the normalised manifest. Any defect raises
    :class:`PackError`; a malformed manifest's
    :class:`ManifestError` is translated into PackError with
    its message preserved, so pack callers have exactly one
    failure class to handle.
    """
    if not isinstance(data, dict):
        raise PackError("plugin pack must be an object")
    unknown = set(data) - _ENVELOPE_FIELDS
    if unknown:
        raise PackError(
            f"unknown pack keys: {sorted(unknown, key=repr)}")
    if data.get("format") != PACK_FORMAT:
        raise PackError(
            f"pack format must be {PACK_FORMAT!r}: "
            f"{data.get('format')!r}")
    if data.get("pack_version") != PACK_VERSION:
        raise PackError(
            f"unsupported pack_version: {data.get('pack_version')!r} "
            f"(this host reads {PACK_VERSION})")
    if data.get("kind") != PACK_KIND:
        raise PackError(f"pack kind must be {PACK_KIND!r}: "
                        f"{data.get('kind')!r}")
    if data.get("schema") != PACK_SCHEMA:
        raise PackError(f"pack schema must be {PACK_SCHEMA!r}: "
                        f"{data.get('schema')!r}")
    if "plugin" not in data:
        raise PackError("plugin pack is missing its 'plugin' manifest")
    if "content_sha256" not in data:
        raise PackError("plugin pack is missing 'content_sha256'")
    stated = data["content_sha256"]
    if not isinstance(stated, str) or not stated:
        raise PackError("pack content_sha256 must be a string")
    provenance = data.get("provenance", {})
    if not isinstance(provenance, dict):
        raise PackError("pack provenance must be an object")
    plugin_data = data["plugin"]
    if not isinstance(plugin_data, dict):
        raise PackError("pack 'plugin' must be a manifest object")
    try:
        plugin_bytes = canonical_manifest_bytes(plugin_data)
    except (TypeError, ValueError) as exc:
        raise PackError(f"pack plugin is not JSON-able: {exc}") from exc
    if len(plugin_bytes) > PACK_MAX_BYTES:
        raise PackError(
            f"pack plugin exceeds {PACK_MAX_BYTES} canonical bytes")
    try:
        manifest = manifest_from_data(plugin_data)
    except ManifestError as exc:
        raise PackError(f"invalid plugin manifest in pack: {exc}") from exc
    actual = manifest_checksum(manifest)
    if actual != stated:
        raise PackError(
            "pack content_sha256 does not match its manifest: "
            f"stated {stated!r}, computed {actual!r}")
    return ParsedPack(manifest=manifest, provenance=dict(provenance),
                      content_sha256=actual)


def pack_data_only_problem(manifest: PluginManifest) -> str | None:
    """Why this manifest cannot travel in a pack, or None.

    Prompt hooks are callables bound at registration by
    trusted code (P-081 section 1); a pack carries data only,
    so a hook-declaring manifest has no honest pack install.
    Citizens with hooks register in-tree from their own
    packages (P-084 and kin).
    """
    if manifest.prompt_hooks:
        ids = ", ".join(hook.id for hook in manifest.prompt_hooks)
        return (
            "pack declares prompt hooks "
            f"({ids}), which are code bound by trusted in-tree "
            "registration; packs carry data only, so this plugin "
            "cannot be installed from a pack")
    return None
