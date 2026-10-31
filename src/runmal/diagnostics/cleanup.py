"""``runmal cleanup`` — the clean-up tool built over the doctor (F-04).

ST-73 (P-002 census, P-004 delta) asked for a tool that scans for
and removes orphaned files, images, chats of deleted characters,
and stale chat backups, **with per-category risk warnings**. The
doctor (S804) diagnoses some of this — it warns about orphaned
asset directories — but it never cleans, and its orphan test is
coarse (a directory counts as orphaned there unless its character
currently has an avatar). This module is the confirming tool the
doctor's action text points at: it re-judges every category
precisely against the database, attaches the category's risk
warning to every item, and deletes only under discipline:

- **Dry-run by default.** Scanning and planning delete nothing;
  removal requires an explicit ``apply=True`` (CLI: ``--apply``).
- **Re-validation at delete time.** Every item is re-checked
  against the live tree immediately before removal (the character
  is still absent, the file is still unreferenced, the backup is
  still expired and still not the newest of its kind). An item
  whose facts changed since the scan is skipped, never deleted.
- **Containment.** Only paths resolved inside the data dir are
  ever removed, and symlinks are never followed or removed.
- **Risk gating.** Items in a ``high`` risk category (chats of
  deleted characters) are removed only with ``allow_high_risk``;
  unrecognized files in the backups directory are **never**
  removed by this tool — it cannot know what they are.
- **Database discipline.** The scan reads the database read-only
  raw SQLite, like the doctor, so it works on a possibly-broken
  install. If the database is missing or unreadable, no category
  that needs it is judged at all — nothing is called an orphan
  without the database's word. Chat removal is the only write,
  done in one transaction with foreign keys enforced, plus the
  chat's summaries (which carry no foreign key).

The tool never prints secret values: it reports ids, paths,
counts and sizes only.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir

DB_FILENAME = "runmal.db"

ORPHAN_CHARACTER_ASSETS = "orphan_character_assets"
UNREFERENCED_CHARACTER_FILES = "unreferenced_character_files"
CHATS_OF_DELETED_CHARACTERS = "chats_of_deleted_characters"
STALE_BACKUPS = "stale_backups"
STALE_STAGING = "stale_staging"
UNRECOGNIZED_BACKUP_FILES = "unrecognized_backup_files"

#: Category -> (risk, warning). The warning is part of every item
#: in the category: ST-73's "per-category risk warnings" are data,
#: not prose around the tool.
CATEGORY_RISK: dict[str, tuple[str, str]] = {
    ORPHAN_CHARACTER_ASSETS: (
        "medium",
        "the character is gone from the database, so nothing "
        "references these files; deletion is permanent and removes "
        "the last local copy of that character's art",
    ),
    UNREFERENCED_CHARACTER_FILES: (
        "medium",
        "this file sits in a character's asset folder but is not "
        "the avatar the database references; it may be an older "
        "avatar or a hand-placed file, and deletion is permanent",
    ),
    CHATS_OF_DELETED_CHARACTERS: (
        "high",
        "chats hold conversation history and memory provenance; "
        "the character is only soft-deleted and can be restored, "
        "and deleting its chats is irreversible",
    ),
    STALE_BACKUPS: (
        "medium",
        "backups are recovery copies; only backups older than the "
        "stale threshold and never the newest of their kind are "
        "listed, but deleting one removes that recovery point "
        "forever",
    ),
    STALE_STAGING: (
        "low",
        "staging holds verified restore scratch copies, never "
        "live data; deletion only loses the staged copy",
    ),
    UNRECOGNIZED_BACKUP_FILES: (
        "high",
        "this file matches no Rúnmál backup naming, so the tool "
        "cannot know what it is; it is reported and never deleted "
        "by this tool",
    ),
}

#: Categories this tool will never remove, whatever flags it gets.
NEVER_REMOVABLE = frozenset({UNRECOGNIZED_BACKUP_FILES})

# Backup naming is the backups service's contract (S114/S802);
# the patterns are restated here so the diagnostics stay
# import-light on a possibly-broken install, like the doctor.
_BACKUP_PATTERNS = {
    "db": re.compile(r"^runmal-backup-\d{8}T\d{6}\.db$"),
    "full": re.compile(r"^runmal-full-backup-\d{8}T\d{6}\.zip$"),
}

DEFAULT_STALE_BACKUP_DAYS = 30
DEFAULT_STALE_STAGING_DAYS = 7


@dataclass
class CleanupItem:
    category: str
    risk: str
    warning: str
    detail: str
    path: str | None = None
    item_id: str | None = None
    size_bytes: int = 0
    modified_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CleanupReport:
    base_dir: str
    db_path: str
    stale_backup_days: int
    stale_staging_days: int
    items: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # [{category, reason}]

    @property
    def total_bytes(self) -> int:
        return sum(i.size_bytes for i in self.items)

    def by_category(self, category: str) -> list:
        return [i for i in self.items if i.category == category]

    def to_dict(self) -> dict:
        return {
            "base_dir": self.base_dir,
            "db_path": self.db_path,
            "stale_backup_days": self.stale_backup_days,
            "stale_staging_days": self.stale_staging_days,
            "total_bytes": self.total_bytes,
            "items": [i.to_dict() for i in self.items],
            "skipped": list(self.skipped),
        }


@dataclass
class CleanupResult:
    dry_run: bool
    planned: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # [{item, reason}]
    bytes_reclaimed: int = 0

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "planned": [i.to_dict() for i in self.planned],
            "removed": [i.to_dict() for i in self.removed],
            "skipped": list(self.skipped),
            "bytes_reclaimed": self.bytes_reclaimed,
        }


def _item(category: str, detail: str, **kw) -> CleanupItem:
    risk, warning = CATEGORY_RISK[category]
    return CleanupItem(category=category, risk=risk, warning=warning, detail=detail, **kw)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def _tree_size(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _latest_mtime(path: Path) -> float:
    try:
        latest = path.stat().st_mtime
    except OSError:
        return 0.0
    if path.is_dir() and not path.is_symlink():
        for child in path.rglob("*"):
            try:
                latest = max(latest, child.stat().st_mtime)
            except OSError:
                pass
    return latest


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def _age_days(now: datetime, ts: float) -> float:
    return (now.timestamp() - ts) / 86400.0


def _load_characters(db_path: Path) -> dict | None:
    """{id: {avatar_asset, deleted_at}} or None when unjudgeable."""
    if not db_path.is_file():
        return None
    try:
        conn = _connect_ro(db_path)
        try:
            rows = conn.execute(
                "SELECT id, avatar_asset, deleted_at FROM characters"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return {
        row[0]: {"avatar_asset": row[1], "deleted_at": row[2]} for row in rows
    }


def _scan_assets(base: Path, characters: dict, report: CleanupReport) -> None:
    root = base / "assets" / "characters"
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if entry.is_symlink():
            report.skipped.append(
                {
                    "category": ORPHAN_CHARACTER_ASSETS,
                    "reason": f"symlinked asset entry not judged: {entry.name}",
                }
            )
            continue
        if not entry.is_dir():
            report.items.append(
                _item(
                    UNREFERENCED_CHARACTER_FILES,
                    f"file directly under assets/characters belongs to no character: {entry.name}",
                    path=str(entry),
                    size_bytes=_tree_size(entry),
                    modified_at=_iso(_latest_mtime(entry)),
                )
            )
            continue
        character = characters.get(entry.name)
        if character is None:
            report.items.append(
                _item(
                    ORPHAN_CHARACTER_ASSETS,
                    f"asset directory of character {entry.name}, "
                    "which has no row in the database",
                    path=str(entry),
                    item_id=entry.name,
                    size_bytes=_tree_size(entry),
                    modified_at=_iso(_latest_mtime(entry)),
                )
            )
            continue
        referenced = character["avatar_asset"]
        for path in sorted(entry.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(entry).as_posix()
            if referenced and rel == referenced:
                continue
            report.items.append(
                _item(
                    UNREFERENCED_CHARACTER_FILES,
                    f"{entry.name}/{rel} is not the avatar the database "
                    f"references for that character ({referenced or 'none'})",
                    path=str(path),
                    item_id=entry.name,
                    size_bytes=_tree_size(path),
                    modified_at=_iso(_latest_mtime(path)),
                )
            )


def _scan_deleted_chats(db_path: Path, report: CleanupReport) -> None:
    try:
        conn = _connect_ro(db_path)
        try:
            rows = conn.execute(
                "SELECT c.id, c.character_id, c.title, ch.id, ch.deleted_at "
                "FROM chats c LEFT JOIN characters ch "
                "ON ch.id = c.character_id "
                "WHERE c.character_id IS NOT NULL "
                "AND (ch.id IS NULL OR ch.deleted_at IS NOT NULL)"
            ).fetchall()
            counts = dict(
                conn.execute(
                    "SELECT chat_id, COUNT(*) FROM messages GROUP BY chat_id"
                ).fetchall()
            )
        finally:
            conn.close()
    except sqlite3.Error:
        report.skipped.append(
            {
                "category": CHATS_OF_DELETED_CHARACTERS,
                "reason": "chats table unreadable; category not judged",
            }
        )
        return
    for chat_id, character_id, _title, owner_id, _deleted_at in rows:
        state = (
            "character no longer exists"
            if owner_id is None
            else "character is soft-deleted"
        )
        report.items.append(
            _item(
                CHATS_OF_DELETED_CHARACTERS,
                f"chat {chat_id} of {state} character {character_id} "
                f"({counts.get(chat_id, 0)} message(s))",
                item_id=chat_id,
                size_bytes=0,
            )
        )


def _scan_backups(base: Path, now: datetime, report: CleanupReport) -> None:
    directory = base / "backups"
    if not directory.is_dir():
        return
    by_kind: dict[str, list[Path]] = {kind: [] for kind in _BACKUP_PATTERNS}
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        kind = next(
            (k for k, pat in _BACKUP_PATTERNS.items() if pat.match(entry.name)),
            None,
        )
        if kind is None:
            report.items.append(
                _item(
                    UNRECOGNIZED_BACKUP_FILES,
                    f"{entry.name} in the backups directory matches no "
                    "Rúnmál backup filename pattern",
                    path=str(entry),
                    size_bytes=_tree_size(entry),
                    modified_at=_iso(_latest_mtime(entry)),
                )
            )
        else:
            by_kind[kind].append(entry)
    for kind, files in by_kind.items():
        if not files:
            continue
        ordered = sorted(files, key=lambda p: _latest_mtime(p), reverse=True)
        newest = ordered[0]
        for entry in ordered[1:]:
            age = _age_days(now, _latest_mtime(entry))
            if age > report.stale_backup_days:
                report.items.append(
                    _item(
                        STALE_BACKUPS,
                        f"{entry.name} is {age:.0f} days old "
                        f"(threshold {report.stale_backup_days}); "
                        f"the newest {kind} backup ({newest.name}) is kept",
                        path=str(entry),
                        size_bytes=_tree_size(entry),
                        modified_at=_iso(_latest_mtime(entry)),
                    )
                )


def _scan_staging(base: Path, now: datetime, report: CleanupReport) -> None:
    directory = base / "staging"
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink():
            report.skipped.append(
                {
                    "category": STALE_STAGING,
                    "reason": f"symlinked staging entry not judged: {entry.name}",
                }
            )
            continue
        age = _age_days(now, _latest_mtime(entry))
        if age > report.stale_staging_days:
            report.items.append(
                _item(
                    STALE_STAGING,
                    f"staging entry {entry.name} is {age:.0f} days old "
                    f"(threshold {report.stale_staging_days})",
                    path=str(entry),
                    size_bytes=_tree_size(entry),
                    modified_at=_iso(_latest_mtime(entry)),
                )
            )


def scan_cleanup(
    *,
    db_path: str | Path | None = None,
    base_dir: Path | None = None,
    now: datetime | None = None,
    stale_backup_days: int = DEFAULT_STALE_BACKUP_DAYS,
    stale_staging_days: int = DEFAULT_STALE_STAGING_DAYS,
) -> CleanupReport:
    """Scan the installation for cleanable items. Deletes nothing."""
    base = Path(base_dir) if base_dir else data_dir()
    db = Path(db_path) if db_path else base / DB_FILENAME
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    report = CleanupReport(
        base_dir=str(base),
        db_path=str(db),
        stale_backup_days=stale_backup_days,
        stale_staging_days=stale_staging_days,
    )
    characters = _load_characters(db)
    if characters is None:
        for category in (
            ORPHAN_CHARACTER_ASSETS,
            UNREFERENCED_CHARACTER_FILES,
            CHATS_OF_DELETED_CHARACTERS,
        ):
            report.skipped.append(
                {
                    "category": category,
                    "reason": "database missing or unreadable; category "
                    "not judged — nothing is called orphan without the "
                    "database",
                }
            )
    else:
        _scan_assets(base, characters, report)
        _scan_deleted_chats(db, report)
    _scan_backups(base, moment, report)
    _scan_staging(base, moment, report)
    return report


def _revalidate_file_item(item: CleanupItem, report: CleanupReport, now: datetime) -> str | None:
    """Return a skip reason, or None when the item's facts still hold."""
    path = Path(item.path)
    base = Path(report.base_dir).resolve()
    try:
        resolved = path.resolve()
    except OSError as exc:
        return f"path unresolvable: {exc}"
    if not resolved.is_relative_to(base):
        return "path resolves outside the data dir; refused"
    if path.is_symlink():
        return "symlink; not followed or removed"
    if not path.exists():
        return "already gone"
    if item.category in (ORPHAN_CHARACTER_ASSETS, UNREFERENCED_CHARACTER_FILES):
        characters = _load_characters(Path(report.db_path))
        if characters is None:
            return "database became unreadable; orphan state unproven"
        if item.category == ORPHAN_CHARACTER_ASSETS:
            if item.item_id in characters:
                return "character exists again; no longer orphaned"
        else:
            character = characters.get(item.item_id) if item.item_id else None
            if item.item_id is None:
                pass  # stray file under assets/characters: no owner to re-check
            elif character is None:
                return "owning character vanished; re-scan before removing"
            elif (
                character["avatar_asset"]
                and path.name == character["avatar_asset"]
                and path.parent.name == item.item_id
            ):
                return "file is now the character's referenced avatar"
    elif item.category == STALE_BACKUPS:
        kind = next(
            (k for k, pat in _BACKUP_PATTERNS.items() if pat.match(path.name)),
            None,
        )
        if kind is None:
            return "no longer matches a backup filename pattern"
        siblings = [
            p
            for p in path.parent.iterdir()
            if p.is_file() and _BACKUP_PATTERNS[kind].match(p.name)
        ]
        if siblings and max(siblings, key=lambda p: _latest_mtime(p)) == path:
            return "this is now the newest backup of its kind; kept"
        if _age_days(now, _latest_mtime(path)) <= report.stale_backup_days:
            return "no longer older than the stale threshold"
    elif item.category == STALE_STAGING:
        if _age_days(now, _latest_mtime(path)) <= report.stale_staging_days:
            return "no longer older than the stale threshold"
    return None


