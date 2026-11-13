"""Voice auto-projection HTTP surface (P-104): the per-session
opt-in toggle and its status view, on the founding
``/api/v1/voice`` road (bearer-gated like every API, wired in
app.py). Owner scoping follows the P-101/P-103 rule exactly:
a session whose owner differs answers 404 — existence never
leaks. The store resolves per request like the P-103
projection routes (a fresh VoiceSessionStore over the data
dir). Toggling a LIVE session also updates the live host's
session object, so the next live turn honours the toggle
without a restart of the host.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from runmal.db.deps import get_owner_id
from runmal.voice import autoproject as auto_mod
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


@router.post("/voice/sessions/{session_id}/auto-project")
async def set_auto_project(
    session_id: str,
    payload: dict,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    store, found = _session_or_404(request, session_id, owner_id)
    if "enabled" not in payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="enabled is required",
        )
    found.auto_project = bool(payload.get("enabled"))
    store.save_session(found)
    controller = getattr(request.app.state, "live_voice_controller", None)
    if controller is not None and hasattr(controller, "session_for"):
        live_session = controller.session_for(session_id)
        if live_session is not None and live_session is not found:
            live_session.auto_project = found.auto_project
    return auto_mod.autoproject_status(found)


@router.get("/voice/sessions/{session_id}/auto-projection")
async def get_auto_projection(
    session_id: str,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    _store, found = _session_or_404(request, session_id, owner_id)
    return auto_mod.autoproject_status(found)
