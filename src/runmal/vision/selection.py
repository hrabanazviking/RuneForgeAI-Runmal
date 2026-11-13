"""Vision provider selection + capability truth (P-119).

P-117 shipped the vision provider seam with exactly one
provider, hardcoded in the router. This module is the
selection layer P-117 named open (its items 1 and 2), in the
honest form the tree supports today:

- a CATALOGUE of the providers that exist, as data - each
  labelled with whether it is a SEMANTIC caption provider.
  Neither shipped provider is: the metadata provider reports
  sniffed truth, and the deterministic test provider below
  is a labelled stand-in (the P-086/P-087 house pattern).
  ``semantic_caption_available`` is therefore False, stated
  as data with its reason - never implied otherwise;
- a deterministic TEST provider (road ``deterministic_test``)
  whose description is a deterministic function of the actual
  bytes. It proves selection end-to-end and gives a future
  real captioner a proven road to drop into. It is never
  presented - here, in the API, or in its own output text -
  as a semantic caption;
- BACKEND VISION TRUTH derived from the chat adapters' own
  declared ``Capabilities.vision`` (P-053 discipline): read
  live via ``backends.capabilities.default_model``, imported
  never copied, so this surface cannot drift from the code
  that would send requests. Today no backend declares
  vision, and every row says so (source ``declared``);
- SELECTION with plain refusals: an unknown provider is an
  error naming the known roads; a semantic requirement with
  no semantic provider available raises
  ``VisionUnavailableError`` - selection NEVER falls back
  silently to a non-semantic provider when semantic was
  required (P-075: nothing is fabricated).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from runmal.assets.imaging import sniff_image
from runmal.vision.service import (
    MetadataVisionProvider,
    VisionProviderError,
    VisionUnavailableError,
)

ROAD_METADATA = "metadata"
ROAD_DETERMINISTIC_TEST = "deterministic_test"

#: Provenance of a backend truth row (P-053 vocabulary).
SOURCE_DECLARED = "declared"


# ---------------------------------------------------- test provider


class DeterministicTestVisionProvider:
    """A labelled test provider: deterministic bytes-in/text-out.

    Its description is built ONLY from sniffed truth about the
    bytes (format, dimensions, byte size, sha256) in a fixed
    template, so the same bytes always yield the same text -
    which is what makes selection testable without a model.
    The text names itself a test description and states
    plainly that no semantic caption was produced.
    """

    provider_id = "runmal.vision.deterministic-test"
    model = "byte-fingerprint-1"
    road = ROAD_DETERMINISTIC_TEST

    def describe(self, image_bytes: bytes, question: str = "") -> str:
        info = sniff_image(image_bytes)
        if info.format == "unknown" or info.error:
            raise VisionProviderError(
                "bytes do not sniff as a supported image"
                + (f" ({info.error})" if info.error else "")
            )
        dims = (
            f"{info.width}x{info.height}"
            if info.width is not None and info.height is not None
            else "unknown dimensions"
        )
        digest = hashlib.sha256(image_bytes).hexdigest()
        return (
            f"Deterministic test description [deterministic_test]: "
            f"{info.format} image, {dims}, {len(image_bytes)} bytes, "
            f"sha256 {digest}. Test road only: this text is a "
            "deterministic fingerprint of the bytes, not a semantic "
            "caption - no semantic caption was produced."
        )


def _providers() -> tuple:
    return (MetadataVisionProvider(), DeterministicTestVisionProvider())


# -------------------------------------------------------- catalogue


@dataclass(frozen=True)
class ProviderRow:
    """One provider's truth, as data."""

    provider_id: str
    model: str
    road: str
    semantic: bool
    available: bool
    note: str

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "road": self.road,
            "semantic": self.semantic,
            "available": self.available,
            "note": self.note,
        }


_PROVIDER_NOTES = {
    ROAD_METADATA: (
        "Sniffed truth about the bytes only (format, dimensions, "
        "size, sha256). Not a semantic caption."
    ),
    ROAD_DETERMINISTIC_TEST: (
        "Deterministic test road: a fixed-template fingerprint of "
        "the bytes, for exercising provider selection. Not a "
        "semantic caption."
    ),
}


