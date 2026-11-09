"""Character face history HTTP surface (P-162): the board
of one owned character's kept face history across all of
its chats, on the /api/v1/faces road, bearer-gated like
every API and wired in app.py.

Owner scoping: a character that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
board state (no chats, no history, some history, all
history) is DATA at 200, never an error: the client
decides what to show from the named states. The truth
layer lives in runmal.faces.character_history; this
module is only the HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import character_history as history_service

router = APIRouter(tags=["faces"])


@router.get("/faces/character-history")
async def character_face_history(
    character_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await history_service.resolve_character_face_history(
        session, owner_id, character_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found")
    return document
