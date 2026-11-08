"""Folder watcher: watched folders ingest as attachments
(P-121, Part VIII — DERIVED scope; see the P-121 slice doc).

P-120 gave images shown to a chat a durable home (chat image
attachments) and named the folder watcher as the natural
follow-on: attachments are its first-class destination. This
module is that follow-on, with its honesty bound stated
plainly:

- This is an EXPLICIT POLLING SCAN road, not a watcher daemon.
  No background thread, service or OS watcher observes any
  folder between scans, and no record here claims otherwise.
  A "watch folder" is a registration (data); a scan is a
  deliberate operation that ingests what is new since the
  recorded ingestions.
- A registration binds an owner, a designated CHAT and a
  server-side folder path (the operator's own path, stored as
  data). Registration never claims the folder exists; existence
  is a scan-time fact, reported plainly by the scan.
- A scan walks the folder (top level, or recursively when the
  registration says so), in sorted path order, capped at
  ``MAX_FILES_PER_SCAN`` candidates with any truncation named
  in the report. For each candidate it reads the actual bytes:
  a read failure, bytes over the house 16 MiB cap, and an
  attacher refusal (P-120: bytes that do not sniff as a
  supported image) are each a NAMED SKIP that stores nothing.
  The sha256 of the actual bytes is the dedupe truth: a
  (watch, path, sha256) already ingested is skipped as
  already-ingested — an unchanged file never duplicates, and
  a changed file at the same path ingests anew.
- Ingestion goes through P-120's ``attach_image`` as a
  CHAT-LEVEL attachment (message_id None; the filename is the
  file's own name, kept as the operator's label, data only).
  The attacher is resolved LAZILY at scan time — this slice's
  base predates P-120 and the keeper reconciles at banking
  (the P-118 precedent) — and is injectable so the scan can be
  exercised honestly without it. When the attachments module
  is absent, a scan raises a plain ``WatchError`` naming the
  absence and stores nothing.
- Persistence rides the P-117 house pattern: a versioned JSON
  index (``vision_watcher.json``) in the data dir, tolerant
  load (a corrupt store reads as empty, never bricks). NO
  migration. Custody: ``purge_chat`` removes a chat's watch
  registrations and their ingested records (the attachments
  themselves remain P-120 custody).
- custody & control completion (P-124): an attachment's
  death forgets its ingested records (``forget_attachment``),
  so the dedupe memory never tombstones a file whose
  attachment the owner deleted — a later scan judges the
  file fresh and may ingest it anew. And a registration's
  ``enabled`` flag gains its missing handle
  (``set_enabled``): until P-124 no road could ever change
  it, though the scan has always refused a disabled watch.
- Scanning generates NO description or caption and performs
  NO safety scan; ingestion inherits P-120's sniff-only
  stance, and no record claims otherwise.
- history & search (P-127): the watcher store gains the
  owner-wide history + literal search surface P-122 gave
  descriptions and P-125 gave attachments - ``search``
  over registrations (literal over the folder path only)
  and ``list_ingested_for_owner`` / ``search_ingested``
  over the ingested records (owner resolved through watch
  ownership; literal over source_path and sha256 only).
  Search is literal substring matching - never semantic,
  never ranked - and persists nothing: the scan report
  itself remains a synchronous result, unstored.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

WATCHER_VERSION = 1
WATCHER_FILENAME = "vision_watcher.json"

# Parity with the house image caps (P-120 MAX_ATTACHMENT_BYTES,
# cards MAX_ASSET_BYTES): one image-size law everywhere. The
# literal is kept here so this module never imports a module
# its base may not carry yet; the scan's attacher enforces the
# same cap again on its own side.
MAX_WATCH_BYTES = 16 * 1024 * 1024

MAX_FILES_PER_SCAN = 200


class WatchError(ValueError):
    """A watch operation the state of the world forbids."""


def watcher_index_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / WATCHER_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ records


@dataclass(frozen=True)
class WatchFolder:
    """One registered watch: a folder bound to a designated chat."""

    id: str
    owner_id: str
    chat_id: str
    path: str  # operator-supplied folder path, stored as data
    recursive: bool
    enabled: bool
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "chat_id": self.chat_id,
            "path": self.path,
            "recursive": self.recursive,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WatchFolder:
        return cls(
            id=str(data.get("id", "")),
            owner_id=str(data.get("owner_id", "")),
            chat_id=str(data.get("chat_id", "")),
            path=str(data.get("path", "")),
            recursive=bool(data.get("recursive", False)),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True)
class IngestedRecord:
    """One successful ingestion: a path's bytes became an attachment."""

    watch_id: str
    source_path: str
    sha256: str
    size: int
    attachment_id: str
    ingested_at: str

    def to_dict(self) -> dict:
        return {
            "watch_id": self.watch_id,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "size": self.size,
            "attachment_id": self.attachment_id,
            "ingested_at": self.ingested_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IngestedRecord:
        return cls(
            watch_id=str(data.get("watch_id", "")),
            source_path=str(data.get("source_path", "")),
            sha256=str(data.get("sha256", "")),
            size=int(data.get("size", 0)),
            attachment_id=str(data.get("attachment_id", "")),
            ingested_at=str(data.get("ingested_at", "")),
        )


@dataclass
class ScanReport:
    """The plain outcome of one scan: what landed, what skipped."""

    watch_id: str
    chat_id: str
    scanned: int
    ingested: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "watch_id": self.watch_id,
            "chat_id": self.chat_id,
            "scanned": self.scanned,
            "ingested": list(self.ingested),
            "skipped": [dict(row) for row in self.skipped],
            "truncated": self.truncated,
        }


