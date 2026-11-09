"""Character face roster HTTP surface (P-156): the roster
document for one owned character, on the /api/v1/faces
road, bearer-gated like every API and wired in app.py.

Owner scoping: a character that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
roster state (no set, empty set, nothing renderable) is
DATA at 200, never an error: the client decides what to
show from the named state and fallbacks. The truth layer
lives in runmal.faces.roster; this module is only the
HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import roster as roster_service

router = APIRouter(tags=["faces"])


@router.get("/faces/roster")
async def face_roster(
    character_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await roster_service.resolve_character_roster(
        session, owner_id, character_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found")
    return document
