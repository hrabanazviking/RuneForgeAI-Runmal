"""Character asset REST API (P-023). All routes require the local
bearer credential (applied in app.py, like characters)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets import service
from runmal.assets.models import asset_to_dict
from runmal.cards.parser import MAX_ASSET_BYTES
from runmal.characters.service import UnsafeFilenameError
from runmal.db.deps import get_owner_id, get_session
from runmal.safety import SafetyError, read_upload_capped

router = APIRouter(tags=["characters"])


@router.get("/characters/{character_id}/assets")
async def list_assets(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    rows = await service.list_assets(session, user_id, character_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="character not found")
    return [asset_to_dict(row) for row in rows]


@router.get("/characters/{character_id}/assets/{asset_id}")
async def get_asset(
    character_id: str,
    asset_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    row = await service.get_asset(session, user_id, character_id, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset_to_dict(row)


@router.get("/characters/{character_id}/assets/{asset_id}/content")
async def get_asset_content(
    character_id: str,
    asset_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    row = await service.get_asset(session, user_id, character_id, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if row.status != "stored":
        raise HTTPException(status_code=404, detail="asset content not stored")
    found = service.read_asset_content(character_id, row)
    if found is None:
        raise HTTPException(status_code=404, detail="asset content not stored")
    data, media_type = found
    return Response(content=data, media_type=media_type)


@router.get("/characters/{character_id}/assets/{asset_id}/thumbnail")
async def get_asset_thumbnail(
    character_id: str,
    asset_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    row = await service.get_asset(session, user_id, character_id, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if row.thumbnail_status != "ready":
        raise HTTPException(
            status_code=404,
            detail=f"thumbnail_unavailable:{row.thumbnail_status}",
        )
    found = service.read_asset_thumbnail(character_id, row)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"thumbnail_unavailable:{row.thumbnail_status}",
        )
    data, media_type = found
    return Response(content=data, media_type=media_type)


@router.post(
    "/characters/{character_id}/assets", status_code=status.HTTP_201_CREATED
)
async def upload_asset(
    character_id: str,
    file: UploadFile,
    kind: str = Form("embedded"),
    name: str = Form(""),
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await read_upload_capped(file, MAX_ASSET_BYTES)
        row = await service.add_asset(
            session,
            user_id,
            character_id,
            kind=kind,
            name=name,
            filename=file.filename or "",
            data=data,
        )
    except SafetyError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="character not found") from None
    except UnsafeFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asset_to_dict(row)
