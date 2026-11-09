"""Character speaking roster HTTP surface (P-159): the
speaking roster document for one owned character, on the
/api/v1/faces road, bearer-gated like every API and wired
in app.py.

Owner scoping: a character that is unknown - or owned by
someone else - answers 404; existence never leaks. Every
roster state (no set, empty set, nothing renderable) is
DATA at 200, never an error: the client decides what to
show and play from the named states. The truth layer
lives in runmal.faces.speaking_roster; this module is
only the HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import speaking_roster as speaking_roster_service

router = APIRouter(tags=["faces"])


@router.get("/faces/speaking-roster")
async def speaking_roster(
    character_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    document = await speaking_roster_service.resolve_character_speaking_roster(
        session, owner_id, character_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found")
    return document
