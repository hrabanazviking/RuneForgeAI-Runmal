"""Backup REST API (S114, S802). All routes require the local bearer credential."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from runmal.backups import full as full_service
from runmal.backups import service

router = APIRouter(tags=["backups"])


@router.post("/backups", status_code=status.HTTP_201_CREATED)
async def create_backup():
    """Take an online backup of the live database (safe while serving)."""
    try:
        info = service.backup_database()
    except service.BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return info.to_dict()


@router.get("/backups")
async def list_backups():
    return service.list_backups()


@router.post("/backups/{filename}/stage")
async def stage_backup(filename: str):
    """Restore a backup to a staging path and verify the staging copy.

    The live database is never touched; a failed restore raises and the
    staging file is removed.
    """
    try:
        name = service.validate_backup_name(filename)
    except service.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = service.backups_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="backup not found")
    try:
        staged = service.stage_restore(path)
    except service.BackupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return staged.to_dict()


@router.post("/backups/full", status_code=status.HTTP_201_CREATED)
async def create_full_backup():
    """Take a full backup bundle (database + assets), safe while serving."""
    try:
        info = full_service.create_full_backup()
    except service.BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return info.to_dict()


@router.post("/backups/full/{filename}/stage")
async def stage_full_backup(filename: str):
    """Validate a full backup bundle and stage it with a restore report.

    The live installation is never touched; a failed validation raises
    and nothing remains staged.
    """
    try:
        name = full_service.validate_full_backup_name(filename)
    except service.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = service.backups_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="full backup not found")
    try:
        report = full_service.stage_full_restore(path)
    except service.BackupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.to_dict()


class ArchiveImportIn(BaseModel):
    path: str


@router.post("/archive/import")
async def import_archive(body: ArchiveImportIn):
    """Import a portable .runmal archive into a fresh staging directory."""
    from datetime import UTC, datetime

    from runmal.portable.archive import ArchiveError
    from runmal.portable.restore import import_archive as run_import

    staging_root = (
        service.staging_dir() / f"archive-import-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    )
    try:
        report = await run_import(body.path, staging_root)
    except ArchiveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.to_dict()
