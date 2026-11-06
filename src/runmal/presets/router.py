"""Sampling preset CRUD API (S207)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.presets import interop, service

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


@router.post("/presets/import", status_code=status.HTTP_201_CREATED)
async def import_preset(
    body: dict,
    name: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Import a preset file (native / SillyTavern text / chat, P-021)."""
    try:
        imported = interop.parse_preset(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if name:
        imported = replace(imported, name=name)
    try:
        preset = await service.import_preset(session, user_id, imported)
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise _to_409(exc) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        ) from exc
    return service.preset_to_dict(preset)


@router.get("/presets/{preset_id}/export")
async def export_preset(
    preset_id: str,
    format: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Export a preset as a file object (native / st-text / st-chat)."""
    preset = await service.get_preset(session, user_id=user_id, preset_id=preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    data = service.preset_to_dict(preset)
    carriage = service.interop_data(preset)
    view = interop.PresetFileView(
        name=preset.name,
        params=data["params"],
        template_ref=preset.template_ref,
        source_format=data["source_format"],
        raw=carriage.get("raw"),
        prompts=data["prompts"],
        prompt_order=data["prompt_order"],
    )
    fmt = format if format is not None else data["source_format"]
    try:
        payload = interop.export_preset(view, format=fmt)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return json.loads(payload)


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
