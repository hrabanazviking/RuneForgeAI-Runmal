"""Backup REST API (S114). All routes require the local bearer credential."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

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
