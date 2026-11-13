"""Character speaking chats HTTP surface (P-166): the
board of one owned character's current faces across all
of its chats, paired with the character's CURRENT voice
resolution, on the /api/v1/faces road, bearer-gated like
every API and wired in app.py.

Owner scoping: a character that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
board state (no chats, none ready, some ready, all
ready) is DATA at 200, never an error: the client
decides what to show from the named states. The voice
half is the character's current S512 resolution, stated
once at board level - S512 keys voice by character. The
truth layer lives in runmal.faces.speaking_chats; this
module is only the HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import speaking_chats as speaking_chats_service

router = APIRouter(tags=["faces"])


@router.get("/faces/speaking-chats")
async def character_speaking_chats(
    character_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await speaking_chats_service.resolve_character_speaking_chats(
        session, owner_id, character_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found")
    return document
