"""Content safety guards for imported data (P-027).

Imported content is data, never code: every importer that takes
bytes, JSON text, compressed payloads or archive member tables from
an untrusted source runs them past these guards first, so a hostile
or merely broken file is refused for a typed, testable reason before
any parser with recursive or unbounded behaviour touches it.

Clean-room basis: the requirements are as recorded in
``docs/SECURITY_MODEL.md`` section 9 (imports and assets are
untrusted input: bounded archive extraction, content-size limits,
no execution of imported scripts/macros by default) and section 13
(security acceptance mindset: negative cases are first-class tests),
together with the roadmap's P-027 line in
``docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`` (content
safety rails: imported content is data, never code -- importers
parse defensively). No mirror source code was read.

Error messages name limits, member names and key names only; they
never include payload body content, so a refusal is safe to log or
surface to the user verbatim.

These guards are pure and stateless: no I/O, no globals mutated, and
the module-level limits are ordinary module constants.
"""

from __future__ import annotations

import json
import stat
import zlib
from enum import StrEnum

#: Maximum bracket nesting accepted in a JSON document.
MAX_JSON_DEPTH = 100


class SafetyErrorKind(StrEnum):
    INPUT_TOO_LARGE = "input_too_large"
    NESTING_TOO_DEEP = "nesting_too_deep"
    DUPLICATE_KEY = "duplicate_key"
    INVALID_JSON = "invalid_json"
    DECOMPRESSION_TOO_LARGE = "decompression_too_large"
    DUPLICATE_MEMBER = "duplicate_member"
    LINK_MEMBER = "link_member"
    ARCHIVE_TOO_MANY_MEMBERS = "archive_too_many_members"
    ARCHIVE_MEMBER_TOO_LARGE = "archive_member_too_large"
    ARCHIVE_TOTAL_TOO_LARGE = "archive_total_too_large"


class SafetyError(ValueError):
    """Imported content was refused for a typed, testable reason."""

    def __init__(self, kind: SafetyErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)


def check_bytes(data: bytes | str | bytearray, limit: int | None, *, what: str = "input") -> None:
    """Refuse *data* whose length exceeds *limit* bytes.

    ``what`` names the input in the refusal (for example ``"JSON
    input"``); the payload itself is never included in the message.
    A ``limit`` of ``None`` disables the check.
    """
    if limit is None:
        return None
    size = len(data)
    if size > limit:
        raise SafetyError(
            SafetyErrorKind.INPUT_TOO_LARGE,
            f"{what} is {size} bytes, exceeding limit of {limit} bytes",
        )
    return None


def _check_json_depth(raw: bytes, max_depth: int) -> None:
    """Iteratively pre-scan bracket depth, skipping strings/escapes.

    Runs before ``json.loads`` so deeply nested input is refused
    without ever recursing. Bracket characters inside a JSON string
    do not count, and an escaped quote does not end the string.
    Unbalanced closing brackets are left for the JSON parser to
    report as invalid JSON; this scan only enforces the depth cap.
    """
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # double quote
                in_string = False
            continue
        if byte == 0x22:  # double quote
            in_string = True
        elif byte in (0x7B, 0x5B):  # { or [
            depth += 1
            if depth > max_depth:
                raise SafetyError(
                    SafetyErrorKind.NESTING_TOO_DEEP,
                    f"JSON nesting depth exceeds limit of {max_depth}",
                )
        elif byte in (0x7D, 0x5D):  # } or ]
            if depth > 0:
                depth -= 1


def _object_no_duplicates(pairs: list) -> dict:
    """``object_pairs_hook`` rejecting duplicate keys per object."""
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise SafetyError(
                SafetyErrorKind.DUPLICATE_KEY,
                f"duplicate JSON key {key!r}",
            )
        obj[key] = value
    return obj