# ------------------------------------------------------------- store


class WatchStore:
    """Durable watch store: one JSON index in the data dir.

    Holds the watch registrations and the ingested records.
    A corrupt index reads as empty and never bricks the
    surface (the P-117 tolerant-load stance).
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / WATCHER_FILENAME

    def _load(self) -> tuple[list[WatchFolder], list[IngestedRecord]]:
        try:
            doc = json.loads(self.index_path.read_text())
        except (OSError, ValueError):
            return [], []
        if not isinstance(doc, dict):
            return [], []
        watches: list[WatchFolder] = []
        raw_watches = doc.get("watches")
        if isinstance(raw_watches, list):
            for row in raw_watches:
                if isinstance(row, dict):
                    watches.append(WatchFolder.from_dict(row))
        ingested: list[IngestedRecord] = []
        raw_ingested = doc.get("ingested")
        if isinstance(raw_ingested, list):
            for row in raw_ingested:
                if isinstance(row, dict):
                    ingested.append(IngestedRecord.from_dict(row))
        return watches, ingested

    def _save(
        self,
        watches: list[WatchFolder],
        ingested: list[IngestedRecord],
    ) -> None:
        doc = {
            "version": WATCHER_VERSION,
            "watches": [row.to_dict() for row in watches],
            "ingested": [row.to_dict() for row in ingested],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    # -- watches -------------------------------------------------

    def add_watch(self, watch: WatchFolder) -> WatchFolder:
        watches, ingested = self._load()
        self._save(watches + [watch], ingested)
        return watch

    def get_watch(self, watch_id: str) -> WatchFolder | None:
        watches, _ = self._load()
        for row in watches:
            if row.id == watch_id:
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[WatchFolder]:
        watches, _ = self._load()
        return [row for row in watches if row.owner_id == owner_id]

    def list_for_chat(self, chat_id: str) -> list[WatchFolder]:
        watches, _ = self._load()
        return [row for row in watches if row.chat_id == chat_id]

    def remove_watch(self, watch_id: str) -> WatchFolder | None:
        watches, ingested = self._load()
        kept = [row for row in watches if row.id != watch_id]
        removed = [row for row in watches if row.id == watch_id]
        if not removed:
            return None
        kept_ingested = [row for row in ingested if row.watch_id != watch_id]
        self._save(kept, kept_ingested)
        return removed[0]

    def set_enabled(self, watch_id: str, enabled: bool) -> WatchFolder | None:
        """Control (P-124): set a registration's enabled flag.

        Returns the updated registration, or None for an
        unknown watch (nothing is written). Every other
        field and all ingested records are preserved. This
        is the flag's first handle: registration always
        created enabled watches and the scan has always
        refused a disabled one, but until P-124 no road
        could change the flag.
        """
        watches, ingested = self._load()
        updated = None
        out: list[WatchFolder] = []
        for row in watches:
            if row.id == watch_id:
                updated = replace(row, enabled=bool(enabled))
                out.append(updated)
            else:
                out.append(row)
        if updated is None:
            return None
        self._save(out, ingested)
        return updated

    def purge_chat(self, chat_id: str) -> int:
        """Custody: drop a chat's watches + their ingested records."""
        watches, ingested = self._load()
        doomed = {row.id for row in watches if row.chat_id == chat_id}
        if not doomed:
            return 0
        kept = [row for row in watches if row.chat_id != chat_id]
        kept_ingested = [
            row for row in ingested if row.watch_id not in doomed]
        self._save(kept, kept_ingested)
        return len(doomed)

    # -- ingested --------------------------------------------------

    def list_ingested(self, watch_id: str) -> list[IngestedRecord]:
        _, ingested = self._load()
        return [row for row in ingested if row.watch_id == watch_id]

    def record_ingested(self, record: IngestedRecord) -> IngestedRecord:
        watches, ingested = self._load()
        self._save(watches, ingested + [record])
        return record

    def forget_attachment(self, attachment_id: str) -> int:
        """Custody (P-124): forget one attachment's ingested records.

        Called when an attachment dies (a single delete, or
        its message's deletion): the records naming it are
        the scan's dedupe memory, and left behind they would
        skip the source file as already-ingested forever,
        though the attachment they produced is gone.
        Forgetting claims nothing about the source file —
        it still sits in its folder, and the next scan
        judges it fresh. An empty id names no attachment
        and forgets nothing; when nothing matches, the
        store file is left byte-untouched. Returns the
        number of records forgotten.
        """
        if not attachment_id:
            return 0
        watches, ingested = self._load()
        kept = [row for row in ingested
                if row.attachment_id != attachment_id]
        removed = len(ingested) - len(kept)
        if removed:
            self._save(watches, kept)
        return removed

    # -- history / search (P-127) ---------------------------

    def search(
        self,
        owner_id: str,
        query: str = "",
        *,
        chat_id: str | None = None,
        enabled: bool | None = None,
        recursive: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WatchFolder], int]:
        """Owner-scoped history search over the registrations.

        LITERAL case-insensitive substring matching over the
        folder path only - the one text identifier a
        registration honestly holds; never semantic, never
        ranked; rows keep store append order. Owner scoping
        happens FIRST: foreign registrations are never
        matched, counted, or returned. An empty query
        matches every owned row (that is the history
        listing). Returns (page, total) where total is the
        full match count before paging.
        """
        needle = (query or "").strip().lower()
        rows = self.list_for_owner(owner_id)
        if chat_id is not None:
            rows = [row for row in rows if row.chat_id == chat_id]
        if enabled is not None:
            rows = [row for row in rows if row.enabled == bool(enabled)]
        if recursive is not None:
            rows = [
                row for row in rows if row.recursive == bool(recursive)]
        if needle:
            rows = [row for row in rows if needle in row.path.lower()]
        total = len(rows)
        effective_limit = max(1, min(200, int(limit)))
        effective_offset = max(0, int(offset))
        return rows[effective_offset:effective_offset + effective_limit], total

    def list_ingested_for_owner(
            self, owner_id: str) -> list[IngestedRecord]:
        """Every ingested record of the owner's watches.

        Ingested records carry no owner field of their own;
        ownership is resolved through the watch
        registrations, in store append order.
        """
        watches, ingested = self._load()
        owned = {row.id for row in watches if row.owner_id == owner_id}
        return [row for row in ingested if row.watch_id in owned]

    def search_ingested(
        self,
        owner_id: str,
        query: str = "",
        *,
        watch_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IngestedRecord], int]:
        """Owner-scoped history search over the ingested records.

        Owner scoping happens FIRST via watch ownership:
        records of foreign watches are never matched,
        counted, or returned. LITERAL case-insensitive
        substring matching over the source_path and the
        sha256 only - the two text identifiers the record
        honestly holds (the P-125 field discipline); never
        semantic, never ranked. Exact watch / chat filters;
        a filter naming a foreign watch or chat simply
        matches nothing at this layer (the HTTP layer
        refuses unknown-or-foreign filter targets with 404
        before calling). Returns (page, total).
        """
        watches, _ = self._load()
        by_id = {row.id: row for row in watches}
        rows = self.list_ingested_for_owner(owner_id)
        if watch_id is not None:
            rows = [row for row in rows if row.watch_id == watch_id]
        if chat_id is not None:
            rows = [
                row for row in rows
                if by_id.get(row.watch_id) is not None
                and by_id[row.watch_id].chat_id == chat_id
            ]
        needle = (query or "").strip().lower()
        if needle:
            rows = [
                row for row in rows
                if needle in row.source_path.lower()
                or needle in row.sha256.lower()
            ]
        total = len(rows)
        effective_limit = max(1, min(200, int(limit)))
        effective_offset = max(0, int(offset))
        return rows[effective_offset:effective_offset + effective_limit], total


