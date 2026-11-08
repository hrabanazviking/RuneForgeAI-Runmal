"""Voice repeat-request HTTP surface (P-108): a session's
pending repeat requests and the host acknowledgement
roads - on the founding ``/api/v1/voice`` road (bearer-
gated like every API, wired in app.py).

Owner scoping follows the P-105 mishearing router: a
session that is unknown - or owned by someone else -
answers 404 on every session road; existence never leaks.
The truth layer lives in runmal.voice.repeat_requests
(derived from P-105's mishearing truth, the single
source); this module is only the HTTP shape.

P-115 adds the owner-scoped cross-session digest road
(GET /voice/repeat-requests/digest) over the same truth.

The signal is data, not dialogue: no road here creates a
chat message, generates text, or calls a responder. A
host reads the signal and acts - or not - through its
own surface.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from runmal.db.deps import get_owner_id
from runmal.voice import mishearing as mis_mod
from runmal.voice import repeat_requests as rr_mod
from runmal.voice import session as voice_session

router = APIRouter(tags=["voice"])


def _data_dir() -> Path:
    return Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))


def _session_or_404(session_id: str, owner_id: str):
    store = voice_session.VoiceSessionStore(
        _data_dir() / voice_session.SESSIONS_FILENAME)
    found = store.get(session_id)
    if found is None or found.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="voice session not found",
        )
    return found


def _ack_store() -> rr_mod.AcknowledgementStore:
    return rr_mod.AcknowledgementStore(_data_dir() / rr_mod.ACK_FILENAME)


def _pairs() -> dict:
    return mis_mod.ReplacementStore(
        _data_dir() / mis_mod.REPLACEMENTS_FILENAME).pairs()


def _view(found) -> dict:
    return rr_mod.session_repeat_requests(found, _pairs(), _ack_store())


@router.get("/voice/sessions/{session_id}/repeat-requests")
async def get_repeat_requests(
    session_id: str,
    request: Request,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    return _view(_session_or_404(session_id, owner_id))


@router.post(
    "/voice/sessions/{session_id}/repeat-requests/{turn_no}/acknowledge")
async def acknowledge_repeat_request(
    session_id: str,
    turn_no: int,
    payload: dict | None = None,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    found = _session_or_404(session_id, owner_id)
    pairs = _pairs()
    turn = next((t for t in found.turns if t.turn_no == turn_no), None)
    request_view = (
        rr_mod.turn_repeat_request(turn, pairs) if turn is not None
        else None)
    if request_view is None:
        # No such turn, no word evidence, or every word
        # confident: there is no request to acknowledge.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="turn has no repeat request",
        )
    note = str((payload or {}).get("note", "") or "")
    _ack_store().acknowledge(session_id, turn_no, note)
    return _view(found)


@router.delete(
    "/voice/sessions/{session_id}/repeat-requests/{turn_no}/acknowledge")
async def clear_repeat_acknowledgement(
    session_id: str,
    turn_no: int,
    owner_id: str = Depends(get_owner_id),
) -> dict:
    found = _session_or_404(session_id, owner_id)
    removed = _ack_store().clear(session_id, turn_no)
    return {"removed": removed, **_view(found)}


def _live_session_ids() -> set:
    store = voice_session.VoiceSessionStore(
        _data_dir() / voice_session.SESSIONS_FILENAME)
    return {s.session_id for s in store.all_sessions()}


@router.get("/voice/repeat-requests/digest")
async def get_repeat_digest(
    owner_id: str = Depends(get_owner_id),
) -> dict:
    """P-115: the cross-session repeat-request digest.

    Owner-scoped, exactly like the per-session roads above:
    the roll-up covers only the caller's own sessions, so
    no other owner's session, chat or pending turn is ever
    named. (The P-111 housekeeping roads below stay
    install-wide - they expose only counts and inert ids
    of the install-wide acknowledgement store; the digest
    names live sessions, so it follows the P-108 road.)
    A pure read against the wall clock: acknowledges
    nothing, deletes nothing, creates no message.
    """
    store = voice_session.VoiceSessionStore(
        _data_dir() / voice_session.SESSIONS_FILENAME)
    mine = [s for s in store.all_sessions() if s.user_id == owner_id]
    return rr_mod.repeat_digest(mine, _pairs(), _ack_store())


@router.get("/voice/repeat-requests/housekeeping")
async def get_repeat_housekeeping(
    owner_id: str = Depends(get_owner_id),
) -> dict:
    """P-111: the acknowledgement store's housekeeping truth.

    Install-wide, exactly like the acknowledgement store itself
    (the P-108 stance, stated plainly): the bearer gate is the
    API's own, and the view names inert session ids - records
    whose session no longer exists - so a host can see what a
    prune would remove. Acknowledging nothing, deleting
    nothing: a pure read.
    """
    _ = owner_id  # the bearer gate is the authorisation (API law)
    return rr_mod.housekeeping_view(_ack_store(), _live_session_ids())


@router.post("/voice/repeat-requests/housekeeping/prune")
async def prune_repeat_housekeeping(
    owner_id: str = Depends(get_owner_id),
) -> dict:
    """P-111: remove inert acknowledgement records (only those).

    Live sessions' records are never touched; a prune with
    nothing inert removes nothing and says so. The report
    carries before/after counts and the removed session ids.
    """
    _ = owner_id
    return rr_mod.prune_inert_acknowledgements(
        _ack_store(), _live_session_ids())
