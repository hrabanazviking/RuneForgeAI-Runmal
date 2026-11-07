"""Character asset models (P-023).

An asset is one blob that belongs to a character: the card art, an
expression sprite, a background, an image embedded in the card, or a
whole pack (archive). The row in ``character_assets`` records where
the asset came from and what Rúnmál did with its bytes; the bytes
themselves live on disk under a relative path and are never carried
in these models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = [
    "MEDIA_TYPES",
    "AssetKind",
    "AssetStatus",
    "ImageInfo",
    "ThumbnailStatus",
    "asset_to_dict",
]


class AssetKind(StrEnum):
    CARD_ART = "card_art"
    EXPRESSION = "expression"
    BACKGROUND = "background"
    EMBEDDED = "embedded"
    PACK = "pack"


class AssetStatus(StrEnum):
    STORED = "stored"
    EXTERNAL_UNFETCHED = "external_unfetched"
    MISSING_BYTES = "missing_bytes"


class ThumbnailStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE_NON_PNG = "unavailable_non_png"
    UNAVAILABLE_DECODE = "unavailable_decode"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class ImageInfo:
    """Facts sniffed from image bytes (see runmal.assets.imaging).

    ``error`` is a short code ("empty" / "corrupt") when the bytes
    claim an image format but are invalid; for non-images ``format``
    is "unknown" and ``error`` stays None.
    """

    format: str = "unknown"
    width: int | None = None
    height: int | None = None
    error: str | None = None


MEDIA_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _plain(value: object) -> object:
    if isinstance(value, StrEnum):
        return str(value)
    return value


def asset_to_dict(asset: object) -> dict:
    """Serialise a CharacterAsset row. Never includes bytes or
    absolute paths — only the stored relative paths."""
    created_at = getattr(asset, "created_at", "")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    thumbnail_status = _plain(getattr(asset, "thumbnail_status", ""))
    return {
        "id": getattr(asset, "id", ""),
        "character_id": getattr(asset, "character_id", ""),
        "kind": _plain(getattr(asset, "kind", "")),
        "name": getattr(asset, "name", ""),
        "source_type": getattr(asset, "source_type", ""),
        "source_uri": getattr(asset, "source_uri", ""),
        "source_ext": getattr(asset, "source_ext", ""),
        "status": _plain(getattr(asset, "status", "")),
        "detail": getattr(asset, "detail", ""),
        "format": getattr(asset, "format", ""),
        "media_type": getattr(asset, "media_type", ""),
        "width": getattr(asset, "width", None),
        "height": getattr(asset, "height", None),
        "byte_size": getattr(asset, "byte_size", 0),
        "sha256": getattr(asset, "sha256", ""),
        "storage_relpath": getattr(asset, "storage_relpath", None),
        "thumbnail_status": thumbnail_status,
        "has_thumbnail": thumbnail_status == "ready",
        "created_at": created_at,
    }
