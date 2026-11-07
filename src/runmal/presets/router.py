"""Sampling preset CRUD API (S207)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.presets import bundles, interop, packs, service

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


class BundleIn(BaseModel):
    bundle: dict[str, Any]


class OverrideIn(BaseModel):
    bundle_id: str
    overrides: dict[str, Any] | None = None


def _bundle_404() -> HTTPException:
    return HTTPException(status_code=404, detail="bundle not found")


def _bundle_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "already exists" in msg:
        return _to_409(exc)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.post("/presets/bundles", status_code=status.HTTP_201_CREATED)
async def create_bundle(body: BundleIn, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        row = await bundles.create_bundle(session, user_id, body.bundle)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    return bundles.bundle_to_dict(row)


@router.get("/presets/bundles")
async def list_bundles(user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    rows = await bundles.list_bundles(session, user_id)
    return [bundles.bundle_to_dict(r) for r in rows]


@router.post("/presets/bundles/import", status_code=status.HTTP_201_CREATED)
async def import_bundle(body: dict, name: str | None = None, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        row, report = await bundles.import_bundle(session, user_id, body, name=name)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    out = bundles.bundle_to_dict(row)
    out["import_report"] = report
    return out


class PackExportIn(BaseModel):
    name: str
    bundle_ids: list[str] | None = None
    preset_ids: list[str] | None = None
    items: list[dict[str, Any]] | None = None


@router.post("/presets/packs/export")
async def export_pack(body: PackExportIn, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        return await packs.export_library_pack(session, user_id, body.name, bundle_ids=body.bundle_ids, preset_ids=body.preset_ids, extra_items=body.items)
    except ValueError as exc:
        raise _bundle_error(exc) from exc


@router.post("/presets/packs/inspect")
async def inspect_pack(body: dict, user_id: str = Depends(get_owner_id)):
    try:
        return packs.inspect_pack(body)
    except ValueError as exc:
        raise _bundle_error(exc) from exc


@router.post("/presets/packs/import")
async def import_pack(body: dict, on_conflict: str = "create_new", user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        report = await packs.import_pack(session, user_id, body, on_conflict=on_conflict)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    return {"import_report": report}


@router.get("/presets/bundles/{bundle_id}/share")
async def share_bundle(bundle_id: str, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    row = await bundles.get_bundle(session, user_id, bundle_id)
    if row is None:
        raise _bundle_404()
    return bundles.build_share(bundles.bundle_to_dict(row)["bundle"])


@router.get("/presets/bundles/{bundle_id}")
async def get_bundle(bundle_id: str, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    row = await bundles.get_bundle(session, user_id, bundle_id)
    if row is None:
        raise _bundle_404()
    return bundles.bundle_to_dict(row)


@router.patch("/presets/bundles/{bundle_id}")
async def update_bundle(bundle_id: str, body: BundleIn, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        row = await bundles.update_bundle(session, user_id, bundle_id, body.bundle)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    if row is None:
        raise _bundle_404()
    return bundles.bundle_to_dict(row)


@router.delete("/presets/bundles/{bundle_id}")
async def delete_bundle(bundle_id: str, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    if not await bundles.delete_bundle(session, user_id, bundle_id):
        raise _bundle_404()
    return {"ok": True}


@router.get("/presets/overrides")
async def list_overrides(user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    rows = await bundles.list_overrides(session, user_id)
    return [bundles.override_to_dict(r) for r in rows]


@router.put("/presets/overrides/{scope_kind}/{owner_id}")
async def set_override(scope_kind: str, owner_id: str, body: OverrideIn, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        row = await bundles.set_override(session, user_id, scope_kind, owner_id, body.bundle_id, body.overrides)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="bundle or owner not found")
    return bundles.override_to_dict(row)


@router.get("/presets/overrides/{scope_kind}/{owner_id}")
async def get_override(scope_kind: str, owner_id: str, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        row = await bundles.get_override(session, user_id, scope_kind, owner_id)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="override not found")
    return bundles.override_to_dict(row)


@router.delete("/presets/overrides/{scope_kind}/{owner_id}")
async def delete_override(scope_kind: str, owner_id: str, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    try:
        ok = await bundles.delete_override(session, user_id, scope_kind, owner_id)
    except ValueError as exc:
        raise _bundle_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="override not found")
    return {"ok": True}


@router.get("/presets/resolve")
async def resolve_presets(chat_id: str | None = None, character_id: str | None = None, user_id: str = Depends(get_owner_id), session: AsyncSession = Depends(get_session)):
    view = await bundles.resolve_effective(session, user_id, chat_id=chat_id, character_id=character_id)
    return {"effective": view}


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
