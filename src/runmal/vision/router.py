"""Vision HTTP surface (P-117): describe-on-request for an
owned chat, the chat's description list, and the last
description (the VX-50 read surface, as data) — on the
``/api/v1/vision`` road, bearer-gated like every API and
wired in app.py.

Owner scoping: a chat that is unknown — or owned by someone
else — answers 404 on every road; existence never leaks.
The truth layer lives in runmal.vision.service; this module
is only the HTTP shape. The only provider this slice ships
is the metadata provider (sniffed truth, road "metadata");
no road here invents a semantic caption.

P-119: describe now selects its provider through
runmal.vision.selection — the request may name a provider
by road or provider_id, or require a semantic provider
(refused plainly today: none exists in-tree) — and
GET /vision/providers exposes the provider catalogue plus
the backends' declared vision truth as data.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets import service as asset_service
from runmal.chats import service as chat_service
from runmal.db.deps import get_owner_id, get_session
from runmal.vision import selection as vision_selection
from runmal.vision import service as vision_service

router = APIRouter(tags=["vision"])


def _store() -> vision_service.VisionStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return vision_service.VisionStore(
        base / vision_service.DESCRIPTIONS_FILENAME)


async def _chat_or_404(session: AsyncSession, owner_id: str, chat_id: str):
    chat = await chat_service.get_chat(session, owner_id, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found")
    return chat


class DescribeRequest(BaseModel):
    chat_id: str
    asset_id: str | None = None
    image_b64: str | None = None
    question: str = ""
    provider: str | None = None
    require_semantic: bool = False


@router.post("/vision/describe")
async def describe(
    body: DescribeRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, body.chat_id)
    if body.asset_id:
        if not chat.character_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset not found")
        asset = await asset_service.get_asset(
            session, owner_id, chat.character_id, body.asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset not found")
        found = asset_service.read_asset_content(chat.character_id, asset)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset bytes not found")
        image_bytes = found[0]
        source_kind = vision_service.SOURCE_ASSET
        source_ref = body.asset_id
    elif body.image_b64 is not None:
        try:
            image_bytes = base64.b64decode(body.image_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="image_b64 is not valid base64") from None
        source_kind = vision_service.SOURCE_INLINE
        source_ref = ""
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="asset_id or image_b64 is required")
    try:
        provider = vision_selection.select_provider(
            body.provider, semantic_required=body.require_semantic)
        record = vision_service.describe_image(
            _store(),
            chat_id=chat.id,
            owner_id=owner_id,
            image_bytes=image_bytes,
            provider=provider,
            source_kind=source_kind,
            source_ref=source_ref,
            question=body.question or "",
        )
    except vision_service.VisionProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    except vision_service.VisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return record.to_dict()


@router.get("/vision/providers")
async def list_providers(
    owner_id: str = Depends(get_owner_id),
):
    return vision_selection.providers_payload()


@router.get("/vision/descriptions")
async def list_descriptions(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    rows = _store().list_for_chat(chat.id)
    return {"chat_id": chat.id, "descriptions": [r.to_dict() for r in rows]}


@router.get("/vision/last")
async def last_description(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    record = _store().last_for_chat(chat.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no vision description for this chat")
    return record.to_dict()
