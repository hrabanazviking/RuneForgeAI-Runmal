"""Scenario definition sharing packs (P-141, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-141 slice doc.
What the derivation found missing, and what lands here:

- the third stored library had no sealed way to travel.
  Lorebooks (P-045) and prompt artefacts (P-063) move as
  sharing packs — a JSON envelope with a manifest, a
  SHA-256 content checksum and a provenance record,
  inspectable before import and duplicate-aware on
  import — built ahead of Part XII's hub so the hub can
  carry them unchanged (the census names scenarios as
  pack content, VX-59 / VX-60). Scenarios had only
  P-133's bare file export: no checksum, no provenance,
  no inspect-before-import, no duplicate law, and the
  composed export -> create road provably cannot carry
  the record's P-131 import report with it (P-137: the
  report is the one part that road cannot reproduce —
  P-133's one-way naming law).

A scenario pack is ONE stored definition as a
self-contained, importable file:

- the payload is the stored definition itself — the
  P-026 native shape, which P-133 pinned as dict-equal
  to the stored truth — carried verbatim under the
  ``scenario`` key. No second scenario format is
  invented: import writes through P-131's store door
  (``ScenarioStore.create``), whose only validation law
  is P-026's parser, exactly as a plain create.
- identity is simpler here than for lorebooks, and
  honestly so: a lorebook payload needs parse
  normalisation before it can be hashed because several
  file shapes store one way; a stored scenario
  definition IS the normalised shape already, so
  ``content_sha256`` is the SHA-256 of the canonical
  JSON (sorted keys, compact separators) of the
  definition dict itself — defined over what an import
  would actually store, never over pack file bytes, so
  re-serialising a pack never invalidates it (the
  P-045 rule).
- provenance (the P-029 honesty rules): the record
  carries the source definition's id, name, pinned
  revision and ORIGINAL source format (a Voxta-born
  definition's payload is native while its provenance
  honestly says "voxta"), the export stamp, the app
  version, the content checksum, and ``source_report``
  — the source record's P-131 import report verbatim,
  the one artefact the file roads cannot carry. A
  field whose fact is unknown is OMITTED, never
  fabricated; a caller ``note`` rides only when one
  was supplied. Provenance is NOT stored on the new
  record: its carriers are the pack itself and the
  import report, which returns it verbatim.
- collision discipline (never silently overwriting,
  P-025 / P-045): import NEVER merges into or
  overwrites an existing definition. An exact
  duplicate (an owned definition with the same content
  checksum) writes nothing and returns the existing
  record with ``duplicate_exact`` in the report. A
  same-name, different-content definition is a name
  collision: with the default ``on_conflict=
  "create_new"`` a FRESH record (new id) is created
  under the same name — the store has never enforced
  unique names; definitions are told apart by id, and
  the report flags ``name_collision`` — and with
  ``on_conflict="reject"`` the import refuses and
  nothing is written.
- a malformed pack — bad envelope, version, manifest,
  checksum, or a payload the store door would refuse —
  refuses WHOLE in :func:`parse_pack`, before any
  write exists.

What a pack does NOT carry, stated plainly: no
organisation row (filing is library-local by P-134's
design, and P-137's duplication — this slice's closest
in-tree relative — carries none either) and no binding
(a binding is a chat attachment, P-132; its seeded
content is the chat's own truth and cannot travel).
The new record's own import report is its fresh native
parse's report; the pack's ``source_report`` rides in
the pack and the import report as data and is never
installed as the record's report.

One structural divergence from P-045, forced by the
store shape and stated rather than hidden: the
scenario stores are owner-scoped JSON documents
(P-131), not SQL rows, so this module is synchronous
and takes a ``ScenarioStore`` — no session, no
migration; the head stays 0041.

Safety: byte/str input is decoded with
``runmal.safety.safe_json_loads`` under a local
16 MiB cap (named as local, the P-063 precedent; the
scenario-FILE cap remains P-026's 8 MiB law), and
already-decoded input is checked with
``validate_json_tree``. Truth-as-data throughout
(P-027): packing, inspecting and importing a
definition plays nothing back and executes nothing
it carries.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime

from runmal import __version__
from runmal.safety import SafetyError, safe_json_loads, validate_json_tree
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError

PACK_FORMAT = "runmal-scenario-pack"
PACK_VERSION = 1
PACK_KIND = "scenario"
PACK_SCHEMA = "runmal-p141-scenario-pack-v1"
PROVENANCE_VERSION = 1
PROVENANCE_SOURCE_KIND = "scenario_pack_export"
MAX_PACK_BYTES = 16 * 1024 * 1024

CONFLICT_CREATE_NEW = "create_new"
CONFLICT_REJECT = "reject"
CONFLICT_MODES = frozenset({CONFLICT_CREATE_NEW, CONFLICT_REJECT})

_PAYLOAD_FORMAT = "native"

__all__ = [
    "CONFLICT_CREATE_NEW",
    "CONFLICT_MODES",
    "CONFLICT_REJECT",
    "MAX_PACK_BYTES",
    "PACK_FORMAT",
    "PACK_KIND",
    "PACK_SCHEMA",
    "PACK_VERSION",
    "PROVENANCE_SOURCE_KIND",
    "PROVENANCE_VERSION",
    "PackError",
    "build_pack",
    "canonical_bytes",
    "content_checksum",
    "import_pack",
    "inspect_pack",
    "pack_to_bytes",
    "parse_pack",
]


class PackError(ValueError):
    """A scenario pack is malformed, tampered with, or refused."""


def canonical_bytes(payload: object) -> bytes:
    """The canonical JSON bytes identity is defined over."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_checksum(definition: dict) -> str:
    """SHA-256 over the canonical definition (the content identity).

    The definition dict is already the normalised stored
    shape (P-133's dict-equality law), so no parse
    normalisation precedes the hash — what is hashed is
    exactly what an import would store.
    """
    return hashlib.sha256(canonical_bytes(definition)).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _counts(payload: dict) -> tuple[int, int]:
    roles = payload.get("roles")
    bootstrap = payload.get("bootstrap_messages")
    return (
        len(roles) if isinstance(roles, list) else 0,
        len(bootstrap) if isinstance(bootstrap, list) else 0,
    )


