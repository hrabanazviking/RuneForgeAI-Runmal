"""Character CRUD + avatar/asset references (S106)."""

from __future__ import annotations

import hashlib
import json
import posixpath
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets.service import (
    clone_character_assets,
    ingest_card_assets,
    purge_character_asset_files,
)
from runmal.auth import data_dir
from runmal.cards import import_card
from runmal.cards.exporter import export_json
from runmal.cards.models import CharacterCard
from runmal.characters.provenance import (
    build_provenance,
    dump_provenance,
    parse_provenance,
)
from runmal.characters.versioning import (
    DUPLICATE_ATTR,
    content_hash_of,
    effective_content_hash,
    effective_lineage_id,
    find_name_siblings,
    lineage_max_version,
)
from runmal.db.models import Character

MAX_AVATAR_BYTES = 16 * 1024 * 1024
MAX_FILENAME_LEN = 128
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_FILENAME_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class UnsafeFilenameError(ValueError):
    pass


def validate_asset_filename(filename: str, allowed_extensions: set[str]) -> str:
    """Return a safe filename or raise UnsafeFilenameError."""
    if not filename or len(filename) > MAX_FILENAME_LEN:
        raise UnsafeFilenameError(f"bad filename: {filename!r}")
    if (
        "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or posixpath.normpath(filename) != filename
        or filename in (".", "..")
    ):
        raise UnsafeFilenameError(f"bad filename: {filename!r}")
    if any(ch not in _FILENAME_ALLOWED for ch in filename):
        raise UnsafeFilenameError(f"bad filename: {filename!r}")
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise UnsafeFilenameError(f"extension not allowed: {filename!r}")
    return filename


def character_asset_dir(character_id: str) -> Path:
    path = data_dir() / "assets" / "characters" / character_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def character_to_dict(character: Character) -> dict:
    return {
        "id": character.id,
        "name": character.name,
        "created_at": character.created_at.isoformat(),
        "has_avatar": bool(character.avatar_asset),
        "avatar_asset": character.avatar_asset,
        "version_no": getattr(character, "version_no", None) or 1,
        "lineage_id": effective_lineage_id(character),
        "content_hash": effective_content_hash(character),
        "provenance": parse_provenance(character),
    }


def _resolve_provenance(card, provenance, *, digest, source_bytes):
    """Merge caller provenance facts with the card/hash/time facts.

    A caller (e.g. bulk library import) supplies only the facts it
    knows -- source_kind, original filename/relpath and the
    original file bytes facts -- as a plain dict. The service fills
    in the rest from the parsed card, always sets ``content_hash``
    to the stored form digest, and sets ``imported_at`` when the
    caller record lacks one (``build_provenance`` stamps UTC now).
    With no caller record the character is ``manual`` and, when
    original bytes are in hand, their hash/length are recorded.
    """
    if provenance is None:
        sha = (
            hashlib.sha256(source_bytes).hexdigest()
            if source_bytes is not None
            else None
        )
        length = len(source_bytes) if source_bytes is not None else None
        return build_provenance(
            card,
            source_kind="manual",
            original_sha256=sha,
            original_byte_length=length,
            content_hash=digest,
        )
    if "original_sha256" in provenance:
        sha = provenance.get("original_sha256")
    elif source_bytes is not None:
        sha = hashlib.sha256(source_bytes).hexdigest()
    else:
        sha = None
    if "original_byte_length" in provenance:
        length = provenance.get("original_byte_length")
    elif source_bytes is not None:
        length = len(source_bytes)
    else:
        length = None
    return build_provenance(
        card,
        source_kind=provenance.get("source_kind") or "manual",
        imported_at=provenance.get("imported_at"),
        original_filename=provenance.get("original_filename"),
        relpath=provenance.get("relpath"),
        original_sha256=sha,
        original_byte_length=length,
        parent_character_id=provenance.get("parent_character_id"),
        content_hash=digest,
    )


