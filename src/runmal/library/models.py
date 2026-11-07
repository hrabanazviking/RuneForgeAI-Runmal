"""Bulk library import report models (P-022).

A bulk import is one act with a report: every file seen is accounted
for exactly once as accepted, repaired, refused, or skipped, so
``total_seen == accepted + repaired + refused + skipped`` always.
The report never carries file contents - only names, sizes, hashes,
verdicts, and reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

__all__ = [
    "BulkEntry",
    "BulkImportReport",
    "BulkKind",
    "BulkOutcome",
    "RefusalCode",
    "RepairCode",
    "RepairNote",
    "SkippedEntry",
]


class BulkOutcome(StrEnum):
    ACCEPTED = "accepted"
    REPAIRED = "repaired"
    REFUSED = "refused"
    SKIPPED = "skipped"


class BulkKind(StrEnum):
    CARD = "card"
    LOREBOOK = "lorebook"
    UNKNOWN = "unknown"


class RefusalCode(StrEnum):
    """Why a file was refused.

    The first ten values are the card parser's ``CardErrorKind``
    values carried verbatim; the rest are bulk-import codes.
    """

    # CardErrorKind values, verbatim.
    INPUT_TOO_LARGE = "input_too_large"
    INVALID_JSON = "invalid_json"
    TRUNCATED = "truncated"
    NOT_A_CARD = "not_a_card"
    UNSUPPORTED_VERSION = "unsupported_version"
    BAD_ARCHIVE = "bad_archive"
    PATH_TRAVERSAL = "path_traversal"
    ASSET_TOO_LARGE = "asset_too_large"
    NO_CARD_DATA = "no_card_data"
    INVALID_PNG = "invalid_png"
    # Bulk-import codes.
    INVALID_LOREBOOK = "invalid_lorebook"
    UNRECOGNIZED_CONTENT = "unrecognized_content"
    AMBIGUOUS_KIND = "ambiguous_kind"
    UNSUPPORTED_KIND = "unsupported_kind"
    MISSING_NAME = "missing_name"
    DUPLICATE_EXACT = "duplicate_exact"
    DUPLICATE_IN_BATCH = "duplicate_in_batch"
    BATCH_LIMIT = "batch_limit"
    UNREADABLE = "unreadable"
    STORAGE_ERROR = "storage_error"


class RepairCode(StrEnum):
    """The closed list of repairs a bulk import may apply."""

    BOM_STRIPPED = "bom_stripped"
    CONTENT_SNIFFED = "content_sniffed"
    LOREBOOK_NAME_FROM_FILENAME = "lorebook_name_from_filename"
    NAME_WHITESPACE_TRIMMED = "name_whitespace_trimmed"


@dataclass
class RepairNote:
    code: RepairCode
    detail: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.code, str) and not isinstance(self.code, RepairCode):
            try:
                self.code = RepairCode(self.code)
            except ValueError:
                pass

    def to_dict(self) -> dict:
        return {"code": str(self.code), "detail": self.detail}


@dataclass
class SkippedEntry:
    relpath: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {"relpath": self.relpath, "reason": self.reason}


@dataclass
class BulkEntry:
    """The verdict for one seen file."""

    relpath: str
    filename: str
    size_bytes: int = 0
    sha256: str = ""
    detected_kind: BulkKind = BulkKind.UNKNOWN
    detected_format: str | None = None
    outcome: BulkOutcome = BulkOutcome.REFUSED
    reason_code: RefusalCode | None = None
    reason: str = ""
    repairs: list[RepairNote] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_id: str | None = None
    created_name: str | None = None
    duplicate_of: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.detected_kind, str) and not isinstance(
            self.detected_kind, BulkKind
        ):
            try:
                self.detected_kind = BulkKind(self.detected_kind)
            except ValueError:
                self.detected_kind = BulkKind.UNKNOWN
        if isinstance(self.outcome, str) and not isinstance(self.outcome, BulkOutcome):
            try:
                self.outcome = BulkOutcome(self.outcome)
            except ValueError:
                pass
        if isinstance(self.reason_code, str) and not isinstance(
            self.reason_code, RefusalCode
        ):
            try:
                self.reason_code = RefusalCode(self.reason_code)
            except ValueError:
                pass
        self.repairs = [
            r if isinstance(r, RepairNote) else RepairNote(**r) if isinstance(r, dict) else r
            for r in self.repairs
        ]

    def to_dict(self) -> dict:
        return {
            "relpath": self.relpath,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "detected_kind": str(self.detected_kind),
            "detected_format": self.detected_format,
            "outcome": str(self.outcome),
            "reason_code": str(self.reason_code) if self.reason_code is not None else None,
            "reason": self.reason,
            "repairs": [r.to_dict() for r in self.repairs],
            "notes": list(self.notes),
            "created_id": self.created_id,
            "created_name": self.created_name,
            "duplicate_of": self.duplicate_of,
        }


@dataclass
class BulkImportReport:
    """The report of one bulk import act."""

    batch_id: str = ""
    source_label: str = ""
    dry_run: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    totals: dict = field(default_factory=dict)
    entries: list[BulkEntry] = field(default_factory=list)
    skipped: list[SkippedEntry] = field(default_factory=list)

    def compute_totals(self) -> dict:
        totals = {
            "total_seen": len(self.entries),
            "accepted": 0,
            "repaired": 0,
            "refused": 0,
            "skipped": 0,
        }
        for entry in self.entries:
            key = str(entry.outcome)
            if key in totals:
                totals[key] += 1
        return totals

    @property
    def ok(self) -> bool:
        """True when the act refused nothing."""
        return self.compute_totals().get("refused", 0) == 0

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "source_label": self.source_label,
            "dry_run": self.dry_run,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "totals": self.compute_totals(),
            "entries": [e.to_dict() for e in self.entries],
            "skipped": [s.to_dict() for s in self.skipped],
        }
