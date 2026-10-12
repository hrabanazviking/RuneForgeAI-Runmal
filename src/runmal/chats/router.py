"""Chat + message REST API (S107). All routes require the local bearer credential."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service
from runmal.chats.service import chat_to_dict, event_to_dict, message_to_dict
from runmal.db.deps import get_owner_id, get_session

router = APIRouter(tags=["chats"])


class ChatCreate(BaseModel):
    title: str = ""
    character_id: str | None = None


class ChatUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1)


@router.post("/chats", status_code=status.HTTP_201_CREATED)
async def create_chat(
    body: ChatCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        chat = await service.create_chat(session, user_id, body.title, body.character_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="character not found") from None
    return chat_to_dict(chat)


@router.get("/chats")
async def list_chats(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    return [chat_to_dict(chat, count) for chat, count in await service.list_chats(session, user_id)]


@router.get("/chats/{chat_id}")
async def get_chat(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    chat = await service.get_chat(session, user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    history = await service.get_history(session, user_id, chat_id) or []
    payload = chat_to_dict(chat, len(history))
    payload["messages"] = [message_to_dict(m) for m in history]
    return payload


@router.patch("/chats/{chat_id}")
async def rename_chat(
    chat_id: str,
    body: ChatUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    chat = await service.rename_chat(session, user_id, chat_id, body.title)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_chat(session, user_id, chat_id):
        raise HTTPException(status_code=404, detail="chat not found")
    return {"deleted": True, "id": chat_id}


@router.post("/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def append_message(
    chat_id: str,
    body: MessageCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        message = await service.append_message(session, user_id, chat_id, body.role, body.content)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return message_to_dict(message)


@router.get("/chats/{chat_id}/messages")
async def get_history(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    history = await service.get_history(session, user_id, chat_id)
    if history is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return [message_to_dict(m) for m in history]


@router.patch("/chats/{chat_id}/messages/{message_id}")
async def edit_message(
    chat_id: str,
    message_id: str,
    body: MessageUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        message = await service.edit_message(session, user_id, chat_id, message_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.delete("/chats/{chat_id}/messages/{message_id}")
async def delete_message(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_message(session, user_id, chat_id, message_id):
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True, "id": message_id}


@router.get("/chats/{chat_id}/events")
async def list_events(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    events = await service.list_events(session, user_id, chat_id)
    if events is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return [event_to_dict(e) for e in events]