def _parse_payload(payload: dict):
    """P-026's parser is the only validation law (the store door's).

    Every refusal surfaces as PackError — one typed refusal
    at the pack boundary, so the router's ValueError -> 422
    mapping covers every malformed pack, never a bare 500
    (the P-045 precedent).
    """
    try:
        return parse_scenario_file(copy.deepcopy(payload))
    except ScenarioParseError as exc:
        raise PackError(
            f"scenario payload is not importable: {exc}") from exc
    except Exception as exc:  # tolerant-parser edge shapes
        raise PackError(
            f"scenario payload is not importable: {exc}") from exc


def _check_native_shape(payload: dict) -> None:
    if payload.get("source_format") != _PAYLOAD_FORMAT:
        raise PackError(
            "pack payload must be the native scenario shape "
            "(source_format 'native'); a Voxta-shaped file "
            "travels through the P-131 store door first and "
            "packs from its stored definition"
        )


# ---------------------------------------------------------------- build


def build_pack(record, *, exported_at: str | None = None,
               note: str | None = None) -> dict:
    """Seal one stored definition record in a pack envelope.

    The payload is the record's stored definition verbatim,
    validated through P-026's own parser first — a pack is
    never minted around contents the store door would
    refuse. Facts the record does not carry are omitted
    from provenance, never fabricated.
    """
    payload = copy.deepcopy(record.definition)
    if not isinstance(payload, dict):
        raise PackError("stored definition is not a JSON object")
    _check_native_shape(payload)
    parsed = _parse_payload(payload)
    stamp = exported_at if exported_at is not None else _now_iso()
    checksum = content_checksum(payload)
    role_count, bootstrap_count = _counts(payload)
    provenance: dict = {
        "provenance_version": PROVENANCE_VERSION,
        "source_kind": PROVENANCE_SOURCE_KIND,
        "source_definition_id": record.id,
        "source_definition_name": record.name,
        "source_revision": record.revision,
        "source_format": record.source_format,
        "exported_at": stamp,
        "app_version": __version__,
        "content_sha256": checksum,
    }
    if isinstance(record.report, dict) and record.report:
        provenance["source_report"] = copy.deepcopy(record.report)
    if note is not None:
        provenance["note"] = note
    manifest = {
        "definition_name": parsed.name,
        "role_count": role_count,
        "bootstrap_count": bootstrap_count,
        "content_sha256": checksum,
        "payload_canonical_bytes": len(canonical_bytes(payload)),
        "exported_at": stamp,
        "app_version": __version__,
        "payload_format": _PAYLOAD_FORMAT,
    }
    return {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "kind": PACK_KIND,
        "schema": PACK_SCHEMA,
        "manifest": manifest,
        "provenance": provenance,
        "scenario": payload,
    }


