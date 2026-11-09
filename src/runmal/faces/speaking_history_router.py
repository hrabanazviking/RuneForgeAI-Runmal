"""Speaking history HTTP surface (P-161): the speaking
history document for one owned chat, on the /api/v1/faces
road, bearer-gated like every API and wired in app.py.

Owner scoping: a chat that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
presentation state (no character, no set, no selection,
an unbound current) is DATA at 200, never an error: the
speaking history of a chat with no character is an empty
history with voice None, stated honestly. The voice half
is TODAY's resolution only (voice_scope: current_only) -
S512 stores no voice history. The truth layer lives in
runmal.faces.speaking_history; this module is only the
HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import speaking_history as speaking_history_service

router = APIRouter(tags=["faces"])


@router.get("/faces/speaking-history")
async def speaking_history(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await speaking_history_service.resolve_speaking_history(
        session, owner_id, chat_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat not found")
    return document
