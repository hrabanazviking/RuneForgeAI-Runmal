"""Voice mishearing HTTP surface (P-105): a session's
mishearing truth (confidence evidence, low-confidence words,
the P-114 session aggregate report,
replacement suggestions) and the user replacement lexicon -
on the founding ``/api/v1/voice`` road (bearer-gated like
every API, wired in app.py).

Owner scoping follows the P-103 projection router: a session
that is unknown - or owned by someone else - answers 404 on
the session road; existence never leaks. The lexicon is
install-wide, like voice settings (the P-105 design states
it plainly), so its roads carry no owner scoping. The truth
layer itself lives in runmal.voice.mishearing; this module
is only the HTTP shape.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from runmal.db.deps import get_owner_id
from runmal.voice import mishearing as mis_mod
from runmal.voice import session as voice_session

router = APIRouter(tags=["voice"])


def _data_dir() -> Path:
    return Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))


def _session_or_404(request: Request, session_id: str, owner_id: str):
    store = voice_session.VoiceSessionStore(
        _data_dir() / voice_session.SESSIONS_FILENAME)
    found = store.get(session_id)
    if found is None or found.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="voice session not found",
        )
    return found


def _replacement_store() -> mis_mod.ReplacementStore:
    return mis_mod.ReplacementStore(
        _data_dir() / mis_mod.REPLACEMENTS_FILENAME)


@router.get("/voice/sessions/{session_id}/mishearings")
async def get_voice_mishearings(
    session_id: str,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    found = _session_or_404(request, session_id, owner_id)
    return mis_mod.session_mishearing(found, _replacement_store().pairs())


@router.get("/voice/sessions/{session_id}/mishearing-report")
async def get_voice_mishearing_report(
    session_id: str,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    found = _session_or_404(request, session_id, owner_id)
    return mis_mod.session_mishearing_report(
        found, _replacement_store().pairs())


@router.get("/voice/mishearing-replacements")
async def get_mishearing_replacements() -> dict:
    return _replacement_store().view()


@router.put("/voice/mishearing-replacements")
async def put_mishearing_replacement(payload: dict) -> dict:
    store = _replacement_store()
    try:
        return store.set(
            str(payload.get("misheard", "") or ""),
            str(payload.get("replacement", "") or ""),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None


@router.delete("/voice/mishearing-replacements/{misheard}")
async def delete_mishearing_replacement(misheard: str) -> dict:
    store = _replacement_store()
    removed = store.remove(misheard)
    return {"removed": removed, **store.view()}