def provider_catalogue() -> list[ProviderRow]:
    """Every vision provider that exists in-tree, as data."""
    return [
        ProviderRow(
            provider_id=provider.provider_id,
            model=provider.model,
            road=provider.road,
            semantic=False,
            available=True,
            note=_PROVIDER_NOTES.get(provider.road, ""),
        )
        for provider in _providers()
    ]


def semantic_caption_available() -> bool:
    """True only when a real semantic provider exists in-tree."""
    return any(row.semantic and row.available for row in provider_catalogue())


# --------------------------------------------------- backend truth


@dataclass(frozen=True)
class BackendVisionTruth:
    """One chat backend's declared vision truth, as data."""

    backend_key: str
    model_id: str
    vision_declared: bool
    source: str

    def to_dict(self) -> dict:
        return {
            "backend_key": self.backend_key,
            "model_id": self.model_id,
            "vision_declared": self.vision_declared,
            "source": self.source,
        }


def backend_vision_truth() -> list[BackendVisionTruth]:
    """Per-backend ``Capabilities.vision`` truth (P-053 road).

    Read live from each adapter's declared default model via
    ``backends.capabilities.default_model`` - imported, never
    copied - so a backend that one day declares vision changes
    this surface with no edit here. The import is lazy: the
    vision package does not drag the backend stack in at
    import time.
    """
    from runmal.backends.capabilities import default_model
    from runmal.backends.profiles import CHAT_BACKENDS

    rows: list[BackendVisionTruth] = []
    for backend_key in CHAT_BACKENDS:
        model = default_model(backend_key)
        rows.append(
            BackendVisionTruth(
                backend_key=backend_key,
                model_id=model.model_id,
                vision_declared=bool(model.capabilities.vision),
                source=SOURCE_DECLARED,
            )
        )
    return rows


def any_backend_declares_vision() -> bool:
    return any(row.vision_declared for row in backend_vision_truth())


def providers_payload() -> dict:
    """The inspectable truth surface behind GET /vision/providers."""
    return {
        "providers": [row.to_dict() for row in provider_catalogue()],
        "semantic_caption_available": semantic_caption_available(),
        "semantic_caption_note": (
            "No semantic caption provider exists in-tree and no "
            "chat backend declares Capabilities.vision; semantic "
            "requests are refused plainly until a real provider "
            "lands."
        ),
        "backends": [row.to_dict() for row in backend_vision_truth()],
    }


# -------------------------------------------------------- selection


def select_provider(requested: str | None = None, *, semantic_required: bool = False):
    """Choose a vision provider, or refuse plainly.

    ``requested`` names a provider by road or provider_id;
    None selects the metadata provider (P-117's default).
    ``semantic_required=True`` never falls back: with no
    semantic provider in the catalogue it raises
    ``VisionUnavailableError``.
    """
    if semantic_required:
        return select_semantic_provider()
    if requested is None:
        return MetadataVisionProvider()
    for provider in _providers():
        if requested in (provider.road, provider.provider_id):
            return provider
    known = ", ".join(sorted({p.road for p in _providers()}))
    raise VisionProviderError(
        f"unknown vision provider {requested!r}; known roads: {known}"
    )


def select_semantic_provider():
    """The semantic road, honestly: unavailable today.

    No provider in the catalogue is semantic and no chat
    backend declares ``Capabilities.vision`` (see
    ``backend_vision_truth``), so there is nothing honest to
    select. Raises ``VisionUnavailableError`` until a real
    semantic provider lands in-tree.
    """
    for row in provider_catalogue():
        if row.semantic and row.available:
            for provider in _providers():
                if provider.provider_id == row.provider_id:
                    return provider
    raise VisionUnavailableError(
        "no semantic vision provider is configured: the catalogue "
        "holds only non-semantic roads (metadata, deterministic_test) "
        "and no chat backend declares Capabilities.vision; refusing "
        "to invent a caption"
    )
