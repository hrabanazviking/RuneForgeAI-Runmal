"""Inspector HTTP surface (P-203, P-204, P-210): the
composed overview on GET /inspector/chats/{chat_id},
the events document on GET
/inspector/chats/{chat_id}/events and the reasoning
document on GET /inspector/chats/{chat_id}/reasoning -
bearer-gated like every API in app.py and owner-scoped
like every chat road. Unknown or foreign chats answer
the house 404 idiom ("chat not found"), never a leaked
existence signal beyond what sibling chat roads already
give. The truth layer lives in runmal.inspector.overview,
runmal.inspector.events and runmal.inspector.reasoning;
this module is only the HTTP shape. All three roads are
pure reads: they write nothing, compose no prompt and
run no activation inspection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.inspector import events as events_service
from runmal.inspector import overview as overview_service
from runmal.inspector import reasoning as reasoning_service

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


@router.get("/inspector/chats/{chat_id}/events")
async def get_inspector_events(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The chat's Inspector events document (P-204): the
    S107 chat event log as a by-kind census with honest
    coverage sections for the events / actions / flags
    triad - counts, kind names and timestamps only, no
    event data payloads and no message content."""
    payload = await events_service.build_events_document(session, user_id, chat_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return payload


@router.get("/inspector/chats/{chat_id}/reasoning")
async def get_inspector_reasoning(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The chat's Inspector reasoning document (P-210): the
    P-205 reasoning record as a per-chat census -
    per-message active statuses, recorded swipe indexes
    and per-status counts over active views and over all
    swipe documents - with no thinking text anywhere."""
    payload = await reasoning_service.build_reasoning_document(
        session, user_id, chat_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return payload