def pack_to_bytes(pack: dict) -> bytes:
    """Serialise a pack for sharing (human-inspectable JSON).

    The checksum covers the canonical payload, not these
    bytes, so re-serialisation never invalidates a pack.
    """
    return json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8")


# ---------------------------------------------------------------- parse


def _coerce_to_dict(data: bytes | str | dict) -> dict:
    if isinstance(data, dict):
        return copy.deepcopy(data)
    if isinstance(data, (bytes, bytearray, str)):
        try:
            parsed = safe_json_loads(data, limit=MAX_PACK_BYTES)
        except SafetyError as exc:
            raise PackError(str(exc)) from exc
        if not isinstance(parsed, dict):
            raise PackError("scenario pack must be a JSON object")
        return parsed
    raise PackError(
        f"scenario pack must be bytes, str or dict, "
        f"got {type(data).__name__}")


def parse_pack(data: bytes | str | dict) -> dict:
    """Validate a pack end to end; returns a deep copy of it.

    Every check runs before any write exists: envelope
    shape, format and version, manifest against payload
    (definition name, role / bootstrap counts, canonical
    byte length), the content checksum, provenance
    presence and checksum agreement, and the payload
    through P-026's own parser in the native shape.
    Unknown top-level keys are tolerated (a future hub
    may annotate a pack it carries); unknown provenance
    keys are preserved and returned verbatim in reports.
    Raises :class:`PackError` with a precise reason.
    """
    pack = _coerce_to_dict(data)
    try:
        validate_json_tree(pack)
    except SafetyError as exc:
        raise PackError(str(exc)) from exc
    if pack.get("format") != PACK_FORMAT:
        raise PackError(f"pack format is not {PACK_FORMAT!r}")
    version = pack.get("pack_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise PackError(f"pack_version must be an integer, got {version!r}")
    if version != PACK_VERSION:
        raise PackError(
            f"unsupported scenario pack version {version} "
            f"(this build supports {PACK_VERSION}); upgrade Rúnmál "
            "or re-export with a supported version"
        )
    if pack.get("kind") != PACK_KIND:
        raise PackError(f"pack kind is not {PACK_KIND!r}")
    manifest = pack.get("manifest")
    if not isinstance(manifest, dict):
        raise PackError("pack manifest missing or not an object")
    provenance = pack.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        raise PackError("pack provenance missing or not an object")
    payload = pack.get("scenario")
    if not isinstance(payload, dict):
        raise PackError("pack scenario payload missing or not an object")
    _check_native_shape(payload)
    parsed = _parse_payload(payload)
    if manifest.get("definition_name") != parsed.name:
        raise PackError(
            f"manifest definition_name {manifest.get('definition_name')!r} "
            f"does not match payload definition name {parsed.name!r}"
        )
    role_count, bootstrap_count = _counts(payload)
    for key, actual in (
        ("role_count", role_count),
        ("bootstrap_count", bootstrap_count),
    ):
        declared = manifest.get(key)
        if (
            isinstance(declared, bool)
            or not isinstance(declared, int)
            or declared != actual
        ):
            raise PackError(
                f"manifest {key} {declared!r} does not match "
                f"payload count {actual}"
            )
    expected = manifest.get("content_sha256")
    actual_sha = content_checksum(payload)
    if not isinstance(expected, str) or expected != actual_sha:
        raise PackError(
            "pack checksum mismatch: contents do not match the "
            "manifest content_sha256 (the pack was altered or "
            "corrupted in transit)"
        )
    canonical_len = len(canonical_bytes(payload))
    declared_len = manifest.get("payload_canonical_bytes")
    if (
        isinstance(declared_len, bool)
        or not isinstance(declared_len, int)
        or declared_len != canonical_len
    ):
        raise PackError(
            f"manifest payload_canonical_bytes {declared_len!r} does "
            f"not match canonical payload length {canonical_len}"
        )
    prov_sha = provenance.get("content_sha256")
    if prov_sha is not None and prov_sha != actual_sha:
        raise PackError(
            "provenance content_sha256 does not match the manifest "
            "checksum (the provenance record was altered or forged)"
        )
    if (
        "payload_format" in manifest
        and manifest["payload_format"] is not None
        and manifest["payload_format"] != _PAYLOAD_FORMAT
    ):
        raise PackError(
            f"manifest payload_format {manifest['payload_format']!r} "
            f"does not match payload format {_PAYLOAD_FORMAT!r}"
        )
    return pack


def inspect_pack(data: bytes | str | dict) -> dict:
    """Validate a pack and report on it WITHOUT importing.

    The hub's pre-flight: a receiver can see what a pack
    is, where it says it came from, and that its contents
    are intact, before deciding to import it. Touches no
    store and writes nothing.
    """
    pack = parse_pack(data)
    manifest = pack["manifest"]
    return {
        "schema": PACK_SCHEMA,
        "valid": True,
        "format": pack["format"],
        "pack_version": pack["pack_version"],
        "kind": pack["kind"],
        "definition_name": manifest["definition_name"],
        "role_count": manifest["role_count"],
        "bootstrap_count": manifest["bootstrap_count"],
        "content_sha256": manifest["content_sha256"],
        "checksum_verified": True,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
    }


# --------------------------------------------------------------- import

_NOTE_FRESH_REPORT = (
    "the new record's own import report is its fresh "
    "native parse's report; the pack's source_report "
    "rides in the provenance above and in this report "
    "as data — it is not installed as the record's report"
)
_NOTE_NOTHING_ELSE_TRAVELS = (
    "no organisation row and no binding travels in a "
    "pack or is created by importing one: filing is "
    "library-local and a binding is a chat attachment"
)
_NOTE_IDENTITY = (
    "pack identity is the definition payload only — "
    "the source record's id, revision and filing are "
    "never part of it"
)


def import_pack(store, owner_id: str, data: bytes | str | dict, *,
                on_conflict: str = CONFLICT_CREATE_NEW,
                now: str | None = None):
    """Import a pack whole; returns (record, import report).

    Never overwrites: an exact duplicate returns the
    existing record unwritten; a same-name collision
    either creates a fresh record (default) or refuses
    (``on_conflict="reject"``). The write is P-131's
    store door and nothing else. The report carries the
    pack's manifest and provenance verbatim — their
    carriers are the pack and this report; provenance
    is not stored on the record.

    The duplicate scan is over the OWNER's records only
    (another owner's identical definition never counts
    as this owner's duplicate) and is O(owned
    definitions): pack import is a deliberate act, not
    a hot path. The check-then-create is not
    transactional across concurrent imports of the same
    pack — the JSON store has no unique constraint to
    lean on without a migration — so two racing imports
    can both create; accepted for a single-owner local
    app and stated plainly rather than hidden (the
    P-045 honesty precedent).
    """
    if on_conflict not in CONFLICT_MODES:
        raise PackError(
            f"unknown on_conflict mode: {on_conflict!r} "
            f"(valid: {sorted(CONFLICT_MODES)})"
        )
    pack = parse_pack(data)
    payload = pack["scenario"]
    manifest = pack["manifest"]
    checksum = manifest["content_sha256"]
    owned = store.list_for_owner(owner_id)
    report: dict = {
        "schema": PACK_SCHEMA,
        "content_sha256": checksum,
        "definition_name": manifest["definition_name"],
        "on_conflict": on_conflict,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
        "imported_at": _now_iso(),
        "notes": [
            _NOTE_FRESH_REPORT,
            _NOTE_NOTHING_ELSE_TRAVELS,
            _NOTE_IDENTITY,
        ],
    }
    for record in owned:
        if content_checksum(record.definition) == checksum:
            report.update(
                {
                    "created": False,
                    "duplicate_exact": True,
                    "name_collision": False,
                    "definition_id": record.id,
                    "revision": record.revision,
                }
            )
            return record, report
    name_collision = any(
        record.name == manifest["definition_name"] for record in owned)
    if name_collision and on_conflict == CONFLICT_REJECT:
        raise PackError(
            f"a scenario definition named "
            f"{manifest['definition_name']!r} already exists "
            f"with different contents and on_conflict='reject'"
        )
    record = store.create(owner_id, payload, now=now)
    report.update(
        {
            "created": True,
            "duplicate_exact": False,
            "name_collision": name_collision,
            "definition_id": record.id,
            "revision": record.revision,
        }
    )
    return record, report
