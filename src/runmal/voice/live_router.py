"""Live voice HTTP surface (P-102): start / speak / interrupt /
stop / inspect a voice session's live orchestrator, on the
founding ``/api/v1/voice`` road (bearer-gated like every API).

The session citizen is P-101's: this module imports it LAZILY
inside the handlers, so the router imports cleanly on a tree
where P-101 has not landed yet — on such a tree the live roads
answer 503 plainly rather than pretending. Tests and hosts may
inject ``app.state.live_session_store`` (any object with the
store's get/save_session shape) and their own
``app.state.live_voice_controller``; create_app constructs the
default controller.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_session

from runmal.voice.audio import DeviceRole
from runmal.voice.live import LiveVoiceController, LiveVoiceError
from runmal.voice.router import get_provider, load_roles

router = APIRouter(tags=["voice"])


def _controller(request: Request) -> LiveVoiceController:
    controller = getattr(request.app.state, "live_voice_controller", None)
    if controller is None:
        controller = LiveVoiceController()
        controller.attach_app(request.app)
        request.app.state.live_voice_controller = controller
    return controller


def _store(request: Request):
    injected = getattr(request.app.state, "live_session_store", None)
    if injected is not None:
        return injected
    try:
        from runmal.voice.session import SESSIONS_FILENAME, VoiceSessionStore
    except ImportError:
        return None
    data_dir = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return VoiceSessionStore(data_dir / SESSIONS_FILENAME)


def _session_or_404(request: Request, session_id: str):
    store = _store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="voice sessions are not available on this tree (P-101 session module missing)",
        )
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="voice session not found"
        )
    return store, session


def _role_playback_factory(request: Request):
    """The HTTP road's playback: the app provider's sink for the
    resolved companion_output role, falling back to user_playback.
    An unassigned or remap-required role refuses with its truth —
    never a silent default device (INV-022)."""

    def factory(session) -> object:
        provider = get_provider(request)
        resolved = load_roles(request).resolve(provider)
        for role in (DeviceRole.COMPANION_OUTPUT, DeviceRole.USER_PLAYBACK):
            entry = resolved[role]
            if entry.usable and entry.device is not None:
                return provider.open_playback(entry.device.device_id)
        truths = ", ".join(
            f"{role.value}={resolved[role].status.value}"
            for role in (DeviceRole.COMPANION_OUTPUT, DeviceRole.USER_PLAYBACK)
        )
        raise LiveVoiceError(f"no usable playback role resolved ({truths})")

    return factory


@router.post("/voice/sessions/{session_id}/live/start", status_code=status.HTTP_201_CREATED)
async def start_live(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    store, session = _session_or_404(request, session_id)
    controller = _controller(request)
    if not session.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is stopped"
        )
    if controller.is_live(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is already live"
        )
    try:
        result = controller.start(
            session,
            store=store,
            playback_factory=(
                None if controller.playback_factory is not None else _role_playback_factory(request)
            ),
        )
    except LiveVoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    # P-112: starting live back-projects an opted-in session's
    # pre-existing turns (the P-104 limitation this closes:
    # live start was the one projection-aware road that never
    # walked the service). The async host layer decides, the
    # controller stays synchronous/DB-free, and the report
    # rides only when a projection was attempted - exactly
    # the speak road's contract, through the same helper.
    result = await _maybe_autoproject(request, controller, session_id, db, result)
    return result


@router.get("/voice/sessions/{session_id}/live")
async def get_live(session_id: str, request: Request) -> dict:
    _store_obj, session = _session_or_404(request, session_id)
    result = _controller(request).status(session_id)
    result["chat_id"] = session.chat_id
    if not result["live"]:
        result["turns_recorded"] = len(session.turns)
    return result


@router.post("/voice/sessions/{session_id}/live/speak", status_code=status.HTTP_201_CREATED)
async def speak_live(
    session_id: str,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    _session_or_404(request, session_id)
    controller = _controller(request)
    if not controller.is_live(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is not live"
        )
    text = str(payload.get("text", "") or "")
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="speak text must not be empty",
        )
    try:
        result = controller.speak(session_id, text)
    except LiveVoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    # P-104: the async host auto-projects an opted-in session's
    # turn (the controller itself stays synchronous/DB-free).
    result = await _maybe_autoproject(request, controller, session_id, db, result)
    return result


@router.post("/voice/sessions/{session_id}/live/interrupt")
async def interrupt_live(session_id: str, request: Request) -> dict:
    _session_or_404(request, session_id)
    controller = _controller(request)
    if not controller.is_live(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is not live"
        )
    interrupted = controller.interrupt(session_id)
    return {"interrupted": interrupted, **controller.status(session_id)}


async def _maybe_autoproject(request: Request, controller, session_id: str, db, result: dict) -> dict:
    """P-104 wiring shared by the speak/stop roads: when the live
    host's session opted into auto-projection, project its
    pending turns through P-103's service and ride the report
    on the response (only when a projection was attempted).
    Duck-typed test doubles without the flag are untouched."""
    if not hasattr(controller, "session_for"):
        return result
    host_session = controller.session_for(session_id)
    if host_session is None or not getattr(host_session, "auto_project", False):
        return result
    from runmal.voice import autoproject as _auto

    report = await _auto.autoproject_session(
        db, session=host_session, store=controller.store_for(session_id))
    if report["attempted"]:
        return {**result, "auto_projection": report}
    return result


@router.post("/voice/sessions/{session_id}/live/stop")
async def stop_live(
    session_id: str,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    _session_or_404(request, session_id)
    controller = _controller(request)
    if not controller.is_live(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is not live"
        )
    try:
        result = controller.stop(session_id, note=str(payload.get("note", "") or ""))
    except LiveVoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    # P-104: stopping an opted-in session projects whatever is
    # still pending (feed_frames turns land here — they have no
    # HTTP road of their own). The host is dropped by stop, so
    # the citizen is re-read through the store for this pass.
    store = _store(request)
    found = store.get(session_id) if store is not None else None
    if found is not None and getattr(found, "auto_project", False):
        from runmal.voice import autoproject as _auto

        report = await _auto.autoproject_session(db, session=found, store=store)
        if report["attempted"]:
            result = {**result, "auto_projection": report}
    return result
