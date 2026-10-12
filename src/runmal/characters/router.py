"""Character REST API (S106). All routes require the local bearer credential."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import CardParseError
from runmal.characters import service
from runmal.characters.service import UnsafeFilenameError, character_to_dict
from runmal.db.deps import get_owner_id, get_session

router = APIRouter(tags=["characters"])


class CharacterCreate(BaseModel):
    card: dict
    name: str | None = None


class CharacterUpdate(BaseModel):
    card: dict | None = None
    name: str | None = None


@router.post("/characters", status_code=status.HTTP_201_CREATED)
async def create_character(
    body: CharacterCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        character = await service.create_character(session, user_id, body.card, body.name)
    except CardParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid card: {exc.kind}") from exc
    return character_to_dict(character)


@router.get("/characters")
async def list_characters(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    characters = await service.list_characters(session, user_id)
    return [character_to_dict(c) for c in characters]


@router.get("/characters/{character_id}")
async def get_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.patch("/characters/{character_id}")
async def update_character(
    character_id: str,
    body: CharacterUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        character = await service.update_character(
            session, user_id, character_id, name=body.name, card_data=body.card
        )
    except CardParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid card: {exc.kind}") from exc
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.delete("/characters/{character_id}")
async def delete_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_character(session, user_id, character_id):
        raise HTTPException(status_code=404, detail="character not found")
    return {"deleted": True, "id": character_id}


@router.post("/characters/{character_id}/avatar")
async def upload_avatar(
    character_id: str,
    file: UploadFile,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await file.read()
        stored = await service.set_avatar(session, user_id, character_id, file.filename or "", data)
    except KeyError:
        raise HTTPException(status_code=404, detail="character not found") from None
    except UnsafeFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"filename": stored}


@router.get("/characters/{character_id}/avatar")
async def get_avatar(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None or not character.avatar_asset:
        raise HTTPException(status_code=404, detail="avatar not found")
    try:
        found = service.read_avatar(character_id, character.avatar_asset)
    except UnsafeFilenameError:
        raise HTTPException(status_code=404, detail="avatar not found") from None
    if found is None:
        raise HTTPException(status_code=404, detail="avatar not found")
    data, media_type = found
    return Response(content=data, media_type=media_type)
