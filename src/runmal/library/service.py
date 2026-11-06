"""Bulk library import service (P-022).

Imports a whole folder (or an equivalent upload set) of a user's
character cards + lorebooks as one act with a report: every file is
classified content-first, repaired only from the closed repair list,
checked for exact duplicates (against the existing library and
within the batch), and stored as its own transaction - one file's
failure never undoes another's and never leaves a partial lorebook.
The report carries names, sizes, hashes, verdicts, and reasons only,
never file contents.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets.service import build_asset_plan, purge_character_asset_files
from runmal.cards import import_card
from runmal.cards.errors import CardErrorKind, CardParseError
from runmal.cards.exporter import export_json
from runmal.cards.models import CharacterCard
from runmal.cards.parser import MAX_INPUT_BYTES, PNG_SIGNATURE, ZIP_SIGNATURE
from runmal.characters.provenance import build_provenance
from runmal.characters.service import create_character_from_card
from runmal.db.models import Character, Lorebook
from runmal.library.models import (
    BulkEntry,
    BulkImportReport,
    BulkKind,
    BulkOutcome,
    RefusalCode,
    RepairCode,
    RepairNote,
    SkippedEntry,
)
from runmal.lorebooks import service as lore_service
from runmal.lorebooks import transfer

__all__ = [
    "MAX_DEPTH",
    "MAX_FILES",
    "MAX_TOTAL_BYTES",
    "import_library_folder",
    "import_library_uploads",
]

MAX_FILES = 1000
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_DEPTH = 8

_UTF8_BOM = b"\xef\xbb\xbf"

#: Extensions considered as import candidates. Extensionless files
#: and .txt files are candidates too, classified purely by content.
CANDIDATE_EXTENSIONS = frozenset(
    {".json", ".jsonl", ".png", ".charx", ".zip", ".txt", ""}
)

#: What an extension claims the content is; disagreement with the
#: sniffed content is the ``content_sniffed`` repair.
_EXTENSION_FORMATS = {".json": "json", ".png": "png", ".charx": "charx", ".zip": "charx"}

#: Canonical extension per sniffed format. The card parser dispatches
#: on filename suffix OR content signature, so bulk import hands it a
#: parse name matching the SNIFFED format - content wins over the
#: file's own extension, which is exactly the content_sniffed repair.
_FORMAT_EXTENSIONS = {"json": ".json", "png": ".png", "charx": ".charx"}

_CARD_DATA_FIELDS = frozenset(
    {
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "creator_notes",
        "system_prompt",
        "post_history_instructions",
        "alternate_greetings",
        "tags",
        "creator",
        "character_version",
        "character_book",
        "extensions",
        "nickname",
        "group_only_greetings",
    }
)
_CARD_SPECIFIC_FIELDS = frozenset(
    {
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "alternate_greetings",
        "character_book",
        "creator_notes",
        "system_prompt",
        "post_history_instructions",
    }
)
_PRESET_SAMPLER_KEYS = frozenset(
    {
        "temp",
        "top_p",
        "top_k",
        "min_p",
        "rep_pen",
        "tfs",
        "freq_pen",
        "presence_pen",
        "genamt",
        "dynatemp_low",
        "dynatemp_high",
        "dynatemp_exponent",
        "mirostat",
        "typical_p",
        "epsilon_cutoff",
        "eta_cutoff",
    }
)
# Recognised-but-not-library shapes and the slice that owns each.
_UNSUPPORTED_HOMES = {"preset": "P-021", "chat": "P-020", "persona": "P-018"}


def _refuse(entry: BulkEntry, code: RefusalCode, reason: str) -> BulkEntry:
    entry.outcome = BulkOutcome.REFUSED
    entry.reason_code = code
    entry.reason = reason
    return entry


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        pass


def _extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def _is_persona_shape(obj: dict) -> bool:
    if "description_position" in obj or "descriptionPosition" in obj:
        return True
    return (
        "prompt" in obj
        and isinstance(obj.get("name"), str)
        and not any(key in obj for key in _CARD_SPECIFIC_FIELDS)
    )


def _is_preset_shape(obj: dict) -> bool:
    if "prompts" in obj and "prompt_order" in obj:
        return True
    return len(_PRESET_SAMPLER_KEYS.intersection(obj)) >= 3


def _is_chat_shape(obj: dict) -> bool:
    if "character_name" in obj and ("user_name" in obj or "chat_metadata" in obj):
        return True
    return "mes" in obj and "is_user" in obj


def _classify_json(obj: dict) -> str:
    """Classify a parsed JSON object.

    Returns one of: card, lorebook, ambiguous, preset, chat, persona,
    unknown. Content-first per the P-022 decision table.
    """
    spec = obj.get("spec")
    has_card_spec = isinstance(spec, str) and spec.startswith("chara_card_")
    data = obj.get("data")
    envelope_card = (
        isinstance(data, dict)
        and isinstance(data.get("name"), str)
        and bool(data.get("name"))
        and any(key in data for key in _CARD_DATA_FIELDS)
    )
    has_entries = isinstance(obj.get("entries"), (dict, list))
    if has_card_spec or envelope_card:
        return "ambiguous" if has_entries else "card"
    if has_entries:
        return "lorebook"
    if _is_persona_shape(obj):
        return "persona"
    if _is_preset_shape(obj):
        return "preset"
    if _is_chat_shape(obj):
        return "chat"
    name = obj.get("name")
    if isinstance(name, str) and name and any(key in obj for key in _CARD_DATA_FIELDS):
        return "card"
    if sum(1 for key in _CARD_SPECIFIC_FIELDS if key in obj) >= 2:
        # Card-shaped fields with no usable name: still a card, and
        # the card path will refuse it as missing_name.
        return "card"
    return "unknown"


def _looks_like_chat_jsonl(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError:
        return False
    return isinstance(header, dict) and _is_chat_shape(header)


def _canonical_lorebook_hash(shape: dict) -> str:
    """SHA-256 of the canonical JSON of an export_book shape.

    Keys are sorted; entries are sorted by their own canonical JSON
    so the hash does not depend on storage/listing order.
    """
    canon = dict(shape)
    entries = canon.get("entries") or []
    canon["entries"] = sorted(
        json.dumps(e, sort_keys=True, ensure_ascii=False) for e in entries
    )
    canon["entries"] = [json.loads(blob) for blob in canon["entries"]]
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _lorebook_hash(book_fields: dict, entry_fields: list[dict]) -> str:
    shape = transfer.export_book(
        {
            "name": book_fields.get("name", ""),
            "description": book_fields.get("description", ""),
            "scan_depth": book_fields.get("scan_depth", 4),
            "token_budget": book_fields.get("token_budget"),
        },
        entry_fields,
    )
    return _canonical_lorebook_hash(shape)


@dataclass
class _Batch:
    """Per-act state: the existing-library index plus batch winners."""

    session: AsyncSession
    user_id: str
    dry_run: bool
    char_hashes: dict[str, str]
    char_names: dict[str, str]
    book_hashes: dict[str, str]
    book_names: dict[str, str]
    batch_char_hashes: dict[str, str] = field(default_factory=dict)
    batch_book_hashes: dict[str, str] = field(default_factory=dict)
    batch_char_names: dict[str, str | None] = field(default_factory=dict)
    batch_book_names: dict[str, str | None] = field(default_factory=dict)
    bytes_seen: int = 0
    source_kind: str = "library_upload"


async def _build_index(
    session: AsyncSession, user_id: str
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """Index the existing library once per act.

    Characters are hashed by SHA-256 of their stored ``card_json``;
    lorebooks by the canonical JSON of their ``export_book`` shape.
    A database failure here propagates: DB unavailable at the start
    fails the whole act, it is not a per-file refusal.
    """
    char_hashes: dict[str, str] = {}
    char_names: dict[str, str] = {}
    result = await session.execute(
        select(Character).where(
            Character.user_id == user_id, Character.deleted_at.is_(None)
        )
    )
    for character in result.scalars().all():
        digest = hashlib.sha256(character.card_json.encode("utf-8")).hexdigest()
        char_hashes.setdefault(digest, character.id)
        char_names.setdefault(character.name, character.id)
    book_hashes: dict[str, str] = {}
    book_names: dict[str, str] = {}
    result = await session.execute(
        select(Lorebook).where(Lorebook.user_id == user_id)
    )
    for book in result.scalars().all():
        entries = await lore_service.list_entries(session, user_id, book.id) or []
        shape = transfer.export_book(
            lore_service.lorebook_to_dict(book, len(entries)),
            [lore_service.entry_to_dict(e) for e in entries],
        )
        book_hashes.setdefault(_canonical_lorebook_hash(shape), book.id)
        book_names.setdefault(book.name, book.id)
    return char_hashes, char_names, book_hashes, book_names


def _sniff_repair(
    repairs: list[RepairNote], filename: str, detected_format: str
) -> None:
    ext = _extension(filename)
    implied = _EXTENSION_FORMATS.get(ext)
    if implied is not None and implied != detected_format:
        repairs.append(
            RepairNote(
                RepairCode.CONTENT_SNIFFED,
                f"extension {ext!r} implies {implied} but content is "
                f"{detected_format}; imported by content",
            )
        )


async def _finish_card(
    batch: _Batch,
    entry: BulkEntry,
    card: CharacterCard,
    filename: str,
    detected_format: str,
    repairs: list[RepairNote],
    source_bytes: bytes | None = None,
) -> BulkEntry:
    entry.detected_kind = BulkKind.CARD
    entry.detected_format = detected_format
    if not card.name or not card.name.strip():
        return _refuse(entry, RefusalCode.MISSING_NAME, "card has no name")
    if card.name != card.name.strip():
        trimmed = card.name.strip()
        repairs.append(
            RepairNote(
                RepairCode.NAME_WHITESPACE_TRIMMED,
                f"card name {card.name!r} trimmed to {trimmed!r}",
            )
        )
        card.name = trimmed
    _sniff_repair(repairs, filename, detected_format)
    entry.repairs = repairs
    plan_count = len(
        build_asset_plan(
            card,
            has_container_art=(
                source_bytes is not None and card.source_format == "png"
            ),
            source_bytes=source_bytes,
        )
    )
    digest = hashlib.sha256(export_json(card, "2")).hexdigest()
    if digest in batch.char_hashes:
        entry.duplicate_of = batch.char_hashes[digest]
        return _refuse(
            entry,
            RefusalCode.DUPLICATE_EXACT,
            f"exact duplicate of existing character {entry.duplicate_of}",
        )
    if digest in batch.batch_char_hashes:
        entry.duplicate_of = batch.batch_char_hashes[digest]
        return _refuse(
            entry,
            RefusalCode.DUPLICATE_IN_BATCH,
            f"duplicate of {entry.duplicate_of} in this batch",
        )
    collision = batch.char_names.get(card.name) or batch.batch_char_names.get(card.name)
    if collision:
        entry.notes.append(f"name_collision:{collision}")
    if batch.dry_run:
        if plan_count:
            entry.notes.append(f"assets_would_store_p023:{plan_count}")
        entry.outcome = BulkOutcome.REPAIRED if repairs else BulkOutcome.ACCEPTED
        entry.created_name = card.name
        batch.batch_char_hashes[digest] = entry.relpath
        batch.batch_char_names.setdefault(card.name, entry.relpath)
        return entry
    character = None
    try:
        provenance = build_provenance(
            card,
            source_kind=batch.source_kind,
            original_filename=entry.filename,
            relpath=entry.relpath,
            original_sha256=entry.sha256,
            original_byte_length=entry.size_bytes,
        )
        character = await create_character_from_card(
            batch.session,
            batch.user_id,
            card,
            commit=False,
            source_bytes=source_bytes,
            provenance=provenance,
        )
        await batch.session.commit()
    except SQLAlchemyError as exc:
        if character is not None:
            purge_character_asset_files(character.id)
        await _safe_rollback(batch.session)
        return _refuse(entry, RefusalCode.STORAGE_ERROR, f"storage failed: {exc}")
    except Exception as exc:  # never leak a per-file failure
        if character is not None:
            purge_character_asset_files(character.id)
        await _safe_rollback(batch.session)
        return _refuse(entry, RefusalCode.STORAGE_ERROR, f"storage failed: {exc}")
    if plan_count:
        entry.notes.append(f"assets_stored_p023:{plan_count}")
    entry.outcome = BulkOutcome.REPAIRED if repairs else BulkOutcome.ACCEPTED
    entry.created_id = character.id
    entry.created_name = character.name
    if getattr(character, "version_no", 1) and character.version_no > 1:
        entry.notes.append(f"versioned:v{character.version_no}")
    batch.batch_char_hashes[digest] = entry.relpath
    batch.batch_char_names[card.name] = character.id
    return entry


async def _import_card_bytes(
    batch: _Batch,
    entry: BulkEntry,
    data: bytes,
    filename: str,
    detected_format: str,
    repairs: list[RepairNote],
) -> BulkEntry:
    entry.detected_kind = BulkKind.CARD
    entry.detected_format = detected_format
    parse_name = f"{PurePosixPath(filename).stem}{_FORMAT_EXTENSIONS[detected_format]}"
    try:
        card = import_card(data, parse_name)
    except CardParseError as exc:
        entry.repairs = repairs
        if exc.kind == CardErrorKind.NOT_A_CARD and "no name" in str(exc).lower():
            return _refuse(entry, RefusalCode.MISSING_NAME, str(exc))
        return _refuse(entry, RefusalCode(exc.kind.value), str(exc))
    return await _finish_card(
        batch,
        entry,
        card,
        filename,
        detected_format,
        repairs,
        source_bytes=data if detected_format == "png" else None,
    )


async def _import_lorebook(
    batch: _Batch,
    entry: BulkEntry,
    obj: dict,
    filename: str,
    repairs: list[RepairNote],
) -> BulkEntry:
    entry.detected_kind = BulkKind.LOREBOOK
    entry.detected_format = "json"
    _sniff_repair(repairs, filename, "json")
    entry.repairs = repairs
    work = obj
    raw_entries = obj.get("entries")
    is_native_list = isinstance(raw_entries, list) and not (
        raw_entries
        and isinstance(raw_entries[0], dict)
        and ("key" in raw_entries[0] or "keysecondary" in raw_entries[0])
    )
    name_value = obj.get("name")
    if is_native_list and (
        name_value is None or (isinstance(name_value, str) and not name_value.strip())
    ):
        stem = PurePosixPath(filename).stem
        if stem:
            work = dict(obj)
            work["name"] = stem
            repairs.append(
                RepairNote(
                    RepairCode.LOREBOOK_NAME_FROM_FILENAME,
                    f"lorebook name taken from filename stem {stem!r}",
                )
            )
    # Pre-validate fully (pure) BEFORE any create.
    try:
        book_fields, entry_fields = transfer.parse_import(work)
    except ValueError as exc:
        return _refuse(entry, RefusalCode.INVALID_LOREBOOK, str(exc))
    book_name = book_fields.get("name", "")
    if isinstance(book_name, str) and book_name != book_name.strip():
        trimmed = book_name.strip()
        if not trimmed:
            return _refuse(
                entry, RefusalCode.INVALID_LOREBOOK, "lorebook import needs a name"
            )
        repairs.append(
            RepairNote(
                RepairCode.NAME_WHITESPACE_TRIMMED,
                f"lorebook name {book_name!r} trimmed to {trimmed!r}",
            )
        )
        book_fields = dict(book_fields)
        book_fields["name"] = trimmed
        work = dict(work)
        work["name"] = trimmed
    # Entry-level validation (position/keys/knobs) runs in dry runs
    # too, so dry-run verdicts match real-run verdicts exactly.
    try:
        transfer.validate_parsed_book(book_fields, entry_fields)
    except ValueError as exc:
        return _refuse(entry, RefusalCode.INVALID_LOREBOOK, str(exc))
    digest = _lorebook_hash(book_fields, entry_fields)
    if digest in batch.book_hashes:
        entry.duplicate_of = batch.book_hashes[digest]
        return _refuse(
            entry,
            RefusalCode.DUPLICATE_EXACT,
            f"exact duplicate of existing lorebook {entry.duplicate_of}",
        )
    if digest in batch.batch_book_hashes:
        entry.duplicate_of = batch.batch_book_hashes[digest]
        return _refuse(
            entry,
            RefusalCode.DUPLICATE_IN_BATCH,
            f"duplicate of {entry.duplicate_of} in this batch",
        )
    if not is_native_list and not (
        isinstance(name_value, str) and name_value.strip()
    ):
        entry.notes.append("name_defaulted:Imported lorebook")
    collision = batch.book_names.get(book_fields["name"]) or batch.batch_book_names.get(
        book_fields["name"]
    )
    if collision:
        entry.notes.append(f"name_collision:{collision}")
    if batch.dry_run:
        entry.outcome = BulkOutcome.REPAIRED if repairs else BulkOutcome.ACCEPTED
        entry.created_name = book_fields["name"]
        batch.batch_book_hashes[digest] = entry.relpath
        batch.batch_book_names.setdefault(book_fields["name"], entry.relpath)
        return entry
    try:
        book = await transfer.import_book_transactional(
            batch.session, batch.user_id, work, commit=False
        )
        await batch.session.commit()
    except ValueError as exc:
        await _safe_rollback(batch.session)
        return _refuse(entry, RefusalCode.INVALID_LOREBOOK, str(exc))
    except SQLAlchemyError as exc:
        await _safe_rollback(batch.session)
        return _refuse(entry, RefusalCode.STORAGE_ERROR, f"storage failed: {exc}")
    except Exception as exc:  # never leak a per-file failure
        await _safe_rollback(batch.session)
        return _refuse(entry, RefusalCode.STORAGE_ERROR, f"storage failed: {exc}")
    entry.outcome = BulkOutcome.REPAIRED if repairs else BulkOutcome.ACCEPTED
    entry.created_id = book.id
    entry.created_name = book.name
    batch.batch_book_hashes[digest] = entry.relpath
    batch.batch_book_names[book.name] = book.id
    return entry


async def _import_one(
    batch: _Batch, relpath: str, filename: str, data: bytes
) -> BulkEntry:
    """Import one file's bytes. NO exception escapes this function."""
    entry = BulkEntry(
        relpath=relpath,
        filename=filename,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    try:
        if batch.bytes_seen + len(data) > MAX_TOTAL_BYTES:
            return _refuse(
                entry,
                RefusalCode.BATCH_LIMIT,
                f"batch byte limit exceeded ({MAX_TOTAL_BYTES} bytes)",
            )
        batch.bytes_seen += len(data)
        if len(data) > MAX_INPUT_BYTES:
            return _refuse(
                entry,
                RefusalCode.INPUT_TOO_LARGE,
                f"file is {len(data)} bytes; limit is {MAX_INPUT_BYTES}",
            )
        repairs: list[RepairNote] = []
        body = data
        if body.startswith(_UTF8_BOM):
            while body.startswith(_UTF8_BOM):
                body = body[len(_UTF8_BOM) :]
            repairs.append(
                RepairNote(
                    RepairCode.BOM_STRIPPED, "UTF-8 BOM removed before JSON parse"
                )
            )
        if body[:8] == PNG_SIGNATURE:
            return await _import_card_bytes(batch, entry, body, filename, "png", repairs)
        if body[:4] in (ZIP_SIGNATURE, b"PK\x05\x06", b"PK\x07\x08"):
            return await _import_card_bytes(
                batch, entry, body, filename, "charx", repairs
            )
        stripped = body.strip()
        if not stripped:
            return _refuse(entry, RefusalCode.INVALID_JSON, "file is empty")
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if _looks_like_chat_jsonl(body):
                return _refuse(
                    entry,
                    RefusalCode.UNSUPPORTED_KIND,
                    "recognised chat file; chats are handled by slice "
                    f"{_UNSUPPORTED_HOMES['chat']}, not bulk library import",
                )
            if stripped[:1] in (b"{", b"["):
                try:
                    import_card(body, filename)
                except CardParseError as card_exc:
                    if card_exc.kind == CardErrorKind.NOT_A_CARD and "no name" in str(
                        card_exc
                    ).lower():
                        return _refuse(entry, RefusalCode.MISSING_NAME, str(card_exc))
                    return _refuse(
                        entry, RefusalCode(card_exc.kind.value), str(card_exc)
                    )
                except Exception:
                    pass
                return _refuse(
                    entry, RefusalCode.INVALID_JSON, f"file is not valid JSON: {exc}"
                )
            return _refuse(
                entry,
                RefusalCode.UNRECOGNIZED_CONTENT,
                "content is neither a character card nor a lorebook",
            )
        if not isinstance(obj, dict):
            return _refuse(
                entry,
                RefusalCode.UNRECOGNIZED_CONTENT,
                "content is neither a character card nor a lorebook",
            )
        classification = _classify_json(obj)
        if classification == "ambiguous":
            entry.detected_format = "json"
            return _refuse(
                entry,
                RefusalCode.AMBIGUOUS_KIND,
                "file matches both character card and lorebook shapes",
            )
        if classification in _UNSUPPORTED_HOMES:
            entry.detected_format = "json"
            entry.notes.append(f"detected_shape:{classification}")
            entry.notes.append(f"home_slice:{_UNSUPPORTED_HOMES[classification]}")
            return _refuse(
                entry,
                RefusalCode.UNSUPPORTED_KIND,
                f"recognised {classification} file; {classification}s are handled "
                f"by slice {_UNSUPPORTED_HOMES[classification]}, "
                "not bulk library import",
            )
        if classification == "unknown":
            entry.detected_format = "json"
            return _refuse(
                entry,
                RefusalCode.UNRECOGNIZED_CONTENT,
                "content is neither a character card nor a lorebook",
            )
        if classification == "card":
            return await _import_card_bytes(batch, entry, body, filename, "json", repairs)
        return await _import_lorebook(batch, entry, obj, filename, repairs)
    except Exception as exc:  # last-resort guard: nothing escapes
        await _safe_rollback(batch.session)
        entry.outcome = BulkOutcome.REFUSED
        entry.reason_code = RefusalCode.STORAGE_ERROR
        entry.reason = f"unexpected failure: {exc}"
        return entry


@dataclass
class _Discovered:
    relpath: str
    path: Path
    is_symlink: bool


def _discover(root: Path, recursive: bool) -> list[_Discovered]:
    found: list[_Discovered] = []
    if root.is_file() or root.is_symlink():
        return [_Discovered(root.name, root, root.is_symlink())]
    root_resolved = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Never descend into symlinked directories.
        dirnames[:] = [
            d for d in dirnames if not (Path(dirpath) / d).is_symlink()
        ]
        if not recursive:
            dirnames[:] = []
        for name in filenames:
            path = Path(dirpath) / name
            relpath = path.relative_to(root).as_posix()
            if not path.is_symlink():
                # Resolved paths must stay inside the root.
                try:
                    path.resolve().relative_to(root_resolved)
                except (ValueError, OSError):
                    found.append(_Discovered(relpath, path, True))
                    continue
            found.append(_Discovered(relpath, path, path.is_symlink()))
    return found


def _skipped_entry(relpath: str, filename: str, reason: str) -> BulkEntry:
    return BulkEntry(
        relpath=relpath,
        filename=filename,
        outcome=BulkOutcome.SKIPPED,
        reason=reason,
    )


def _limit_entry(relpath: str, filename: str, path: Path | None) -> BulkEntry:
    size = 0
    if path is not None:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
    return BulkEntry(
        relpath=relpath,
        filename=filename,
        size_bytes=size,
        outcome=BulkOutcome.REFUSED,
        reason_code=RefusalCode.BATCH_LIMIT,
        reason="batch limit exceeded",
    )


async def _run_batch(
    batch: _Batch,
    source_label: str,
    started_at: datetime,
    items: list[tuple[str, str, bytes | Path]],
) -> BulkImportReport:
    """Shared driver: items are (relpath, filename, bytes-or-Path)."""
    entries: list[BulkEntry] = []
    skipped: list[SkippedEntry] = []
    candidates = 0
    for relpath, filename, payload in items:
        if isinstance(payload, Path) and payload.is_symlink():
            entries.append(_skipped_entry(relpath, filename, "symlink_not_followed"))
            skipped.append(SkippedEntry(relpath, "symlink_not_followed"))
            continue
        if _extension(filename) not in CANDIDATE_EXTENSIONS:
            entries.append(
                _skipped_entry(relpath, filename, "unsupported_extension")
            )
            skipped.append(SkippedEntry(relpath, "unsupported_extension"))
            continue
        depth = len(PurePosixPath(relpath).parts) - 1
        if depth > MAX_DEPTH:
            entries.append(
                BulkEntry(
                    relpath=relpath,
                    filename=filename,
                    outcome=BulkOutcome.REFUSED,
                    reason_code=RefusalCode.BATCH_LIMIT,
                    reason=f"path depth {depth} exceeds limit {MAX_DEPTH}",
                )
            )
            continue
        candidates += 1
        if candidates > MAX_FILES:
            entries.append(
                BulkEntry(
                    relpath=relpath,
                    filename=filename,
                    outcome=BulkOutcome.REFUSED,
                    reason_code=RefusalCode.BATCH_LIMIT,
                    reason=f"batch file limit exceeded ({MAX_FILES} files)",
                )
            )
            continue
        if isinstance(payload, Path):
            try:
                size = payload.stat().st_size
            except OSError:
                size = 0
            if size > MAX_INPUT_BYTES:
                entries.append(
                    BulkEntry(
                        relpath=relpath,
                        filename=filename,
                        size_bytes=size,
                        outcome=BulkOutcome.REFUSED,
                        reason_code=RefusalCode.INPUT_TOO_LARGE,
                        reason=(
                            f"file is {size} bytes; limit is {MAX_INPUT_BYTES}"
                        ),
                    )
                )
                continue
            try:
                data = payload.read_bytes()
            except OSError as exc:
                entries.append(
                    BulkEntry(
                        relpath=relpath,
                        filename=filename,
                        outcome=BulkOutcome.REFUSED,
                        reason_code=RefusalCode.UNREADABLE,
                        reason=f"file could not be read: {exc}",
                    )
                )
                continue
        else:
            data = payload
        entries.append(await _import_one(batch, relpath, filename, data))
    report = BulkImportReport(
        batch_id=str(uuid.uuid4()),
        source_label=source_label,
        dry_run=batch.dry_run,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        entries=entries,
        skipped=skipped,
    )
    report.totals = report.compute_totals()
    return report


async def import_library_folder(
    session: AsyncSession,
    user_id: str,
    root: Path,
    *,
    dry_run: bool = False,
    recursive: bool = True,
) -> BulkImportReport:
    """Import a whole folder of cards + lorebooks as one act (P-022)."""
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        raise FileNotFoundError(f"import root does not exist: {root}")
    started_at = datetime.now(UTC)
    char_hashes, char_names, book_hashes, book_names = await _build_index(
        session, user_id
    )
    batch = _Batch(
        session=session,
        user_id=user_id,
        dry_run=dry_run,
        char_hashes=char_hashes,
        char_names=char_names,
        book_hashes=book_hashes,
        book_names=book_names,
        source_kind="library_folder",
    )
    discovered = _discover(root, recursive)
    discovered.sort(key=lambda d: (d.relpath.casefold(), d.relpath))
    items: list[tuple[str, str, bytes | Path]] = [
        (d.relpath, d.path.name, d.path) for d in discovered
    ]
    return await _run_batch(batch, str(root), started_at, items)


async def import_library_uploads(
    session: AsyncSession,
    user_id: str,
    files: list[tuple[str, bytes]],
    *,
    dry_run: bool = False,
) -> BulkImportReport:
    """Import an uploaded set of cards + lorebooks as one act (P-022)."""
    started_at = datetime.now(UTC)
    char_hashes, char_names, book_hashes, book_names = await _build_index(
        session, user_id
    )
    batch = _Batch(
        session=session,
        user_id=user_id,
        dry_run=dry_run,
        char_hashes=char_hashes,
        char_names=char_names,
        book_hashes=book_hashes,
        book_names=book_names,
        source_kind="library_upload",
    )
    prepared: list[tuple[str, str, bytes | Path]] = []
    for name, data in files:
        relpath = name.replace("\\", "/")
        while relpath.startswith("./"):
            relpath = relpath[2:]
        filename = PurePosixPath(relpath).name or relpath
        prepared.append((relpath, filename, bytes(data)))
    prepared.sort(key=lambda item: (item[0].casefold(), item[0]))
    return await _run_batch(batch, "uploads", started_at, prepared)
