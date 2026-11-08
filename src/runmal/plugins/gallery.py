"""The gallery plugin (P-095): per-chat image gallery with
generation history.

Roadmap line: "The gallery plugin: chat image gallery with
generation history (Voxta users expect it; ST users bolt it
on -- here it's a citizen)."

A first-class P-081 citizen (pattern: P-087/P-092/P-093) that
gives every chat a gallery: the images associated with the
chat, listed and inspected with their provenance -- generated
via P-087, attached by the owner, or derived from a bound
character's P-023 assets.

Why this citizen exists (P095_SCOUT.md): P-023 is the one
durable image store but it is character-scoped and knows
nothing of chats; P-087 generates per chat but its generation
ledger is process-local, so the history dies with the
process. The gallery is the durable, per-chat, provenance-
carrying join of the two. It stores NO bytes for asset-backed
entries (it references P-023 asset ids and reads facts and
thumbnail state through the P-023 roads) and generates
nothing (P-087 owns generation). The one byte-keeping road
is attaching an image to a chat with no bound character,
where P-023 cannot land by construction: those bytes live in
the gallery's own byte store under a road labelled
``attached_local`` -- stated plainly, never disguised as a
P-023 asset, and no thumbnails are claimed for them.

Durable store: the P-089 file idiom -- one JSON document per
owner at ``data_dir()/gallery/<user_id>.json``, written
atomically (tmp sibling, chmod 0600, replace), strictly
re-validated on read; a corrupt store raises
:class:`GalleryError` and is never silently reset. No
migration: head stays 0041.

Provenance honesty: a generated entry carries the P-087
record's facts verbatim (prompt, prompt_source, road,
provider, model, generation id, sha256); the deterministic
local road stays labelled ``deterministic_local`` here too.
Generation import is pull-based and explicit
(:func:`import_chat_generations` consumes a bound P-087
instance's history) -- the gallery preserves what it is
handed and never claims to have observed generations it was
not shown. Ingest is idempotent per (chat, generation id).

Sandbox stance (P-082): only v1 surface permissions are
declared (``chat.read``, ``ui.contribute``; ``chat.write``
is RESERVED and NOT declared), so the derived resource grant
set is EMPTY. The optional P-087 instance is host wiring
handed to trusted in-tree registration code, not a plugin
resource grant. Wiring: :func:`register_plugin` only;
``build_registry`` / ``create_app`` are unchanged. No HTTP
routes in this slice (P-094 is in flight against the shared
plugins router; the P-087 citizen likewise ships none). See
docs/GALLERY_PLUGIN_2026-11-07.md and
hidden_files/P095_DESIGN.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from runmal.assets.imaging import sniff_image
from runmal.auth import data_dir
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.gallery"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "gallery-panel"
STORE_SCHEMA = "runmal-p095-gallery-v1"
STORE_DIR_NAME = "gallery"
BYTES_DIR_NAME = "gallery_bytes"
SOURCE_GENERATED = "generated"
SOURCE_ASSET = "asset"
SOURCE_ATTACHED = "attached"
SOURCE_KINDS = frozenset({SOURCE_GENERATED, SOURCE_ASSET, SOURCE_ATTACHED})
STORAGE_ASSET = "asset"
STORAGE_LOCAL = "gallery_local"
STORAGE_NONE = "none"
STORAGE_KINDS = frozenset({STORAGE_ASSET, STORAGE_LOCAL, STORAGE_NONE})
ROAD_ATTACHED_LOCAL = "attached_local"
ROAD_ATTACHED_ASSET = "attached_asset"
ROAD_ASSET_DERIVED = "asset_derived"
MAX_CHATS_PER_USER = 500
MAX_ENTRIES_PER_CHAT = 500
MAX_TITLE_CHARS = 120
MAX_NOTES_CHARS = 500
MAX_PROMPT_CHARS = 4000
DECLARED_EVENTS = ("chat.created",)
_ID_RE = re.compile(r"[0-9a-fA-F-]{1,64}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_ENTRY_FIELDS = frozenset({
    "id", "chat_id", "source_kind", "asset_id", "generation_id",
    "prompt", "prompt_source", "road", "provider", "model",
    "filename", "format", "width", "height", "byte_size",
    "sha256", "storage", "title", "notes", "added_by", "added_at",
})


class GalleryError(ValueError):
    """A gallery refusal: bad input, bad store, bad binding."""


class GalleryNotFoundError(GalleryError):
    """The named gallery entry does not exist."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise GalleryError(f"invalid {what}: {value!r}")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise GalleryError(f"invalid {what}: {value!r}") from None
    return value


