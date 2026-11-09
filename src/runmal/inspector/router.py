"""Inspector HTTP surface (P-203): the composed
overview on one road - GET /inspector/chats/{chat_id} -
bearer-gated like every API in app.py and owner-scoped
like every chat road. Unknown or foreign chats answer
the house 404 idiom ("chat not found"), never a leaked
existence signal beyond what sibling chat roads already
give. The truth layer lives in runmal.inspector.
overview; this module is only the HTTP shape. The road
is a pure read: it writes nothing, composes no prompt
and runs no activation inspection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.inspector import overview as overview_service

router = APIRouter(tags=["inspector"])


@router.get("/inspector/chats/{chat_id}")
async def get_inspector_overview(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The chat's composed Inspector overview (P-203):
    P-075 provenance summary verbatim, P-059 prompt-road
    availability, P-043 bound-lorebook pointers and the
    scenario-binding state, each under an honest status."""
    payload = await overview_service.build_overview(session, user_id, chat_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return payload
