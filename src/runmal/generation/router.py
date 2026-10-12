"""Generation REST API (S108): POST /generate streams normalized SSE."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from runmal.generation import service

router = APIRouter(tags=["generation"])


class GenerateMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class GenerateRequest(BaseModel):
    messages: list[GenerateMessage] = Field(min_length=1)
    request_id: str | None = None


class CancelRequest(BaseModel):
    request_id: str


@router.post("/generate")
async def generate(body: GenerateRequest):
    request_id = body.request_id or service.new_request_id()
    prompt = "\n".join(m.content for m in body.messages)

    async def sse():
        async for event in service.generate_events(request_id, prompt):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Request-ID": request_id},
    )


@router.post("/generate/cancel")
async def cancel_generate(body: CancelRequest):
    return {"cancelled": service.cancel_request(body.request_id)}
