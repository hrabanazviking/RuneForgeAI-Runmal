"""Voice turn projection HTTP surface (P-103): project a
voice session's recorded turns into its chat, and inspect
projection state - on the founding ``/api/v1/voice`` road
(bearer-gated like every API, wired in app.py).

The session citizen is P-101's; the store resolves per
request exactly like the P-101 session routes (a fresh
VoiceSessionStore over the data dir). Owner scoping follows
the P-101 rule: a session whose owner differs, or whose
chat is missing/foreign, answers 404 - existence never
leaks. Projection itself lives in runmal.voice.projection;
this module is only the HTTP shape.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.voice import projection as proj_mod
from runmal.voice import session as voice_session

router = APIRouter(tags=["voice"])


def _session_store(request: Request) -> voice_session.VoiceSessionStore:
    data_dir = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return voice_session.VoiceSessionStore(
        data_dir / voice_session.SESSIONS_FILENAME)


def _session_or_404(request: Request, session_id: str, owner_id: str):
    store = _session_store(request)
    found = store.get(session_id)
    if found is None or found.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="voice session not found",
        )
    return store, found


@router.post(
    "/voice/sessions/{session_id}/project",
    status_code=status.HTTP_201_CREATED,
)
async def project_voice_session(
    session_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    store, found = _session_or_404(request, session_id, owner_id)
    try:
        return await proj_mod.project_session_turns(
            session, user_id=owner_id, session=found, store=store)
    except (proj_mod.ProjectionError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="voice session not found",
        ) from None


@router.get("/voice/sessions/{session_id}/projection")
async def get_voice_projection(
    session_id: str,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    _store, found = _session_or_404(request, session_id, owner_id)
    return proj_mod.projection_status(found)
