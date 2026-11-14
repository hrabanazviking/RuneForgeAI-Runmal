"""Local persona + user-name API (R-03).

Until R-03, a chat's persona could be read or switched ONLY through
the bridge-token surface (``bridge/router.py``, scoped bridge
credentials, INV-029) — the local owner, whose credential guards
every other ``/api/v1`` route, had no door at all. This router is
that door, over the same service the bridge uses
(``chats.service.set_chat_persona``), with the same semantics:
switching is an explicit state change affecting FUTURE turns only;
stored messages keep their original speaker snapshots.

Routes (mounted under ``/api/v1`` in ``runmal.app``, local-credential
auth like every engine route):

- ``GET  /chats/{chat_id}/persona`` — the chat's active persona
  (``{character_id, name}`` or null).
- ``POST /chats/{chat_id}/persona`` — set it (body
  ``{"character_id": …}``; null clears). Unknown chat → 404;
  unknown/foreign character → 422 (the bridge route's shape for the
  same fact).
- ``GET  /user-name`` — the persisted ``{{user}}`` name (R-03,
  ``runmal.persona.user_settings``): the stored name, or the default
  ``"User"`` when unset, with ``is_set`` saying which.
- ``PUT  /user-name`` — set it (body ``{"user_name": …}``); an empty
  name clears the setting back to the default.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters.service import get_character
from runmal.chats import service as chats_service
from runmal.db.deps import get_owner_id, get_session
from runmal.persona import user_settings

router = APIRouter(tags=["persona"])


class PersonaIn(BaseModel):
    character_id: str | None = None


class UserNameIn(BaseModel):
    user_name: str


async def _persona_view(session: AsyncSession, user_id: str, chat) -> dict:
    persona = None
    if chat.character_id:
        character = await get_character(session, user_id, chat.character_id)
        if character is not None:
            persona = {"character_id": character.id, "name": character.name}
    return {"chat_id": chat.id, "persona": persona}


@router.get("/chats/{chat_id}/persona")
async def get_chat_persona(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    chat = await chats_service.get_chat(session, user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return await _persona_view(session, user_id, chat)


@router.post("/chats/{chat_id}/persona")
async def set_chat_persona_route(
    chat_id: str,
    body: PersonaIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    existing = await chats_service.get_chat(session, user_id, chat_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="chat not found")
    previous = existing.character_id
    try:
        chat = await chats_service.set_chat_persona(
            session,
            user_id,
            chat_id,
            body.character_id,
            event_data={"source": "local"},
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="character not found",
        ) from None
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    payload = await _persona_view(session, user_id, chat)
    payload["previous_character_id"] = previous
    return payload


@router.get("/user-name")
async def get_user_name_route():
    return {
        "user_name": user_settings.get_user_name(),
        "is_set": user_settings.is_user_name_set(),
    }


@router.put("/user-name")
async def set_user_name_route(body: UserNameIn):
    try:
        user_settings.set_user_name(body.user_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {
        "user_name": user_settings.get_user_name(),
        "is_set": user_settings.is_user_name_set(),
    }