async def _get_binding_row(binding_module, session, user_id, character_id):
    """Fetch a character's lorebook binding row via lorebooks.binding.

    Uses ``get_binding_row`` when the binding module exposes it,
    else the ownership-scoped ``get_binding``; the call arity is
    matched to the getter's signature (with/without ``user_id``).
    Returns None when the module exposes no getter.
    """
    import inspect

    fn = getattr(binding_module, "get_binding_row", None) or getattr(
        binding_module, "get_binding", None
    )
    if fn is None:
        return None
    positional = [
        param
        for param in inspect.signature(fn).parameters.values()
        if param.kind
        in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 3:
        return await fn(session, user_id, character_id)
    return await fn(session, character_id)


async def create_character_from_card(
    session: AsyncSession,
    user_id: str,
    card: CharacterCard,
    *,
    name: str | None = None,
    commit: bool = True,
    source_bytes: bytes | None = None,
    provenance: dict | None = None,
) -> Character:
    """Create a Character from an already-parsed card (P-022).

    Stores ``export_json(card, "2")`` exactly as ``create_character``
    does. The card's assets are persisted by P-023's
    ``ingest_card_assets`` (declared descriptors, embedded CHARX
    bytes, and - for a PNG card - the container bytes themselves
    as card art, passed in as ``source_bytes``). Asset ingestion
    failure never refuses an otherwise-valid card: on an unexpected
    ingest error the character's asset files are purged and
    creation continues (the P-022 discipline). With
    ``commit=False`` the row is only flushed, leaving the
    transaction to the caller (bulk import's per-file atomicity).

    P-025: same-name cards are versioned, never silently
    overwritten. The stored text's SHA-256 (the P-022 identity) is
    compared live against every non-deleted same-name sibling: an
    exact match returns that sibling unchanged, flagged with
    ``DUPLICATE_ATTR`` so callers can tell it apart (no row is
    added, no assets are ingested and nothing is committed on
    that path). Otherwise the new row takes the next unused
    ``version_no`` in the lineage (counting deleted rows, so a
    number is never reused) and joins
    the first sibling's lineage; a first-of-name row starts a new
    lineage rooted at its own id. Row names stay unsuffixed:
    versions are distinguished by ``version_no`` + ``lineage_id``
    only. The digest is also stored in the ``content_hash`` column
    as a creation-time index/cache; identity checks always
    recompute it live (see ``versioning.effective_content_hash``).
    """
    stored_text = export_json(card, "2").decode("utf-8")
    digest = content_hash_of(stored_text)
    effective_name = name or card.name
    siblings = await find_name_siblings(session, user_id, effective_name)
    for sib in siblings:
        if effective_content_hash(sib) == digest:
            setattr(sib, DUPLICATE_ATTR, True)
            return sib
    lineage_id = effective_lineage_id(siblings[0]) if siblings else None
    if lineage_id is not None:
        # Numbering counts every row the lineage has ever held,
        # deleted rows included, so a version number is never
        # reused after a soft delete (dedup above scans live
        # siblings only).
        version_no = await lineage_max_version(session, user_id, lineage_id) + 1
    else:
        version_no = 1
    provenance_record = _resolve_provenance(
        card, provenance, digest=digest, source_bytes=source_bytes
    )
    character = Character(
        user_id=user_id,
        name=effective_name,
        card_json=stored_text,
        version_no=version_no,
        lineage_id=lineage_id,
        content_hash=digest,
        provenance_json=dump_provenance(provenance_record),
    )
    session.add(character)
    await session.flush()
    if lineage_id is None:
        character.lineage_id = character.id
    # P-039: an embedded character_book travels as a real bound
    # lorebook. Materialise it (flush-only) alongside the character.
    # A malformed embedded book never refuses an otherwise-valid
    # card -- the asset discipline below: expunge any partial
    # binding/book/entry rows the failed attempt staged in
    # session.new and continue without a binding. card_json still
    # carries the book verbatim either way.
    _pre_book_new = {id(obj) for obj in session.new}
    try:
        from runmal.lorebooks import binding as _book_binding

        if _book_binding.character_book_entries(card.character_book):
            await _book_binding.materialise_character_book(
                session, user_id, character, card.character_book
            )
    except Exception:
        for obj in list(session.new):
            if id(obj) not in _pre_book_new and type(obj).__name__ in (
                "CharacterBookBinding",
                "Lorebook",
                "LoreEntry",
            ):
                session.expunge(obj)
    try:
        await ingest_card_assets(
            session,
            user_id,
            character.id,
            card,
            source_bytes=source_bytes,
            has_container_art=(
                source_bytes is not None and card.source_format == "png"
            ),
        )
    except Exception:
        # Asset failure never refuses an otherwise-valid card; drop
        # any partially written files and un-stage any asset rows
        # the failed ingest added, then continue without them.
        purge_character_asset_files(character.id)
        for obj in list(session.new):
            if type(obj).__name__ == "CharacterAsset" and (
                getattr(obj, "character_id", None) == character.id
            ):
                session.expunge(obj)
    if commit:
        await session.commit()
    return character


async def create_character(
    session: AsyncSession, user_id: str, card_data: dict, name: str | None = None
) -> Character:
    card = import_card(json.dumps(card_data).encode(), "card.json")
    return await create_character_from_card(
        session,
        user_id,
        card,
        name=name,
        provenance=build_provenance(card, source_kind="api_json"),
    )


async def list_characters(session: AsyncSession, user_id: str) -> list[Character]:
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user_id, Character.deleted_at.is_(None))
        .order_by(Character.created_at)
    )
    return list(result.scalars().all())