def _delete_chat(db_path: Path, chat_id: str) -> bool:
    """Delete one chat in one transaction (FK on) + its summaries."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            if not conn.execute(
                "SELECT 1 FROM chats WHERE id = ?", (chat_id,)
            ).fetchone():
                return False
            # chat_summaries.chat_id carries no foreign key (S404
            # model), so it is deleted explicitly; messages and
            # chat_events cascade from the chat row.
            conn.execute("DELETE FROM chat_summaries WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return True
    finally:
        conn.close()


def clean_cleanup(
    report: CleanupReport,
    *,
    categories: set[str] | None = None,
    apply: bool = False,
    allow_high_risk: bool = False,
    now: datetime | None = None,
) -> CleanupResult:
    """Plan (dry-run) or perform removal of a scan's items.

    ``categories=None`` selects every removable category; high-risk
    items are planned/removed only with ``allow_high_risk`` and
    NEVER_REMOVABLE categories are always skipped with their reason.
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    result = CleanupResult(dry_run=not apply)
    for item in report.items:
        label = {"category": item.category, "item": item.detail, "path": item.path}
        if categories is not None and item.category not in categories:
            continue
        if item.category in NEVER_REMOVABLE:
            result.skipped.append({**label, "reason": "category is never removable by this tool"})
            continue
        if item.risk == "high" and not allow_high_risk:
            result.skipped.append(
                {**label, "reason": "high-risk category requires allow_high_risk"}
            )
            continue
        if item.category == CHATS_OF_DELETED_CHARACTERS:
            if apply:
                # Re-validate: the chat must still belong to a
                # deleted or missing character.
                characters = _load_characters(Path(report.db_path))
                if characters is None:
                    result.skipped.append({**label, "reason": "database unreadable"})
                    continue
                conn = _connect_ro(Path(report.db_path))
                try:
                    row = conn.execute(
                        "SELECT character_id FROM chats WHERE id = ?",
                        (item.item_id,),
                    ).fetchone()
                finally:
                    conn.close()
                if row is None:
                    result.skipped.append({**label, "reason": "chat already gone"})
                    continue
                owner = characters.get(row[0]) if row[0] else None
                if row[0] is not None and owner is not None and owner["deleted_at"] is None:
                    result.skipped.append(
                        {**label, "reason": "character is no longer deleted"}
                    )
                    continue
                if _delete_chat(Path(report.db_path), item.item_id):
                    result.removed.append(item)
                else:
                    result.skipped.append({**label, "reason": "chat already gone"})
            else:
                result.planned.append(item)
            continue
        reason = _revalidate_file_item(item, report, moment)
        if reason is not None:
            result.skipped.append({**label, "reason": reason})
            continue
        if not apply:
            result.planned.append(item)
            continue
        path = Path(item.path)
        size = _tree_size(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        result.removed.append(item)
        result.bytes_reclaimed += size
    return result
