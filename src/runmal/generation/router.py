"""Generation REST API (S108; S307: resolved through the backend seam).

POST /generate streams UI-shaped SSE produced from the selected backend's
normalized events. The backend is resolved from the request's `profile_id`,
else the chat's persisted backend profile (`chat_id`), else the offline
fake default — so the route works with no real provider configured.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends import profiles as backend_profiles
from runmal.backends.base import ChatBackend
from runmal.backends.messages import ChatMessage
from runmal.chats import service as chats
from runmal.db.deps import get_owner_id, get_session
from runmal.generation import service

router = APIRouter(tags=["generation"])


class GenerateMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class GenerateRequest(BaseModel):
    messages: list[GenerateMessage] = Field(min_length=1)
    request_id: str | None = None
    chat_id: str | None = None
    profile_id: str | None = None


class CancelRequest(BaseModel):
    request_id: str


async def _resolve_backend(
    session: AsyncSession, user_id: str, body: GenerateRequest
) -> ChatBackend:
    profile = None
    if body.profile_id is not None:
        profile = await backend_profiles.get_profile(
            session, user_id, body.profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="profile not found")
    elif body.chat_id is not None:
        chat = await chats.get_chat(session, user_id, body.chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="chat not found")
        if chat.backend_profile_id:
            profile = await backend_profiles.get_profile(
                session, user_id, chat.backend_profile_id)
    if profile is None:
        return service.default_backend()
    return await backend_profiles.build_chat_backend(session, profile)


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    request_id = body.request_id or service.new_request_id()
    backend = await _resolve_backend(session, user_id, body)
    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]

    async def sse():
        async for event in service.generate_events(
                request_id, messages=messages, backend=backend):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Request-ID": request_id, "X-Backend-Key": backend.backend_key},
    )


@router.post("/generate/cancel")
async def cancel_generate(body: CancelRequest):
    return {"cancelled": service.cancel_request(body.request_id)}