# ----------------------------------------------------------- service


def register_watch(
    store: WatchStore,
    *,
    owner_id: str,
    chat_id: str,
    path: str,
    recursive: bool = False,
    now: str | None = None,
) -> WatchFolder:
    """Register a folder to be scanned into a designated chat.

    Refusals are plain and total — nothing is stored: an empty
    path, an empty chat, and an exact duplicate registration
    (same owner, chat and path) each raise ``WatchError``.
    The folder is NOT required to exist here: existence is a
    scan-time fact, never faked at registration.
    """
    cleaned = (path or "").strip()
    if not cleaned:
        raise WatchError("a watch folder path is required")
    if not (chat_id or "").strip():
        raise WatchError("a designated chat is required")
    for row in store.list_for_owner(owner_id):
        if row.chat_id == chat_id and row.path == cleaned:
            raise WatchError(
                "this folder is already registered for this chat")
    watch = WatchFolder(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        chat_id=chat_id,
        path=cleaned,
        recursive=bool(recursive),
        enabled=True,
        created_at=now or _now_iso(),
    )
    return store.add_watch(watch)


def _default_attacher(data_dir: Path):
    """Resolve P-120's attach_image lazily, or refuse plainly.

    Returns a callable ``(data, *, chat_id, owner_id, filename)``
    yielding the attachment record. When the attachments module
    is not in this tree yet, raises ``WatchError`` naming the
    absence — a scan then stores nothing.
    """
    try:
        from runmal.vision import attachments
    except ImportError:
        raise WatchError(
            "image attachments (P-120) are not available in this "
            "tree yet; a scan cannot ingest without them") from None

    att_store = attachments.AttachmentStore(Path(data_dir))

    def attach(data: bytes, *, chat_id: str, owner_id: str,
               filename: str):
        return attachments.attach_image(
            att_store, chat_id=chat_id, owner_id=owner_id,
            data=data, filename=filename)

    return attach


