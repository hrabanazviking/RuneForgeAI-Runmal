"""Character assets (P-023): card art, expressions, backgrounds,
embedded images and packs belonging to a character.

Models and imaging are imported eagerly; the service and router are
loaded lazily through ``__getattr__`` so importing this package never
cycles back through the app / service layers.
"""

from __future__ import annotations

import importlib
from typing import Any

from runmal.assets.imaging import (
    is_probable_archive,
    make_png_thumbnail,
    sniff_image,
)
from runmal.assets.models import (
    MEDIA_TYPES,
    AssetKind,
    AssetStatus,
    ImageInfo,
    ThumbnailStatus,
    asset_to_dict,
)

__all__ = [
    "MEDIA_TYPES",
    "AssetKind",
    "AssetStatus",
    "ImageInfo",
    "ThumbnailStatus",
    "asset_to_dict",
    "is_probable_archive",
    "make_png_thumbnail",
    "sniff_image",
]

_LAZY_MODULES = ("runmal.assets.service", "runmal.assets.router")


def __getattr__(name: str) -> Any:
    """Resolve service / router names lazily (no import cycle, and
    the package imports cleanly before those modules exist)."""
    for module_name in _LAZY_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
