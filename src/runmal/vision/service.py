"""Vision descriptions (P-117, Part VIII opener — DERIVED scope).

The roadmap gives Part VIII one line only ("Vision Services",
P-117..P-130); this slice's scope is derived from the in-tree
census/architecture record — see the P-117 slice doc. What the
derivation found missing, and what lands here:

- a vision description as a first-class citizen OF A CHAT:
  until now ``Capabilities.vision`` was a declared-but-empty
  promise — no backend declared it, no code consumed it, and
  there was no describe surface or store at all;
- an honest provider seam (P-053 discipline): a provider is
  any object with ``provider_id`` / ``model`` / ``road`` and
  ``describe(image_bytes, question) -> str``; provider truth
  rides on every record as data;
- ONE real provider that never fabricates (P-075 no-content
  law): the metadata provider, whose description is built
  ONLY from the sniffed truth about the bytes (format,
  dimensions, byte size, sha256 — assets/imaging). It is
  labelled road "metadata" and is plainly NOT a semantic
  caption. Semantic providers are later Part VIII slices.
- NO provider configured = a plain refusal
  (``VisionUnavailableError``), never an invented description.
- persistence in the house JSON-store pattern (voice/session
  S513): a versioned document ``vision_descriptions.json`` in
  the data dir, tolerant load — a corrupt store reads as
  empty and never bricks the vision surface. NO migration.
- the last description per chat is retrievable as data —
  the read surface behind VX-50's "the last vision
  description is a template variable" (the prompt-composer
  wiring itself is a later slice, named open in the doc).
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.assets.imaging import sniff_image

DESCRIPTIONS_VERSION = 1
DESCRIPTIONS_FILENAME = "vision_descriptions.json"

SOURCE_ASSET = "asset"
SOURCE_INLINE = "inline"


class VisionError(ValueError):
    """A vision operation the state of the world forbids."""


class VisionUnavailableError(VisionError):
    """No vision provider is configured — nothing is invented."""


class VisionProviderError(VisionError):
    """The provider could not describe these bytes."""


def descriptions_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / DESCRIPTIONS_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class VisionDescription:
    """One persisted vision description, bound to a chat."""

    id: str
    chat_id: str
    owner_id: str
    source_kind: str  # "asset" | "inline"
    source_ref: str  # asset id, or "" for inline bytes
    question: str
    description: str
    provider_id: str
    provider_model: str
    provider_road: str  # "metadata" | a future provider's road
    image_format: str
    image_width: int | None
    image_height: int | None
    image_bytes: int
    image_sha256: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "owner_id": self.owner_id,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "question": self.question,
            "description": self.description,
            "provider": {
                "provider_id": self.provider_id,
                "model": self.provider_model,
                "road": self.provider_road,
            },
            "image": {
                "format": self.image_format,
                "width": self.image_width,
                "height": self.image_height,
                "bytes": self.image_bytes,
                "sha256": self.image_sha256,
            },
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VisionDescription:
        provider = data.get("provider") or {}
        image = data.get("image") or {}
        return cls(
            id=str(data.get("id", "")),
            chat_id=str(data.get("chat_id", "")),
            owner_id=str(data.get("owner_id", "")),
            source_kind=str(data.get("source_kind", "")),
            source_ref=str(data.get("source_ref", "")),
            question=str(data.get("question", "")),
            description=str(data.get("description", "")),
            provider_id=str(provider.get("provider_id", "")),
            provider_model=str(provider.get("model", "")),
            provider_road=str(provider.get("road", "")),
            image_format=str(image.get("format", "unknown")),
            image_width=image.get("width"),
            image_height=image.get("height"),
            image_bytes=int(image.get("bytes", 0)),
            image_sha256=str(image.get("sha256", "")),
            created_at=str(data.get("created_at", "")),
        )


# ---------------------------------------------------------- provider


class MetadataVisionProvider:
    """The honest baseline provider: sniffed truth, nothing else.

    Its description names the format, dimensions, byte size
    and digest of the image — real, inspectable facts. It
    never claims to know what the picture SHOWS.
    """

    provider_id = "runmal.vision.metadata"
    model = "sniff-1"
    road = "metadata"

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
            f"Image metadata: {info.format} image, {dims}, "
            f"{len(image_bytes)} bytes, sha256 {digest}. "
            "Metadata road only: no semantic caption was produced."
        )


# ------------------------------------------------------------- store


class VisionStore:
    """Durable description store: vision_descriptions.json."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> list[VisionDescription]:
        try:
            doc = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows = doc.get("descriptions")
        if not isinstance(rows, list):
            return []
        out: list[VisionDescription] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(VisionDescription.from_dict(row))
        return out

    def _save(self, rows: list[VisionDescription]) -> None:
        doc = {
            "version": DESCRIPTIONS_VERSION,
            "descriptions": [row.to_dict() for row in rows],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def append(self, record: VisionDescription) -> VisionDescription:
        rows = self._load()
        rows.append(record)
        self._save(rows)
        return record

    def list_for_chat(self, chat_id: str) -> list[VisionDescription]:
        return [row for row in self._load() if row.chat_id == chat_id]

    def last_for_chat(self, chat_id: str) -> VisionDescription | None:
        rows = self.list_for_chat(chat_id)
        return rows[-1] if rows else None


# ----------------------------------------------------------- service


def describe_image(
    store: VisionStore,
    *,
    chat_id: str,
    owner_id: str,
    image_bytes: bytes,
    provider=None,
    source_kind: str = SOURCE_INLINE,
    source_ref: str = "",
    question: str = "",
    now: str | None = None,
) -> VisionDescription:
    """Describe *image_bytes* for a chat and persist the record.

    Refusals are plain and total: empty bytes raise
    ``VisionError``; no provider raises
    ``VisionUnavailableError`` (nothing is fabricated, nothing
    is stored); a provider's refusal propagates as
    ``VisionProviderError`` and nothing is stored.
    """
    if not image_bytes:
        raise VisionError("no image bytes to describe")
    if provider is None:
        raise VisionUnavailableError(
            "no vision provider is configured; refusing to invent a description"
        )
    text = provider.describe(image_bytes, question)
    info = sniff_image(image_bytes)
    record = VisionDescription(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        owner_id=owner_id,
        source_kind=source_kind,
        source_ref=source_ref,
        question=question,
        description=text,
        provider_id=str(getattr(provider, "provider_id", "")),
        provider_model=str(getattr(provider, "model", "")),
        provider_road=str(getattr(provider, "road", "")),
        image_format=info.format,
        image_width=info.width,
        image_height=info.height,
        image_bytes=len(image_bytes),
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        created_at=now or _now_iso(),
    )
    return store.append(record)
