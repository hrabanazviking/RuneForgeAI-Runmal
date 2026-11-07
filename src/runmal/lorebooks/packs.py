"""Lorebook sharing packs (P-045).

Roadmap line: *Book sharing: lorebooks as importable packs
(Part XII's hub carries them).*

A pack is ONE lorebook as a self-contained, importable file:
the book an owner can hand to another Rúnmál instance (or keep
as a portable copy) and the receiver can import whole, with the
contents proven intact and the origin stated honestly. Part
XII's sovereign hub (P-187..P-202, per the roadmap table) is
the future carrier — signed local packs and friend-instance
exchange instead of a central store (DELTA_TABLE VX-59) — so
this slice builds the pack itself, as data, and the hub will
carry it unchanged.

Format decision (recorded per the slice brief)
----------------------------------------------
The pack is a single JSON envelope, NOT a ``.runmal`` archive
and NOT a bare native export:

- A lorebook is one aggregate — book settings + entries, no
  binary assets — so the ZIP/member machinery of the portable
  archive (``runmal.portable.archive``, S801) buys nothing
  here. That archive remains the whole-library backup format;
  a pack is the single-book sharing format, and it composes
  the archive's *discipline* (a manifest, a SHA-256 over the
  contents, honest exclusions) without its container.
- A bare ``transfer.export_book`` payload carries no checksum
  and no provenance, so a shared file could be silently
  altered and its origin silently lost. The envelope adds
  exactly those two things around the UNCHANGED native
  payload: import parses the payload with the existing
  ``transfer.parse_import`` / ``validate_parsed_book`` path,
  and creation writes through ``transfer.import_book_transactional``
  — no parallel lorebook format is invented.
- The payload may also come from the file layer:
  ``interop.export_native(LorebookFile)`` output packs with
  :func:`build_pack_from_native_payload`, so a world-info
  file's natively-modelled contents can travel as a pack too.

Envelope (``format`` ``runmal-lorebook-pack``, version 1)::

    {"format": ..., "pack_version": 1, "kind": "lorebook",
     "schema": "runmal-p045-lorebook-pack-v1",
     "manifest": {"book_name", "entry_count",
                  "content_sha256", "payload_canonical_bytes",
                  "exported_at", "app_version",
                  "payload_format", "payload_version"},
     "provenance": {...see below...},
     "lorebook": <transfer.export_book native payload>}

Checksums: ``content_sha256`` is the SHA-256 of the canonical
JSON (sorted keys, compact separators) of the payload's
NORMALISED form — the (book fields, entry fields) pair that
``transfer.parse_import`` produces, entries sorted by their
own canonical JSON. Identity is therefore defined over what
an import would actually store, never over raw file bytes:
cosmetic payload differences the import path normalises away
(a default spelled out vs omitted, ``useProbability`` folded
into the effective percent by the store, a tolerant numeric
spelling) do not mint a false "different book", and two files
that would store identically hash identically. Entry order
is NOT part of identity either: the store lists entries by
priority / creation time and the scan orders by priority
anyway. The checksum doubles as the exact-duplicate identity
(the P-025 precedent). It covers the normalised payload,
never the pack file bytes: re-serialising a pack
(whitespace, key order) does not invalidate it. The manifest
also carries ``payload_canonical_bytes``, the byte length
of that canonical form, as a cheap hub-side size check.

Provenance (the P-029 honesty rules, mirrored): the record
carries ``provenance_version``, ``source_kind``
(``lorebook_pack_export``), the source book's id and name when
the export came from a stored book, ``exported_at``, the
exporting ``app_version`` and the ``content_sha256``. A field
whose fact is unknown is OMITTED, never fabricated — a pack
built from a bare payload has no ``source_book_id``. An
optional caller ``note`` rides only when one was supplied.
Provenance is NOT stored on the lorebook row (no migration in
this slice; the head stays 0032): its carriers are the pack
itself and the import report, which returns the pack's
provenance verbatim alongside the outcome. Unknown keys in an
incoming pack's provenance are preserved in that report
verbatim — carried, never interpreted.

Collision discipline (never silently overwriting, P-025):
import NEVER merges into or overwrites an existing book.

- Exact duplicate (an owned book with the same content
  checksum): nothing is written; the existing book is
  returned with ``duplicate_exact`` in the report — the
  first copy wins, exactly as P-025's duplicate cards.
- Same name, different contents: with the default
  ``on_conflict="create_new"`` a FRESH book (new id) is
  created and the report flags ``name_collision``; with
  ``on_conflict="reject"`` the import refuses and nothing
  is written. Lorebooks have no version lineage (that is a
  character-card concept, P-025), so no version is minted
  and no name is suffixed — the two books share a name and
  are told apart by id and checksum, stated plainly in the
  report.

Safety: byte/str input is decoded with
``runmal.safety.safe_json_loads`` under the same 32 MiB cap
as lorebook file interop (``interop.MAX_LOREBOOK_BYTES``),
and already-decoded input is checked with
``validate_json_tree``; the payload then passes the import
path's own validation before anything is written, and the
write itself is the transactional P-022 import, so a pack
that fails anywhere leaves nothing behind.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal import __version__
from runmal.db.models import Lorebook
from runmal.lorebooks import service, transfer
from runmal.lorebooks.interop import MAX_LOREBOOK_BYTES
from runmal.safety import SafetyError, safe_json_loads, validate_json_tree

PACK_FORMAT = "runmal-lorebook-pack"
PACK_VERSION = 1
PACK_KIND = "lorebook"
PACK_SCHEMA = "runmal-p045-lorebook-pack-v1"
PROVENANCE_VERSION = 1
PROVENANCE_SOURCE_KIND = "lorebook_pack_export"
MAX_PACK_BYTES = MAX_LOREBOOK_BYTES

CONFLICT_CREATE_NEW = "create_new"
CONFLICT_REJECT = "reject"
CONFLICT_MODES = frozenset({CONFLICT_CREATE_NEW, CONFLICT_REJECT})

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
    "build_pack_from_file",
    "build_pack_from_native_payload",
    "canonical_payload",
    "content_checksum",
    "import_pack",
    "inspect_pack",
    "pack_to_bytes",
    "parse_pack",
]


class PackError(ValueError):
    """A lorebook pack is malformed, tampered with, or refused."""


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_payload(native_payload: dict) -> dict:
    """The content-identity form of a native lorebook payload.

    The payload is first normalised through the import path's
    own parser (``transfer.parse_import``), so identity is
    defined over the (book, entries) an import would store;
    entries are then sorted by their own canonical JSON so
    entry order is not part of identity. Raises ValueError
    (from the parser) for an unimportable payload.
    """
    book_fields, entry_fields = transfer.parse_import(native_payload)
    return {
        "book": book_fields,
        "entries": sorted(entry_fields, key=_canonical_bytes),
    }


def content_checksum(native_payload: dict) -> str:
    """SHA-256 over the canonical payload (the content identity)."""
    return hashlib.sha256(_canonical_bytes(canonical_payload(native_payload))).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_pack_from_native_payload(
    native_payload: dict,
    *,
    exported_at: str | None = None,
    note: str | None = None,
    source_book_id: str | None = None,
) -> dict:
    """Wrap a native lorebook payload in a pack envelope.

    The payload is validated with the existing import parser
    first — a pack is never minted around contents the import
    path would refuse. Facts the caller does not have are
    omitted from provenance, never fabricated.
    """
    if not isinstance(native_payload, dict):
        raise PackError("lorebook payload must be a JSON object")
    try:
        validate_json_tree(native_payload)
    except SafetyError as exc:
        raise PackError(str(exc)) from exc
    try:
        book_fields, entry_fields = transfer.parse_import(native_payload)
        transfer.validate_parsed_book(book_fields, entry_fields)
    except ValueError as exc:
        raise PackError(f"lorebook payload is not importable: {exc}") from exc
    stamp = exported_at if exported_at is not None else _now_iso()
    checksum = content_checksum(native_payload)
    canonical_len = len(_canonical_bytes(canonical_payload(native_payload)))
    provenance: dict = {
        "provenance_version": PROVENANCE_VERSION,
        "source_kind": PROVENANCE_SOURCE_KIND,
    }
    if source_book_id is not None:
        provenance["source_book_id"] = source_book_id
    provenance["source_book_name"] = book_fields["name"]
    provenance["exported_at"] = stamp
    provenance["app_version"] = __version__
    provenance["content_sha256"] = checksum
    if note is not None:
        provenance["note"] = note
    manifest = {
        "book_name": book_fields["name"],
        "entry_count": len(entry_fields),
        "content_sha256": checksum,
        "payload_canonical_bytes": canonical_len,
        "exported_at": stamp,
        "app_version": __version__,
        "payload_format": native_payload.get("format"),
        "payload_version": native_payload.get("version"),
    }
    return {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "kind": PACK_KIND,
        "schema": PACK_SCHEMA,
        "manifest": manifest,
        "provenance": provenance,
        "lorebook": copy.deepcopy(native_payload),
    }


def build_pack(
    book: dict,
    entries: list[dict],
    *,
    exported_at: str | None = None,
    note: str | None = None,
) -> dict:
    """Pack a stored book (API dicts, as the export route holds)."""
    payload = transfer.export_book(book, entries)
    return build_pack_from_native_payload(
        payload,
        exported_at=exported_at,
        note=note,
        source_book_id=book.get("id"),
    )


def build_pack_from_file(
    book_file,
    *,
    exported_at: str | None = None,
    note: str | None = None,
) -> dict:
    """Pack a file-layer book (``interop.LorebookFile``).

    The payload is ``interop.export_native``'s native shape.
    A file has no stored-book id, so provenance honestly
    carries none.
    """
    from runmal.lorebooks.interop import export_native

    return build_pack_from_native_payload(
        export_native(book_file), exported_at=exported_at, note=note
    )


def pack_to_bytes(pack: dict) -> bytes:
    """Serialise a pack for sharing (human-inspectable JSON).

    The checksum covers the canonical payload, not these
    bytes, so re-serialisation never invalidates a pack.
    """
    return json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8")


def _coerce_to_dict(data: bytes | str | dict) -> dict:
    if isinstance(data, dict):
        return copy.deepcopy(data)
    if isinstance(data, (bytes, bytearray, str)):
        try:
            parsed = safe_json_loads(data, limit=MAX_PACK_BYTES)
        except SafetyError as exc:
            raise PackError(str(exc)) from exc
        if not isinstance(parsed, dict):
            raise PackError("lorebook pack must be a JSON object")
        return parsed
    raise PackError(f"lorebook pack must be bytes, str or dict, got {type(data).__name__}")


def parse_pack(data: bytes | str | dict) -> dict:
    """Validate a pack end to end; returns a deep copy of it.

    Every check runs before any write exists: envelope shape,
    format and version, manifest against payload (book name,
    entry count), the content checksum, provenance presence,
    and the payload through the import path's own parser +
    pre-validation. Unknown top-level keys are tolerated (a
    future hub may annotate a pack it carries); the payload's
    own unknown fields are the file layer's concern, exactly
    as in P-019 — the DB payload here is the native shape.
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
            f"unsupported lorebook pack version {version} "
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
    payload = pack.get("lorebook")
    if not isinstance(payload, dict):
        raise PackError("pack lorebook payload missing or not an object")
    try:
        book_fields, entry_fields = transfer.parse_import(payload)
        transfer.validate_parsed_book(book_fields, entry_fields)
    except ValueError as exc:
        raise PackError(f"pack lorebook payload is not importable: {exc}") from exc
    entry_count = manifest.get("entry_count")
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count != len(entry_fields)
    ):
        raise PackError(
            f"manifest entry_count {entry_count!r} does not match "
            f"payload entry count {len(entry_fields)}"
        )
    if manifest.get("book_name") != book_fields["name"]:
        raise PackError(
            f"manifest book_name {manifest.get('book_name')!r} does not "
            f"match payload book name {book_fields['name']!r}"
        )
    expected = manifest.get("content_sha256")
    actual = content_checksum(payload)
    if not isinstance(expected, str) or expected != actual:
        raise PackError(
            "pack checksum mismatch: contents do not match the "
            "manifest content_sha256 (the pack was altered or "
            "corrupted in transit)"
        )
    canonical_len = len(_canonical_bytes(canonical_payload(payload)))
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
    for key in ("payload_format", "payload_version"):
        if key in manifest and manifest[key] is not None:
            payload_key = "format" if key == "payload_format" else "version"
            if manifest[key] != payload.get(payload_key):
                raise PackError(
                    f"manifest {key} {manifest[key]!r} does not match "
                    f"payload {payload_key} {payload.get(payload_key)!r}"
                )
    return pack


