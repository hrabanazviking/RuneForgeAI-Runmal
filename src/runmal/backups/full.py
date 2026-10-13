"""Full backup bundles + staging restore with report (S802).

A full backup is more than the database: it is the installation —
SQLite database (taken with the S114 online-backup API, safe while the
app is active) + the asset tree, sealed in one ZIP bundle with a
manifest of SHA-256 checksums.

Restore discipline is inherited from S114 and strengthened: a bundle
is validated (manifest, checksums, DB integrity, schema revision)
BEFORE anything is staged; staging extracts into a fresh directory and
produces a RestoreReport; the live installation is never written to,
so a failed restore cannot corrupt the working install. Swapping a
staged restore into place is a separate, deliberate act outside this
module.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runmal import __version__
from runmal.auth import data_dir
from runmal.backups import service
from runmal.backups.service import BackupError

FULL_BACKUP_FILENAME_RE = re.compile(r"^runmal-full-backup-\d{8}T\d{6}\.zip$")
FULL_FORMAT_VERSION = 1
MANIFEST_NAME = "backup-manifest.json"
DB_MEMBER = "runmal.db"
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

__all__ = [
    "FULL_BACKUP_FILENAME_RE",
    "BackupError",
    "FullBackupInfo",
    "RestoreReport",
    "create_full_backup",
    "stage_full_restore",
    "validate_full_backup_name",
]


@dataclass
class FullBackupInfo:
    name: str
    path: str
    sha256: str
    size_bytes: int
    created_at: str
    schema_revision: str
    app_version: str
    asset_files: int
    secrets_included: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RestoreCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class RestoreReport:
    ok: bool
    bundle: str
    staged_db: str | None
    staged_assets_dir: str | None
    schema_revision: str | None
    counts: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "bundle": self.bundle,
            "staged_db": self.staged_db,
            "staged_assets_dir": self.staged_assets_dir,
            "schema_revision": self.schema_revision,
            "counts": self.counts,
            "checks": [asdict(c) for c in self.checks],
            "warnings": list(self.warnings),
        }


def validate_full_backup_name(name: str) -> str:
    if not FULL_BACKUP_FILENAME_RE.match(name):
        raise BackupError(f"not a Rúnmál full-backup filename: {name!r}")
    return name


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def create_full_backup(
    *,
    db_path: str | Path | None = None,
    base_dir: Path | None = None,
    dest: str | Path | None = None,
) -> FullBackupInfo:
    """Bundle DB (online backup) + assets into one sealed ZIP.

    Safe while the app is active: the database member is produced by
    the S114 online-backup API, never by copying the live file.
    """
    base = base_dir or data_dir()
    src_db = Path(db_path) if db_path else service.default_db_path()
    if dest is None:
        service.backups_dir().mkdir(parents=True, exist_ok=True)
        dst = service.backups_dir() / f"runmal-full-backup-{_timestamp()}.zip"
    else:
        dst = Path(dest)
        dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise BackupError(f"refusing to overwrite existing file: {dst}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "runmal.db"
        db_info = service.backup_database(source=src_db, dest=tmp_db)
        db_bytes = tmp_db.read_bytes()

        assets: dict[str, bytes] = {}
        assets_root = base / "assets"
        if assets_root.is_dir():
            for path in sorted(assets_root.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(base).as_posix()
                    assets[rel] = path.read_bytes()

        manifest = {
            "kind": "runmal-full-backup",
            "format_version": FULL_FORMAT_VERSION,
            "app_version": __version__,
            "schema_revision": db_info.schema_revision,
            "created_at": datetime.now(UTC).isoformat(),
            "database": {
                "member": DB_MEMBER,
                "sha256": _sha256_bytes(db_bytes),
                "size_bytes": len(db_bytes),
            },
            "assets": {rel: _sha256_bytes(blob) for rel, blob in sorted(assets.items())},
            "secrets_included": False,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:

            def write(name: str, blob: bytes) -> None:
                info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, blob)

            write(DB_MEMBER, db_bytes)
            for rel, blob in sorted(assets.items()):
                write(rel, blob)
            write(MANIFEST_NAME, json.dumps(manifest, indent=2).encode("utf-8"))
        blob = buffer.getvalue()
        dst.write_bytes(blob)
    return FullBackupInfo(
        name=dst.name,
        path=str(dst),
        sha256=_sha256_bytes(blob),
        size_bytes=len(blob),
        created_at=manifest["created_at"],
        schema_revision=manifest["schema_revision"],
        app_version=__version__,
        asset_files=len(assets),
    )


def _check_member_name(name: str) -> None:
    if (
        name.startswith("/")
        or name.startswith("\\")
        or "\\" in name
        or any(part in ("..", "") for part in name.split("/"))
    ):
        raise BackupError(f"unsafe bundle member name: {name!r}")


def _read_bundle(bundle: str | Path) -> tuple[dict, dict[str, bytes]]:
    p = Path(bundle)
    if not p.is_file():
        raise BackupError(f"no full backup at {p}")
    try:
        zf = zipfile.ZipFile(p)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(f"not a readable bundle: {exc}") from exc
    with zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise BackupError("duplicate member names in bundle")
        for name in names:
            _check_member_name(name)
        if MANIFEST_NAME not in names:
            raise BackupError("backup-manifest.json missing")
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except json.JSONDecodeError as exc:
            raise BackupError(f"bundle manifest unreadable: {exc}") from exc
        members = {name: zf.read(name) for name in names if name != MANIFEST_NAME}
    if not isinstance(manifest, dict) or manifest.get("kind") != "runmal-full-backup":
        raise BackupError("manifest kind is not runmal-full-backup")
    if manifest.get("format_version") != FULL_FORMAT_VERSION:
        raise BackupError(
            f"unsupported full-backup format version: {manifest.get('format_version')!r}"
        )
    if manifest.get("secrets_included") is not False:
        raise BackupError("bundle claims secrets were included; refusing")
    return manifest, members


def _verify_members(manifest: dict, members: dict[str, bytes]) -> None:
    db_meta = manifest.get("database") or {}
    db_blob = members.get(DB_MEMBER)
    if db_blob is None:
        raise BackupError("database member missing from bundle")
    if _sha256_bytes(db_blob) != db_meta.get("sha256"):
        raise BackupError("database member checksum mismatch")
    expected_assets = manifest.get("assets") or {}
    for rel, expected in expected_assets.items():
        blob = members.get(rel)
        if blob is None:
            raise BackupError(f"asset member missing: {rel}")
        if _sha256_bytes(blob) != expected:
            raise BackupError(f"asset checksum mismatch: {rel}")
    extra = set(members) - {DB_MEMBER} - set(expected_assets)
    if extra:
        raise BackupError(f"unmanifested members in bundle: {sorted(extra)}")


def _db_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        out = {}
        for table in (
            "users",
            "characters",
            "chats",
            "messages",
            "memories",
            "lorebooks",
            "sampling_presets",
            "backend_profiles",
        ):
            try:
                out[table] = conn.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed names
                ).fetchone()[0]
            except sqlite3.Error:
                out[table] = 0
        return out
    finally:
        conn.close()


def stage_full_restore(
    bundle: str | Path, *, staging_root: str | Path | None = None
) -> RestoreReport:
    """Validate a full-backup bundle and stage it; never touch the live DB.

    On any failure the staged directory is removed and BackupError is
    raised — the working installation is byte-identical afterwards.
    """
    manifest, members = _read_bundle(bundle)
    checks: list[RestoreCheck] = []
    _verify_members(manifest, members)
    checks.append(RestoreCheck("checksums", True, "all member checksums verified"))

    if staging_root is None:
        service.staging_dir().mkdir(parents=True, exist_ok=True)
        root = service.staging_dir() / f"full-restore-{_timestamp()}"
    else:
        root = Path(staging_root)
    if root.exists():
        raise BackupError(f"refusing to overwrite staging directory: {root}")
    root.mkdir(parents=True)
    try:
        staged_db = root / "runmal.db"
        staged_db.write_bytes(members[DB_MEMBER])
        info = service.verify_backup(staged_db)
        checks.append(
            RestoreCheck("database_integrity", True, f"integrity ok, schema {info.schema_revision}")
        )
        if info.schema_revision != manifest.get("schema_revision"):
            raise BackupError(
                "schema revision mismatch: manifest "
                f"{manifest.get('schema_revision')!r} vs database "
                f"{info.schema_revision!r}"
            )
        assets_dir = root / "assets"
        asset_count = 0
        for rel in manifest.get("assets") or {}:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(members[rel])
            asset_count += 1
        checks.append(RestoreCheck("assets", True, f"{asset_count} asset files staged"))
        counts = _db_counts(staged_db)
        checks.append(RestoreCheck("contents", True, json.dumps(counts)))
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return RestoreReport(
        ok=True,
        bundle=str(bundle),
        staged_db=str(staged_db),
        staged_assets_dir=str(assets_dir),
        schema_revision=info.schema_revision,
        counts=counts,
        checks=checks,
    )