def _candidates(folder: Path, recursive: bool) -> list[Path]:
    if recursive:
        found = [p for p in folder.rglob("*") if p.is_file()]
    else:
        found = [p for p in folder.iterdir() if p.is_file()]
    return sorted(found, key=lambda p: str(p))


def scan_watch(
    store: WatchStore,
    watch: WatchFolder,
    *,
    attacher=None,
    now: str | None = None,
) -> ScanReport:
    """Poll *watch*'s folder once and ingest what is new.

    Plain refusals (nothing ingested, nothing recorded): a
    disabled watch, a folder that is missing or not a
    directory, and — when no attacher is injected — the
    attachments module being absent from the tree. Per-file
    problems are named skips in the report, never errors:
    unreadable bytes, bytes over the house cap, unchanged
    (path, sha256) pairs, and attacher refusals (bytes that
    do not sniff as a supported image).
    """
    if not watch.enabled:
        raise WatchError("this watch is disabled; refusing to scan")
    folder = Path(watch.path)
    if not folder.is_dir():
        raise WatchError(
            f"watch folder is missing or not a directory: {watch.path}")
    if attacher is None:
        attacher = _default_attacher(store.data_dir)
    stamp = now or _now_iso()
    candidates = _candidates(folder, watch.recursive)
    truncated = len(candidates) > MAX_FILES_PER_SCAN
    candidates = candidates[:MAX_FILES_PER_SCAN]
    seen = {
        (row.source_path, row.sha256)
        for row in store.list_ingested(watch.id)
    }
    report = ScanReport(
        watch_id=watch.id, chat_id=watch.chat_id,
        scanned=0, truncated=truncated)
    for candidate in candidates:
        report.scanned += 1
        source = str(candidate)
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            report.skipped.append(
                {"path": source, "reason": f"unreadable: {exc}"})
            continue
        if len(data) > MAX_WATCH_BYTES:
            report.skipped.append({
                "path": source,
                "reason": (
                    f"too_large: {len(data)} bytes over the "
                    f"{MAX_WATCH_BYTES} byte cap"),
            })
            continue
        digest = hashlib.sha256(data).hexdigest()
        if (source, digest) in seen:
            report.skipped.append(
                {"path": source, "reason": "already_ingested"})
            continue
        try:
            record = attacher(
                data, chat_id=watch.chat_id,
                owner_id=watch.owner_id, filename=candidate.name)
        except Exception as exc:  # the attacher's plain refusal
            report.skipped.append(
                {"path": source, "reason": f"refused: {exc}"})
            continue
        attachment_id = str(getattr(record, "id", "") or "")
        store.record_ingested(IngestedRecord(
            watch_id=watch.id, source_path=source, sha256=digest,
            size=len(data), attachment_id=attachment_id,
            ingested_at=stamp))
        seen.add((source, digest))
        report.ingested.append(attachment_id)
    return report
