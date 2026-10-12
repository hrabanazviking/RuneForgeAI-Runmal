"""Safe SQLite online backup + restore-to-staging verification (S114).

Backups use SQLite's online backup API (`Connection.backup`), which is safe
while the app holds the database open (WAL mode; the API handles locking).
A backup contains the database file only -- never the bearer credential or
other secrets (`secrets_included` is always False in the metadata).

Restore discipline: a backup is NEVER applied directly over the live
database. `stage_restore` copies it to a staging path and verifies the
staging copy (integrity check + schema revision); any failure deletes the
staging file and raises, so a corrupt backup cannot replace the working DB.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal import __version__
from runmal.auth import data_dir

BACKUP_FILENAME_RE = re.compile(r"^runmal-backup-\d{8}T\d{6}\.db$")
BACKUPS_DIRNAME = "backups"
STAGING_DIRNAME = "staging"
DB_FILENAME = "runmal.db"


class BackupError(Exception):
    """Typed backup/restore failure."""


@dataclass
class BackupInfo:
    name: str
    path: str
    sha256: str
    size_bytes: int
    created_at: str
    schema_revision: str
    app_version: str
    secrets_included: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def backups_dir() -> Path:
    return data_dir() / BACKUPS_DIRNAME


def staging_dir() -> Path:
    return data_dir() / STAGING_DIRNAME


def default_db_path() -> Path:
    return data_dir() / DB_FILENAME


def validate_backup_name(name: str) -> str:
    """Accept only our own timestamped backup filenames (no separators)."""
    if not BACKUP_FILENAME_RE.match(name):
        raise BackupError(f"not a Rúnmál backup filename: {name!r}")
    return name


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    if len(rows) != 1 or rows[0][0] != "ok":
        detail = rows[0][0] if rows else "no result"
        raise BackupError(f"integrity_check failed: {detail}")


def _schema_revision(conn: sqlite3.Connection) -> str:
    try:
        rows = conn.execute("SELECT revision FROM schema_migrations ORDER BY revision").fetchall()
    except sqlite3.Error as exc:
        raise BackupError(f"backup has no schema_migrations table: {exc}") from exc
    if not rows:
        raise BackupError("backup has empty schema_migrations")
    return str(rows[-1][0])


def verify_backup(path: str | Path) -> BackupInfo:
    """Open a backup read-only, integrity-check it, return its metadata."""
    p = Path(path)
    if not p.is_file():
        raise BackupError(f"no backup at {p}")
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30)
    try:
        _integrity_check(conn)
        revision = _schema_revision(conn)
    except sqlite3.Error as exc:
        raise BackupError(f"backup {p.name} failed verification: {exc}") from exc
    finally:
        conn.close()
    return BackupInfo(
        name=p.name,
        path=str(p),
        sha256=_sha256(p),
        size_bytes=p.stat().st_size,
        created_at=_utc_now(),
        schema_revision=revision,
        app_version=__version__,
    )


def backup_database(source: str | Path | None = None, dest: str | Path | None = None) -> BackupInfo:
    """Online-backup the live database, verify the copy, return metadata.

    Safe to call while the app is serving: SQLite's backup API copies
    through the live lock state instead of needing the app stopped.
    """
    src = Path(source) if source else default_db_path()
    if not src.is_file():
        raise BackupError(f"no database at {src}")
    if dest is None:
        backups_dir().mkdir(parents=True, exist_ok=True)
        dst = backups_dir() / f"runmal-backup-{_timestamp()}.db"
    else:
        dst = Path(dest)
        dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise BackupError(f"refusing to overwrite existing file: {dst}")
    src_conn = sqlite3.connect(str(src), timeout=30)
    try:
        dst_conn = sqlite3.connect(str(dst), timeout=30)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    # Only report success after the copy proves itself.
    return verify_backup(dst)


def stage_restore(backup_path: str | Path, staging_path: str | Path | None = None) -> BackupInfo:
    """Restore a backup to a staging path and verify the staging copy.

    The live database is never touched by this function. Any failure
    deletes the staging file and raises BackupError.
    """
    src = Path(backup_path)
    verify_backup(src)  # fail fast on a corrupt backup, before copying
    if staging_path is None:
        staging_dir().mkdir(parents=True, exist_ok=True)
        dst = staging_dir() / f"restore-{_timestamp()}.db"
    else:
        dst = Path(staging_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise BackupError(f"refusing to overwrite staging file: {dst}")
    try:
        shutil.copy2(src, dst)
        staged = verify_backup(dst)
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    return staged


def list_backups() -> list[dict]:
    """List backup files present (metadata from the filesystem, unverified)."""
    directory = backups_dir()
    if not directory.is_dir():
        return []
    entries = []
    for p in sorted(directory.iterdir()):
        if p.is_file() and BACKUP_FILENAME_RE.match(p.name):
            stat = p.stat()
            entries.append(
                {
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
    return entries