def _check_text(value, what: str, limit: int) -> str:
    if not isinstance(value, str):
        raise GalleryError(f"{what} must be a string: {value!r}")
    if len(value) > limit:
        raise GalleryError(f"{what} exceeds {limit} chars: {len(value)}")
    return value


def _check_opt_id(value, what: str):
    if value is None:
        return None
    return _check_id(value, what)


# -- Durable per-owner store (file idiom, no migration) -------------------


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    """The owner's gallery store file under the data dir. The
    user id is validated as a UUID before it becomes a path."""
    _check_id(user_id, "user_id")
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{user_id}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "counter": 0, "chats": {}}


def _stored_entry(row) -> dict:
    """A stored entry re-validated on read: corrupt rows
    raise, never silently vanish from the owner's store."""
    if not isinstance(row, dict):
        raise GalleryError("stored gallery entry is not an object")
    extra = set(row) - _ENTRY_FIELDS
    if extra:
        raise GalleryError(
            f"stored gallery entry has unknown keys: {sorted(extra)}")
    missing = _ENTRY_FIELDS - set(row)
    if missing:
        raise GalleryError(
            f"stored gallery entry is missing keys: {sorted(missing)}")
    if row["source_kind"] not in SOURCE_KINDS:
        raise GalleryError(
            f"stored entry has unknown source_kind: {row['source_kind']!r}")
    if row["storage"] not in STORAGE_KINDS:
        raise GalleryError(
            f"stored entry has unknown storage: {row['storage']!r}")
    _check_id(row["chat_id"], "chat_id")
    _check_opt_id(row["asset_id"], "asset_id")
    if row["generation_id"] is not None and not isinstance(row["generation_id"], str):
        raise GalleryError("stored entry has a bad generation_id")
    if not isinstance(row["sha256"], str) or (
            row["sha256"] and not _SHA_RE.fullmatch(row["sha256"])):
        raise GalleryError("stored entry has a bad sha256")
    for name in ("width", "height"):
        if row[name] is not None and not _is_int(row[name]):
            raise GalleryError(f"stored entry has a bad {name}")
    if not _is_int(row["byte_size"]) or row["byte_size"] < 0:
        raise GalleryError("stored entry has a bad byte_size")
    return dict(row)


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GalleryError(f"gallery store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("chats"), dict) \
            or not _is_int(doc.get("counter")):
        raise GalleryError("gallery store has an unknown shape")
    for chat_id, section in doc["chats"].items():
        _check_id(chat_id, "chat_id")
        if not isinstance(section, dict) or not isinstance(section.get("entries"), list):
            raise GalleryError("gallery store has an unknown shape")
        for row in section["entries"]:
            _stored_entry(row)
    return doc


def _save_doc(user_id: str, doc: dict, base_dir: Path | None = None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _chat_entries(doc: dict, chat_id: str) -> list[dict]:
    section = doc["chats"].get(chat_id)
    if section is None:
        return []
    return [_stored_entry(row) for row in section["entries"]]


# -- The single write road -------------------------------------------------


def _append_entry(user_id: str, chat_id: str, fields: dict, *,
                  base_dir: Path | None = None) -> dict:
    """Append one validated entry; the one write road every
    verb funnels through, so caps and ids hold everywhere."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    if chat_id not in doc["chats"] and len(doc["chats"]) >= MAX_CHATS_PER_USER:
        raise GalleryError(
            f"owner already holds galleries for {MAX_CHATS_PER_USER} chats")
    entries = _chat_entries(doc, chat_id)
    if len(entries) >= MAX_ENTRIES_PER_CHAT:
        raise GalleryError(
            f"chat gallery already holds {MAX_ENTRIES_PER_CHAT} entries")
    doc["counter"] += 1
    entry = {
        "id": f"gal-{doc['counter']:04d}",
        "chat_id": chat_id,
        "source_kind": fields["source_kind"],
        "asset_id": fields.get("asset_id"),
        "generation_id": fields.get("generation_id"),
        "prompt": fields.get("prompt", ""),
        "prompt_source": fields.get("prompt_source", ""),
        "road": fields.get("road", ""),
        "provider": fields.get("provider", ""),
        "model": fields.get("model", ""),
        "filename": fields.get("filename", ""),
        "format": fields.get("format", ""),
        "width": fields.get("width"),
        "height": fields.get("height"),
        "byte_size": fields.get("byte_size", 0),
        "sha256": fields.get("sha256", ""),
        "storage": fields["storage"],
        "title": _check_text(fields.get("title", ""), "title", MAX_TITLE_CHARS),
        "notes": _check_text(fields.get("notes", ""), "notes", MAX_NOTES_CHARS),
        "added_by": fields.get("added_by", "owner"),
        "added_at": _now_iso(),
    }
    _stored_entry(entry)
    entries.append(entry)
    doc["chats"][chat_id] = {"entries": entries}
    _save_doc(user_id, doc, base_dir)
    return copy.deepcopy(entry)


def _find_entry(doc: dict, chat_id: str, entry_id: str) -> tuple[list[dict], int]:
    entries = _chat_entries(doc, chat_id)
    for index, row in enumerate(entries):
        if row["id"] == entry_id:
            return entries, index
    raise GalleryNotFoundError(
        f"no gallery entry {entry_id!r} in chat {chat_id!r}")


# -- Generation history: the durable home of the P-087 ledger --------------


def record_generation(user_id: str, chat_id: str, record, *,
                      added_by: str = "owner",
                      base_dir: Path | None = None) -> dict:
    """Ingest one P-087 generation record into the durable
    gallery. Idempotent per (chat, generation id): a record
    already preserved returns its existing entry unchanged.
    The record's provenance is carried verbatim; a record
    whose chat disagrees, or that lacks its road / provider /
    sha256 facts, refuses loudly and records nothing."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if not isinstance(record, dict):
        raise GalleryError(f"generation record must be an object: {record!r}")
    if record.get("chat_id") != chat_id:
        raise GalleryError(
            f"generation record belongs to chat {record.get('chat_id')!r}, "
            f"not {chat_id!r}")
    generation_id = record.get("id")
    if not isinstance(generation_id, str) or not generation_id:
        raise GalleryError("generation record has no id")
    for name in ("prompt", "road", "provider", "model", "sha256"):
        if not isinstance(record.get(name), str) or not record[name]:
            raise GalleryError(f"generation record lacks its {name} fact")
    if not _SHA_RE.fullmatch(record["sha256"]):
        raise GalleryError("generation record has a bad sha256")
    doc = _load_doc(user_id, base_dir)
    for row in _chat_entries(doc, chat_id):
        if row["source_kind"] == SOURCE_GENERATED \
                and row["generation_id"] == generation_id:
            return copy.deepcopy(row)
    asset_id = record.get("asset_id")
    if asset_id is not None:
        _check_id(asset_id, "asset_id")
    landed = bool(record.get("landed")) and asset_id is not None
    notes = ""
    if not landed:
        reason = record.get("landing_reason") or "not_landed"
        notes = f"not landed as an asset: {reason}"
        if record.get("landing_error"):
            notes += f" ({record['landing_error']})"
    return _append_entry(user_id, chat_id, {
        "source_kind": SOURCE_GENERATED,
        "asset_id": asset_id if landed else None,
        "generation_id": generation_id,
        "prompt": _check_text(record["prompt"], "prompt", MAX_PROMPT_CHARS),
        "prompt_source": record.get("prompt_source", ""),
        "road": record["road"],
        "provider": record["provider"],
        "model": record["model"],
        "filename": "",
        "format": record.get("format", ""),
        "width": record.get("image_width"),
        "height": record.get("image_height"),
        "byte_size": record.get("byte_size", 0),
        "sha256": record["sha256"],
        "storage": STORAGE_ASSET if landed else STORAGE_NONE,
        "title": "",
        "notes": notes,
        "added_by": added_by,
    }, base_dir=base_dir)


def sync_generation_history(user_id: str, chat_id: str, records, *,
                            added_by: str = "owner",
                            base_dir: Path | None = None) -> dict:
    """Bulk-ingest a P-087 history list; returns the report
    {added: [entry, ...], skipped: int} where skipped counts
    records already preserved (the idempotence receipt)."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if not isinstance(records, list):
        raise GalleryError(f"records must be a list: {records!r}")
    before = {row["generation_id"] for row in list_entries(
        user_id, chat_id, source_kind=SOURCE_GENERATED, base_dir=base_dir)}
    added = []
    skipped = 0
    for record in records:
        gid = record.get("id") if isinstance(record, dict) else None
        if gid is not None and gid in before:
            skipped += 1
            continue
        entry = record_generation(
            user_id, chat_id, record, added_by=added_by, base_dir=base_dir)
        added.append(entry)
        before.add(entry["generation_id"])
    return {"added": added, "skipped": skipped}


# -- Reads and curation ------------------------------------------------------


def list_entries(user_id: str, chat_id: str, *, source_kind: str | None = None,
                 base_dir: Path | None = None) -> list[dict]:
    """The chat's gallery entries in insertion order,
    optionally filtered to one source kind."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if source_kind is not None and source_kind not in SOURCE_KINDS:
        raise GalleryError(f"unknown source_kind: {source_kind!r}")
    doc = _load_doc(user_id, base_dir)
    rows = _chat_entries(doc, chat_id)
    if source_kind is not None:
        rows = [row for row in rows if row["source_kind"] == source_kind]
    return copy.deepcopy(rows)


def get_entry(user_id: str, chat_id: str, entry_id: str, *,
              base_dir: Path | None = None) -> dict:
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    entries, index = _find_entry(doc, chat_id, entry_id)
    return copy.deepcopy(entries[index])


def generation_history(user_id: str, chat_id: str, *,
                       base_dir: Path | None = None) -> list[dict]:
    """The preserved generation history for one chat: the
    generated entries, in the order they were generated."""
    return list_entries(
        user_id, chat_id, source_kind=SOURCE_GENERATED, base_dir=base_dir)


def gallery_summary(user_id: str, chat_id: str, *,
                    base_dir: Path | None = None) -> dict:
    """Counts by source kind and by road, plus total bytes:
    the gallery's shape at a glance, provenance intact."""
    rows = list_entries(user_id, chat_id, base_dir=base_dir)
    by_source: dict[str, int] = {}
    by_road: dict[str, int] = {}
    total_bytes = 0
    for row in rows:
        by_source[row["source_kind"]] = by_source.get(row["source_kind"], 0) + 1
        if row["road"]:
            by_road[row["road"]] = by_road.get(row["road"], 0) + 1
        total_bytes += row["byte_size"]
    return {
        "chat_id": chat_id,
        "entry_count": len(rows),
        "by_source": by_source,
        "by_road": by_road,
        "total_bytes": total_bytes,
        "generation_count": by_source.get(SOURCE_GENERATED, 0),
    }


def update_entry(user_id: str, chat_id: str, entry_id: str, *,
                 title: str | None = None, notes: str | None = None,
                 base_dir: Path | None = None) -> dict:
    """Curation only: title and notes may change; every
    provenance field is immutable and untouched here."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    entries, index = _find_entry(doc, chat_id, entry_id)
    entry = entries[index]
    if title is not None:
        entry["title"] = _check_text(title, "title", MAX_TITLE_CHARS)
    if notes is not None:
        entry["notes"] = _check_text(notes, "notes", MAX_NOTES_CHARS)
    doc["chats"][chat_id] = {"entries": entries}
    _save_doc(user_id, doc, base_dir)
    return copy.deepcopy(entry)


def _local_bytes_path(user_id: str, chat_id: str, sha256: str, fmt: str, *,
                      base_dir: Path | None = None) -> Path:
    """The gallery byte-store path for one local attachment.
    Built only from validated UUIDs and the content hash, so
    no caller text ever becomes a path segment."""
    root = Path(base_dir) if base_dir is not None else data_dir()
    ext = fmt if fmt in ("png", "jpeg", "gif", "webp") else "bin"
    return root / BYTES_DIR_NAME / user_id / chat_id / f"{sha256}.{ext}"


def _drop_local_bytes(user_id: str, entry: dict, *,
                      base_dir: Path | None = None) -> None:
    if entry["storage"] != STORAGE_LOCAL:
        return
    path = _local_bytes_path(
        user_id, entry["chat_id"], entry["sha256"], entry["format"],
        base_dir=base_dir)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def remove_entry(user_id: str, chat_id: str, entry_id: str, *,
                 base_dir: Path | None = None) -> dict:
    """Remove one entry; a gallery_local entry's byte file is
    removed with it. P-023 assets are never touched: removing
    a generated/asset entry removes the gallery's reference,
    not the character's asset. Returns the removed entry."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    entries, index = _find_entry(doc, chat_id, entry_id)
    removed = entries.pop(index)
    doc["chats"][chat_id] = {"entries": entries}
    _save_doc(user_id, doc, base_dir)
    _drop_local_bytes(user_id, removed, base_dir=base_dir)
    return copy.deepcopy(removed)


def clear_gallery(user_id: str, chat_id: str, *,
                  base_dir: Path | None = None) -> int:
    """The explicit emptying verb -- the ONLY road that clears
    a chat gallery (chat.deleted events never do). Returns
    the number of entries removed."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    entries = _chat_entries(doc, chat_id)
    if chat_id in doc["chats"]:
        del doc["chats"][chat_id]
        _save_doc(user_id, doc, base_dir)
    for entry in entries:
        _drop_local_bytes(user_id, entry, base_dir=base_dir)
    return len(entries)


# -- Async chat roads (owner-scoped, P-023 joining) --------------------------


async def attach_asset(session, user_id: str, chat_id: str, asset_id: str, *,
                       title: str = "", added_by: str = "owner",
                       base_dir: Path | None = None) -> dict | None:
    """The asset-derived road: gallery-reference an existing
    P-023 asset of the chat's bound character. Returns None
    for a missing/not-owned chat; raises GalleryError when
    the chat has no bound character or the asset is not that
    character's. Bytes are never copied -- the entry carries
    the asset id and the row's sniffed facts."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_id(asset_id, "asset_id")
    from runmal.assets import service as assets_service
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if not chat.character_id:
        raise GalleryError(
            "chat has no bound character; its assets cannot be "
            "gallery-referenced (no_character_bound)")
    asset = await assets_service.get_asset(
        session, user_id, chat.character_id, asset_id)
    if asset is None:
        raise GalleryError(
            f"asset {asset_id!r} is not an asset of the chat's bound "
            "character (asset_missing_or_wrong_character)")
    return _append_entry(user_id, chat_id, {
        "source_kind": SOURCE_ASSET,
        "asset_id": asset.id,
        "road": ROAD_ASSET_DERIVED,
        "filename": asset.name or "",
        "format": asset.format or "",
        "width": asset.width,
        "height": asset.height,
        "byte_size": asset.byte_size or 0,
        "sha256": asset.sha256 or "",
        "storage": STORAGE_ASSET,
        "title": title,
        "added_by": added_by,
    }, base_dir=base_dir)


async def attach_image(session, user_id: str, chat_id: str, *,
                       filename: str, data: bytes, title: str = "",
                       added_by: str = "owner",
                       base_dir: Path | None = None) -> dict | None:
    """The attached road: the owner attaches image bytes to a
    chat. Bytes are sniffed before anything is recorded;
    non-image bytes refuse loudly. A character-bound chat
    lands the bytes through P-023 (kind background) and the
    entry is storage=asset; an unbound chat keeps the bytes
    in the gallery byte store, storage=gallery_local under
    the attached_local road -- labelled, never disguised.
    Returns None for a missing/not-owned chat."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise GalleryError("attached image bytes must be non-empty bytes")
    info = sniff_image(bytes(data))
    if info.format == "unknown" or info.error:
        raise GalleryError(
            f"attached bytes are not a recognisable image "
            f"(format={info.format!r}, error={info.error!r})")
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    sha256 = hashlib.sha256(bytes(data)).hexdigest()
    if chat.character_id:
        from runmal.assets import service as assets_service

        name = Path(filename or "attached").stem or "attached"
        row = await assets_service.add_asset(
            session, user_id, chat.character_id,
            kind="background", name=name,
            filename=filename or f"attached.{info.format}", data=bytes(data))
        return _append_entry(user_id, chat_id, {
            "source_kind": SOURCE_ATTACHED,
            "asset_id": row.id,
            "road": ROAD_ATTACHED_ASSET,
            "filename": filename or "",
            "format": info.format,
            "width": info.width,
            "height": info.height,
            "byte_size": len(data),
            "sha256": sha256,
            "storage": STORAGE_ASSET,
            "title": title,
            "added_by": added_by,
        }, base_dir=base_dir)
    path = _local_bytes_path(
        user_id, chat_id, sha256, info.format, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return _append_entry(user_id, chat_id, {
        "source_kind": SOURCE_ATTACHED,
        "asset_id": None,
        "road": ROAD_ATTACHED_LOCAL,
        "filename": filename or "",
        "format": info.format,
        "width": info.width,
        "height": info.height,
        "byte_size": len(data),
        "sha256": sha256,
        "storage": STORAGE_LOCAL,
        "title": title,
        "added_by": added_by,
    }, base_dir=base_dir)


async def gallery_view(session, user_id: str, chat_id: str, *,
                       base_dir: Path | None = None) -> dict | None:
    """The inspectable per-chat gallery: entries enriched live
    from P-023 where they are asset-backed (asset status and
    thumbnail facts, asset_missing stated plainly when the
    row is gone) and from the byte store where they are
    gallery_local (bytes present | missing). Owner-scoped:
    None for a missing/not-owned chat."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    from runmal.assets.models import asset_to_dict
    from runmal.assets import service as assets_service
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    assets_by_id: dict[str, dict] = {}
    if chat.character_id:
        rows = await assets_service.list_assets(session, user_id, chat.character_id)
        for row in rows or []:
            assets_by_id[row.id] = asset_to_dict(row)
    entries = []
    for entry in list_entries(user_id, chat_id, base_dir=base_dir):
        view = dict(entry)
        if entry["storage"] == STORAGE_ASSET and entry["asset_id"]:
            facts = assets_by_id.get(entry["asset_id"])
            if facts is None:
                view["asset_state"] = "asset_missing"
                view["has_thumbnail"] = False
            else:
                view["asset_state"] = facts["status"]
                view["asset_kind"] = facts["kind"]
                view["asset_thumbnail_status"] = facts["thumbnail_status"]
                view["has_thumbnail"] = facts["has_thumbnail"]
        elif entry["storage"] == STORAGE_LOCAL:
            path = _local_bytes_path(
                user_id, chat_id, entry["sha256"], entry["format"],
                base_dir=base_dir)
            view["bytes_state"] = "present" if path.is_file() else "missing"
            view["has_thumbnail"] = False
        else:
            view["has_thumbnail"] = False
        entries.append(view)
    return {
        "plugin_id": PLUGIN_ID,
        "chat_id": chat_id,
        "character_id": chat.character_id,
        "title": chat.title,
        "entries": entries,
        "summary": gallery_summary(user_id, chat_id, base_dir=base_dir),
    }


async def import_chat_generations(session, user_id: str, chat_id: str, *,
                                  image_plugin=None, plugin=None,
                                  base_dir: Path | None = None) -> dict | None:
    """Pull a P-087 citizen's per-chat history into the
    durable gallery (the preservation road). The image plugin
    instance comes from the caller or from the bound gallery
    citizen (``plugin``); with neither, GalleryError names
    the missing wiring. Owner-scoped: None for a
    missing/not-owned chat."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    source = image_plugin
    if source is None and plugin is not None:
        source = plugin.image_plugin
    if source is None:
        raise GalleryError(
            "no image-generation plugin is bound; generation import "
            "needs the P-087 citizen instance as host wiring")
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    report = sync_generation_history(
        user_id, chat_id, source.history(chat_id), base_dir=base_dir)
    return {
        "chat_id": chat_id,
        "added": report["added"],
        "added_count": len(report["added"]),
        "skipped": report["skipped"],
        "history": generation_history(user_id, chat_id, base_dir=base_dir),
    }


# -- The P-081 citizen -------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Chat Gallery",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Per-chat image gallery with provenance "
                       "and a preserved generation history.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.sidebar",
                "label": "Chat Gallery",
                "order": 90,
                "payload": {"kind": "panel", "route": "chat-gallery"},
            }
        ],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class GalleryPlugin:
    """The citizen: a UI contribution plus a declared chat
    event whose handler abstains -- gallery entries change
    only through the explicit verbs, never because an event
    fired. Host wiring only: the store root override and the
    optional P-087 instance for generation import."""

    def __init__(self, base_dir: Path | None = None, *,
                 image_plugin=None) -> None:
        self._base_dir = base_dir
        self._image_plugin = image_plugin

    @property
    def manifest(self):
        return build_manifest()

    @property
    def image_plugin(self):
        return self._image_plugin

    def bind_image_plugin(self, image_plugin) -> None:
        self._image_plugin = image_plugin

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    async def on_event(self, event) -> None:
        return None


def register_plugin(registry: PluginRegistry, *,
                    base_dir: Path | None = None,
                    image_plugin=None,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, GalleryPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = GalleryPlugin(base_dir, image_plugin=image_plugin)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS", "MAX_CHATS_PER_USER", "MAX_ENTRIES_PER_CHAT",
    "MAX_NOTES_CHARS", "MAX_PROMPT_CHARS", "MAX_TITLE_CHARS",
    "PLUGIN_ID", "PLUGIN_VERSION", "ROAD_ASSET_DERIVED",
    "ROAD_ATTACHED_ASSET", "ROAD_ATTACHED_LOCAL", "SOURCE_ASSET",
    "SOURCE_ATTACHED", "SOURCE_GENERATED", "SOURCE_KINDS",
    "STORAGE_ASSET", "STORAGE_KINDS", "STORAGE_LOCAL", "STORAGE_NONE",
    "STORE_DIR_NAME", "STORE_SCHEMA", "UI_LOCAL_ID", "VERSION",
    "GalleryError", "GalleryNotFoundError", "GalleryPlugin",
    "attach_asset", "attach_image", "build_manifest", "clear_gallery",
    "gallery_summary", "gallery_view", "generation_history", "get_entry",
    "import_chat_generations", "list_entries", "manifest_data",
    "record_generation", "register_plugin", "remove_entry",
    "sandbox_grants", "store_path", "sync_generation_history",
    "update_entry",
]
