"""Generation REST API (S108; S307: resolved through the backend seam;
R-03: params + the composed turn).

POST /generate streams UI-shaped SSE produced from the selected backend's
normalized events. Two message sources, one stream shape:

- **Raw mode** (the original contract, unchanged): the request carries
  ``messages`` and they are sent verbatim. A request with only
  ``messages`` behaves exactly as it did before R-03.
- **Composed mode** (R-03): the request carries only ``chat_id`` (no
  ``messages``); the prompt is composed server-side from the chat via
  the bridge-proven path (``bridge.conversation.compose_messages``:
  the active character's persona system prompt — with ``{{user}}``
  resolved from the persisted user-name setting — then the stored
  history in order).

The backend is resolved from the request's `profile_id`, else the chat's
persisted backend profile (`chat_id`), else the offline fake default —
so the route works with no real provider configured.

Sampling parameters (R-03, see docs/COMPOSED_TURN_2026-11-14.md for the
full design): the effective params are merged per-key, lowest
precedence first —

1. engine defaults (every field unset; the backend adapter decides),
2. the chat's applied preset params (only when `chat_id` names a chat
   with a preset pinned),
3. the request's per-send `params` (this call only).

The merged bag is validated by ``presets.service.validate_params`` and
converted to the canonical ``SamplingParams``; that typed value is what
reaches the backend through the generation service. Invalid params are
a 422 before anything streams. This route never persists the reply:
landing a generated turn in a chat is the bridge's and the
continue/impersonate roads' job, not /generate's.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends import profiles as backend_profiles
from runmal.backends.base import ChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.bridge import conversation as bridge_conversation
from runmal.chats import service as chats
from runmal.db.deps import get_owner_id, get_session
from runmal.generation import service
from runmal.presets import service as presets_service

router = APIRouter(tags=["generation"])


class GenerateMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class GenerateRequest(BaseModel):
    # Raw mode: `messages` verbatim. Composed mode (R-03): omit
    # `messages` (or send an empty list) and name `chat_id`.
    messages: list[GenerateMessage] | None = None
    request_id: str | None = None
    chat_id: str | None = None
    profile_id: str | None = None
    # Per-send sampling overrides (R-03): a presets-shaped param bag,
    # validated by presets.service.validate_params.
    params: dict[str, Any] | None = None


class CancelRequest(BaseModel):
    request_id: str


async def _resolve_backend(
    session: AsyncSession,
    user_id: str,
    body: GenerateRequest,
    chat=None,
) -> ChatBackend:
    profile = None
    if body.profile_id is not None:
        profile = await backend_profiles.get_profile(
            session, user_id, body.profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="profile not found")
    elif chat is not None and chat.backend_profile_id:
        profile = await backend_profiles.get_profile(
            session, user_id, chat.backend_profile_id)
    if profile is None:
        return service.default_backend()
    return await backend_profiles.build_chat_backend(session, profile)


async def resolve_sampling_params(
    session: AsyncSession,
    user_id: str,
    *,
    chat=None,
    per_send: dict[str, Any] | None = None,
) -> SamplingParams:
    """The effective sampling params for one /generate call (R-03).

    Merge order (per key, later wins): the chat preset's params, then
    the per-send overrides. The merged bag is validated as a preset
    bag and converted to the canonical typed form; a ValueError from
    either step is a 422 — bad params never reach a backend.
    """
    merged: dict[str, Any] = {}
    if chat is not None and getattr(chat, "preset_id", None):
        preset = await presets_service.get_preset(session, user_id, chat.preset_id)
        if preset is not None:
            params = presets_service.preset_to_dict(preset).get("params")
            if isinstance(params, dict):
                merged.update(params)
    if per_send:
        merged.update(per_send)
    try:
        validated = presets_service.validate_params(merged)
        return SamplingParams.from_bag(validated)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    request_id = body.request_id or service.new_request_id()
    chat = None
    if body.chat_id is not None:
        chat = await chats.get_chat(session, user_id, body.chat_id)
        if chat is None and (body.profile_id is None or not body.messages):
            # Pre-R-03, a chat_id that named no owned chat was a 404
            # whenever the chat was actually consulted (no explicit
            # profile, or the composed road which needs the chat).
            # With an explicit profile AND raw messages the chat was
            # never consulted and still is not.
            raise HTTPException(status_code=404, detail="chat not found")
    backend = await _resolve_backend(session, user_id, body, chat)
    params = await resolve_sampling_params(
        session, user_id, chat=chat, per_send=body.params
    )
    if body.messages:
        messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
        mode = "raw"
    elif chat is not None:
        messages = await bridge_conversation.compose_messages(session, user_id, chat)
        if not messages:
            raise HTTPException(
                status_code=422,
                detail="chat has no messages to compose",
            )
        mode = "composed"
    else:
        raise HTTPException(
            status_code=422,
            detail="messages or chat_id is required",
        )

    async def sse():
        async for event in service.generate_events(
                request_id, messages=messages, backend=backend,
                params=params, chat_id=body.chat_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "X-Backend-Key": backend.backend_key,
            "X-Generation-Mode": mode,
        },
    )


@router.post("/generate/cancel")
async def cancel_generate(body: CancelRequest):
    return {"cancelled": service.cancel_request(body.request_id)}
