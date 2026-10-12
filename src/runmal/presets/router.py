"""Sampling preset CRUD API (S207)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.presets import service

router = APIRouter(tags=["presets"])


class PresetIn(BaseModel):
    name: str
    params: dict[str, Any] | None = None
    template_ref: str = ""


class PresetPatch(BaseModel):
    name: str | None = None
    params: dict[str, Any] | None = None
    template_ref: str | None = None


def _to_409(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/presets", status_code=status.HTTP_201_CREATED)
async def create_preset(
    body: PresetIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        preset = await service.create_preset(
            session,
            user_id=user_id,
            name=body.name,
            params=body.params,
            template_ref=body.template_ref,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise _to_409(exc) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        ) from exc
    return service.preset_to_dict(preset)


@router.get("/presets")
async def list_presets(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    presets = await service.list_presets(session, user_id=user_id)
    return [service.preset_to_dict(p) for p in presets]


@router.get("/presets/{preset_id}")
async def get_preset(
    preset_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    preset = await service.get_preset(session, user_id=user_id, preset_id=preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    return service.preset_to_dict(preset)


@router.patch("/presets/{preset_id}")
async def update_preset(
    preset_id: str,
    body: PresetPatch,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        preset = await service.update_preset(
            session,
            user_id=user_id,
            preset_id=preset_id,
            name=body.name,
            params=body.params,
            template_ref=body.template_ref,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise _to_409(exc) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        ) from exc
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    return service.preset_to_dict(preset)


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_preset(session, user_id=user_id, preset_id=preset_id):
        raise HTTPException(status_code=404, detail="preset not found")
    return {"ok": True}