def inspect_pack(data: bytes | str | dict) -> dict:
    """Validate a pack and report on it WITHOUT importing.

    The hub's pre-flight: a receiver can see what a pack is,
    where it says it came from, and that its contents are
    intact, before deciding to import it.
    """
    pack = parse_pack(data)
    manifest = pack["manifest"]
    return {
        "schema": PACK_SCHEMA,
        "valid": True,
        "format": pack["format"],
        "pack_version": pack["pack_version"],
        "kind": pack["kind"],
        "book_name": manifest["book_name"],
        "entry_count": manifest["entry_count"],
        "content_sha256": manifest["content_sha256"],
        "checksum_verified": True,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
    }


async def _owned_book_checksums(
    session: AsyncSession, user_id: str
) -> list[tuple[Lorebook, str]]:
    """(book, content checksum) for every book the user owns.

    Owner-scoped (``service.list_lorebooks`` filters by user),
    so another owner's identical book never counts as this
    owner's duplicate — importing a shared pack into a fresh
    library always creates that owner's own copy. The scan is
    O(owned books x entries): pack import is a deliberate,
    user-initiated act, not a hot path, and exactness of the
    duplicate verdict matters more here than the export cost.
    Note the check-then-create is not transactional across
    concurrent imports of the same pack (there is no unique
    constraint to lean on without a migration); two racing
    imports can both create. Accepted for a single-owner
    local app and stated plainly rather than hidden.
    """
    out: list[tuple[Lorebook, str]] = []
    for book, _count in await service.list_lorebooks(session, user_id):
        entries = await service.list_entries(session, user_id, book.id) or []
        payload = transfer.export_book(
            service.lorebook_to_dict(book, len(entries)),
            [service.entry_to_dict(e) for e in entries],
        )
        out.append((book, content_checksum(payload)))
    return out


