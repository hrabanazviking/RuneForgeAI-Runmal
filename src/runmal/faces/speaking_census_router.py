"""Face speaking census HTTP surface (P-167): one
owner's current faces across every character and
chat, each character row carrying its own current
voice, on the /api/v1/faces road, bearer-gated like
every API and wired in app.py.

Owner scoping: the census subject is the caller
themselves - there is no id parameter, nothing
foreign can be named, and every census state (no
characters, no chats, none ready, some ready, all
ready) is DATA at 200, never an error: the client
decides what to show from the named states. Voice
stands inside character rows only; this road adds
no owner-level voice of any kind. The truth layer
lives in runmal.faces.speaking_census; this module
is only the HTTP shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.faces import speaking_census as census_service

router = APIRouter(tags=["faces"])


@router.get("/faces/speaking-census")
async def face_speaking_census(
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    return await census_service.resolve_face_speaking_census(
        session, owner_id)
