"""Character provenance (P-029).

Provenance on import: where a card came from and when, kept with
the character so creator credit survives in Runmal. A provenance
record is a small JSON object stored in the character's
provenance_json column (migration 0023).

Honesty rules: byte-level facts about the original file
(original_sha256 / original_byte_length) are present as
null when they are unknown -- they are never fabricated, and a
re-serialised form is never hashed and passed off as the
original file's bytes.
"""

from __future__ import annotations

import json
import ntpath
import posixpath
from datetime import UTC, datetime

PROVENANCE_VERSION = 1

SOURCE_KINDS = frozenset(
    {
        "library_folder",
        "library_upload",
        "api_json",
        "copy",
        "manual",
    }
)


def _basename(filename: str) -> str:
    return ntpath.basename(posixpath.basename(filename))


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_provenance(
    card,
    *,
    source_kind,
    imported_at=None,
    original_filename=None,
    relpath=None,
    original_sha256=None,
    original_byte_length=None,
    parent_character_id=None,
    content_hash=None,
) -> dict:
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown provenance source_kind: {source_kind!r}")
    if imported_at is None:
        imported_at = datetime.now(UTC).isoformat()
    else:
        imported_at = _iso(imported_at)
    record: dict = {}
    record["provenance_version"] = PROVENANCE_VERSION
    record["source_kind"] = source_kind
    if card is not None:
        card_format = getattr(card, "source_format", None)
        if card_format is not None:
            record["card_format"] = card_format
        spec_version = getattr(card, "spec_version", None)
        if spec_version is not None:
            record["spec_version"] = spec_version
        creator = getattr(card, "creator", None)
        if creator is not None:
            record["creator"] = creator
        character_version = getattr(card, "character_version", None)
        if character_version is not None:
            record["character_version"] = character_version
        source = getattr(card, "source", None)
        if source is not None:
            record["source"] = list(source)
        creation_date = getattr(card, "creation_date", None)
        if creation_date is not None:
            record["card_creation_date"] = creation_date
        modification_date = getattr(card, "modification_date", None)
        if modification_date is not None:
            record["card_modification_date"] = modification_date
    record["imported_at"] = imported_at
    if original_filename is not None:
        record["original_filename"] = _basename(original_filename)
    if relpath is not None:
        record["relpath"] = relpath
    record["original_sha256"] = original_sha256
    record["original_byte_length"] = original_byte_length
    if content_hash is not None:
        record["content_hash"] = content_hash
    if parent_character_id is not None:
        record["parent_character_id"] = parent_character_id
    return record


def dump_provenance(record) -> str:
    if record is None:
        return "{}"
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def parse_provenance(character) -> dict | None:
    if character is None:
        return None
    if isinstance(character, dict):
        return dict(character) if character else None
    if isinstance(character, str):
        raw = character
    else:
        raw = getattr(character, "provenance_json", None)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw) if raw else None
    text = str(raw).strip()
    if not text or text == "{}":
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    return parsed


provenance_to_dict = parse_provenance