async def import_pack(
    session: AsyncSession,
    user_id: str,
    data: bytes | str | dict,
    *,
    on_conflict: str = CONFLICT_CREATE_NEW,
) -> tuple[Lorebook, dict]:
    """Import a pack whole; returns (book, import report).

    Never overwrites: an exact duplicate returns the existing
    book unwritten; a same-name collision either creates a
    fresh book (default) or refuses (``on_conflict="reject"``).
    The report carries the pack's manifest and provenance
    verbatim — provenance's carriers are the pack and this
    report; it is not stored on the lorebook row.
    """
    if on_conflict not in CONFLICT_MODES:
        raise PackError(
            f"unknown on_conflict mode: {on_conflict!r} "
            f"(valid: {sorted(CONFLICT_MODES)})"
        )
    pack = parse_pack(data)
    payload = pack["lorebook"]
    manifest = pack["manifest"]
    checksum = manifest["content_sha256"]
    owned = await _owned_book_checksums(session, user_id)
    report: dict = {
        "schema": PACK_SCHEMA,
        "content_sha256": checksum,
        "book_name": manifest["book_name"],
        "manifest_entry_count": manifest["entry_count"],
        "on_conflict": on_conflict,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
        "imported_at": _now_iso(),
    }
    for book, owned_checksum in owned:
        if owned_checksum == checksum:
            entries = await service.list_entries(session, user_id, book.id) or []
            report.update(
                {
                    "created": False,
                    "duplicate_exact": True,
                    "name_collision": False,
                    "book_id": book.id,
                    "entry_count": len(entries),
                }
            )
            return book, report
    name_collision = any(book.name == manifest["book_name"] for book, _ in owned)
    if name_collision and on_conflict == CONFLICT_REJECT:
        raise PackError(
            f"a lorebook named {manifest['book_name']!r} already "
            "exists and on_conflict='reject' refuses to import "
            "a second book under that name"
        )
    book = await transfer.import_book_transactional(session, user_id, payload)
    entries = await service.list_entries(session, user_id, book.id) or []
    report.update(
        {
            "created": True,
            "duplicate_exact": False,
            "name_collision": name_collision,
            "book_id": book.id,
            "entry_count": len(entries),
        }
    )
    return book, report
