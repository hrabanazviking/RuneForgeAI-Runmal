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
