"""Image attachments on chats and messages (P-120, Part VIII —
DERIVED scope; see the P-120 slice doc).

Until now an image a user wanted to show a chat had no durable
home: the P-117 describe road takes bytes inline and discards
them, and the P-023 asset store is character-scoped, not
chat-scoped. An attachment is the missing first-class citizen:

- a user-supplied image bound to a CHAT, and optionally to one
  MESSAGE of that chat (message_id None = chat-level);
- bytes persisted on the P-117 house pattern — a versioned
  JSON index (``vision_attachments.json``) in the data dir
  plus byte files under ``vision_attachments/`` named by
  attachment id with the extension taken from the SNIFFED
  format, never from the user-supplied filename. NO migration.
- the record claims ONLY honest truth (P-075 no-content law):
  sniffed format / dimensions / byte size / sha256
  (assets/imaging), who attached it, to which chat/message,
  and when. The filename is the user's own label, stored as
  data; it is never used as a filesystem path and never
  treated as a claim about what the image shows.
- attaching generates NO description or caption; describing an
  attachment is a separate explicit P-117 describe call whose
  record names source_kind "attachment". Nothing here is a
  safety scan: bytes are sniffed as images, not moderated,
  and the record never claims otherwise.
- refusals are plain and total: empty bytes, bytes over the
  house 16 MiB cap, and bytes that do not sniff as a supported
  image all raise ``AttachmentError`` and store NOTHING.
- custody: deleting a message purges its attachments and
  deleting a chat purges the chat's (the P-118 purge idiom,
  wired from runmal.chats.service); a single delete removes
  the index row AND the byte file together.
- thumbnails (P-123) are DERIVED ON READ through the
  in-tree P-023 PNG engine (assets/imaging
  make_png_thumbnail): nothing derived is ever stored,
  so thumbnails need no custody of their own. The engine
  is PNG-only, so a non-PNG attachment refuses plainly;
  thumbnail availability is a request-time fact and is
  never pre-claimed in the attachment record.
- history/search (P-125) is the P-122 parity surface for
  this store: an owner can list and find their attachments
  ACROSS chats, not only per-chat. Search is LITERAL
  case-insensitive substring matching over the filename
  and the image sha256 only - the two text identifiers the
  record honestly holds - with owner scoping FIRST (foreign
  rows are never matched, counted, or returned), exact
  chat / message / format filters, and paging with the
  full total. It is never semantic and never ranked, and
  it reads no image bytes: the record claims no content
  text, so there is nothing semantic to search.
- describe-on-attach (P-126) is an explicit opt-in on the
  HTTP attach road ONLY, and it amends the road's form of
  the no-description invariant above, never the service's:
  attach_image itself still generates NO description
  (every service caller, above all the P-121 watcher scan,
  keeps that invariant exactly), while a caller who opts
  in on the road gets the attachment AND its description
  or neither - see attach_and_describe.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.assets.imaging import make_png_thumbnail, sniff_image
from runmal.vision.service import SOURCE_ATTACHMENT, describe_image

ATTACHMENTS_VERSION = 1
ATTACHMENTS_FILENAME = "vision_attachments.json"
ATTACHMENTS_DIRNAME = "vision_attachments"

# Parity with the house image caps (cards MAX_ASSET_BYTES,
# characters MAX_AVATAR_BYTES): one image-size law everywhere.
MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024

_FORMAT_EXT = {"png": "png", "jpeg": "jpg", "gif": "gif", "webp": "webp"}

# The sniffed format vocabulary (the _FORMAT_EXT keys): the
# only values an attachment record can honestly carry, and
# the validation set for the P-125 history format filter.
KNOWN_FORMATS = ("png", "jpeg", "gif", "webp")
_FORMAT_MEDIA_TYPE = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


class AttachmentError(ValueError):
    """An attachment operation the state of the world forbids."""


def attachments_index_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / ATTACHMENTS_FILENAME


def attachments_bytes_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / ATTACHMENTS_DIRNAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def media_type_for(image_format: str) -> str:
    return _FORMAT_MEDIA_TYPE.get(image_format, "application/octet-stream")


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class ImageAttachment:
    """One persisted image attachment, bound to a chat."""

    id: str
    chat_id: str
    message_id: str | None  # None = chat-level attachment
    owner_id: str
    filename: str  # user-supplied label, data only
    image_format: str
    image_width: int | None
    image_height: int | None
    image_bytes: int
    image_sha256: str
    created_at: str

    @property
    def media_type(self) -> str:
        return media_type_for(self.image_format)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "owner_id": self.owner_id,
            "filename": self.filename,
            "media_type": self.media_type,
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
    def from_dict(cls, data: dict) -> ImageAttachment:
        image = data.get("image") or {}
        return cls(
            id=str(data.get("id", "")),
            chat_id=str(data.get("chat_id", "")),
            message_id=data.get("message_id") or None,
            owner_id=str(data.get("owner_id", "")),
            filename=str(data.get("filename", "")),
            image_format=str(image.get("format", "unknown")),
            image_width=image.get("width"),
            image_height=image.get("height"),
            image_bytes=int(image.get("bytes", 0)),
            image_sha256=str(image.get("sha256", "")),
            created_at=str(data.get("created_at", "")),
        )


# ------------------------------------------------------------- store


class AttachmentStore:
    """Durable attachment store: JSON index + byte files.

    Constructed on the data dir; the index lives at
    ``<data_dir>/vision_attachments.json`` and bytes under
    ``<data_dir>/vision_attachments/<id>.<ext>``. A corrupt
    index reads as empty and never bricks the surface
    (the P-117 tolerant-load stance).
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / ATTACHMENTS_FILENAME
        self.bytes_dir = self.data_dir / ATTACHMENTS_DIRNAME

    # -- index --------------------------------------------------

    def _load(self) -> list[ImageAttachment]:
        try:
            doc = json.loads(self.index_path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows = doc.get("attachments")
        if not isinstance(rows, list):
            return []
        out: list[ImageAttachment] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(ImageAttachment.from_dict(row))
        return out

    def _save(self, rows: list[ImageAttachment]) -> None:
        doc = {
            "version": ATTACHMENTS_VERSION,
            "attachments": [row.to_dict() for row in rows],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    # -- bytes --------------------------------------------------

    def bytes_path(self, record: ImageAttachment) -> Path:
        ext = _FORMAT_EXT.get(record.image_format, "bin")
        return self.bytes_dir / f"{record.id}.{ext}"

    def read_bytes(self, record: ImageAttachment) -> bytes | None:
        """The stored bytes, or None when the byte file is gone."""
        try:
            return self.bytes_path(record).read_bytes()
        except OSError:
            return None

    def _write_bytes(self, record: ImageAttachment, data: bytes) -> None:
        self.bytes_dir.mkdir(parents=True, exist_ok=True)
        self.bytes_path(record).write_bytes(data)

    def _remove_bytes(self, record: ImageAttachment) -> None:
        try:
            self.bytes_path(record).unlink()
        except OSError:
            pass

    # -- operations ----------------------------------------------

    def append(self, record: ImageAttachment, data: bytes) -> ImageAttachment:
        """Persist bytes + index row together.

        Bytes land first; if the index save fails, the byte
        file is removed best-effort so bytes never orphan
        silently behind a failed attach.
        """
        rows = self._load()
        self._write_bytes(record, data)
        try:
            self._save(rows + [record])
        except OSError:
            self._remove_bytes(record)
            raise
        return record

    def get(self, attachment_id: str) -> ImageAttachment | None:
        for row in self._load():
            if row.id == attachment_id:
                return row
        return None

    def list_for_chat(self, chat_id: str) -> list[ImageAttachment]:
        return [row for row in self._load() if row.chat_id == chat_id]

    def list_for_message(self, message_id: str) -> list[ImageAttachment]:
        return [row for row in self._load() if row.message_id == message_id]

    # -- history / search (P-125) ---------------------------

    def list_for_owner(self, owner_id: str) -> list[ImageAttachment]:
        return [row for row in self._load() if row.owner_id == owner_id]

    def search(
        self,
        owner_id: str,
        query: str = "",
        *,
        chat_id: str | None = None,
        message_id: str | None = None,
        image_format: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImageAttachment], int]:
        """Owner-scoped history search over the stored rows.

        LITERAL case-insensitive substring matching over the
        filename and the image sha256 only - never semantic,
        never ranked; rows keep store append order. Owner
        scoping happens FIRST: foreign rows are never matched,
        counted, or returned. An empty query matches every
        owned row (that is the history listing). An unknown
        image_format is a plain AttachmentError refusal.
        Returns (page, total) where total is the full match
        count before paging.
        """
        if image_format is not None and image_format not in KNOWN_FORMATS:
            raise AttachmentError(
                f"unknown image_format {image_format!r}; known formats: "
                f"{', '.join(KNOWN_FORMATS)}")
        needle = (query or "").strip().lower()
        rows = self.list_for_owner(owner_id)
        if chat_id is not None:
            rows = [row for row in rows if row.chat_id == chat_id]
        if message_id is not None:
            rows = [row for row in rows if row.message_id == message_id]
        if image_format is not None:
            rows = [row for row in rows if row.image_format == image_format]
        if needle:
            rows = [
                row
                for row in rows
                if needle in row.filename.lower()
                or needle in row.image_sha256.lower()
            ]
        total = len(rows)
        effective_limit = max(1, min(200, int(limit)))
        effective_offset = max(0, int(offset))
        return rows[effective_offset:effective_offset + effective_limit], total

    def remove(self, attachment_id: str) -> ImageAttachment | None:
        rows = self._load()
        kept = [row for row in rows if row.id != attachment_id]
        removed = [row for row in rows if row.id == attachment_id]
        if not removed:
            return None
        self._save(kept)
        self._remove_bytes(removed[0])
        return removed[0]

    def purge_chat(self, chat_id: str) -> int:
        """Custody: remove a chat's attachments; return the count."""
        rows = self._load()
        kept = [row for row in rows if row.chat_id != chat_id]
        removed = [row for row in rows if row.chat_id == chat_id]
        if not removed:
            return 0
        self._save(kept)
        for row in removed:
            self._remove_bytes(row)
        return len(removed)

    def purge_message(self, message_id: str) -> int:
        """Custody: remove a message's attachments; return the count."""
        rows = self._load()
        kept = [row for row in rows if row.message_id != message_id]
        removed = [row for row in rows if row.message_id == message_id]
        if not removed:
            return 0
        self._save(kept)
        for row in removed:
            self._remove_bytes(row)
        return len(removed)


# ----------------------------------------------------------- service


def attach_image(
    store: AttachmentStore,
    *,
    chat_id: str,
    owner_id: str,
    data: bytes,
    message_id: str | None = None,
    filename: str = "",
    now: str | None = None,
) -> ImageAttachment:
    """Attach user-supplied image bytes to a chat (or a message).

    Refusals are plain and total — nothing is stored: empty
    bytes, bytes over the house cap, and bytes that do not
    sniff as a supported image each raise ``AttachmentError``.
    The record stores sniffed truth only; *filename* is kept
    as the user's own label (trimmed, length-capped) and is
    never used as a path or a content claim.
    """
    if not data:
        raise AttachmentError("no image bytes to attach")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentError(
            f"image is {len(data)} bytes; the cap is "
            f"{MAX_ATTACHMENT_BYTES} bytes")
    info = sniff_image(data)
    if info.format == "unknown" or info.error:
        raise AttachmentError(
            "bytes do not sniff as a supported image"
            + (f" ({info.error})" if info.error else ""))
    record = ImageAttachment(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        message_id=message_id or None,
        owner_id=owner_id,
        filename=(filename or "").strip()[:200],
        image_format=info.format,
        image_width=info.width,
        image_height=info.height,
        image_bytes=len(data),
        image_sha256=hashlib.sha256(data).hexdigest(),
        created_at=now or _now_iso(),
    )
    return store.append(record, data)


# ---------------------------------------------------------- thumbnail
# P-123: thumbnails derived on read (see the module docstring).

THUMBNAIL_DEFAULT_MAX_DIM = 256  # the P-023 engine default
THUMBNAIL_MAX_DIM_LIMIT = 1024


def thumbnail_bytes(
    store: AttachmentStore,
    record: ImageAttachment,
    max_dim: int = THUMBNAIL_DEFAULT_MAX_DIM,
) -> bytes:
    """Derive a PNG thumbnail of *record*'s stored bytes.

    The derivation rides the P-023 engine
    (assets.imaging.make_png_thumbnail) and stores
    NOTHING: no byte file, no index change. Refusals are
    plain and total, each naming its bound:

    - max_dim outside 1..THUMBNAIL_MAX_DIM_LIMIT;
    - a non-PNG attachment - the engine is PNG-only, and the
      full bytes are never served in a thumbnail's place;
    - the byte file missing (the router maps this one to
      404: its text starts with "attachment bytes not found");
    - a PNG outside the engine's decodable subset
      (interlaced, unsupported bit depth / colour type, or
      corrupt pixel data).
    """
    if not (1 <= int(max_dim) <= THUMBNAIL_MAX_DIM_LIMIT):
        raise AttachmentError(
            f"max_dim {max_dim} is outside the supported "
            f"1..{THUMBNAIL_MAX_DIM_LIMIT} range")
    if record.image_format != "png":
        raise AttachmentError(
            f"thumbnails are PNG-only in-tree (the P-023 engine "
            f"decodes PNG only); this attachment is "
            f"{record.image_format or 'unknown'} - refusing to "
            f"substitute the full image")
    data = store.read_bytes(record)
    if data is None:
        raise AttachmentError("attachment bytes not found")
    thumb = make_png_thumbnail(data, max_dim=int(max_dim))
    if thumb is None:
        raise AttachmentError(
            "attachment PNG is outside the thumbnail engine's "
            "decodable subset (interlaced, unsupported bit "
            "depth or colour type, or corrupt pixel data)")
    return thumb


# ------------------------------------------------- describe-on-attach
# P-126: the HTTP attach road's explicit opt-in (see the module
# docstring for the reconciliation). attach_image above is
# unchanged and still generates no description.


def attach_and_describe(
    store: AttachmentStore,
    vision_store,
    *,
    chat_id: str,
    owner_id: str,
    data: bytes,
    message_id: str | None = None,
    filename: str = "",
    question: str = "",
    provider=None,
    now: str | None = None,
):
    # Attach *data* and describe the attachment, atomically.
    # The pair lands together or not at all: attach_image runs
    # first (its plain refusals ride unchanged and nothing is
    # described), then describe_image describes the very same
    # bytes as source_kind attachment - the exact call the P-117
    # describe road makes for an attachment, so the record is
    # indistinguishable from a two-call flow's and inherits the
    # whole P-122 custody story. On ANY describe failure the
    # just-created attachment is removed (index row AND byte
    # file) and the error re-raised; describe_image itself
    # stores nothing on failure (P-117 law), so no half-state
    # survives. provider=None rides describe_image's plain
    # unavailable refusal (and rolls back): this function never
    # invents a provider - selection is the caller's act (the
    # router's, via P-119). Returns (attachment, description).
    record = attach_image(
        store, chat_id=chat_id, owner_id=owner_id, data=data,
        message_id=message_id, filename=filename, now=now)
    try:
        description = describe_image(
            vision_store, chat_id=chat_id, owner_id=owner_id,
            image_bytes=data, provider=provider,
            source_kind=SOURCE_ATTACHMENT, source_ref=record.id,
            question=question, now=now)
    except Exception:
        store.remove(record.id)
        raise
    return record, description
