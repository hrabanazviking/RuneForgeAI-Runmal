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

from fastapi import APIRouter, HTTPException, Request, status

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
async def start_live(session_id: str, request: Request) -> dict:
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
        return controller.start(
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


@router.get("/voice/sessions/{session_id}/live")
async def get_live(session_id: str, request: Request) -> dict:
    _store_obj, session = _session_or_404(request, session_id)
    result = _controller(request).status(session_id)
    result["chat_id"] = session.chat_id
    if not result["live"]:
        result["turns_recorded"] = len(session.turns)
    return result


@router.post("/voice/sessions/{session_id}/live/speak", status_code=status.HTTP_201_CREATED)
async def speak_live(session_id: str, payload: dict, request: Request) -> dict:
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
        return controller.speak(session_id, text)
    except LiveVoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None


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


@router.post("/voice/sessions/{session_id}/live/stop")
async def stop_live(session_id: str, payload: dict, request: Request) -> dict:
    _session_or_404(request, session_id)
    controller = _controller(request)
    if not controller.is_live(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="voice session is not live"
        )
    try:
        return controller.stop(session_id, note=str(payload.get("note", "") or ""))
    except LiveVoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
