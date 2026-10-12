"""Character CRUD + avatar/asset references (S106)."""

from __future__ import annotations

import json
import posixpath
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.auth import data_dir
from runmal.cards import import_card
from runmal.cards.exporter import export_json
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
    }


async def create_character(
    session: AsyncSession, user_id: str, card_data: dict, name: str | None = None
) -> Character:
    card = import_card(json.dumps(card_data).encode(), "card.json")
    character = Character(
        user_id=user_id,
        name=name or card.name,
        card_json=export_json(card, "2").decode("utf-8"),
    )
    session.add(character)
    await session.flush()
    await session.commit()
    return character


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
    clone = Character(
        user_id=user_id,
        name=f"{source.name} (copy)",
        card_json=source.card_json,
        avatar_asset=source.avatar_asset,
    )
    session.add(clone)
    await session.flush()
    src_dir = character_asset_dir(source.id)
    if any(src_dir.iterdir()):
        shutil.copytree(
            src_dir, character_asset_dir(clone.id), dirs_exist_ok=True
        )
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
