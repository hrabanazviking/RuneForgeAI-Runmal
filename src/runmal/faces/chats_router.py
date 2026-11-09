"""Character face chats HTTP surface (P-160): the board
of one owned character's chats and their current faces,
on the /api/v1/faces road, bearer-gated like every API
and wired in app.py.

Owner scoping: a character that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
board state (no chats, none ready, some ready, all
ready) is DATA at 200, never an error: the client
decides what to show from the named states. The truth
layer lives in runmal.faces.chats; this module is only
the HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import chats as chats_service

router = APIRouter(tags=["faces"])


@router.get("/faces/chats")
async def face_chats(
    character_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await chats_service.resolve_character_face_chats(
        session, owner_id, character_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found")
    return document
