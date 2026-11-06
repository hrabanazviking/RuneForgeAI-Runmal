"""Character versioning (P-025).

Same-name cards are versioned, never silently overwritten: importing
or creating a character whose name already exists for the user either
matches an existing version exactly (an exact duplicate, returned
unchanged) or becomes the next version in that name's lineage.

Identity is content-based: a version's identity is the SHA-256 of the
normalised stored form -- the ``export_json`` v2 text, exactly the
digest defined by P-022.  ``effective_content_hash`` always computes
that digest live from the stored ``card_json``; the ``content_hash``
column is only a creation-time index/cache, because other writers
(``update_character``, ``update_editor_fields`` and library organise's
``_rewrite_card_tags``) rewrite ``card_json`` without touching the
column, so a stored value can go stale and must never be trusted for
deduplication.

Row names stay unsuffixed: versions are distinguished by
``version_no`` + ``lineage_id`` only, never by a ``(v2)`` name suffix.

Byte-level provenance is P-029 and is out of scope here.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Character

DUPLICATE_ATTR = "p025_duplicate_exact"


def content_hash_of(card_json: str) -> str:
    """SHA-256 hex digest of the normalised stored form (P-022)."""
    return hashlib.sha256(card_json.encode("utf-8")).hexdigest()


def effective_lineage_id(character) -> str:
    """Lineage id, falling back to the character's own id.

    Legacy rows (created before P-025) have ``lineage_id is None``;
    each such row is its own lineage root.
    """
    return getattr(character, "lineage_id", None) or character.id


def effective_content_hash(character) -> str:
    """Content hash, always computed live from ``card_json``.

    Never returns the stored ``content_hash`` column preferentially:
    several writers rewrite ``card_json`` without touching the column,
    so the stored value can be stale and dedup would misfire.  The
    column remains a creation-time index/cache only.
    """
    return content_hash_of(character.card_json or "")


def _version_no(character) -> int:
    value = getattr(character, "version_no", None)
    return int(value) if value is not None else 1


async def find_name_siblings(
    session: AsyncSession, user_id: str, name: str
) -> list[Character]:
    """Non-deleted characters of ``user_id`` with exactly ``name``.

    Ordered by ``version_no`` ascending, then ``created_at`` ascending.
    """
    result = await session.execute(
        select(Character)
        .where(
            Character.user_id == user_id,
            Character.name == name,
            Character.deleted_at.is_(None),
        )
        .order_by(Character.version_no.asc(), Character.created_at.asc())
    )
    return list(result.scalars().all())


def version_to_dict(character, *, latest_version_no=None) -> dict:
    return {
        "character_id": character.id,
        "name": character.name,
        "version_no": _version_no(character),
        "lineage_id": effective_lineage_id(character),
        "content_hash": effective_content_hash(character),
        "created_at": character.created_at.isoformat()
        if character.created_at is not None
        else None,
        "deleted": character.deleted_at is not None,
        "is_latest": (
            latest_version_no is not None
            and _version_no(character) == latest_version_no
        ),
    }


async def _get_target(
    session: AsyncSession, user_id: str, character_id: str
) -> Character | None:
    """Non-deleted character by id + owner (inline, avoids cycles)."""
    result = await session.execute(
        select(Character).where(
            Character.id == character_id,
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _lineage_rows(
    session: AsyncSession, user_id: str, lineage: str
) -> list[Character]:
    result = await session.execute(
        select(Character).where(
            Character.user_id == user_id,
            or_(Character.lineage_id == lineage, Character.id == lineage),
        )
    )
    rows = [
        c for c in result.scalars().all() if effective_lineage_id(c) == lineage
    ]
    rows.sort(key=lambda c: (_version_no(c), c.created_at))
    return rows


async def lineage_max_version(
    session: AsyncSession, user_id: str, lineage: str
) -> int:
    """Highest version_no ever used in a lineage, deleted rows included.

    Version numbers are never reused inside a lineage: if v2 is
    soft-deleted and new same-name content arrives, it becomes v3,
    not a second v2 (which would make ``get_version(2)`` ambiguous).
    Deduplication still scans live siblings only (see
    ``find_name_siblings``); only the numbering counts deleted rows.
    """
    rows = await _lineage_rows(session, user_id, lineage)
    return max((_version_no(c) for c in rows), default=0)


def _latest_version_no(rows: list[Character]) -> int:
    non_deleted = [c for c in rows if c.deleted_at is None]
    pool = non_deleted or rows
    return max((_version_no(c) for c in pool), default=1)


async def list_versions(
    session: AsyncSession, user_id: str, character_id: str
) -> dict | None:
    target = await _get_target(session, user_id, character_id)
    if target is None:
        return None
    lineage = effective_lineage_id(target)
    rows = await _lineage_rows(session, user_id, lineage)
    latest = _latest_version_no(rows)
    return {
        "character_id": target.id,
        "lineage_id": lineage,
        "name": target.name,
        "latest_version_no": latest,
        "versions": [
            version_to_dict(c, latest_version_no=latest) for c in rows
        ],
    }


async def get_version(
    session: AsyncSession, user_id: str, character_id: str, version_no: int
) -> dict | None:
    target = await _get_target(session, user_id, character_id)
    if target is None:
        return None
    lineage = effective_lineage_id(target)
    rows = await _lineage_rows(session, user_id, lineage)
    row = next((c for c in rows if _version_no(c) == version_no), None)
    if row is None:
        return None
    latest = _latest_version_no(rows)
    payload = version_to_dict(row, latest_version_no=latest)
    payload["card"] = json.loads(row.card_json)
    return payload
