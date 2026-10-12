"""Prompt inspector API (roadmap S215).

POST /api/v1/debug/prompt-inspect composes a hypothetical prompt from
stored data and returns its S214 Prompt Trace. Read-only; the trace
never contains prompt content or secrets (S214 safety contract).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.prompt.inspect import inspect_prompt

router = APIRouter(tags=["debug"])


class InspectRequest(BaseModel):
    character_id: str | None = None
    lorebook_ids: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    context_limit: int = Field(default=4096, ge=64)
    reserve_response: int = Field(default=512, ge=0)


@router.post("/debug/prompt-inspect")
async def prompt_inspect(
    body: InspectRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    result = await inspect_prompt(
        session,
        owner_id,
        character_id=body.character_id,
        lorebook_ids=body.lorebook_ids,
        messages=body.messages,
        context_limit=body.context_limit,
        reserve_response=body.reserve_response,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character or lorebook not found",
        )
    return result