async def get_character(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    include_deleted: bool = False,
) -> Character | None:
    stmt = select(Character).where(
        Character.id == character_id, Character.user_id == user_id
    )
    if not include_deleted:
        stmt = stmt.where(Character.deleted_at.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def duplicate_character(
    session: AsyncSession, user_id: str, character_id: str
) -> Character | None:
    """Copy a character (card + avatar assets) under a fresh id (S303)."""
    source = await get_character(session, user_id, character_id)
    if source is None:
        return None
    try:
        source_card = import_card(source.card_json.encode(), "card.json")
    except Exception:
        source_card = None
    clone_provenance = build_provenance(
        source_card,
        source_kind="copy",
        parent_character_id=source.id,
        content_hash=content_hash_of(source.card_json),
    )
    clone = Character(
        user_id=user_id,
        name=f"{source.name} (copy)",
        card_json=source.card_json,
        avatar_asset=source.avatar_asset,
        provenance_json=dump_provenance(clone_provenance),
    )
    session.add(clone)
    await session.flush()
    src_dir = character_asset_dir(source.id)
    if any(src_dir.iterdir()):
        shutil.copytree(
            src_dir, character_asset_dir(clone.id), dirs_exist_ok=True
        )
    await clone_character_assets(session, source.id, clone.id)
    # P-039: the clone gets its OWN materialised copy of the
    # source's bound book -- never a shared lorebook, or edits to
    # one character's book would silently rewrite the other's.
    # Serialise the source binding to its travelling dict, then
    # materialise a fresh lorebook + fresh entries + a fresh
    # binding for the clone at the same precedence. A copy never
    # fails over its book link.
    try:
        from runmal.lorebooks import binding as _book_binding

        src_binding = await _get_binding_row(
            _book_binding, session, user_id, source.id
        )
        if src_binding is not None:
            book_dict = await _book_binding.serialise_bound_book(
                session, src_binding
            )
            if isinstance(book_dict, dict):
                await _book_binding.materialise_character_book(
                    session,
                    user_id,
                    clone,
                    book_dict,
                    precedence=getattr(src_binding, "precedence", None),
                )
    except Exception:
        pass
    await session.commit()
    return clone


async def restore_character(
    session: AsyncSession, user_id: str, character_id: str
) -> Character | None:
    """Undo a soft delete (S303). Raises ValueError when not deleted."""
    character = await get_character(
        session, user_id, character_id, include_deleted=True
    )
    if character is None:
        return None
    if character.deleted_at is None:
        raise ValueError("character is not deleted")
    character.deleted_at = None
    await session.commit()
    return character


async def update_character(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    name: str | None = None,
    card_data: dict | None = None,
) -> Character | None:
    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    if card_data is not None:
        card = import_card(json.dumps(card_data).encode(), "card.json")
        character.card_json = export_json(card, "2").decode("utf-8")
        if name is None:
            character.name = card.name
    if name is not None:
        character.name = name
    await session.commit()
    return character


# -- Persona / scenario / greeting editor (S212) -------------------------
# The editor edits the persona-facing card fields in place. The stored card
# is parsed, only the editor fields change, and the card is re-exported --
# unknown-but-valid fields and extensions survive (INV-009).

EDITOR_TEXT_LIMIT = 32000
EDITOR_MAX_GREETINGS = 50
EDITOR_GREETING_LIMIT = 8000

_EDITOR_FIELDS = (
    "description",
    "personality",
    "scenario",
    "first_mes",
    "alternate_greetings",
)


def _editor_view(character: Character) -> dict:
    card = import_card(character.card_json.encode(), "card.json")
    return {
        "character_id": character.id,
        "name": character.name,
        "description": card.description,
        "personality": card.personality,
        "scenario": card.scenario,
        "first_mes": card.first_mes,
        "alternate_greetings": list(card.alternate_greetings),
    }


async def get_editor_fields(
    session: AsyncSession, user_id: str, character_id: str
) -> dict | None:
    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    return _editor_view(character)


async def update_editor_fields(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    description: str | None = None,
    personality: str | None = None,
    scenario: str | None = None,
    first_mes: str | None = None,
    alternate_greetings: list[str] | None = None,
) -> dict | None:
    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    card = import_card(character.card_json.encode(), "card.json")
    for field_name, value in (
        ("description", description),
        ("personality", personality),
        ("scenario", scenario),
        ("first_mes", first_mes),
    ):
        if value is not None:
            if len(value) > EDITOR_TEXT_LIMIT:
                raise ValueError(f"{field_name} exceeds {EDITOR_TEXT_LIMIT} chars")
            setattr(card, field_name, value)
    if alternate_greetings is not None:
        if len(alternate_greetings) > EDITOR_MAX_GREETINGS:
            raise ValueError(
                f"at most {EDITOR_MAX_GREETINGS} alternate greetings"
            )
        for greeting in alternate_greetings:
            if len(greeting) > EDITOR_GREETING_LIMIT:
                raise ValueError(
                    f"a greeting exceeds {EDITOR_GREETING_LIMIT} chars"
                )
        card.alternate_greetings = list(alternate_greetings)
    character.card_json = export_json(card, "2").decode("utf-8")
    await session.commit()
    return _editor_view(character)


async def delete_character(session: AsyncSession, user_id: str, character_id: str) -> bool:
    character = await get_character(session, user_id, character_id)
    if character is None:
        return False
    # Soft delete (S303): stamp and hide; assets and the row are retained
    # so the deletion can be undone (restore_character).
    character.deleted_at = datetime.now(UTC)
    await session.commit()
    return True


async def set_avatar(
    session: AsyncSession,
    user_id: str,
    character_id: str,
    filename: str,
    data: bytes,
) -> str:
    character = await get_character(session, user_id, character_id)
    if character is None:
        raise KeyError(character_id)
    safe = validate_asset_filename(filename, IMAGE_EXTENSIONS)
    if len(data) > MAX_AVATAR_BYTES:
        raise ValueError(f"avatar too large: {len(data)} bytes")
    target = character_asset_dir(character_id) / safe
    target.write_bytes(data)
    character.avatar_asset = safe
    await session.commit()
    return safe


def read_avatar(character_id: str, filename: str) -> tuple[bytes, str] | None:
    safe = validate_asset_filename(filename, IMAGE_EXTENSIONS)
    target = character_asset_dir(character_id) / safe
    if not target.is_file():
        return None
    suffix = target.suffix.lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }[suffix]
    return target.read_bytes(), media_type
