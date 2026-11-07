"""Character asset storage service (P-023).

Turns a parsed card's declared + embedded assets into
``CharacterAsset`` rows plus bytes on disk, serves those bytes back,
and supports manual uploads, duplication, CHARX re-export and
rollback cleanup. Bytes live under
``data_dir()/assets/characters/<character_id>/p023/``; rows carry
only relative paths (``p023/...``).

The characters service is imported lazily inside functions: the
characters service imports this module at its top level, so a
module-level import here would cycle.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets.imaging import is_probable_archive, make_png_thumbnail, sniff_image
from runmal.assets.models import MEDIA_TYPES, AssetKind, ThumbnailStatus
from runmal.auth import data_dir
from runmal.cards.models import CharacterCard
from runmal.cards.parser import MAX_ASSET_BYTES
from runmal.db.models import CharacterAsset

MAX_THUMBNAIL_DIM = 256

_STORAGE_PREFIX = "p023"
_EMBEDDED_SCHEMES = ("embeded://", "embedded://")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_MAX_STORAGE_NAME = 120


def asset_storage_dir(character_id: str) -> Path:
    """Directory holding a character's P-023 asset bytes.

    Creates the directory (like ``character_asset_dir`` does); call
    it on write paths.
    """
    path = data_dir() / "assets" / "characters" / character_id / _STORAGE_PREFIX
    path.mkdir(parents=True, exist_ok=True)
    return path


def _character_dir(character_id: str) -> Path:
    return data_dir() / "assets" / "characters" / character_id


def _storage_name_for(source_key: str, data: bytes, taken: dict[str, str]) -> str:
    """Flatten *source_key* into a safe, collision-free file name."""
    sha = hashlib.sha256(data).hexdigest()
    name = source_key.replace("/", "__")
    name = _UNSAFE_CHARS.sub("_", name)
    name = name.lstrip(".")
    if not name:
        name = "asset"
    stem, dot, ext = name.rpartition(".")
    if dot and stem:
        suffix = f".{ext}"
    else:
        stem, suffix = name, ""
    if len(stem) + len(suffix) > _MAX_STORAGE_NAME:
        stem = stem[: max(1, _MAX_STORAGE_NAME - len(suffix))]
        name = f"{stem}{suffix}"
    else:
        name = f"{stem}{suffix}"
    owner = taken.get(name)
    if owner is not None and owner != sha:
        tag = f"-{sha[:8]}"
        room = _MAX_STORAGE_NAME - len(suffix) - len(tag)
        name = f"{stem[: max(1, room)]}{tag}{suffix}"
    return name


@dataclass
class PlannedAsset:
    kind: str
    name: str = ""
    source_type: str = ""
    source_uri: str = ""
    source_ext: str = ""
    data: bytes | None = None
    status: str = "stored"
    detail: str = ""


def build_asset_plan(
    card: CharacterCard,
    *,
    has_container_art: bool,
    source_bytes: bytes | None,
) -> list[PlannedAsset]:
    """Plan the asset rows for *card* (pure, no I/O).

    Order: container art first, then one entry per declared v3
    asset descriptor, then embedded bytes no descriptor consumed.
    """
    plan: list[PlannedAsset] = []
    consumed: set[str] = set()
    if has_container_art and source_bytes:
        plan.append(
            PlannedAsset(
                kind=AssetKind.CARD_ART.value,
                name="card_art",
                source_type="container",
                data=source_bytes,
                status="stored",
            )
        )
    for ref in card.asset_refs:
        if not isinstance(ref, dict):
            continue
        raw_type = ref.get("type")
        raw_uri = ref.get("uri")
        raw_name = ref.get("name")
        raw_ext = ref.get("ext")
        source_type = raw_type if isinstance(raw_type, str) else ""
        source_uri = raw_uri if isinstance(raw_uri, str) else ""
        name = raw_name if isinstance(raw_name, str) else ""
        source_ext = raw_ext if isinstance(raw_ext, str) else ""
        if source_type == "icon":
            kind = AssetKind.CARD_ART.value
        elif source_type == "emotion":
            kind = AssetKind.EXPRESSION.value
        elif source_type == "background":
            kind = AssetKind.BACKGROUND.value
        else:
            kind = AssetKind.EMBEDDED.value
        entry = PlannedAsset(
            kind=kind,
            name=name,
            source_type=source_type,
            source_uri=source_uri,
            source_ext=source_ext,
        )
        scheme = next(
            (s for s in _EMBEDDED_SCHEMES if source_uri.startswith(s)), None
        )
        if scheme is not None:
            key = source_uri[len(scheme) :]
            data = card.resolve_asset(source_uri)
            if data is not None:
                entry.data = data
                entry.status = "stored"
                consumed.add(key)
            else:
                entry.status = "missing_bytes"
                entry.detail = "embedded_uri_unresolved"
        elif "://" in source_uri:
            entry.status = "external_unfetched"
            entry.detail = "external_uri_not_fetched"
        elif not source_uri:
            entry.status = "missing_bytes"
            entry.detail = "no_uri"
        else:
            data = card.assets.get(source_uri)
            if data is not None:
                entry.data = data
                entry.status = "stored"
                consumed.add(source_uri)
            else:
                entry.status = "missing_bytes"
                entry.detail = "asset_not_found"
        plan.append(entry)
    for key, data in card.assets.items():
        if key == "card.json" or key in consumed:
            continue
        kind = (
            AssetKind.PACK.value
            if is_probable_archive(data)
            else AssetKind.EMBEDDED.value
        )
        plan.append(
            PlannedAsset(kind=kind, name=key, data=data, status="stored")
        )
    return plan


def _source_key_for(entry: PlannedAsset) -> str:
    if entry.source_type == "container":
        return "card_art.png"
    for scheme in _EMBEDDED_SCHEMES:
        if entry.source_uri.startswith(scheme):
            return entry.source_uri[len(scheme) :] or entry.name or "asset"
    if entry.source_uri and "://" not in entry.source_uri:
        return entry.source_uri
    return entry.name or "asset"


def _store_bytes(
    character_id: str,
    source_key: str,
    data: bytes,
    taken: dict[str, str],
) -> dict:
    """Sniff + write one asset's bytes (and PNG thumbnail).

    Returns row metadata. A failed main write reports
    ``write_failed`` instead of raising; a failed thumbnail write
    only downgrades the thumbnail.
    """
    sha = hashlib.sha256(data).hexdigest()
    info = sniff_image(data)
    fmt = info.format or "unknown"
    meta: dict = {
        "sha256": sha,
        "format": fmt,
        "media_type": MEDIA_TYPES.get(fmt, ""),
        "width": info.width,
        "height": info.height,
        "byte_size": len(data),
        "sniff_error": info.error,
        "storage_relpath": None,
        "thumbnail_relpath": None,
        "thumbnail_status": ThumbnailStatus.NOT_APPLICABLE.value,
        "write_failed": False,
    }
    storage_name = _storage_name_for(source_key, data, taken)
    taken[storage_name] = sha
    base = asset_storage_dir(character_id)
    try:
        (base / storage_name).write_bytes(data)
    except OSError:
        meta["write_failed"] = True
        return meta
    meta["storage_relpath"] = f"{_STORAGE_PREFIX}/{storage_name}"
    if fmt == "png":
        thumb = make_png_thumbnail(data, MAX_THUMBNAIL_DIM)
        if thumb is None:
            meta["thumbnail_status"] = ThumbnailStatus.UNAVAILABLE_DECODE.value
        else:
            thumb_name = f"{storage_name}.png"
            try:
                thumb_dir = base / "thumb"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                (thumb_dir / thumb_name).write_bytes(thumb)
                meta["thumbnail_relpath"] = (
                    f"{_STORAGE_PREFIX}/thumb/{thumb_name}"
                )
                meta["thumbnail_status"] = ThumbnailStatus.READY.value
            except OSError:
                meta["thumbnail_status"] = (
                    ThumbnailStatus.UNAVAILABLE_DECODE.value
                )
    elif fmt in ("jpeg", "gif", "webp"):
        meta["thumbnail_status"] = ThumbnailStatus.UNAVAILABLE_NON_PNG.value
    return meta


async def ingest_card_assets(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    card: CharacterCard,
    *,
    source_bytes: bytes | None = None,
    has_container_art: bool = False,
) -> list[CharacterAsset]:
    """Persist every asset *card* carries for a fresh character.

    Rows are added and flushed; the caller owns the transaction
    (no commit here). Per-asset problems (oversize bytes, write
    failures, corrupt images) degrade that asset's row only.
    """
    plan = build_asset_plan(
        card, has_container_art=has_container_art, source_bytes=source_bytes
    )
    taken: dict[str, str] = {}
    rows: list[CharacterAsset] = []
    for entry in plan:
        row = CharacterAsset(
            character_id=character_id,
            user_id=user_id,
            kind=entry.kind,
            name=entry.name,
            source_type=entry.source_type,
            source_uri=entry.source_uri,
            source_ext=entry.source_ext,
            status=entry.status,
            detail=entry.detail,
        )
        if entry.data is not None:
            if len(entry.data) > MAX_ASSET_BYTES:
                row.status = "missing_bytes"
                row.detail = "oversize_not_stored"
                row.byte_size = len(entry.data)
            else:
                meta = _store_bytes(
                    character_id, _source_key_for(entry), entry.data, taken
                )
                row.sha256 = meta["sha256"]
                row.format = meta["format"]
                row.media_type = meta["media_type"]
                row.width = meta["width"]
                row.height = meta["height"]
                row.byte_size = meta["byte_size"]
                if meta["write_failed"]:
                    row.status = "missing_bytes"
                    row.detail = "write_failed"
                else:
                    row.storage_relpath = meta["storage_relpath"]
                    row.thumbnail_relpath = meta["thumbnail_relpath"]
                    row.thumbnail_status = meta["thumbnail_status"]
                    if meta["sniff_error"] and not row.detail:
                        row.detail = "corrupt_image"
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def add_asset(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    *,
    kind: str,
    name: str,
    filename: str,
    data: bytes,
) -> CharacterAsset:
    """Store one manually uploaded asset and commit (set_avatar
    pattern). Raises KeyError for a missing character, ValueError
    for a bad kind or oversize bytes, UnsafeFilenameError for a
    bad filename."""
    from runmal.characters import service as character_service

    character = await character_service.get_character(session, user_id, character_id)
    if character is None:
        raise KeyError(character_id)
    if kind not in {member.value for member in AssetKind}:
        raise ValueError(f"unknown asset kind: {kind!r}")
    safe = character_service.validate_asset_filename(
        filename, character_service.IMAGE_EXTENSIONS
    )
    if len(data) > character_service.MAX_AVATAR_BYTES:
        raise ValueError(f"asset too large: {len(data)} bytes")
    display_name = name or Path(safe).stem
    meta = _store_bytes(character_id, safe, data, {})
    row = CharacterAsset(
        character_id=character_id,
        user_id=user_id,
        kind=kind,
        name=display_name,
        source_type="upload",
        source_uri="",
        source_ext=Path(safe).suffix.lstrip("."),
        status="stored",
        detail="",
        format=meta["format"],
        media_type=meta["media_type"],
        width=meta["width"],
        height=meta["height"],
        byte_size=meta["byte_size"],
        sha256=meta["sha256"],
        storage_relpath=meta["storage_relpath"],
        thumbnail_relpath=meta["thumbnail_relpath"],
        thumbnail_status=meta["thumbnail_status"],
    )
    if meta["write_failed"]:
        row.status = "missing_bytes"
        row.detail = "write_failed"
        row.storage_relpath = None
        row.thumbnail_relpath = None
        row.thumbnail_status = ThumbnailStatus.NOT_APPLICABLE.value
    elif meta["sniff_error"] and not row.detail:
        row.detail = "corrupt_image"
    session.add(row)
    await session.flush()
    await session.commit()
    return row


async def list_assets(
    session: AsyncSession, user_id: str, character_id: str
) -> list[CharacterAsset] | None:
    from runmal.characters import service as character_service

    character = await character_service.get_character(session, user_id, character_id)
    if character is None:
        return None
    result = await session.execute(
        select(CharacterAsset)
        .where(
            CharacterAsset.character_id == character_id,
            CharacterAsset.user_id == user_id,
        )
        .order_by(CharacterAsset.created_at, CharacterAsset.id)
    )
    return list(result.scalars().all())


async def get_asset(
    session: AsyncSession, user_id: str, character_id: str, asset_id: str
) -> CharacterAsset | None:
    from runmal.characters import service as character_service

    character = await character_service.get_character(session, user_id, character_id)
    if character is None:
        return None
    result = await session.execute(
        select(CharacterAsset).where(
            CharacterAsset.id == asset_id,
            CharacterAsset.character_id == character_id,
            CharacterAsset.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


def _read_relpath(character_id: str, relpath: str) -> bytes | None:
    base = _character_dir(character_id)
    target = (base / relpath).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        return None
    if not target.is_file():
        return None
    try:
        return target.read_bytes()
    except OSError:
        return None


def read_asset_content(
    character_id: str, asset: CharacterAsset
) -> tuple[bytes, str] | None:
    if asset.status != "stored" or not asset.storage_relpath:
        return None
    data = _read_relpath(character_id, asset.storage_relpath)
    if data is None:
        return None
    return data, asset.media_type or "application/octet-stream"


def read_asset_thumbnail(
    character_id: str, asset: CharacterAsset
) -> tuple[bytes, str] | None:
    if asset.thumbnail_status != ThumbnailStatus.READY.value:
        return None
    if asset.thumbnail_relpath:
        data = _read_relpath(character_id, asset.thumbnail_relpath)
        if data is not None:
            return data, "image/png"
    # Thumbnail file missing: thumbnails are derived data, so
    # regenerate from the stored bytes and heal the file.
    found = read_asset_content(character_id, asset)
    if found is None:
        return None
    thumb = make_png_thumbnail(found[0], MAX_THUMBNAIL_DIM)
    if thumb is None:
        return None
    if asset.thumbnail_relpath:
        try:
            target = _character_dir(character_id) / asset.thumbnail_relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(thumb)
        except OSError:
            pass
    return thumb, "image/png"


async def clone_character_assets(
    session: AsyncSession, source_character_id: str, clone_id: str
) -> None:
    """Copy the asset *rows* of a duplicated character (the files
    themselves are copied by duplicate_character's copytree)."""
    result = await session.execute(
        select(CharacterAsset)
        .where(CharacterAsset.character_id == source_character_id)
        .order_by(CharacterAsset.created_at, CharacterAsset.id)
    )
    for source in result.scalars().all():
        session.add(
            CharacterAsset(
                character_id=clone_id,
                user_id=source.user_id,
                kind=source.kind,
                name=source.name,
                source_type=source.source_type,
                source_uri=source.source_uri,
                source_ext=source.source_ext,
                status=source.status,
                detail=source.detail,
                format=source.format,
                media_type=source.media_type,
                width=source.width,
                height=source.height,
                byte_size=source.byte_size,
                sha256=source.sha256,
                storage_relpath=source.storage_relpath,
                thumbnail_relpath=source.thumbnail_relpath,
                thumbnail_status=source.thumbnail_status,
                created_at=source.created_at,
            )
        )
    await session.flush()


async def rebuild_asset_bytes(
    session: AsyncSession, user_id: str, character_id: str
) -> dict[str, bytes] | None:
    """Rebuild the embedded-bytes mapping for CHARX re-export:
    ``{archive_key: bytes}`` for every stored asset whose bytes
    belong inside the archive."""
    rows = await list_assets(session, user_id, character_id)
    if rows is None:
        return None
    rebuilt: dict[str, bytes] = {}
    for row in rows:
        if row.status != "stored":
            continue
        found = read_asset_content(character_id, row)
        if found is None:
            continue
        data = found[0]
        scheme = next(
            (s for s in _EMBEDDED_SCHEMES if row.source_uri.startswith(s)), None
        )
        if scheme is not None:
            rebuilt.setdefault(row.source_uri[len(scheme) :], data)
        elif row.kind in (AssetKind.EMBEDDED.value, AssetKind.PACK.value):
            # Unconsumed archive entries key by their archive name;
            # a bare-path descriptor keys by the path it resolved
            # from (that path is the archive key).
            if row.source_uri and "://" not in row.source_uri:
                rebuilt.setdefault(row.source_uri, data)
            else:
                rebuilt.setdefault(row.name, data)
    return rebuilt


def purge_character_asset_files(character_id: str) -> None:
    shutil.rmtree(asset_storage_dir(character_id), ignore_errors=True)