def safe_json_loads(
    data: bytes | str,
    *,
    limit: int | None = None,
    max_depth: int = MAX_JSON_DEPTH,
) -> object:
    """Parse JSON defensively: size cap, depth pre-scan, no dup keys.

    ``limit``, when given, caps the input size in bytes (for text
    input, its UTF-8 encoded size). Nesting is checked with the
    iterative pre-scan in :func:`_check_json_depth` *before*
    ``json.loads`` runs; a ``RecursionError`` from the parser is
    still converted to a typed ``NESTING_TOO_DEEP`` refusal as a
    belt-and-braces measure. Decode failures become ``INVALID_JSON``
    and duplicate keys in any one object become ``DUPLICATE_KEY``.
    """
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise SafetyError(
            SafetyErrorKind.INVALID_JSON,
            f"JSON input must be bytes or str, got {type(data).__name__}",
        )
    if limit is not None:
        check_bytes(raw, limit, what="JSON input")
    _check_json_depth(raw, max_depth)
    try:
        return json.loads(data, object_pairs_hook=_object_no_duplicates)
    except SafetyError:
        raise
    except RecursionError as exc:
        raise SafetyError(
            SafetyErrorKind.NESTING_TOO_DEEP,
            f"JSON nesting depth exceeds limit of {max_depth}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise SafetyError(
            SafetyErrorKind.INVALID_JSON,
            f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc
    except UnicodeDecodeError as exc:
        raise SafetyError(
            SafetyErrorKind.INVALID_JSON,
            "invalid JSON: input is not valid text in its detected encoding",
        ) from exc


def validate_json_tree(obj: object, *, max_depth: int = MAX_JSON_DEPTH) -> None:
    """Iteratively check nesting depth of an already-decoded tree.

    Only ``dict`` and ``list`` nodes count towards depth: a top-level
    container is depth 1 and each nested container adds one. Raises
    ``NESTING_TOO_DEEP`` when any container sits deeper than
    ``max_depth``. Uses an explicit stack, never recursion, so a
    pathologically deep tree cannot exhaust the call stack here.
    """
    if not isinstance(obj, (dict, list)):
        return None
    stack: list = [(obj, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > max_depth:
            raise SafetyError(
                SafetyErrorKind.NESTING_TOO_DEEP,
                f"JSON nesting depth exceeds limit of {max_depth}",
            )
        children = node.values() if isinstance(node, dict) else node
        for child in children:
            if isinstance(child, (dict, list)):
                stack.append((child, depth + 1))
    return None


def bounded_zlib_decompress(data: bytes, *, limit: int) -> bytes:
    """Decompress a zlib stream, refusing output over ``limit`` bytes.

    At most ``limit + 1`` bytes are ever materialised: if the stream
    would produce more than ``limit`` bytes -- shown either by that
    extra byte or by input left unconsumed -- the refusal is
    ``DECOMPRESSION_TOO_LARGE``. Corrupt streams raise the
    underlying ``zlib.error`` unchanged.
    """
    decompressor = zlib.decompressobj()
    out = decompressor.decompress(data, limit + 1)
    if len(out) > limit or decompressor.unconsumed_tail:
        raise SafetyError(
            SafetyErrorKind.DECOMPRESSION_TOO_LARGE,
            f"decompressed data exceeds limit of {limit} bytes",
        )
    return out


def _member_name(info: object) -> str:
    for attr in ("filename", "file_name", "name"):
        value = getattr(info, attr, None)
        if value is not None:
            return str(value)
    return ""


def _member_size(info: object) -> int:
    value = getattr(info, "file_size", None)
    if value is None:
        value = getattr(info, "size", 0)
    return int(value or 0)


def _member_external_attr(info: object) -> int:
    return int(getattr(info, "external_attr", 0) or 0)


def audit_zip_members(
    infos: object,
    *,
    max_members: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> None:
    """Audit an archive's member table before anything is extracted.

    ``infos`` is an iterable of ZipInfo-like objects carrying a
    member name (``filename``/``file_name``/``name``), a declared
    ``file_size`` and an ``external_attr``. Checks, in order:
    duplicate member names (``DUPLICATE_MEMBER``); link members,
    whose Unix mode in the high half of ``external_attr`` is a
    symlink (``LINK_MEMBER``); member count
    (``ARCHIVE_TOO_MANY_MEMBERS``); each member's declared size
    (``ARCHIVE_MEMBER_TOO_LARGE``); and the total declared size of
    all members (``ARCHIVE_TOTAL_TOO_LARGE``). Declared sizes are
    audited as declared; nothing is decompressed or extracted here.
    """
    members = list(infos)  # type: ignore[arg-type]
    names = [_member_name(info) for info in members]
    seen: set = set()
    for name in names:
        if name in seen:
            raise SafetyError(
                SafetyErrorKind.DUPLICATE_MEMBER,
                f"duplicate archive member {name!r}",
            )
        seen.add(name)
    for info, name in zip(members, names):
        mode = _member_external_attr(info) >> 16
        if stat.S_ISLNK(mode):
            raise SafetyError(
                SafetyErrorKind.LINK_MEMBER,
                f"archive member {name!r} is a link",
            )
    if len(members) > max_members:
        raise SafetyError(
            SafetyErrorKind.ARCHIVE_TOO_MANY_MEMBERS,
            f"archive has {len(members)} members, exceeding limit of {max_members}",
        )
    total = 0
    for info, name in zip(members, names):
        size = _member_size(info)
        if size > max_member_bytes:
            raise SafetyError(
                SafetyErrorKind.ARCHIVE_MEMBER_TOO_LARGE,
                f"archive member {name!r} is {size} bytes, "
                f"exceeding limit of {max_member_bytes} bytes",
            )
        total += size
    if total > max_total_bytes:
        raise SafetyError(
            SafetyErrorKind.ARCHIVE_TOTAL_TOO_LARGE,
            f"archive members total {total} bytes, "
            f"exceeding limit of {max_total_bytes} bytes",
        )
    return None
