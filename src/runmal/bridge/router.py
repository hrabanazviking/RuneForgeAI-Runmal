"""Bridge credential administration + bridge identity routes (S601).

Two surfaces, deliberately separate:

- `admin_router` — mounted behind the LOCAL application credential.
  The owner creates/lists/revokes bridge credentials here. The token
  plaintext appears exactly once, in the creation response.
- `router` — the bridge-facing surface under /api/v1/bridge/...,
  authenticated by bridge tokens only (see runmal.bridge.auth).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.bridge import conversation, service
from runmal.bridge.auth import BridgeIdentity, get_bridge_identity, require_bridge_scope
from runmal.bridge.service import credential_to_dict
from runmal.chats.service import message_to_dict
from runmal.db.deps import get_owner_id, get_session
from runmal.generation import service as generation_service

admin_router = APIRouter(tags=["bridge-admin"])
router = APIRouter(prefix="/bridge", tags=["bridge"])


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)


@admin_router.post("/bridge/credentials", status_code=status.HTTP_201_CREATED)
async def create_credential(
    body: CredentialCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        credential, token = await service.create_credential(
            session, user_id, body.name, body.scopes
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = credential_to_dict(credential)
    payload["token"] = token  # shown once; only its hash is stored
    return payload


@admin_router.get("/bridge/credentials")
async def list_credentials(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    rows = await service.list_credentials(session, user_id)
    return [credential_to_dict(row) for row in rows]


@admin_router.post("/bridge/credentials/{credential_id}/revoke")
async def revoke_credential(
    credential_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    credential = await service.revoke_credential(session, user_id, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="bridge credential not found")
    return credential_to_dict(credential)


@router.get("/whoami")
async def whoami(identity: BridgeIdentity = Depends(get_bridge_identity)):
    """The bridge's own view of itself: id, name, granted scopes.

    Never returns the token or its hash (INV-023). This is also the
    cheapest liveness/scope probe a bridge can make after pairing.
    """
    return {
        "bridge_id": identity.credential_id,
        "name": identity.name,
        "scopes": list(identity.scopes),
    }


# --- conversation-state API (S602) ------------------------------------------

_read_guard = require_bridge_scope("chat:read", resource_param="chat_id")
_write_guard = require_bridge_scope("chat:write", resource_param="chat_id")


class TurnIn(BaseModel):
    speaker_kind: Literal["user", "companion", "environment"]
    content: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_name: str | None = None
    bridge_timestamp: str | None = None
    metadata: dict | None = None
    # Accepted from the first contract (protocol §6); duplicate
    # suppression is enforced from S610.
    idempotency_key: str | None = None


class GenerateIn(BaseModel):
    request_id: str | None = None


class CancelIn(BaseModel):
    request_id: str


@router.get("/chats/{chat_id}")
async def bridge_chat_state(
    chat_id: str,
    identity: BridgeIdentity = Depends(_read_guard),
    session: AsyncSession = Depends(get_session),
):
    state = await conversation.get_state(session, identity.user_id, chat_id)
    if state is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return state


@router.post("/chats/{chat_id}/turns", status_code=status.HTTP_201_CREATED)
async def bridge_append_turn(
    chat_id: str,
    body: TurnIn,
    identity: BridgeIdentity = Depends(_write_guard),
    session: AsyncSession = Depends(get_session),
):
    try:
        message = await conversation.append_turn(
            session,
            identity.user_id,
            identity.credential_id,
            chat_id,
            speaker_kind=body.speaker_kind,
            content=body.content,
            speaker_id=body.speaker_id,
            speaker_name=body.speaker_name,
            bridge_timestamp=body.bridge_timestamp,
            metadata=body.metadata,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="chat not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = message_to_dict(message)
    payload["idempotency_key"] = body.idempotency_key
    return payload


@router.post("/chats/{chat_id}/generate")
async def bridge_generate(
    chat_id: str,
    body: GenerateIn,
    request: Request,
    identity: BridgeIdentity = Depends(_write_guard),
    session: AsyncSession = Depends(get_session),
):
    state = await conversation.get_state(session, identity.user_id, chat_id)
    if state is None:
        raise HTTPException(status_code=404, detail="chat not found")
    request_id = body.request_id or generation_service.new_request_id()
    factory = request.app.state.session_factory

    async def sse():
        async for event in conversation.stream_generation(
            factory, identity.user_id, identity.credential_id, chat_id, request_id
        ):
            yield conversation.encode_sse(event)

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Request-ID": request_id, "X-Bridge-Protocol": conversation.PROTOCOL_VERSION},
    )


@router.post("/chats/{chat_id}/generate/cancel")
async def bridge_generate_cancel(
    chat_id: str,
    body: CancelIn,
    identity: BridgeIdentity = Depends(_write_guard),
):
    return {"cancelled": generation_service.cancel_request(body.request_id)}


# --- persona switching (S603) -------------------------------------------------


class PersonaIn(BaseModel):
    character_id: str | None = None


@router.post("/chats/{chat_id}/persona")
async def bridge_select_persona(
    chat_id: str,
    body: PersonaIn,
    identity: BridgeIdentity = Depends(get_bridge_identity),
    session: AsyncSession = Depends(get_session),
):
    """Switch the chat's active persona for FUTURE turns (protocol §8).

    Gated by `persona:select:<character-id>` (or `persona:select:*`):
    the scope names the persona being selected, so this check runs in
    the handler where the target is known. Stored messages are never
    rewritten — their speaker snapshots stand.
    """
    from runmal.bridge.scopes import scope_allows
    from runmal.characters.service import get_character
    from runmal.chats import service as chats_service

    if not scope_allows(identity.scopes, "persona:select", body.character_id or "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="bridge credential lacks required scope: persona:select",
        )
    chat = await chats_service.get_chat(session, identity.user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    previous = chat.character_id
    try:
        chat = await chats_service.set_chat_persona(
            session,
            identity.user_id,
            chat_id,
            body.character_id,
            event_data={"source": "bridge", "bridge_id": identity.credential_id},
        )
    except KeyError:
        raise HTTPException(status_code=422, detail="character not found") from None
    if previous != chat.character_id:
        from runmal.bridge import outbox

        await outbox.record_event(
            session,
            chat_id,
            outbox.KIND_PERSONA_CHANGED,
            {"from": previous, "to": chat.character_id, "bridge_id": identity.credential_id},
        )
    persona = None
    if chat.character_id:
        character = await get_character(session, identity.user_id, chat.character_id)
        if character is not None:
            persona = {"character_id": character.id, "name": character.name}
    return {
        "chat_id": chat_id,
        "persona": persona,
        "previous_character_id": previous,
    }


# --- TTS hook (S604) ----------------------------------------------------------

_tts_guard = require_bridge_scope("tts:request")


class TTSIn(BaseModel):
    text: str = Field(min_length=1)
    backend: str | None = None
    voice_id: str | None = None
    language: str | None = None
    chat_id: str | None = None
    speaking_rate: float = 1.0


class PlaybackIn(BaseModel):
    event: str
    detail: dict | None = None


async def _resolve_tts_voice(session, identity: BridgeIdentity, body: TTSIn):
    """Voice for a TTS request, most specific first:

    explicit `voice_id` wins; else the attached chat's persona voice
    profile (S512) — but only when the bridge also holds `chat:read`
    for that chat, since the profile is chat state; else the owner's
    configured default backend with its default voice.
    """
    from runmal.bridge.scopes import scope_allows
    from runmal.chats import service as chats_service
    from runmal.voice.profiles import resolve_character_voice
    from runmal.voice.settings import VoiceSettings
    from runmal.voice.tts import VoiceInfo

    default_key = VoiceSettings.load().tts_backend
    if body.voice_id:
        key = body.backend or default_key
        return key, VoiceInfo(
            voice_id=body.voice_id, language=body.language or "en-us", backend_key=key
        )
    if body.chat_id and scope_allows(identity.scopes, "chat:read", body.chat_id):
        chat = await chats_service.get_chat(session, identity.user_id, body.chat_id)
        if chat is not None and chat.character_id:
            character_voice = await resolve_character_voice(
                session, identity.user_id, chat.character_id
            )
            return character_voice.tts_backend, character_voice.to_voice_info()
    key = body.backend or default_key
    return key, VoiceInfo(voice_id="", language=body.language or "en-us", backend_key=key)


@router.post("/tts", status_code=status.HTTP_202_ACCEPTED)
async def bridge_tts_request(
    body: TTSIn,
    identity: BridgeIdentity = Depends(_tts_guard),
    session: AsyncSession = Depends(get_session),
):
    from runmal.bridge import tts_hook

    backend_key, voice = await _resolve_tts_voice(session, identity, body)
    job = tts_hook.start_job(
        bridge_id=identity.credential_id,
        user_id=identity.user_id,
        text=body.text,
        backend_key=backend_key,
        voice=voice,
        chat_id=body.chat_id,
        speaking_rate=body.speaking_rate,
    )
    return job.to_dict()


def _owned_job(identity: BridgeIdentity, job_id: str):
    from runmal.bridge import tts_hook

    job = tts_hook.get_job(identity.credential_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="tts job not found")
    return job


@router.get("/tts/{job_id}")
async def bridge_tts_status(
    job_id: str,
    identity: BridgeIdentity = Depends(_tts_guard),
    session: AsyncSession = Depends(get_session),
):
    from runmal.bridge import outbox, tts_hook

    job = _owned_job(identity, job_id)
    # First observation of a ready, chat-attached job publishes its
    # tts_ready outbox event (the job itself finished in a worker
    # thread with no DB session; the poll is the durable hand-off).
    if job.status == tts_hook.STATUS_READY and job.chat_id and not job.ready_recorded:
        job.ready_recorded = True
        await outbox.record_event(
            session,
            job.chat_id,
            outbox.KIND_TTS_READY,
            {"job_id": job.id, "bridge_id": identity.credential_id},
        )
    return job.to_dict()


@router.get("/tts/{job_id}/audio")
async def bridge_tts_audio(
    job_id: str,
    identity: BridgeIdentity = Depends(_tts_guard),
):
    from fastapi.responses import Response

    job = _owned_job(identity, job_id)
    if job.audio is None:
        raise HTTPException(status_code=409, detail=f"audio not ready (job is {job.status})")
    return Response(content=job.audio, media_type="audio/wav")


@router.post("/tts/{job_id}/cancel")
async def bridge_tts_cancel(
    job_id: str,
    identity: BridgeIdentity = Depends(_tts_guard),
):
    from runmal.bridge import tts_hook

    job = _owned_job(identity, job_id)
    return {"cancelled": tts_hook.cancel_job(job), "status": job.status}


@router.post("/tts/{job_id}/playback")
async def bridge_tts_playback(
    job_id: str,
    body: PlaybackIn,
    identity: BridgeIdentity = Depends(_tts_guard),
    session: AsyncSession = Depends(get_session),
):
    from runmal.bridge import outbox, tts_hook

    job = _owned_job(identity, job_id)
    try:
        tts_hook.report_playback(job, body.event, body.detail)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.event == "playback.completed" and job.chat_id:
        await outbox.record_event(
            session,
            job.chat_id,
            outbox.KIND_PLAYBACK_COMPLETE,
            {"job_id": job.id, "bridge_id": identity.credential_id},
        )
    return job.to_dict()


# --- durable event outbox (S609) ----------------------------------------------

_events_guard = require_bridge_scope("events:read", resource_param="chat_id")


class AckIn(BaseModel):
    event_id: int


@router.get("/chats/{chat_id}/events")
async def bridge_poll_events(
    chat_id: str,
    after: int | None = None,
    limit: int = 100,
    identity: BridgeIdentity = Depends(_events_guard),
    session: AsyncSession = Depends(get_session),
):
    """Poll the chat's outbox stream. Without `after`, resumes from
    this credential's checkpoint — the reconnect path (§5)."""
    from runmal.bridge import outbox

    chat = await conversation.get_state(session, identity.user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    checkpoint = await outbox.get_checkpoint(session, identity.credential_id, chat_id)
    start = checkpoint if after is None else after
    events = await outbox.list_events(session, chat_id, after_id=start, limit=limit)
    return {
        "chat_id": chat_id,
        "checkpoint": checkpoint,
        "latest": await outbox.latest_event_id(session, chat_id),
        "events": [outbox.event_to_dict(event) for event in events],
    }


@router.post("/chats/{chat_id}/events/ack")
async def bridge_ack_events(
    chat_id: str,
    body: AckIn,
    identity: BridgeIdentity = Depends(_events_guard),
    session: AsyncSession = Depends(get_session),
):
    from runmal.bridge import outbox

    chat = await conversation.get_state(session, identity.user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    checkpoint = await outbox.acknowledge(session, identity.credential_id, chat_id, body.event_id)
    return {"chat_id": chat_id, "checkpoint": checkpoint}
